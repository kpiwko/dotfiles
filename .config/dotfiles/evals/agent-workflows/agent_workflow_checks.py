#!/usr/bin/env python3
"""Neutral end-state outcome boundary for the agent-definition evaluation.

This module is the ONE implementation of the deterministic end-state checks that
both the neutral agent-definition workflow and the legacy worker-budget harness
configs use. It deliberately carries **no** budget, request-evidence, observer,
bootstrap or provider-policy dependency: importing it must never pull in
``worker_budget_checks`` / ``worker_budget_request_evidence`` or any policy
module, so a neutral comparator can score saved records without the budget
research apparatus.

Scope and honesty limits — read before trusting a verdict:

* These functions assert **observable end state only**. They never claim that a
  review happened, a subagent delegation happened, an attempt was retried, or a
  token/money budget was enforced. :func:`score_record` therefore reports
  ``facts["procedure"] = "not_measured"``; a passing end state is never evidence
  of a measured procedure.
* The judge reconstructs a **read-only pristine case** from the trusted dataset
  directory and overlays only the in-place edits the harness actually collected.
  It never inspects the host project cwd, and it fails closed when the record is
  unusable (missing/unknown case directory, mismatched annotation, bad relative
  paths).
* Three outcomes are distinguished. ``unscorable`` means the collected record or
  its metadata cannot be trusted (missing/ambiguous fields, unknown case,
  scenario/case mismatch, unsafe overlay or dataset paths, missing pristine
  seeds, unreadable process artifact): it is never a pass and never a claim that
  the agent did something wrong. ``fail`` means the record is trustworthy and the
  observed end state is wrong (including observed binary replacement of a
  protected seed). ``pass`` means the record is trustworthy and the end state
  matches the reference expectations.
* Known coverage gap: the harness collector diffs against its initial commit
  (``collect.py::_collect_modified_files``), so a file the agent *deleted* does
  not appear as a modified file. Deletion of protected files is therefore NOT
  covered by these checks and must not be claimed as covered.
* Nothing here executes git, a network call, a model, or the agent.
* Trust caveat: scoring is **not** a sandbox. To compare an end state the
  deterministic checkers import and execute the trusted local fixture modules of
  the case in-process, so a hostile or hanging fixture runs with the scorer's
  own privileges. See the trust-boundary paragraph in
  ``AGENT_DEFINITION_EVAL.md``; never score an untrusted case directory.

Harness integration: registered either as a code judge
(``module: agent_workflow_checks`` / ``function: judge_scenario``) or called
directly by saved-run comparison. ``outputs`` is the ``load_case_record``
mapping (``case_dir``, ``annotations``, ``files``, ``modified_files``, …) —
there is no ``workspace`` key, which is exactly why the pristine-reconstruction
path below exists.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Optional

#: Project directory of this module (never the caller's cwd).
PROJECT = Path(__file__).resolve().parent
#: Trusted dataset root holding the pristine per-case inputs.
DATASET_ROOT = PROJECT / "cases" / "worker-budget-v1"

KNOWN_CASE_IDS = (
    "small-edit",
    "failing-test-debug",
    "reviewer-unchanged-handoff",
    "publication-dry-run",
)

#: Case-directory files that are evaluation metadata, not agent-visible inputs.
METADATA_FILES = frozenset({"input.yaml", "annotations.yaml", "answers.yaml"})

UNKNOWN = None

#: Terminal outcome statuses. The boolean judge is true only for ``pass``.
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNSCORABLE = "unscorable"

__all__ = [
    "PROJECT",
    "DATASET_ROOT",
    "KNOWN_CASE_IDS",
    "METADATA_FILES",
    "UNKNOWN",
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_UNSCORABLE",
    "check_failing_test_debug",
    "check_publication_dry_run",
    "check_reviewer_unchanged_handoff",
    "check_small_edit",
    "collect_metrics",
    "evaluate",
    "judge_scenario",
    "read_metrics_document",
    "score_record",
]


# --- trust boundary -------------------------------------------------------


def _safe_rel(rel: str) -> Optional[Path]:
    """Accept only a named relative path: no absolute, no ``..``, no empty."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    candidate = Path(rel)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    return candidate


