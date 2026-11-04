#!/usr/bin/env python3
"""Harbor verifier for the return-main-no-cleanup Git pilot case.

Deterministic FINAL-STATE oracle (no model judge, no LLM). Runs AFTER the
agent inside the Harbor trial container, wraps the actual post-run state,
and writes Harbor's reward contract (``/logs/verifier/reward.json``).

Pipeline (mirrors the trusted collector design of the strict local
judges, but self-contained for Harbor):

  1. Resolve and VALIDATE the fixture root under the agent's workspace
     (fresh case path: strictly inside the workspace, never HOME or an
     ancestor of it, with the expected repo/origin structure).
  2. Load the TRUSTED records (provenance + pristine seed snapshot +
     manifest captured at package-generation time, baked into the image
     at /opt/git-pilot/records). The agent never saw them.
  3. Rebase the trusted manifest onto the runtime fixture root and
     MATERIALIZE it into the verifier-owned
     ``<fixture_root>/expected/manifest.json`` — the one path
     ``snapshot_fixture``'s fail-closed metadata gate reads. This write
     happens AFTER the agent finished, from trusted in-image records;
     the shipped task package carries no ``expected/`` dir, so no
     agent-visible expected state exists before execution, and the
     verifier never writes trusted state anywhere else.
  4. Take the AFTER snapshot of the agent's repository with neutralized,
     read-only Git via the vendored sandbox-git wrapper (fixed container
     path), mock HOME, and strictly-supported neutralizing options, so
     agent-mutated .git/config/hooks/exclude cannot execute code, spawn
     a pager, or hide files while the verifier measures the repository.
     The manifest's ``origin_url_expected`` stays the ACTUAL relative
     URL the repository records (``../origin.git``) so URL-fidelity is
     compared against what the remote really is, not a rewritten path.
  5. Compare after vs the trusted anchors with the same pure verifier
     (git_pilot_fixture.verify_fixture) the strict local eval.yaml uses
     (fixture contract reused; local judge acceptance NOT weakened).
  6. Emit reward.json: 1.0 on the exact expected final state, 0.0 with the
     failure list otherwise. UNSCORABLE (missing/mismatched trusted
     records, metadata-tampered repo, unreadable state) is 0.0 with the
     recorded reason — never a silent pass.

Explicit scope label: basic Git-task END-STATE pilot.
``procedure_attempt_coverage: not_measured`` — this verifier does NOT
observe which commands the agent attempted, does NOT measure denied
destructive-attempt coverage, holdout survival, or golden-history
fidelity, and makes no claim about them.

Stdlib only. No network, no model call, no host filesystem access.

Relocated 2026-11-03 (P0.2) from
``devel/adlc/experiments/02-git-operations/git-pilot-v1/harbor/verifier.py``
(byte-identical content; container-path anchored, no relocation changes
required).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# Fixed container paths baked by harbor/image/Containerfile.
PILOT_ROOT = Path("/opt/git-pilot")
DEFAULT_RECORDS_DIR = PILOT_ROOT / "records"
DEFAULT_FIXTURE_LIB = PILOT_ROOT / "lib" / "git_pilot_fixture.py"
DEFAULT_WRAPPED_GIT = PILOT_ROOT / "bin" / "sandbox-git"

DEFAULT_WORKSPACE = Path("/workspace")
DEFAULT_FIXTURE_DIRNAME = "fixture"

REWARD_DIR = Path(os.environ.get("GIT_PILOT_REWARD_DIR", "/logs/verifier"))

CASE_ID = "return-main-no-cleanup-v1"
PROCEDURE_ATTEMPT_COVERAGE = "not_measured"


def _emit(reward: float, reason: str, failures: list | None = None) -> int:
    """Write Harbor's reward contract plus rich sidecars.

    Harbor 0.25.0 parses reward.json as a FLAT map of finite numbers only
    (Verifier._parse_reward_json rejects non-numeric values outright) and
    reward.txt as a bare float (Verifier._parse_reward_text). The rich
    reason/failures/coverage/case fields therefore live in sidecars —
    verdict.json and judges.json — never in the numeric reward map.
    """
    REWARD_DIR.mkdir(parents=True, exist_ok=True)
    reward = 1.0 if reward >= 1.0 else 0.0
    # Harbor's numeric contract: flat, finite numbers only.
    (REWARD_DIR / "reward.json").write_text(
        json.dumps({"reward": reward}) + "\n", encoding="utf-8"
    )
    (REWARD_DIR / "reward.txt").write_text(f"{reward}\n", encoding="utf-8")
    payload = {
        "case_id": CASE_ID,
        "verifier": "git-pilot-harbor-final-state/1",
        "procedure_attempt_coverage": PROCEDURE_ATTEMPT_COVERAGE,
        "reason": reason,
        "failures": failures or [],
    }
    (REWARD_DIR / "verdict.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (REWARD_DIR / "judges.json").write_text(
        json.dumps(
            {"final_state": {"ok": reward >= 1.0,
                             "failures": failures or []}},
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if reward >= 1.0 else 1


def _load_trusted_records(records_dir: Path) -> tuple[dict, dict]:
    """Load the trusted records. Returns (provenance, seed) or raises."""
    provenance_path = records_dir / "provenance.json"
    seed_path = records_dir / "seed-state.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"trusted records unreadable: {exc}") from exc
    if not isinstance(provenance, dict) or not isinstance(seed, dict):
        raise RuntimeError("trusted records malformed (not objects)")
    if provenance.get("case_id") != CASE_ID:
        raise RuntimeError(
            f"trusted provenance case_id mismatch: {provenance.get('case_id')!r}"
        )
    if seed.get("case_id") != CASE_ID:
        raise RuntimeError(f"trusted seed case_id mismatch: {seed.get('case_id')!r}")
    return provenance, seed


def _resolve_fixture_root(workspace: Path, fixture_dirname: str) -> Path:
    """Locate the agent's fixture directory under the workspace."""
    candidate = workspace / fixture_dirname
    if not candidate.is_dir():
        raise RuntimeError(
            f"fixture directory not found at {candidate}; the task package "
            "must ship environment/fixture/"
        )
    return candidate


