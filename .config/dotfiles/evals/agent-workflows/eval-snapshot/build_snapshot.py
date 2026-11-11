#!/usr/bin/env python3
"""Build and validate the evaluation-only ALL-ILLUSIONIST snapshot (Task 4B.2C).

What this is: a self-contained, committed snapshot of the native OpenCode config
plus one rewritten copy of every role agent definition, used ONLY inside the
worker-budget evaluation workspaces. It is **not** production configuration and
is never registered globally.

Why the rewrite is model-only: the runtime agents under
`~/.config/opencode/agents/` carry the user's ordered tool/shell/skill/subagent
permissions. The evaluation must keep those permissions byte-for-byte and change
**only** which model each role requests. `build()` therefore replaces exactly one
frontmatter line (`model: ...`) per agent file and refuses any file where that
rewrite is not unambiguous.

Manifest: `build()` also writes `manifest.json` with the schema version, pinned
model, ordered roles, SHA-256 of every pre-rewrite source role and every
generated file, plus a `snapshot_id` derived from those fields. The identity has
no timestamp, absolute path, credential or Git state, so the same inputs under
different directories produce the same manifest, while a source-only change
(even one the model rewrite would erase) stays distinguishable.
`verify_snapshot()` rejects a stale or tampered manifest/content pair, and
`write_reference_manifest()` records the checked-in snapshot only after proving
its bytes already correspond to the explicit source roles; it never rewrites
reviewed prompts.

Schema source (pinned runtime 2.1.4, official docs read 2026-11-04):
  * `/docs/config/` — `model`, `small_model` ("lightweight tasks like title
    generation"), `default_agent`, `agent.<name>.model`, `providers`/`provider`,
    `compaction` (auto/keep/buffer — no model field), `experimental.policies`,
    `enabled_providers`.
  * `/docs/policies/` — one action `provider.use`, `effect` allow|deny,
    wildcard `resource`, last-match-wins, deny-all-then-allow pattern, and the
    explicit statement that a policy gates a **provider**, not an individual
    model inside a provider.

Known scope limit (stated, not hidden): OpenCode 2's only policy action is
`provider.use`, which gates a **provider**, not a model id inside it. The
staged file declares one provider and one model and pins every model reference,
including the explicit `--model agentgateway/illusionist` primary-request argv.
That makes *every reference this evaluation controls* illusionist; it is **not**
a runtime guarantee. Two residual facts, stated plainly: (a) OpenCode merges the
user's global config underneath a project config, and that global provider block
still declares other `agentgateway` model ids, so extra aliases may exist in the
effective catalog (provider-level denial does not remove them); (b) provider-
private upstream routing behind the gateway is not observable here. The
post-run assistant-model identity guard in `worker_budget_checks.py` exists so an
operator can check observed identities before a second arm is run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).resolve().parent
SOURCE_AGENTS = Path.home() / ".config" / "opencode" / "agents"

#: Manifest file written next to the generated config.
MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1

ILLUSIONIST = "agentgateway/illusionist"
PROVIDER_ID = "agentgateway"
MODEL_ID = "illusionist"

#: Every role agent the current stack can select, including auxiliary roles.
ROLES = ("orchestrator", "worker", "reviewer", "architect", "planner", "zweistein")

#: Provider entry copied from the user's config (values are ENV REFERENCES only).
_PROVIDER = {
    "name": "AgentGateway",
    "package": "@opencode/ai/providers/openai-compatible",
    "settings": {
        "baseURL": "{env:AGENTGATEWAY_BASE_URL}",
        "apiKey": "{env:AGENTGATEWAY_API_KEY}",
    },
    "models": {
        # Copied verbatim from ~/.config/opencode/opencode.jsonc (illusionist).
        MODEL_ID: {
            "modelID": MODEL_ID,
            "name": "Illusionist (DeepSeek V4.1 Flash)",
            "capabilities": {
                "tools": True,
                "input": ["text", "image"],
                "output": ["text"],
            },
            "limit": {"context": 350000, "output": 32000},
        }
    },
}

#: Deny-by-default provider policy, then the single allow (documented pattern:
#: broad rule first, specific exception after; last matching statement wins).
_POLICIES = [
    {"effect": "deny", "action": "provider.use", "resource": "*"},
    {"effect": "allow", "action": "provider.use", "resource": PROVIDER_ID},
]

#: Ordered global permissions copied VERBATIM from ~/.config/opencode/opencode.jsonc
#: (lines 51-62). The global config defines this array; dropping it in the snapshot
#: would silently change tool/MCP permission semantics, so it is preserved exactly.
_PERMISSIONS = [
    {"action": "Atlassian_*", "resource": "*", "effect": "deny"},
    {"action": "context7_*", "resource": "*", "effect": "deny"},
]


def snapshot_config() -> dict:
    """Return the evaluation-only config document (all model paths illusionist)."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": ILLUSIONIST,
        # Title generation and other lightweight auxiliary requests.
        "small_model": ILLUSIONIST,
        "default_agent": "orchestrator",
        # Config-level pin for every role; the staged agent markdown is pinned too,
        # so a merge-precedence surprise cannot select another model.
        "agent": {role: {"model": ILLUSIONIST} for role in ROLES},
        # Ordered global permissions preserved verbatim (see _PERMISSIONS).
        "permissions": _PERMISSIONS,
        "experimental": {"policies": _POLICIES},
        "enabled_providers": [PROVIDER_ID],
        # No model field exists on compaction; it inherits the session model.
        "compaction": {"auto": True, "keep": {"tokens": 8000}, "buffer": 8000},
        "providers": {PROVIDER_ID: _PROVIDER},
    }