def _dataset_root(override: Optional[str]) -> Optional[Path]:
    """Resolve the dataset root from this module, or an in-project override."""
    if override is None:
        return DATASET_ROOT
    candidate = _safe_rel(override)
    if candidate is None:
        return None
    resolved = (PROJECT / candidate).resolve()
    try:
        resolved.relative_to(PROJECT.resolve())
    except ValueError:
        return None
    return resolved


def _is_cache_noise(rel: Path) -> bool:
    """Interpreter cache bytes are tool noise, never a protected seed input.

    A materialized case root is imported during scoring, so ``__pycache__/*.pyc``
    appears in collected records as an ignored binary artifact. Seed identity must
    agree: a cached bytecode file is not a trusted input the agent could replace.
    """
    return "__pycache__" in rel.parts or rel.suffix == ".pyc"


def _pristine_files(case_id: str, dataset_root: Path) -> dict:
    """Read the pristine (trusted) seed bytes for one case.

    Symlinks are refused: a case fixture must be a real file, so a tampered
    checkout cannot make the judge read a host file. Interpreter cache noise
    (``__pycache__``/``*.pyc``) is excluded so seed identity matches how the
    collector reports it.
    """
    case_dir = dataset_root / case_id
    files = {}
    for entry in sorted(case_dir.rglob("*")):
        if not entry.is_file() or entry.is_symlink():
            continue
        rel = entry.relative_to(case_dir)
        if len(rel.parts) == 1 and rel.name in METADATA_FILES:
            continue
        if _is_cache_noise(rel):
            continue
        files[str(rel)] = entry.read_bytes()
    return files


def _overlay_files(record: dict) -> Optional[tuple]:
    """Return ``(text edits, ignored binary artifact paths)`` or ``None``.

    ``modified_files`` is ``rel -> text`` by contract, so a non-string there is
    malformed metadata and fails closed. ``files["_modified/<rel>"]`` additionally
    carries artifacts the collector could not decode as text
    (``{"_binary": True, ...}``) — e.g. ``__pycache__/*.pyc`` written when the
    seeded test is executed. Those entries are path-validated and returned as
    *ignored* artifacts; the caller still refuses any ignored path that is a
    pristine seed file, so binary replacement of a protected input fails while
    unrelated tool noise does not.
    """
    overlay = {}
    ignored = []
    source = record.get("modified_files")
    if source is not None and not isinstance(source, dict):
        return None
    for rel, value in (source or {}).items():
        safe = _safe_rel(rel)
        if safe is None or not isinstance(value, str):
            return None
        overlay[str(safe)] = value
    files = record.get("files")
    if isinstance(files, dict):
        for key, value in files.items():
            if not isinstance(key, str) or not key.startswith("_modified/"):
                continue
            safe = _safe_rel(key.split("/", 1)[1])
            if safe is None:
                return None
            if not isinstance(value, str):
                if str(safe) not in overlay:
                    ignored.append(str(safe))
                continue
            overlay.setdefault(str(safe), value)
    return overlay, ignored


def _materialize(pristine: dict, overlay: dict, dest: Path) -> Optional[str]:
    """Write pristine bytes plus observed text edits into *dest* (real files).

    Returns ``None`` on success, or a bounded refusal reason. Both inputs are
    written as real files, so a relative overlay path can still collide with the
    tree the seeds just created — e.g. ``notes.txt/x`` below a pristine *file*, or
    an overlay path that names a directory created by another overlay entry. The
    filesystem reports that as ``OSError``; it is a property of the collected
    record, not of the trusted seed, so it is contained here as an ``unscorable``
    refusal instead of an exception escaping the scorer. The reason carries no
    host path or raw exception text.
    """
    if not pristine:
        return "trusted case has no pristine seed bytes"
    try:
        for rel, data in pristine.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for rel, text in overlay.items():
            target = dest / rel
            # Defense in depth for programmatically built records.
            if dest.resolve() not in target.resolve().parents:
                return "collected overlay escapes the materialized case root"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    except OSError as exc:
        return (
            "collected overlay cannot be materialized as real files: "
            f"{type(exc).__name__}"
        )
    return None