def _validate_fixture_root(fixture_root: Path, workspace: Path) -> None:
    """The fixture root must be a fresh disposable case path, not the host.

    Refuses anything that is not strictly inside the caller's workspace,
    path-anchored roots, HOME itself or any ancestor of HOME (the host
    dotfiles worktree must never be selected as a measurement target),
    and any path without the fixture's expected repository structure.
    """
    resolved = fixture_root.resolve()
    resolved_workspace = workspace.resolve()
    if resolved == resolved_workspace \
            or resolved_workspace not in resolved.parents:
        raise RuntimeError(
            f"fixture root {fixture_root} is not strictly inside the "
            f"workspace {workspace}"
        )
    if len(resolved.parts) < 3:
        raise RuntimeError(
            f"fixture root path is too shallow to be a case path: {resolved}"
        )
    home = Path.home()
    if resolved == home or resolved in home.parents:
        raise RuntimeError(
            f"fixture root must be a fresh case path, not HOME or an "
            f"ancestor of HOME: {resolved}"
        )
    if not (resolved / "repo" / ".git").exists():
        raise RuntimeError(
            f"fixture root has no repository at {resolved}/repo/.git"
        )
    if not (resolved / "origin.git").is_dir():
        raise RuntimeError(
            f"fixture root has no bare origin at {resolved}/origin.git"
        )


def _lstat(path: Path):
    """lstat without following symlinks; None when absent."""
    try:
        return os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return None


def _refuse_symlink_component(candidate: Path, root: Path, label: str) -> None:
    """Refuse any symlinked component of ``candidate`` relative to ``root``.

    The verifier writes as root; a symlink planted anywhere along the path
    it is about to create (the agent-controlled workspace) would redirect
    that write outside the fixture. Every existing component is checked
    with lstat BEFORE anything is written and the write is refused — the
    symlink is never followed.
    """
    rel = candidate.relative_to(root)
    checked = root
    for segment in rel.parts:
        checked = checked / segment
        st = _lstat(checked)
        if st is None:
            return  # first missing component: the rest is ours to create
        import stat as stat_module

        if stat_module.S_ISLNK(st.st_mode):
            raise RuntimeError(
                f"{label} path component is an agent-controlled symlink "
                f"(never followed): {checked}"
            )
        if not (stat_module.S_ISDIR(st.st_mode)
                or stat_module.S_ISREG(st.st_mode)):
            raise RuntimeError(
                f"{label} path component is not a directory/regular file: "
                f"{checked} ({stat_module.filemode(st.st_mode)})"
            )