def _rewrite_model(text: str, name: str) -> str:
    """Replace the single frontmatter ``model:`` line, or refuse."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{name}: missing YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:  # pragma: no cover - defensive
        raise ValueError(f"{name}: unterminated YAML frontmatter") from None
    positions = [i for i in range(1, end) if lines[i].startswith("model:")]
    if len(positions) != 1:
        raise ValueError(f"{name}: expected exactly one frontmatter model line")
    lines[positions[0]] = f"model: {ILLUSIONIST}\n"
    return "".join(lines)


class SnapshotError(ValueError):
    """Raised when snapshot inputs or a manifest cannot be trusted."""


def _rewrite_model_with_context(text: str, name: str) -> str:
    """Surface a frontmatter rewrite refusal as a trusted-input failure."""
    try:
        return _rewrite_model(text, name)
    except ValueError as exc:
        raise SnapshotError(str(exc)) from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_sources(source: Path) -> dict[str, bytes]:
    """Read every role source as raw bytes, refusing anything missing."""
    if not source.is_dir():
        raise SnapshotError(f"source agent directory missing: {source}")
    raw: dict[str, bytes] = {}
    for role in ROLES:
        path = source / f"{role}.md"
        if not path.is_file():
            raise SnapshotError(f"missing source agent: {path}")
        raw[role] = path.read_bytes()
    return raw


def _generate(source: Path) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Validate every role input and return (source bytes, generated file bytes).

    Nothing is written here: the whole input set is validated and hashed before
    the caller publishes anything, so a bad role cannot leave a half snapshot.
    """
    raw = _read_sources(source)
    texts: dict[str, str] = {}
    for role, data in raw.items():
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise SnapshotError(f"{role}: source agent is not UTF-8") from exc
        texts[role] = _rewrite_model_with_context(text, role)
    config = snapshot_config()
    problems = validate(config, texts)
    if problems:
        raise SnapshotError("snapshot validation failed: " + "; ".join(problems))
    files = {f"agents/{role}.md": texts[role].encode("utf-8") for role in ROLES}
    files["opencode.jsonc"] = (
        json.dumps(config, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    return raw, files


def _identity_payload(manifest: dict) -> dict:
    """The canonical identity fields; everything else is derived metadata."""
    return {
        "schema_version": manifest["schema_version"],
        "model": manifest["model"],
        "roles": list(manifest["roles"]),
        "source_sha256": manifest["source_sha256"],
        "files_sha256": manifest["files_sha256"],
    }


def snapshot_id(manifest: dict) -> str:
    """SHA-256 over canonical sorted JSON of the identity fields."""
    canonical = json.dumps(
        _identity_payload(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return _sha256_bytes(canonical.encode("utf-8"))


def build_manifest(source: Path = SOURCE_AGENTS) -> dict:
    """Compute the snapshot manifest from role sources without writing anything."""
    raw, files = _generate(source)
    return _manifest_from(raw, files)


def _manifest_from(raw: dict[str, bytes], files: dict[str, bytes]) -> dict:
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "snapshot_id": "",
        "model": ILLUSIONIST,
        "roles": list(ROLES),
        "source_sha256": {f"{role}.md": _sha256_bytes(raw[role]) for role in ROLES},
        "files_sha256": {name: _sha256_bytes(files[name]) for name in sorted(files)},
    }
    manifest["snapshot_id"] = snapshot_id(manifest)
    return manifest


def _expected_files() -> set[str]:
    return {f"agents/{role}.md" for role in ROLES} | {"opencode.jsonc"}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def validate_manifest(manifest: dict) -> list[str]:
    """Return problems with a manifest document; empty means well-formed."""
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    problems: list[str] = []
    expected_keys = {
        "schema_version",
        "snapshot_id",
        "model",
        "roles",
        "source_sha256",
        "files_sha256",
    }
    missing = expected_keys - set(manifest)
    extra = set(manifest) - expected_keys
    if missing:
        problems.append(f"manifest is missing keys: {sorted(missing)}")
    if extra:
        problems.append(f"manifest has unexpected keys: {sorted(extra)}")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        problems.append(f"schema_version is {manifest.get('schema_version')!r}")
    if manifest.get("model") != ILLUSIONIST:
        problems.append(f"model is {manifest.get('model')!r}")
    if manifest.get("roles") != list(ROLES):
        problems.append(f"roles are {manifest.get('roles')!r}")

    source_hashes = manifest.get("source_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != {
        f"{role}.md" for role in ROLES
    }:
        problems.append("source_sha256 does not cover exactly the role sources")
    elif not all(_is_sha256(value) for value in source_hashes.values()):
        problems.append("source_sha256 contains a non-SHA256 value")

    file_hashes = manifest.get("files_sha256")
    if not isinstance(file_hashes, dict) or set(file_hashes) != _expected_files():
        problems.append("files_sha256 does not cover exactly the generated files")
    elif not all(_is_sha256(value) for value in file_hashes.values()):
        problems.append("files_sha256 contains a non-SHA256 value")

    recorded_id = manifest.get("snapshot_id")
    if not _is_sha256(recorded_id):
        problems.append("snapshot_id is not a SHA256 value")
    elif not problems:
        if recorded_id != snapshot_id(manifest):
            problems.append("snapshot_id does not match the manifest identity")
    return problems


def verify_snapshot(dest: Path = SNAPSHOT_DIR) -> dict:
    """Load a snapshot manifest and verify the checked-in bytes still match it.

    Detects a tampered or stale manifest and any generated file whose bytes no
    longer match the recorded hash. Raises ``SnapshotError`` instead of
    regenerating anything.
    """
    manifest_path = dest / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise SnapshotError(f"snapshot manifest missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SnapshotError(f"snapshot manifest unreadable: {manifest_path}") from exc
    problems = validate_manifest(manifest)
    if problems:
        raise SnapshotError("snapshot manifest invalid: " + "; ".join(problems))
    for relative, expected in manifest["files_sha256"].items():
        path = dest / relative
        if not path.is_file():
            problems.append(f"generated file missing: {relative}")
            continue
        if _sha256_bytes(path.read_bytes()) != expected:
            problems.append(f"generated file does not match manifest: {relative}")
    if problems:
        raise SnapshotError("snapshot content mismatch: " + "; ".join(problems))
    return manifest


def write_reference_manifest(
    dest: Path = SNAPSHOT_DIR, source: Path = SOURCE_AGENTS
) -> Path:
    """Write ``manifest.json`` for the checked-in snapshot without regenerating it.

    The agent prompts and config are treated as reviewed artifacts: their bytes
    must already correspond to the explicit source roles, otherwise this refuses
    rather than silently rewriting reviewed content.
    """
    manifest = build_manifest(source)
    mismatched = []
    for relative, expected in manifest["files_sha256"].items():
        path = dest / relative
        if not path.is_file():
            mismatched.append(f"missing {relative}")
        elif _sha256_bytes(path.read_bytes()) != expected:
            mismatched.append(f"differs: {relative}")
    if mismatched:
        raise SnapshotError(
            "checked-in snapshot does not correspond to the source roles; "
            "refusing to regenerate: " + "; ".join(mismatched)
        )
    manifest_path = dest / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return manifest_path


def _is_legacy_destination(dest: Path) -> bool:
    """The default snapshot directory keeps its legacy regeneration behavior."""
    try:
        return dest.resolve() == SNAPSHOT_DIR.resolve()
    except OSError:  # pragma: no cover - defensive
        return False


def _is_nonempty(dest: Path) -> bool:
    return dest.is_dir() and any(dest.iterdir())


def build(
    dest: Path = SNAPSHOT_DIR,
    source: Path = SOURCE_AGENTS,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Write the snapshot config, one rewritten agent per role, and the manifest.

    The whole input set is validated and hashed before a single byte is written.
    A nonempty explicit destination is refused unless ``overwrite=True``; the
    legacy default snapshot directory still regenerates in place. Returns the
    same config/agent path list callers already relied on.
    """
    raw, files = _generate(source)  # validate the entire input set first
    dest = Path(dest)
    if _is_nonempty(dest) and not overwrite and not _is_legacy_destination(dest):
        raise SnapshotError(
            f"destination is not empty: {dest} (pass overwrite=True to replace it)"
        )
    manifest = _manifest_from(raw, files)
    agents_dir = dest / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for role in ROLES:
        out = agents_dir / f"{role}.md"
        out.write_bytes(files[f"agents/{role}.md"])
        written.append(out)
    config_path = dest / "opencode.jsonc"
    config_path.write_bytes(files["opencode.jsonc"])
    written.append(config_path)
    (dest / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return written


def _model_references(document) -> list[str]:
    """Collect every value that names a model (keys: model, small_model, modelID)."""
    found = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}" if path else str(key)
                if key in {"model", "small_model"} and isinstance(value, str):
                    found.append(f"{here}={value}")
                elif key == "modelID" and isinstance(value, str):
                    found.append(f"{here}={value}")
                walk(value, here)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(document)
    return found


def validate(document: dict, agents: dict[str, str] | None = None) -> list[str]:
    """Return a list of problems; an empty list means the snapshot is acceptable."""
    problems: list[str] = []

    if document.get("model") != ILLUSIONIST:
        problems.append(f"main model is {document.get('model')!r}")
    if document.get("small_model") != ILLUSIONIST:
        problems.append(f"small_model is {document.get('small_model')!r}")
    if document.get("default_agent") != "orchestrator":
        problems.append(f"default_agent is {document.get('default_agent')!r}")

    agents_cfg = document.get("agent") or {}
    if set(agents_cfg) != set(ROLES):
        problems.append(f"agent roles are {sorted(agents_cfg)}")
    for role, block in agents_cfg.items():
        if (block or {}).get("model") != ILLUSIONIST:
            problems.append(f"agent {role} model is {(block or {}).get('model')!r}")

    providers = document.get("providers") or {}
    if set(providers) != {PROVIDER_ID}:
        problems.append(f"providers are {sorted(providers)}")
    models = (providers.get(PROVIDER_ID) or {}).get("models") or {}
    if set(models) != {MODEL_ID}:
        problems.append(f"provider models are {sorted(models)}")
    settings = (providers.get(PROVIDER_ID) or {}).get("settings") or {}
    for key in ("baseURL", "apiKey"):
        value = settings.get(key, "")
        if not isinstance(value, str) or not value.startswith("{env:"):
            problems.append(f"provider {key} is not an env reference")

    if document.get("enabled_providers") != [PROVIDER_ID]:
        problems.append(f"enabled_providers are {document.get('enabled_providers')!r}")
    if document.get("permissions") != _PERMISSIONS:
        problems.append("permissions do not match the global ordered permission array")
    if (document.get("experimental") or {}).get("policies") != _POLICIES:
        problems.append("experimental.policies is not deny-default + single provider allow")

    for reference in _model_references(document):
        if not reference.endswith(f"={ILLUSIONIST}") and not reference.endswith(
            f"={MODEL_ID}"
        ):
            problems.append(f"unexpected model reference: {reference}")

    for role, text in (agents or {}).items():
        model_lines = [
            line for line in text.splitlines() if line.startswith("model:")
        ]
        if model_lines != [f"model: {ILLUSIONIST}"]:
            problems.append(f"agent {role} frontmatter model lines: {model_lines}")

    return problems


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=SOURCE_AGENTS)
    parser.add_argument("--dest", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace a nonempty explicit destination",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify the destination manifest/content instead of writing",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="write manifest.json only, verifying checked-in bytes correspond",
    )
    args = parser.parse_args(argv)
    if args.verify:
        print(verify_snapshot(args.dest)["snapshot_id"])
        return 0
    if args.manifest_only:
        print(write_reference_manifest(dest=args.dest, source=args.source))
        return 0
    for path in build(dest=args.dest, source=args.source, overwrite=args.overwrite):
        print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual regeneration entry point
    raise SystemExit(_main())