# --- scenario checks (pure, over a case root) ------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _content_matches(path: Path, expected: str) -> bool:
    """Compare a file to a declared expectation (digest or exact UTF-8 bytes)."""
    if expected.startswith("sha256:"):
        return _sha256(path) == expected.split(":", 1)[1]
    return path.read_bytes() == expected.encode("utf-8")


#: Failures of executing a *trusted local fixture* in-process. The fixtures are
#: ordinary Python, so a broken one can also terminate the interpreter and raise
#: ``SystemExit`` (a ``BaseException`` that ``except Exception`` misses); that is
#: contained here as a failed case. ``KeyboardInterrupt`` is deliberately NOT in
#: this tuple: operator cancellation must still propagate.
_FIXTURE_ERRORS = (Exception, SystemExit)


def _error_text(exc: BaseException, limit: int = 160) -> str:
    """Bounded single-line fixture error text for a one-line reason."""
    text = " ".join(str(exc).split())
    if isinstance(exc, SystemExit):
        text = f"SystemExit({text})" if text else "SystemExit"
    elif not text:
        text = type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "..."


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(scenario: str, ok: bool, reasons: list, facts: dict) -> dict:
    return {"scenario": scenario, "ok": bool(ok), "reasons": reasons, "facts": facts}


def check_small_edit(root: Path, annotations: dict) -> dict:
    """The single fixed line is appended exactly once and nothing else moved."""
    scenario = "small-edit"
    target = root / annotations.get("target", "notes.txt")
    expected_line = annotations.get("appended_line", "")
    reasons: list = []
    facts: dict = {"target": str(target)}

    if not target.is_file():
        return _result(scenario, False, ["target file missing"], facts)

    text = target.read_text(encoding="utf-8")
    facts["bytes"] = len(text.encode("utf-8"))
    facts["appended_occurrences"] = text.count(expected_line) if expected_line else UNKNOWN

    if not expected_line:
        reasons.append("case declaration has no appended_line")
    else:
        if text.count(expected_line) != 1:
            reasons.append("appended line does not occur exactly once")
        if not text.endswith(expected_line + "\n") and not text.endswith(expected_line):
            reasons.append("appended line is not at end of file")
    seed = annotations.get("seed_prefix", "")
    if seed and not text.startswith(seed):
        reasons.append("pre-existing content was not preserved")

    for rel, expected in (annotations.get("forbidden_changes") or {}).items():
        candidate = root / rel
        if not candidate.is_file():
            reasons.append(f"required companion file missing: {rel}")
            continue
        if not _content_matches(candidate, expected):
            reasons.append(f"forbidden change to {rel}")

    return _result(scenario, not reasons, reasons, facts)


def check_failing_test_debug(root: Path, annotations: dict) -> dict:
    """The seeded test target is reachable, and unrelated bytes are untouched."""
    scenario = "failing-test-debug"
    module_rel = annotations.get("module", "boundary.py")
    reasons: list = []
    facts: dict = {"module": module_rel}

    module_path = root / module_rel
    if not module_path.is_file():
        return _result(scenario, False, ["debug target module missing"], facts)

    try:
        module = _load_module(module_path, "agent_workflow_fixture_boundary")
    except _FIXTURE_ERRORS as exc:  # a broken fixture is a failed case
        return _result(
            scenario,
            False,
            [f"target module does not import: {_error_text(exc)}"],
            facts,
        )

    fn = getattr(module, annotations.get("function", "page_bounds"), None)
    if not callable(fn):
        return _result(scenario, False, ["expected helper function missing"], facts)

    expected = {int(k): v for k, v in (annotations.get("expected_calls") or {}).items()}
    produced = {}
    for size, wanted in sorted(expected.items()):
        try:
            produced[size] = list(fn(size))
        except _FIXTURE_ERRORS as exc:
            reasons.append(f"helper raised for n={size}: {_error_text(exc)}")
            continue
        if produced[size] != wanted:
            reasons.append(f"helper mismatch for n={size}: {produced[size]} != {wanted}")
    facts["produced"] = produced

    for rel, expected_content in (annotations.get("unchanged_files") or {}).items():
        candidate = root / rel
        if not candidate.is_file():
            reasons.append(f"unrelated file missing: {rel}")
        elif not _content_matches(candidate, expected_content):
            reasons.append(f"unrelated file changed: {rel}")

    return _result(scenario, not reasons, reasons, facts)