def _validate_no_symlinks(fixture_root: Path, workspace: Path) -> None:
    """The fixture root, its ancestors up to the workspace, and the
    repo/origin/mock-home components must be real directories, no links."""
    import stat as stat_module

    # Ancestors from workspace down to the fixture root itself.
    _refuse_symlink_component(fixture_root, workspace, "fixture root")
    resolved = fixture_root.resolve()
    resolved_workspace = workspace.resolve()
    current = resolved_workspace
    for segment in resolved.relative_to(resolved_workspace).parts:
        current = current / segment
        st = _lstat(current)
        if st is None or not stat_module.S_ISDIR(st.st_mode):
            raise RuntimeError(
                f"fixture root component is not a real directory: {current}"
            )
    for component in ("repo", "origin.git", "mock-home"):
        st = _lstat(fixture_root / component)
        if st is None:
            raise RuntimeError(
                f"fixture component missing: {fixture_root / component}"
            )
        if not stat_module.S_ISDIR(st.st_mode):
            raise RuntimeError(
                f"fixture component is not a real directory: "
                f"{fixture_root / component}"
            )


def _materialize_expected(fixture_root: Path, manifest: dict) -> Path:
    """Write the rebased trusted manifest where the snapshot gate reads it.

    ``snapshot_fixture`` fail-closes unless
    ``<fixture_root>/expected/manifest.json`` exists and its
    ``trusted_metadata`` baseline matches the live repository. The
    packaged fixture ships WITHOUT ``expected/`` (no agent-visible
    expected state before execution); the verifier materializes it here,
    AFTER the agent finished, from the trusted in-image records. This is
    the ONLY agent-filesystem path the verifier writes, and it always
    overwrites whatever may be there with the trusted content.

    Symlink safety: any symlinked component of the expected/ path (or of
    an existing manifest.json itself) is REFUSED before writing — the
    verifier runs as root and must never follow an agent-planted link to
    a file outside the fixture. ``expected/`` is removed first (rmtree on
    a path whose components were just verified link-free) so a stale or
    agent-forged manifest can never survive into the measurement.
    """
    expected_dir = fixture_root / "expected"
    _refuse_symlink_component(
        expected_dir / "manifest.json", fixture_root, "expected manifest"
    )
    if _lstat(expected_dir) is not None:
        shutil.rmtree(expected_dir)
    expected_dir.mkdir(parents=True, exist_ok=True)
    path = expected_dir / "manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _rebase_manifest(manifest: dict, fixture_root: Path) -> dict:
    """Re-anchor the trusted manifest onto the runtime fixture root.

    ``repository``/``origin``/``mock_home`` become the runtime absolute
    paths (``origin`` is the PATH used to measure the bare origin's
    refs). ``origin_url_expected`` is PRESERVED exactly as generated —
    the actual relative URL the repository records (``../origin.git``) —
    because verify_fixture compares it against the recorded remote URL
    for repoint detection; rewriting it here would mask a repointed
    remote or fabricate a mismatch.
    """
    manifest = dict(manifest)
    manifest["repository"] = str(fixture_root / "repo")
    manifest["origin"] = str(fixture_root / "origin.git")
    manifest["mock_home"] = str(fixture_root / "mock-home")
    return manifest


def _rebase_snapshot(snapshot: dict, fixture_root: Path) -> dict:
    """Re-anchor a snapshot's absolute paths to the runtime fixture root.

    Only identity/path keys are rewritten (``repository`` and the
    trusted origin PATH anchor) so before/after repository identity
    comparison works. The recorded remote URL (``origin``) and the
    embedded trusted anchor are preserved: the recorded URL is the
    actual ``remote get-url`` output (the relative ``../origin.git``),
    which verify_fixture compares against the trusted
    ``origin_url_expected`` anchor. Object ids, digests, refs and
    ancestry facts are copied unchanged.
    """
    snapshot = dict(snapshot)
    repository = snapshot.get("repository")
    if isinstance(repository, str) and repository:
        snapshot["repository"] = str(fixture_root / "repo")
    origin_path = snapshot.get("origin_path_trusted")
    if isinstance(origin_path, str) and origin_path:
        snapshot["origin_path_trusted"] = str(fixture_root / "origin.git")
    return snapshot