def check_reviewer_unchanged_handoff(root: Path, annotations: dict) -> dict:
    """Review and validation-reuse are decided separately and correctly."""
    scenario = "reviewer-unchanged-handoff"
    reasons: list = []
    facts: dict = {"rows": {}}

    module_path = root / annotations.get("module", "decision_table.py")
    state_path = root / annotations.get("state", "state.json")
    if not module_path.is_file():
        return _result(scenario, False, ["decision module missing"], facts)
    if not state_path.is_file():
        return _result(scenario, False, ["decision state fixture missing"], facts)

    try:
        module = _load_module(module_path, "agent_workflow_fixture_decision")
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except _FIXTURE_ERRORS as exc:
        return _result(scenario, False, [f"fixture unreadable: {_error_text(exc)}"], facts)

    decide = getattr(module, annotations.get("function", "decide"), None)
    if not callable(decide):
        return _result(scenario, False, ["decision function missing"], facts)

    prior = state.get("prior") or {}
    for row in annotations.get("rows") or []:
        name = row["name"]
        current = dict(prior)
        current.update(state.get("rows", {}).get(name) or {})
        try:
            got = decide(prior, current)
        except _FIXTURE_ERRORS as exc:
            reasons.append(f"decision raised for {name}: {_error_text(exc)}")
            continue
        facts["rows"][name] = got
        want = {
            "review_needed": bool(row["review_needed"]),
            "validation_reusable": bool(row["validation_reusable"]),
        }
        if got != want:
            reasons.append(f"decision mismatch for {name}: {got} != {want}")

    for rel, expected_content in (annotations.get("unchanged_files") or {}).items():
        candidate = root / rel
        if not candidate.is_file():
            reasons.append(f"required fixture missing: {rel}")
        elif not _content_matches(candidate, expected_content):
            reasons.append(f"required fixture changed: {rel}")

    return _result(scenario, not reasons, reasons, facts)


def check_publication_dry_run(root: Path, annotations: dict) -> dict:
    """Expected state passes; every stop path blocks; push is never performed."""
    scenario = "publication-dry-run"
    reasons: list = []
    facts: dict = {"stops": {}}

    module_path = root / annotations.get("module", "preflight.py")
    if not module_path.is_file():
        return _result(scenario, False, ["preflight module missing"], facts)
    try:
        module = _load_module(module_path, "agent_workflow_fixture_preflight")
    except _FIXTURE_ERRORS as exc:
        return _result(
            scenario,
            False,
            [f"preflight module does not import: {_error_text(exc)}"],
            facts,
        )

    check = getattr(module, annotations.get("function", "check_preflight"), None)
    if not callable(check):
        return _result(scenario, False, ["preflight function missing"], facts)

    cases = annotations.get("cases") or {}
    for name, spec in cases.items():
        try:
            verdict = check(spec["expected"], spec["actual"])
        except _FIXTURE_ERRORS as exc:
            reasons.append(f"preflight raised for {name}: {_error_text(exc)}")
            continue
        facts["stops"][name] = verdict
        if not isinstance(verdict, dict):
            reasons.append(f"preflight did not return a mapping for {name}")
            continue
        if verdict.get("push_performed") is not False:
            reasons.append(
                f"push_performed is not False for {name}: {verdict.get('push_performed')!r}"
            )
        want_ok = spec["ok"]
        if bool(verdict.get("ok")) is not want_ok:
            reasons.append(f"ok mismatch for {name}: {verdict.get('ok')!r} != {want_ok}")
        if not want_ok and verdict.get("stop") != name:
            reasons.append(f"stop reason mismatch for {name}: {verdict.get('stop')!r}")

    for rel, expected_content in (annotations.get("unchanged_files") or {}).items():
        candidate = root / rel
        if not candidate.is_file():
            reasons.append(f"required fixture missing: {rel}")
        elif not _content_matches(candidate, expected_content):
            reasons.append(f"required fixture changed: {rel}")

    return _result(scenario, not reasons, reasons, facts)


_CHECKERS = {
    "small-edit": check_small_edit,
    "failing-test-debug": check_failing_test_debug,
    "reviewer-unchanged-handoff": check_reviewer_unchanged_handoff,
    "publication-dry-run": check_publication_dry_run,
}


def evaluate(scenario: str, root: Path, annotations: dict) -> dict:
    """Dispatch one scenario against an already-materialized case root."""
    checker = _CHECKERS.get(scenario)
    if checker is None:
        return _result(scenario, False, [f"unknown scenario {scenario!r}"], {})
    return checker(Path(root), annotations or {})


# --- neutral outcome boundary ---------------------------------------------


def _display(path: Path) -> str:
    """Project-relative display path for diagnostics (never a host cwd)."""
    try:
        return str(Path(path).resolve().relative_to(PROJECT.resolve()))
    except (ValueError, OSError):
        return str(path)


def _unscorable(scenario: Optional[str], reason: str, facts: dict) -> dict:
    return {
        "scenario": scenario,
        "ok": False,
        "reasons": [reason],
        "facts": facts,
        "status": STATUS_UNSCORABLE,
    }


def score_record(
    outputs: dict | None = None,
    dataset_root: str | None = None,
) -> dict:
    """Score one collected case record into a three-valued outcome.

    Returns ``{scenario, ok, reasons, facts, status}``. ``status`` is:

    * ``unscorable`` — the record or its metadata is unusable (no case dir,
      unknown case, missing/mismatched scenario annotation, unsafe dataset
      override or overlay path, missing pristine seeds, unmaterializable case).
      ``ok`` is False and ``reasons`` names the boundary that refused it.
    * ``fail`` — a trustworthy record whose observed end state is wrong:
      including an observed binary replacement of a protected seed.
    * ``pass`` — a trustworthy record whose end state matches expectations.

    ``facts`` is JSON-serializable diagnostic material for reports (case ID,
    observed edits, ignored binary artifacts, checker facts). It always records
    ``procedure = "not_measured"``: no delegation/review/reuse/attempt claim is
    inferred from an outcome.
    """
    record = outputs if isinstance(outputs, dict) else {}
    annotations = record.get("annotations")
    declared = annotations.get("scenario") if isinstance(annotations, dict) else None
    if not isinstance(declared, str) or not declared.strip():
        declared = None
    facts: dict = {"procedure": "not_measured"}
    if not isinstance(outputs, dict):
        return _unscorable(
            declared, "collected record is not a mapping", facts
        )

    raw_case_dir = record.get("case_dir")
    if not isinstance(raw_case_dir, str) or not raw_case_dir.strip():
        return _unscorable(declared, "collected record has no usable case_dir", facts)
    try:
        case_id = Path(raw_case_dir).resolve().name
    except (OSError, RuntimeError):
        return _unscorable(declared, "case_dir cannot be resolved", facts)
    if not case_id:
        return _unscorable(declared, "case_dir has no case directory name", facts)
    facts["case_id"] = case_id
    if case_id not in KNOWN_CASE_IDS:
        return _unscorable(
            declared or case_id, f"unknown case directory {case_id!r}", facts
        )

    if declared is None:
        return _unscorable(
            case_id,
            "collected record has no usable annotations.scenario",
            facts,
        )
    if declared != case_id:
        return _unscorable(
            declared,
            f"scenario {declared!r} does not match case directory {case_id!r}",
            facts,
        )

    root = _dataset_root(dataset_root)
    if root is None:
        return _unscorable(
            declared,
            "dataset root override is not an in-project relative path",
            facts,
        )
    if not root.is_dir():
        return _unscorable(
            declared, f"dataset root is not a directory: {_display(root)}", facts
        )
    facts["dataset_root"] = _display(root)

    parsed = _overlay_files(record)
    if parsed is None:
        return _unscorable(
            declared,
            "collected record has malformed modified_files/files overlay",
            facts,
        )
    overlay, ignored_artifacts = parsed
    facts["observed_text_edits"] = sorted(overlay)
    facts["ignored_binary_artifacts"] = sorted(ignored_artifacts)

    pristine = _pristine_files(case_id, root)
    if not pristine:
        return _unscorable(
            declared,
            f"trusted dataset has no pristine seed files for {case_id!r}",
            facts,
        )
    facts["pristine_files"] = sorted(pristine)

    replaced = sorted(path for path in ignored_artifacts if path in pristine)
    if replaced:
        # An observed binary write over a seed input is tamper, not noise —
        # independent of whether the agent's text fix would also be correct.
        return {
            "scenario": declared,
            "ok": False,
            "reasons": [
                f"binary replacement of protected seed: {path}" for path in replaced
            ],
            "facts": facts,
            "status": STATUS_FAIL,
        }

    with tempfile.TemporaryDirectory(prefix="agent-workflow-case-") as tmp:
        case_root = Path(tmp) / case_id
        case_root.mkdir(parents=True)
        problem = _materialize(pristine, overlay, case_root)
        if problem is not None:
            return _unscorable(declared, problem, facts)
        verdict = evaluate(declared, case_root, annotations)

    reasons = [str(reason) for reason in (verdict.get("reasons") or [])]
    facts["checks"] = verdict.get("facts") or {}
    ok = bool(verdict.get("ok")) and not reasons
    return {
        "scenario": declared,
        "ok": ok,
        "reasons": reasons,
        "facts": facts,
        "status": STATUS_PASS if ok else STATUS_FAIL,
    }