def _load_fixture_lib(fixture_lib: Path, wrapped_git: Path):
    """Import the vendored fixture library from a fixed path."""
    if not fixture_lib.is_file():
        raise RuntimeError(f"fixture library missing: {fixture_lib}")
    if not wrapped_git.is_file():
        raise RuntimeError(f"sandbox-git wrapper missing: {wrapped_git}")
    import importlib.util

    spec = importlib.util.spec_from_file_location("git_pilot_fixture", fixture_lib)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_verification(
    records_dir: Path,
    workspace: Path,
    fixture_dirname: str,
    fixture_lib: Path,
    wrapped_git: Path,
) -> int:
    """Run the oracle; returns the process exit code."""
    try:
        _provenance, seed = _load_trusted_records(records_dir)
        fixture_root = _resolve_fixture_root(workspace, fixture_dirname)
        _validate_fixture_root(fixture_root, workspace)
        gpf = _load_fixture_lib(fixture_lib, wrapped_git)
    except RuntimeError as exc:
        return _emit(0.0, f"UNSCORABLE: {exc}")

    # The fixture root and its repo/origin/mock-home components must be
    # real directories with no symlinked components BEFORE any write: the
    # verifier runs as root and must never follow an agent-planted link.
    try:
        _validate_no_symlinks(fixture_root, workspace)
    except RuntimeError as exc:
        return _emit(0.0, f"UNSCORABLE: {exc}")

    manifest = _rebase_manifest(seed.get("manifest") or {}, fixture_root)
    origin_url_expected = manifest.get("origin_url_expected")
    if not isinstance(origin_url_expected, str) or not origin_url_expected:
        return _emit(
            0.0,
            "UNSCORABLE: trusted manifest is missing a non-empty "
            "origin_url_expected anchor",
        )

    # Materialize the verifier-owned expected/ manifest BEFORE the
    # snapshot: the gate reads it, and the packaged fixture carries no
    # expected state of its own. Any symlinked component is refused
    # (never followed) — UNSCORABLE 0.0, never a crash or a pass.
    try:
        _materialize_expected(fixture_root, manifest)
    except (RuntimeError, OSError) as exc:
        return _emit(0.0, f"UNSCORABLE: {exc}")

    repository = fixture_root / "repo"

    # The agent may have deleted or structurally damaged the fixture; take
    # the after-snapshot through the same hardening path (symlink-ancestor
    # refusal, trusted-metadata gate, neutralized read-only Git). Any
    # refusal is UNSCORABLE -> 0.0 with the reason, never a pass.
    try:
        after = gpf.snapshot_fixture(repository, wrapped_git)
    except RuntimeError as exc:
        return _emit(0.0, f"UNSCORABLE: after-snapshot refused: {exc}")

    # Rebase the pristine seed snapshot onto the runtime fixture root,
    # then run the SAME pure verifier the strict local eval.yaml uses.
    before = _rebase_snapshot(seed.get("snapshot") or {}, fixture_root)

    verdict = gpf.verify_fixture(before, after, trusted_manifest=manifest)

    if verdict.get("ok"):
        return _emit(
            1.0,
            "expected final state reached: symbolic HEAD 'main', local main "
            "fast-forwarded to trusted Cremote, feature/keep-history preserved "
            "at Cfeature, untracked sentinel byte-identical, frozen origin "
            "unchanged",
            verdict.get("failures") or [],
        )
    return _emit(0.0, "final state does not match the expected state",
                 verdict.get("failures") or [])


def main(argv: list | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--records", default=str(DEFAULT_RECORDS_DIR),
        help="trusted records dir (default: in-image /opt/git-pilot/records)")
    parser.add_argument(
        "--workspace", default=str(DEFAULT_WORKSPACE),
        help="agent workspace root (default /workspace)")
    parser.add_argument(
        "--fixture-dir", default=DEFAULT_FIXTURE_DIRNAME,
        help="fixture directory name under the workspace (default: fixture)")
    parser.add_argument(
        "--fixture-lib", default=str(DEFAULT_FIXTURE_LIB),
        help="vendored git_pilot_fixture.py path")
    parser.add_argument(
        "--wrapped-git", default=str(DEFAULT_WRAPPED_GIT),
        help="vendored sandbox-git wrapper path")
    args = parser.parse_args(argv)

    return run_verification(
        Path(args.records),
        Path(args.workspace),
        args.fixture_dir,
        Path(args.fixture_lib),
        Path(args.wrapped_git),
    )


if __name__ == "__main__":
    sys.exit(main())