def judge_scenario(
    outputs: dict | None = None,
    dataset_root: Optional[str] = None,
    **_kwargs,
) -> bool:
    """Harness code judge: True ONLY for a scored ``pass`` outcome.

    Reconstructs the pristine case in a temporary directory, overlays ONLY the
    in-place edits the collector observed, then runs the deterministic checker.
    Any unusable metadata is ``unscorable`` (False), never a silent pass; there
    is no fallback to the caller's cwd (the harness passes no ``workspace`` key).
    """
    return score_record(outputs=outputs, dataset_root=dataset_root)["status"] == STATUS_PASS


# --- usage reporting ------------------------------------------------------


def read_metrics_document(text: Optional[str]) -> dict:
    """Parse a metrics.json document into a partial, UNKNOWN-preserving view."""
    unknown = {
        "status": "unknown",
        "token_usage": UNKNOWN,
        "cost_usd": UNKNOWN,
        "num_turns": UNKNOWN,
        "attempts": UNKNOWN,
        "model": UNKNOWN,
    }
    if text is None:
        return unknown
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        unknown["status"] = "unreadable"
        return unknown
    if not isinstance(data, dict):
        unknown["status"] = "unreadable"
        return unknown
    return {
        "status": "reported",
        "token_usage": data.get("token_usage", UNKNOWN),
        "cost_usd": data.get("cost_usd", UNKNOWN),
        "num_turns": data.get("num_turns", UNKNOWN),
        # No attempt counter exists on this runner; a wrapper may record one.
        "attempts": data.get("attempts", UNKNOWN),
        "model": data.get("model", UNKNOWN),
    }


def collect_metrics(record: dict | None) -> dict:
    """Usage from the collected case record only (``output/metrics.json``).

    No other usage source exists on this runner: no normalized event stream, no
    provider-verified cost. Absent/unreadable/partial data stays UNKNOWN.
    """
    files = (record or {}).get("files")
    if not isinstance(files, dict):
        return read_metrics_document(None)
    document = files.get("output/metrics.json")
    if not isinstance(document, str):
        return read_metrics_document(None)
    return read_metrics_document(document)
