#!/usr/bin/env python3
"""Neutral agent-definition evaluation: offline prepare and saved-run compare.

What this is: the offline half of a two-arm agent-definition comparison.
``prepare_arms`` builds one reproducible snapshot per arm from operator-supplied
agent sources, writes one neutral harness config per arm, and records
``experiment.json`` — the identities a later saved-run comparison needs.
``compare_runs`` then reads *already saved* run artifacts and reports what the
artifacts actually support. Nothing here calls a model, an agent, a network
endpoint or a subprocess; preparation and comparison are pure file operations.

Scope and honesty limits — read before using a prepared experiment or a
comparison report:

* **No live call, no efficacy claim.** A prepared experiment proves only which
  inputs *would* run. It is not evidence that an arm performed better.
* **Snapshots are model-only rewrites.** ``eval-snapshot/build_snapshot.py``
  replaces exactly one frontmatter ``model:`` line per role and preserves every
  other byte (tool/shell/skill/subagent permission order included), so a
  prepared arm differs from its source only in the model identity it requests.
* **Only snapshot locations vary between arms.** ``nonarm_sha256`` hashes the
  config with snapshot sources and the dataset path normalized away; ``prepare``
  refuses to finish when the two arms disagree on it. ``config_sha256`` hashes
  the generated file as written, so per-arm config bytes stay individually
  verifiable.
* **Dataset identity excludes evaluation-only staging.** The dataset content hash
  covers case metadata (``input.yaml``/``annotations.yaml``) and seed bytes and
  deliberately skips ``bootstrap/`` (policy/observer TypeScript from the earlier
  budget research) and generated artifacts (``__pycache__``, ``*.pyc``, ``.git``).
  Because the pinned runner enumerates *every* subdirectory of ``dataset.path`` as
  a case and has no config-level case allowlist, ``prepare`` also publishes a
  byte-identical four-case copy at ``<out>/dataset`` and points both generated arm
  configs at it; the trusted ``cases/worker-budget-v1`` dataset (and its
  ``bootstrap/`` staging) is never modified or used as the run dataset.
* **cwd independence is about resolution, not launching.** Generated configs use
  explicit absolute snapshot and dataset paths, so the pinned config loader and
  workspace materializer work from any caller cwd. The run itself is still
  launched from the eval project: the harness resolves a code judge's ``module``
  against the project root, so the trusted ``agent_workflow_checks`` module and
  its module-relative dataset stay in-project.
* **Runtime isolation is not claimed.** OpenCode merges the user's global config
  underneath a project config; this milestone does not isolate plugins or global
  config.

Layout written by ``prepare_arms`` (``prepare --baseline-source --candidate-source
--out``)::

    <out>/experiment.json
    <out>/dataset/<case-id>/...                 # prepared four-case copy (no bootstrap)
    <out>/baseline/eval.agent-definition.yaml
    <out>/baseline/snapshot/{manifest.json,opencode.jsonc,agents/*.md}
    <out>/candidate/eval.agent-definition.yaml
    <out>/candidate/snapshot/{manifest.json,opencode.jsonc,agents/*.md}

``experiment.json`` (``schema_version: 1``) records, per arm, the snapshot id,
the relative manifest/config paths, the generated config hash and the normalized
non-arm hash; plus the dataset case ids/content hash and the pinned
harness/runtime/model/argv metadata. It has no timestamp and no absolute path, so
preparing the same inputs twice yields byte-identical files. Paths inside it are
relative to the experiment directory; consumers join them onto their own
experiment path (no home-cwd fallback).

Saved-run comparison reads the existing saved-run layout only::

    <run>/harness/run_result.json                # required: per-case exit status/elapsed
    <run>/harness/cases/<case>/...               # per-case harness artifacts (diagnostic)
    <run>/collected/cases/<case>/...             # required for an outcome
    <run>/provenance/run.json                    # saved linkage metadata
    <run>/provenance/manifest.json               # saved copy of the arm snapshot manifest
    <run>/provenance/eval.agent-definition.yaml  # saved copy of the generated arm config

Comparison honesty rules (they are enforced, not advisory):

* **Linkage must be saved, never inferred.** A prepared ``experiment.json`` does
  not prove what an old run used. Before anything is scored, the prepared
  ``<out>/dataset`` copy and the trusted in-project dataset are both re-hashed and
  must match the recorded case ids/content hash; every generated config's absolute
  dataset path, snapshot staging sources and ``runner.plugin_dirs`` must resolve to
  the experiment directory being loaded, so a moved/copied experiment fails closed
  instead of reading the old location. The three ``provenance/`` files must then
  verify against that arm's prepared snapshot/config/dataset, with the saved
  manifest validated as a whole; missing linkage is ``unverified`` and unequal
  controlled inputs are ``incomparable``. The ``harness/run_result.json``
  ``model`` is the harness-recorded/configured model identity, **not** runtime
  attestation of which model actually served a request; it must match the pinned
  model: a mismatch is ``incomparable`` and an absent record is ``unverified``.
  The saved ``provenance/run.json`` ``model`` is only a self-assertion and never
  overrides the harness-recorded value. Old runs without them keep diagnostic
  outcomes but never gain retroactive provenance.
* **Identical generated ``files_sha256`` maps are a smoke pair only.** Two arms
  whose rewritten snapshot bytes are equal cannot support an efficacy comparison
  even when their pre-rewrite sources (and snapshot IDs) differ; the state is
  ``same_content_smoke_only``. In every non-``verified_comparable`` state paired
  deltas are suppressed.
* **No efficacy or ranking is computed, ever.** The tool reports outcomes,
  measured availability and descriptive paired deltas. It never ranks arms,
  never invents procedure counts (``delegations``/``reviews``/``reuse``/
  ``retries``/``attempts``/``length_stops`` stay null with ``not_measured``) and
  never upgrades empty events or native prose into counters.
* **Unknown stays unknown.** Missing exit status is ``unknown``; negative,
  nonfinite or wrong-type numbers are unknown; whole-run totals are never used as
  per-case values; zero is valid only when explicitly recorded. A full-set total
  is emitted only when every expected case has one measured, single-source value.
  ``completed`` requires exit code 0 **and** a passing end state, so a passing
  edit from a failed/timed-out process is not a completed task.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import yaml

#: Project directory of this module (never the caller's cwd).
PROJECT = Path(__file__).resolve().parent
#: Checked-in neutral reference config template.
TEMPLATE_PATH = PROJECT / "eval.agent-definition.yaml"
#: Trusted dataset root holding the pristine per-case inputs.
DATASET_ROOT = PROJECT / "cases" / "worker-budget-v1"
#: Dataset root as written into configs/judges: in-project and module-relative.
DATASET_REL = "cases/worker-budget-v1"
#: Snapshot builder directory (not an importable package: loaded by path).
SNAPSHOT_TOOL = PROJECT / "eval-snapshot" / "build_snapshot.py"

CONFIG_FILENAME = "eval.agent-definition.yaml"
SNAPSHOT_SUBDIR = "snapshot"
EXPERIMENT_FILENAME = "experiment.json"
EXPERIMENT_SCHEMA_VERSION = 1
#: Ordered arms. The baseline arm is the reference; the candidate arm is the one
#: under test. Both are operator-supplied; there is no implicit product candidate.
ARMS = ("baseline", "candidate")

#: The fixed four case IDs of this suite, sorted for a stable manifest.
CASE_IDS = (
    "failing-test-debug",
    "publication-dry-run",
    "reviewer-unchanged-handoff",
    "small-edit",
)

#: Dataset path components that are evaluation staging, not case content.
DATASET_EXCLUDED_PARTS = frozenset({"bootstrap", "__pycache__", ".git"})
DATASET_EXCLUDED_SUFFIXES = (".pyc", ".pyo")

#: Prepared per-experiment dataset copy (relative to the experiment directory).
#: The pinned runner enumerates *every* subdirectory of ``dataset.path`` as a case
#: and has no config-level case allowlist, so a prepared experiment ships a copy
#: containing only the trusted case directories. ``bootstrap/`` (budget/observer
#: TypeScript research staging) therefore cannot be discovered as a fifth case.
DATASET_PREPARED_SUBDIR = "dataset"
#: Harness-injected task fixtures that are never case seeds: a prepared copy keeps
#: only the bytes covered by the dataset identity, and refuses inputs where these
#: would otherwise have to be copied (see ``stage_prepared_dataset``).
DATASET_COPY_EXCLUDED_DIRS = frozenset({"environment", "solution"})
DATASET_COPY_EXCLUDED_NAMES = frozenset({"task.toml", "instruction.md"})

#: Snapshot-relative source for each arm-dependent `dataset.workspace.files` dest.
SNAPSHOT_SOURCES = {
    "opencode.jsonc": "opencode.jsonc",
    ".opencode/agents": "agents",
}

#: Placeholders used by the normalized non-arm hash.
NORMALIZED_DATASET = "<dataset>"
NORMALIZED_SOURCE_ROOTS = "<snapshot-source-roots>"

#: Pinned execution metadata recorded in `experiment.json`.
HARNESS_COMMIT = "b041d5a6db0b1181d51d95190faf8f2c0808c38d"
OPENCODE_RUNTIME = "2.1.4"
MODEL = "agentgateway/illusionist"
JUDGE_MODULE = "agent_workflow_checks"
JUDGE_FUNCTION = "judge_scenario"

# --- saved-run comparison constants ---------------------------------------

COMPARISON_SCHEMA_VERSION = 1
COMPARISON_JSON_FILENAME = "comparison.json"
COMPARISON_MD_FILENAME = "comparison.md"
HARNESS_SUBDIR = "harness"
RUN_RESULT_FILENAME = "run_result.json"
COLLECTED_SUBDIR = "collected"
COLLECTED_CASES_SUBDIR = "cases"
PROVENANCE_SUBDIR = "provenance"
PROVENANCE_RUN_FILENAME = "run.json"

#: Pinned harness the saved records are loaded with. Overridable for a relocated
#: checkout; never resolved against the caller's cwd.
DEFAULT_HARNESS = Path(
    "/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/"
    "vendor/agent-eval-harness-b041d5a6db0b1181d51d95190faf8f2c0808c38d"
)

#: Comparison states. Only ``verified_comparable`` may show paired deltas.
STATE_VERIFIED_COMPARABLE = "verified_comparable"
STATE_SAME_CONTENT = "same_content_smoke_only"
STATE_UNVERIFIED = "unverified"
STATE_INCOMPARABLE = "incomparable"

#: Per-case measured metrics and their numeric kind.
METRIC_KINDS = {
    "elapsed_seconds": "number",
    "token_usage": "integer",
    "cost_usd": "number",
    "num_turns": "integer",
}

#: Largest count a JSON consumer can represent exactly (2**53 - 1). Reported
#: token components outside this range are not used to derive a total.
MAX_SAFE_INTEGER = 2**53 - 1

#: Normalized token-total derivations. They are labelled in the metric ``kind``
#: so aggregates/deltas only combine equivalent accounting and a reported scalar
#: is never mistaken for a mapping component.
TOKEN_TOTAL_MAPPING = "input_output_total"
TOKEN_TOTAL_SCALAR = "reported_scalar"

#: Procedural counters this runner cannot measure. Always null/not_measured;
#: empty events, native prose or fixture assertions never upgrade them.
PROCEDURE_FIELDS = (
    "delegations",
    "reviews",
    "duplicate_reviews",
    "reuse",
    "retries",
    "attempts",
    "length_stops",
)

__all__ = [
    "PROJECT",
    "TEMPLATE_PATH",
    "DATASET_ROOT",
    "DATASET_REL",
    "DATASET_PREPARED_SUBDIR",
    "CONFIG_FILENAME",
    "SNAPSHOT_SUBDIR",
    "EXPERIMENT_FILENAME",
    "EXPERIMENT_SCHEMA_VERSION",
    "ARMS",
    "CASE_IDS",
    "SNAPSHOT_SOURCES",
    "HARNESS_COMMIT",
    "OPENCODE_RUNTIME",
    "MODEL",
    "COMPARISON_SCHEMA_VERSION",
    "COMPARISON_JSON_FILENAME",
    "COMPARISON_MD_FILENAME",
    "PROCEDURE_FIELDS",
    "STATE_VERIFIED_COMPARABLE",
    "STATE_SAME_CONTENT",
    "STATE_UNVERIFIED",
    "STATE_INCOMPARABLE",
    "ComparisonError",
    "PreparationError",
    "arm_config_document",
    "compare_runs",
    "dataset_content_hash",
    "load_experiment",
    "load_template",
    "nonarm_config_hash",
    "normalized_config_document",
    "prepare_arms",
    "render_comparison_markdown",
    "render_config",
    "stage_prepared_dataset",
]


class PreparationError(ValueError):
    """Raised when arm preparation inputs or an output destination cannot be used."""


class ComparisonError(ValueError):
    """Raised when saved-run comparison inputs are missing or structurally unusable."""


# --- snapshot builder ------------------------------------------------------


_BUILDER: ModuleType | None = None


def _builder() -> ModuleType:
    """Load the one existing snapshot builder (never a second snapshot engine)."""
    global _BUILDER
    if _BUILDER is None:
        spec = importlib.util.spec_from_file_location(
            "eval_snapshot_builder_for_agent_definition", SNAPSHOT_TOOL
        )
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise PreparationError(f"cannot load snapshot builder: {SNAPSHOT_TOOL}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _BUILDER = module
    return _BUILDER


# --- hashing helpers -------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha256(document) -> str:
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return _sha256_bytes(canonical.encode("utf-8"))


# --- dataset identity ------------------------------------------------------


def _dataset_files(dataset_root: Path) -> dict[str, str]:
    """Hash every case metadata/seed file, refusing symlinks and unsafe entries.

    Evaluation-only staging (``bootstrap/``, ``__pycache__``, ``.git``) and
    generated bytecode are excluded as before. A symlink that is directly related
    to hashed case content is *refused*, not silently skipped: the identity must
    describe the bytes a run would actually read, so a symlinked file (or a
    symlinked case directory reached through the tree) fails closed.
    """
    entries: dict[str, str] = {}
    for path in sorted(dataset_root.rglob("*")):
        rel = path.relative_to(dataset_root)
        if any(part in DATASET_EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.is_symlink():
            raise PreparationError(
                f"dataset contains a symlink (unsafe for hashing): {rel.as_posix()}"
            )
        if not path.is_file():
            continue
        if rel.name.endswith(DATASET_EXCLUDED_SUFFIXES):
            continue
        entries[rel.as_posix()] = _sha256_bytes(path.read_bytes())
    return entries


def dataset_content_hash(dataset_root: Path = DATASET_ROOT) -> dict:
    """Return ``{case_ids, content_sha256, files_sha256_count}`` for the dataset.

    Metadata and seeds only: ``bootstrap/`` (policy/observer staging) and
    generated artifacts are excluded, so adding a research bootstrap file cannot
    change the identity of the case inputs a prepared arm actually runs.
    """
    dataset_root = Path(dataset_root)
    if not dataset_root.is_dir():
        raise PreparationError(f"dataset directory missing: {dataset_root}")
    case_ids = []
    for entry in dataset_root.iterdir():
        if entry.name in DATASET_EXCLUDED_PARTS:
            continue
        if entry.is_symlink():
            raise PreparationError(
                f"dataset {dataset_root} has a symlink entry: {entry.name}"
            )
        if entry.is_dir():
            case_ids.append(entry.name)
    case_ids = sorted(case_ids)
    if tuple(case_ids) != CASE_IDS:
        raise PreparationError(
            f"dataset {dataset_root} has case ids {case_ids}, expected {list(CASE_IDS)}"
        )
    files = _dataset_files(dataset_root)
    unscoped = sorted(
        rel for rel in files if rel.split("/", 1)[0] not in set(CASE_IDS)
    )
    if unscoped:
        raise PreparationError(
            f"dataset {dataset_root} has files outside a case directory: {unscoped}"
        )
    return {
        "case_ids": list(CASE_IDS),
        "content_sha256": _canonical_sha256(files),
        "files_sha256_count": len(files),
    }


def _dataset_copy_allowed(relative: str) -> bool:
    """True when a dataset-relative path may be copied into a prepared dataset."""
    parts = relative.split("/")
    if set(parts[:-1]) & DATASET_COPY_EXCLUDED_DIRS:
        return False
    return parts[-1] not in DATASET_COPY_EXCLUDED_NAMES


def stage_prepared_dataset(dataset_root: Path, target: Path) -> dict:
    """Byte-copy only the trusted case inputs into *target* and verify identity.

    Copies exactly the files covered by :func:`dataset_content_hash` (case
    metadata and seeds, never ``bootstrap/``, ``__pycache__``, ``.git`` or compiled
    artifacts) as real bytes — no symlinks — and then re-hashes the copy. The
    pinned runner enumerates every subdirectory of ``dataset.path`` as a case and
    has no config-level case allowlist, so the prepared copy is what makes the
    runtime select exactly the four trusted case IDs. Staging is always a copy:
    the trusted dataset is never written, and staging never mutates it.

    A source whose hashed inputs include harness-only fixtures
    (``environment/``, ``solution/``, ``task.toml``, ``instruction.md``) is
    refused rather than silently copying or dropping hashed content.
    """
    dataset_root = Path(dataset_root)
    identity = dataset_content_hash(dataset_root)
    files = _dataset_files(dataset_root)
    excluded = sorted(rel for rel in files if not _dataset_copy_allowed(rel))
    if excluded:
        raise PreparationError(
            "dataset case inputs include harness-only files a prepared copy "
            f"must not contain: {excluded}"
        )
    try:
        target.mkdir(parents=True, exist_ok=False)
        for relative, expected in files.items():
            data = (dataset_root / relative).read_bytes()
            if _sha256_bytes(data) != expected:
                raise PreparationError(f"dataset file changed while copying: {relative}")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        copied = dataset_content_hash(target)
    except OSError as exc:
        raise PreparationError(f"prepared dataset copy failed: {exc}") from exc
    if (
        copied["case_ids"] != identity["case_ids"]
        or copied["content_sha256"] != identity["content_sha256"]
    ):
        raise PreparationError(
            "prepared dataset copy does not match the trusted dataset identity"
        )
    return identity


# --- neutral config --------------------------------------------------------


def load_template(template: Path = TEMPLATE_PATH) -> dict:
    """Load the checked-in neutral reference config document."""
    template = Path(template)
    try:
        document = yaml.safe_load(template.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PreparationError(f"neutral template unreadable: {template}") from exc
    if not isinstance(document, dict):
        raise PreparationError(f"neutral template is not a mapping: {template}")
    return document


def arm_config_document(
    snapshot_dir: Path,
    dataset_root: Path = DATASET_ROOT,
    template: Path = TEMPLATE_PATH,
) -> dict:
    """Return the neutral config for one arm, with explicit absolute locations.

    The snapshot source locations (``dataset.workspace.files`` sources and the
    single snapshot source root in ``runner.plugin_dirs``) are the only per-arm
    values; ``dataset_root`` names the prepared four-case dataset copy that both
    arms share, so the pinned runner discovers exactly those case directories.
    Everything else — argv, ordered permissions, seed inputs, traces and the
    neutral judge — is the checked-in template unchanged.
    """
    document = copy.deepcopy(load_template(template))
    snapshot_dir = Path(snapshot_dir).resolve()
    dataset_dir = Path(dataset_root).resolve()

    workspace = (document.get("dataset") or {}).get("workspace") or {}
    files = workspace.get("files") or []
    rewritten = set()
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative = SNAPSHOT_SOURCES.get(entry.get("dest"))
        if relative is None:
            continue
        entry["source"] = str(snapshot_dir / relative)
        rewritten.add(entry["dest"])
    missing = set(SNAPSHOT_SOURCES) - rewritten
    if missing:
        raise PreparationError(
            f"neutral template lacks snapshot workspace files: {sorted(missing)}"
        )
    document["dataset"]["path"] = str(dataset_dir)

    runner = document.setdefault("runner", {})
    # The pinned materializer resolves `workspace.files` sources against the
    # project root plus `runner.plugin_dirs`. A prepared config lives outside the
    # project, so it declares exactly one source root: its own arm snapshot.
    runner["plugin_dirs"] = [str(snapshot_dir)]
    return document


def render_config(document: dict) -> str:
    """Render an arm config deterministically (stable for hashing)."""
    body = yaml.safe_dump(
        document,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    header = (
        "# GENERATED by agent_definition_eval.py (prepare) — do not edit.\n"
        "# Neutral agent-definition arm config: snapshot and dataset locations are\n"
        "# explicit absolute paths so this file resolves from any caller cwd.\n"
    )
    return header + body


def normalized_config_document(document: dict) -> dict:
    """Return the config with every arm-/location-specific value replaced."""
    clone = copy.deepcopy(document)
    dataset = clone.get("dataset") or {}
    dataset["path"] = NORMALIZED_DATASET
    for entry in (dataset.get("workspace") or {}).get("files") or []:
        if not isinstance(entry, dict):
            continue
        relative = SNAPSHOT_SOURCES.get(entry.get("dest"))
        if relative is not None:
            entry["source"] = f"{NORMALIZED_SOURCE_ROOTS}/{relative}"
    runner = clone.get("runner")
    if isinstance(runner, dict):
        # Normalized whether present or absent: a template without a declared
        # source root and an arm with one must hash identically.
        runner["plugin_dirs"] = NORMALIZED_SOURCE_ROOTS
    return clone


def nonarm_config_hash(document: dict) -> str:
    """SHA-256 of the config remainder that must match across prepared arms."""
    return _canonical_sha256(normalized_config_document(document))


# --- preparation -----------------------------------------------------------


def _refuse_nonempty(
    output_dir: Path, action: str = "preparation", error=PreparationError
) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise error(f"output path is not a directory: {output_dir}")
    if output_dir.is_dir() and any(output_dir.iterdir()):
        raise error(
            f"output directory is not empty: {output_dir} "
            f"({action} never overwrites a previous result)"
        )


def prepare_arms(
    baseline_source: Path,
    candidate_source: Path,
    output_dir: Path,
    *,
    dataset_root: Path = DATASET_ROOT,
    template: Path = TEMPLATE_PATH,
) -> dict:
    """Prepare two source-defined arms offline and write ``experiment.json``.

    Both sources are required; there is no implicit product candidate. The whole
    input set (both role source sets, the dataset and the template) is validated
    and hashed before anything is written, so a bad role or an ambiguous
    frontmatter model cannot leave a half-prepared experiment. A nonempty output
    directory is refused outright.

    Returns the ``experiment.json`` document (also written to
    ``<output_dir>/experiment.json``).
    """
    builder = _builder()
    baseline_source = Path(baseline_source).expanduser().resolve()
    candidate_source = Path(candidate_source).expanduser().resolve()
    output_dir = Path(output_dir).expanduser()
    sources = {"baseline": baseline_source, "candidate": candidate_source}
    if baseline_source == candidate_source:
        raise PreparationError(
            "baseline and candidate sources are the same directory; "
            "define two distinct agent-source sets"
        )

    # Validate + hash every input first: nothing is written before this passes.
    try:
        manifests = {arm: builder.build_manifest(source) for arm, source in sources.items()}
    except builder.SnapshotError as exc:
        raise PreparationError(str(exc)) from exc
    dataset = dataset_content_hash(Path(dataset_root))

    documents = {}
    prepared_dataset = output_dir / DATASET_PREPARED_SUBDIR
    for arm in ARMS:
        arm_snapshot_dir = output_dir / arm / SNAPSHOT_SUBDIR
        document = arm_config_document(arm_snapshot_dir, prepared_dataset, template)
        # Render before writing: a template problem must not publish a snapshot.
        documents[arm] = document

    nonarm = {arm: nonarm_config_hash(document) for arm, document in documents.items()}
    if nonarm["baseline"] != nonarm["candidate"]:
        raise PreparationError(
            "prepared arm configs differ outside the snapshot/dataset locations"
        )

    _refuse_nonempty(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Publish the four-case dataset copy before any snapshot: generated configs
    # point at it, and its identity must match the trusted dataset exactly.
    staged_dataset = output_dir / f".{DATASET_PREPARED_SUBDIR}.stage"
    try:
        staged_identity = stage_prepared_dataset(Path(dataset_root), staged_dataset)
        if staged_identity != dataset:
            raise PreparationError(
                "prepared dataset copy identity disagrees with the validated dataset"
            )
        staged_dataset.rename(prepared_dataset)
    except PreparationError:
        shutil.rmtree(staged_dataset, ignore_errors=True)
        raise

    arms: dict = {}
    for arm in ARMS:
        arm_dir = output_dir / arm
        snapshot_dir = arm_dir / SNAPSHOT_SUBDIR
        try:
            builder.build(dest=snapshot_dir, source=sources[arm])
            manifest = builder.verify_snapshot(snapshot_dir)
        except builder.SnapshotError as exc:  # pragma: no cover - validated above
            raise PreparationError(f"{arm} snapshot could not be published: {exc}") from exc
        if manifest != manifests[arm]:
            raise PreparationError(
                f"{arm} snapshot does not match its validated manifest"
            )
        config_text = render_config(documents[arm])
        config_path = arm_dir / CONFIG_FILENAME
        config_path.write_text(config_text, encoding="utf-8")
        arms[arm] = {
            "snapshot_id": manifest["snapshot_id"],
            "manifest": f"{arm}/{SNAPSHOT_SUBDIR}/{builder.MANIFEST_FILENAME}",
            "config": f"{arm}/{CONFIG_FILENAME}",
            "config_sha256": _sha256_bytes(config_text.encode("utf-8")),
            "nonarm_sha256": nonarm[arm],
        }

    template_document = load_template(template)
    experiment = {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "arms": arms,
        "dataset": {
            "path": DATASET_REL,
            "case_ids": dataset["case_ids"],
            "content_sha256": dataset["content_sha256"],
        },
        "nonarm_sha256": nonarm["baseline"],
        "pinned": {
            "harness_commit": HARNESS_COMMIT,
            "runtime": OPENCODE_RUNTIME,
            "model": MODEL,
            "runner_argv": list(
                ((template_document.get("runner") or {}).get("command")) or []
            ),
            "judge": {"module": JUDGE_MODULE, "function": JUDGE_FUNCTION},
            "snapshot_schema_version": builder.MANIFEST_SCHEMA_VERSION,
        },
    }
    (output_dir / EXPERIMENT_FILENAME).write_text(
        json.dumps(experiment, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return experiment


# --- saved-run comparison --------------------------------------------------


_NEUTRAL_CHECKS: ModuleType | None = None
_NATIVE: SimpleNamespace | None = None


def _neutral_checks() -> ModuleType:
    """Load the neutral end-state scorer by path (no cwd/sys.path fallback)."""
    global _NEUTRAL_CHECKS
    if _NEUTRAL_CHECKS is None:
        spec = importlib.util.spec_from_file_location(
            "agent_definition_neutral_checks", PROJECT / "agent_workflow_checks.py"
        )
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise ComparisonError(f"cannot load neutral scorer in {PROJECT}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _NEUTRAL_CHECKS = module
    return _NEUTRAL_CHECKS


def _native_loader() -> SimpleNamespace:
    """Import the pinned harness record loader (never a second loader)."""
    global _NATIVE
    if _NATIVE is None:
        harness = Path(os.environ.get("AGENT_WORKFLOWS_HARNESS", str(DEFAULT_HARNESS)))
        scripts = harness / "skills" / "eval-run" / "scripts"
        if not (harness / "agent_eval" / "config.py").is_file():
            raise ComparisonError(
                f"pinned harness not available at {harness} "
                "(set AGENT_WORKFLOWS_HARNESS to the pinned checkout)"
            )
        for path in (str(harness), str(scripts)):
            if path not in sys.path:
                sys.path.insert(0, path)
        from agent_eval.config import EvalConfig
        from score import load_case_record

        _NATIVE = SimpleNamespace(EvalConfig=EvalConfig, load_record=load_case_record)
    return _NATIVE


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _require_json_object(path: Path, label: str, error=ComparisonError) -> dict:
    path = Path(path)
    if not path.is_file():
        raise error(f"{label} missing: {path.name}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error(f"{label} is not readable JSON: {path.name} ({exc})") from exc
    if not isinstance(document, dict):
        raise error(f"{label} is not a JSON object: {path.name}")
    return document


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _safe_relative(base: Path, relative, label: str) -> Path:
    """Resolve an experiment-relative file, refusing escapes and symlink drift."""
    if not isinstance(relative, str) or not relative.strip():
        raise ComparisonError(f"{label} path is missing in experiment.json")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ComparisonError(f"{label} path escapes the experiment directory: {relative}")
    base_resolved = Path(base).resolve()
    resolved = (base_resolved / candidate).resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ComparisonError(f"{label} path escapes the experiment directory: {relative}")
    if not resolved.is_file():
        raise ComparisonError(f"{label} file missing in prepared experiment: {relative}")
    return resolved


def _resolved_config_path(value, label: str, arm: str) -> Path:
    """Resolve an absolute staged-config path; a relative one is not trusted."""
    if not isinstance(value, str) or not value.strip():
        raise ComparisonError(f"{arm} config {label} is missing")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise ComparisonError(
            f"{arm} config {label} must be an absolute prepared path: {value}"
        )
    return candidate.resolve()


def _validate_arm_config_locations(
    config_document: dict, arm: str, snapshot_dir: Path, dataset_dir: Path
) -> None:
    """Require every absolute staging location to name this arm's prepared bytes.

    A moved or copied experiment keeps the absolute paths it was prepared with,
    pointing at the *old* location. Re-hashing alone cannot catch that (the old
    bytes still match), so the staged locations are checked against the experiment
    directory that is being loaded. Relocation is not supported: prepare the arms
    in their final directory and fail closed here instead of silently using data
    from another location.
    """
    dataset = config_document.get("dataset")
    if not isinstance(dataset, dict):
        raise ComparisonError(f"{arm} prepared config has no dataset section")
    observed_dataset = _resolved_config_path(dataset.get("path"), "dataset.path", arm)
    if observed_dataset != dataset_dir:
        raise ComparisonError(
            f"{arm} config dataset.path does not resolve to this experiment's "
            f"prepared dataset ({observed_dataset})"
        )
    workspace = dataset.get("workspace")
    sources: dict = {}
    if isinstance(workspace, dict):
        for entry in workspace.get("files") or []:
            if isinstance(entry, dict) and entry.get("dest") in SNAPSHOT_SOURCES:
                sources[entry["dest"]] = entry.get("source")
    for dest, relative in SNAPSHOT_SOURCES.items():
        if dest not in sources:
            raise ComparisonError(
                f"{arm} config has no snapshot staging source for {dest}"
            )
        observed_source = _resolved_config_path(
            sources[dest], f"{dest} staging source", arm
        )
        if observed_source != (snapshot_dir / relative).resolve():
            raise ComparisonError(
                f"{arm} config {dest} staging source does not name this arm's snapshot"
            )
    runner = config_document.get("runner")
    plugin_dirs = runner.get("plugin_dirs") if isinstance(runner, dict) else None
    if (
        not isinstance(plugin_dirs, list)
        or len(plugin_dirs) != 1
        or _resolved_config_path(plugin_dirs[0], "runner.plugin_dirs", arm)
        != snapshot_dir
    ):
        raise ComparisonError(
            f"{arm} config runner.plugin_dirs must be exactly this arm's snapshot"
        )


def _measured_number(value, kind: str):
    """Accept only a real measured number; reject bool/nonfinite/negative/wrong type."""
    if isinstance(value, bool) or value is None:
        return None
    if kind == "integer":
        if not isinstance(value, int):
            return None
        return value if value >= 0 else None
    if not isinstance(value, (int, float)):
        return None
    number = value
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _reported_count(value):
    """One nonnegative safe integer count, or ``None`` when it is not usable."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > MAX_SAFE_INTEGER:
        return None
    return value


def _token_total(value):
    """Normalize reported token usage to ``(derivation, total)`` or ``(None, None)``.

    The pinned runner reports usage as ``{"input": N, "output": N}``; that total
    is derived only when BOTH components are nonnegative safe integer counts.
    An absent, partial, bool, negative, non-integer or out-of-range component
    leaves the total unknown rather than inventing a number. A plain reported
    scalar is retained for compatibility and labelled as a scalar total, never
    reinterpreted as a component and never split into fabricated parts.
    """
    if isinstance(value, bool) or value is None:
        return None, None
    if isinstance(value, dict):
        components = [_reported_count(value.get(name)) for name in ("input", "output")]
        if any(component is None for component in components):
            return None, None
        total = components[0] + components[1]
        if total > MAX_SAFE_INTEGER:
            return None, None
        return TOKEN_TOTAL_MAPPING, total
    scalar = _reported_count(value)
    if scalar is None:
        return None, None
    return TOKEN_TOTAL_SCALAR, scalar


def _measured_exit_code(value):
    """A signed integer process status; bools/floats/strings are not statuses.

    Exit codes are not measurements: any nonzero value (including the pinned
    harness's timeout/spawn ``-1``) is a failed process, so negatives are kept.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def load_experiment(path: Path) -> dict:
    """Load and verify a prepared experiment plus its prepared arm artifacts.

    Structural problems here are tool errors: without a trustworthy experiment we
    cannot state what the runs were supposed to be. (Saved-run provenance problems
    are different — they downgrade the comparison state instead.)
    """
    experiment_path = Path(path).expanduser()
    if experiment_path.is_dir():
        experiment_path = experiment_path / EXPERIMENT_FILENAME
    if not experiment_path.is_file():
        raise ComparisonError(f"experiment file missing: {experiment_path}")
    base = experiment_path.resolve().parent
    document = _require_json_object(experiment_path, "experiment.json")
    if document.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
        raise ComparisonError(
            f"unsupported experiment schema_version: {document.get('schema_version')!r}"
        )
    arms_document = document.get("arms")
    if not isinstance(arms_document, dict) or set(arms_document) != set(ARMS):
        raise ComparisonError("experiment.json must describe exactly baseline and candidate")
    dataset = document.get("dataset")
    if not isinstance(dataset, dict):
        raise ComparisonError("experiment.json has no dataset identity")
    case_ids = dataset.get("case_ids")
    if not isinstance(case_ids, list) or tuple(sorted(case_ids)) != CASE_IDS:
        raise ComparisonError(
            f"experiment.json case ids are not the fixed suite: {case_ids!r}"
        )
    dataset_sha256 = dataset.get("content_sha256")
    if not _is_sha256(dataset_sha256):
        raise ComparisonError("experiment.json dataset content hash is not a SHA-256")
    pinned = document.get("pinned")
    if not isinstance(pinned, dict) or not isinstance(pinned.get("model"), str):
        raise ComparisonError("experiment.json has no pinned model identity")
    nonarm = document.get("nonarm_sha256")
    if not _is_sha256(nonarm):
        raise ComparisonError("experiment.json non-arm hash is not a SHA-256")

    # Re-hash both datasets before anything is scored: the prepared copy a run
    # actually read and the trusted in-project originals its judge reconstructs.
    # Either one drifting from the recorded identity means the saved comparison
    # would not describe the recorded experiment, so it is a tool error.
    prepared_dataset_dir = (base / DATASET_PREPARED_SUBDIR).resolve()
    try:
        prepared_dataset = dataset_content_hash(prepared_dataset_dir)
        trusted_dataset = dataset_content_hash(DATASET_ROOT)
    except PreparationError as exc:
        raise ComparisonError(f"dataset identity cannot be verified: {exc}") from exc
    for label, identity in (
        ("prepared", prepared_dataset),
        ("trusted", trusted_dataset),
    ):
        if identity["case_ids"] != sorted(case_ids):
            raise ComparisonError(
                f"{label} dataset case ids {identity['case_ids']} do not match "
                f"experiment.json {sorted(case_ids)}"
            )
        if identity["content_sha256"] != dataset_sha256:
            raise ComparisonError(
                f"{label} dataset content does not match experiment.json "
                f"(recorded {dataset_sha256}, observed {identity['content_sha256']})"
            )

    builder = _builder()
    prepared_arms: dict = {}
    for arm in ARMS:
        entry = arms_document.get(arm)
        if not isinstance(entry, dict):
            raise ComparisonError(f"experiment arm {arm} is not an object")
        snapshot_id = entry.get("snapshot_id")
        if not _is_sha256(snapshot_id):
            raise ComparisonError(f"experiment arm {arm} snapshot id is not a SHA-256")
        config_sha256 = entry.get("config_sha256")
        if not _is_sha256(config_sha256):
            raise ComparisonError(f"experiment arm {arm} config hash is not a SHA-256")
        arm_nonarm = entry.get("nonarm_sha256")
        if arm_nonarm != nonarm:
            raise ComparisonError(f"experiment arm {arm} non-arm hash disagrees")
        config_path = _safe_relative(base, entry.get("config"), f"{arm} config")
        try:
            config_text = config_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ComparisonError(f"{arm} prepared config is unreadable: {exc}") from exc
        if _sha256_bytes(config_text.encode("utf-8")) != config_sha256:
            raise ComparisonError(f"{arm} prepared config bytes do not match its hash")
        try:
            config_document = yaml.safe_load(config_text)
        except yaml.YAMLError as exc:
            raise ComparisonError(f"{arm} prepared config is not valid YAML: {exc}") from exc
        if not isinstance(config_document, dict):
            raise ComparisonError(f"{arm} prepared config is not a mapping")
        if nonarm_config_hash(config_document) != arm_nonarm:
            raise ComparisonError(f"{arm} prepared config does not match its non-arm hash")
        snapshot_dir = (base / arm / SNAPSHOT_SUBDIR).resolve()
        _validate_arm_config_locations(
            config_document, arm, snapshot_dir, prepared_dataset_dir
        )
        manifest_path = _safe_relative(base, entry.get("manifest"), f"{arm} manifest")
        try:
            manifest = builder.verify_snapshot(manifest_path.parent)
        except builder.SnapshotError as exc:
            raise ComparisonError(f"{arm} prepared snapshot is unusable: {exc}") from exc
        if manifest.get("snapshot_id") != snapshot_id:
            raise ComparisonError(f"{arm} prepared snapshot id disagrees with experiment.json")
        files_sha256 = manifest.get("files_sha256")
        if not isinstance(files_sha256, dict) or not files_sha256:
            raise ComparisonError(f"{arm} prepared snapshot has no generated file hashes")
        prepared_arms[arm] = {
            "snapshot_id": snapshot_id,
            "config_path": config_path,
            "config_sha256": config_sha256,
            "config_document": config_document,
            "nonarm_sha256": arm_nonarm,
            "manifest_path": manifest_path,
            "manifest_document": manifest,
            "files_sha256": dict(files_sha256),
        }

    return {
        "path": experiment_path.resolve(),
        "file": experiment_path.name,
        "sha256": _sha256_file(experiment_path),
        "document": document,
        "case_ids": tuple(case_ids),
        "dataset_sha256": dataset_sha256,
        "nonarm_sha256": nonarm,
        "model": pinned["model"],
        "pinned": pinned,
        "arms": prepared_arms,
    }


def _load_run(run_path: Path) -> dict:
    """Load the required saved-run artifacts; never fall back to whole-run totals."""
    run_dir = Path(run_path).expanduser()
    if not run_dir.is_dir():
        raise ComparisonError(f"run directory missing: {run_dir}")
    result_path = run_dir / HARNESS_SUBDIR / RUN_RESULT_FILENAME
    if not result_path.is_file():
        raise ComparisonError(
            f"run {run_dir.name} has no {HARNESS_SUBDIR}/{RUN_RESULT_FILENAME}; "
            "cannot read per-case status"
        )
    result = _require_json_object(result_path, f"{run_dir.name} {HARNESS_SUBDIR}/{RUN_RESULT_FILENAME}")
    per_case_document = result.get("per_case")
    if per_case_document is None:
        per_case: dict = {}
    elif isinstance(per_case_document, dict):
        per_case = per_case_document
    else:
        raise ComparisonError(f"run {run_dir.name} per_case is not an object")
    collected: dict[str, Path] = {}
    cases_dir = run_dir / COLLECTED_SUBDIR / COLLECTED_CASES_SUBDIR
    if cases_dir.is_dir():
        for entry in sorted(cases_dir.iterdir()):
            if entry.is_dir() and not entry.is_symlink():
                collected[entry.name] = entry
    model = result.get("model")
    return {
        "dir": run_dir,
        "name": run_dir.name,
        "result_path": result_path,
        "result": result,
        "result_sha256": _sha256_file(result_path),
        "per_case": per_case,
        "collected": collected,
        "model": model if isinstance(model, str) else None,
    }


def _load_run_provenance(run: dict, prepared: dict, arm: str) -> dict:
    """Verify the saved arm linkage against the prepared experiment.

    Missing linkage is ``unverified``; present-but-different linkage is
    ``incomparable``. Nothing here is guessed from timestamps, run names or the
    prepared experiment alone — an old run never gains retroactive provenance.
    """
    builder = _builder()
    prov_dir = run["dir"] / PROVENANCE_SUBDIR
    files = {
        "run": prov_dir / PROVENANCE_RUN_FILENAME,
        "manifest": prov_dir / builder.MANIFEST_FILENAME,
        "config": prov_dir / CONFIG_FILENAME,
    }
    missing = [
        f"{PROVENANCE_SUBDIR}/{path.name}" for path in files.values() if not path.is_file()
    ]
    result = {
        "status": STATE_UNVERIFIED,
        "reasons": ["missing_run_provenance"] + missing,
        "arm": None,
        "snapshot_id": None,
        "config_sha256": None,
        "nonarm_sha256": None,
        "dataset_content_sha256": None,
        "case_ids": None,
        "model": None,
        "run_model": None,
        "files_sha256": None,
        "artifacts": [],
    }

    # The harness run record carries the harness-recorded/configured model
    # identity, not runtime attestation of which model served a request. The saved
    # run.json `model` value is only the experiment's self-assertion and can never
    # override it: a harness-recorded mismatch is incomparable even when the
    # provenance claims the pinned model, and an absent record is unverified.
    actual_model = run.get("model")
    if not isinstance(actual_model, str) or not actual_model.strip():
        actual_model = None
    result["run_model"] = actual_model
    model_reasons: list[str] = []
    if actual_model is None:
        model_reasons.append("run_model_missing")
    elif actual_model != prepared["model"]:
        model_reasons.append("run_model_mismatch")
        result["status"] = STATE_INCOMPARABLE

    if missing:
        result["reasons"] = ["missing_run_provenance"] + missing + model_reasons
        return result

    try:
        run_document = json.loads(files["run"].read_text(encoding="utf-8"))
        manifest_document = json.loads(files["manifest"].read_text(encoding="utf-8"))
        config_text = files["config"].read_text(encoding="utf-8")
        config_document = yaml.safe_load(config_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError):
        result["reasons"] = ["malformed_run_provenance"] + model_reasons
        return result
    if not isinstance(run_document, dict) or not isinstance(manifest_document, dict):
        result["reasons"] = ["malformed_run_provenance"] + model_reasons
        return result
    if not isinstance(config_document, dict):
        result["reasons"] = ["malformed_run_provenance"] + model_reasons
        return result
    # Validate the saved manifest as a whole, not only the two fields this
    # comparison happens to read: a partial manifest is not saved provenance.
    if builder.validate_manifest(manifest_document):
        result["reasons"] = ["malformed_run_provenance"] + model_reasons
        return result

    def _field(name, validator, description):
        value = run_document.get(name)
        if not validator(value):
            raise ValueError(f"{name} must be {description}")
        return value

    try:
        if run_document.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        recorded_arm = _field("arm", lambda v: v in ARMS, "baseline or candidate")
        snapshot_id = _field("snapshot_id", _is_sha256, "a SHA-256")
        config_sha256 = _field("config_sha256", _is_sha256, "a SHA-256")
        nonarm_sha256 = _field("nonarm_sha256", _is_sha256, "a SHA-256")
        dataset_sha256 = _field(
            "dataset_content_sha256", _is_sha256, "a SHA-256"
        )
        recorded_cases = _field(
            "case_ids",
            lambda v: isinstance(v, list) and all(isinstance(item, str) for item in v),
            "a list of case ids",
        )
        recorded_model = _field("model", lambda v: isinstance(v, str), "a string")
    except ValueError:
        result["reasons"] = ["malformed_run_provenance"] + model_reasons
        return result

    result.update(
        {
            "arm": recorded_arm,
            "snapshot_id": snapshot_id,
            "config_sha256": config_sha256,
            "nonarm_sha256": nonarm_sha256,
            "dataset_content_sha256": dataset_sha256,
            "case_ids": list(recorded_cases),
            "model": recorded_model,
            "files_sha256": manifest_document.get("files_sha256"),
            "artifacts": [
                {"name": f"{PROVENANCE_SUBDIR}/{path.name}", "sha256": _sha256_file(path)}
                for path in files.values()
            ],
        }
    )

    expected = prepared["arms"][arm]
    mismatches: list[str] = []
    if recorded_arm != arm:
        mismatches.append("arm_mismatch")
    if _sha256_bytes(config_text.encode("utf-8")) != config_sha256:
        mismatches.append("saved_config_bytes_do_not_match_run_json")
    if config_sha256 != expected["config_sha256"]:
        mismatches.append("config_not_prepared")
    if nonarm_config_hash(config_document) != nonarm_sha256:
        mismatches.append("saved_config_nonarm_hash_mismatch")
    if nonarm_sha256 != expected["nonarm_sha256"]:
        mismatches.append("nonarm_config_mismatch")
    if manifest_document.get("snapshot_id") != snapshot_id:
        mismatches.append("saved_manifest_not_run_json")
    if snapshot_id != expected["snapshot_id"]:
        mismatches.append("snapshot_not_prepared")
    # Exact prepared bytes, not a subset: a well-formed saved manifest that is not
    # byte-for-byte this arm's prepared manifest is not that arm's provenance.
    if manifest_document != expected["manifest_document"]:
        mismatches.append("saved_manifest_not_prepared")
    if manifest_document.get("files_sha256") != expected["files_sha256"]:
        mismatches.append("snapshot_content_mismatch")
    if dataset_sha256 != prepared["dataset_sha256"]:
        mismatches.append("dataset_mismatch")
    if sorted(recorded_cases) != sorted(prepared["case_ids"]):
        mismatches.append("case_set_mismatch")
    if recorded_model != prepared["model"]:
        mismatches.append("model_mismatch")
    if mismatches or "run_model_mismatch" in model_reasons:
        result["status"] = STATE_INCOMPARABLE
        result["reasons"] = mismatches + model_reasons
    elif model_reasons:
        result["status"] = STATE_UNVERIFIED
        result["reasons"] = model_reasons
    else:
        result["status"] = STATE_VERIFIED_COMPARABLE
        result["reasons"] = []
    return result


def _sanitize_diagnostics(value):
    """Normalize absolute paths so reports are reproducible across temp roots."""
    if isinstance(value, str):
        if os.path.isabs(value):
            name = Path(value).name
            return f"<path>/{name}" if name else "<path>"
        return value
    if isinstance(value, dict):
        return {key: _sanitize_diagnostics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_diagnostics(item) for item in value]
    return value


def _metric(metric_name: str, candidates: list[tuple[str, str, object]]) -> dict:
    """One measured metric with explicit availability/source, never a silent merge.

    ``candidates`` are ``(kind, locator, raw_value)``. ``kind`` groups
    measurement methods for cross-case totals; ``locator`` names the exact saved
    artifact a value came from.
    """
    measured: list[tuple[str, str, object]] = []
    notes: list[str] = []
    kind_of = METRIC_KINDS[metric_name]
    for kind, locator, raw in candidates:
        if raw is None:
            continue
        if metric_name == "token_usage":
            # Normalize every usage source to one labelled token total. The label
            # is the normalized unit, not the artifact: two agreeing sources do
            # not split the comparability group, while a runner mapping total and
            # a reported scalar stay distinct and are never paired.
            derivation, value = _token_total(raw)
            if derivation is not None:
                kind = f"token_total:{derivation}"
        else:
            value = _measured_number(raw, kind_of)
        if value is None:
            notes.append(f"invalid_{metric_name}@{locator}")
            continue
        measured.append((kind, locator, value))
    if not measured:
        return {
            "value": None,
            "availability": "unknown",
            "source": None,
            "kind": None,
            "sources": [],
            "notes": notes,
        }
    values = {entry[2] for entry in measured}
    sources = [entry[1] for entry in measured]
    kinds = sorted({entry[0] for entry in measured})
    if len(values) > 1:
        return {
            "value": None,
            "availability": "conflicting",
            "source": None,
            "kind": None,
            "sources": sources,
            "notes": notes + [f"conflicting_{metric_name}_sources"],
        }
    return {
        "value": measured[0][2],
        "availability": "measured",
        "source": sources[0],
        "kind": kinds[0],
        "sources": sources,
        "notes": notes,
    }


def _case_metrics(case_id: str, run: dict, record: dict | None) -> dict:
    """Per-case elapsed/usage from authentic per-case artifacts only."""
    entry = run["per_case"].get(case_id)
    fields = entry if isinstance(entry, dict) else {}
    elapsed = _metric(
        "elapsed_seconds",
        [
            (
                "harness_run_result",
                f"{HARNESS_SUBDIR}/{RUN_RESULT_FILENAME}#per_case.{case_id}.duration_s",
                fields.get("duration_s"),
            )
        ],
    )
    collected = _neutral_checks().collect_metrics(record) if record is not None else {}
    metrics = {"elapsed_seconds": elapsed}
    for metric_name in ("token_usage", "cost_usd", "num_turns"):
        candidates = [
            (
                "harness_run_result",
                f"{HARNESS_SUBDIR}/{RUN_RESULT_FILENAME}#per_case.{case_id}.{metric_name}",
                fields.get(metric_name),
            )
        ]
        if record is not None:
            candidates.append(
                (
                    "collected_metrics",
                    f"{COLLECTED_SUBDIR}/{COLLECTED_CASES_SUBDIR}/{case_id}/output/metrics.json",
                    collected.get(metric_name),
                )
            )
        metrics[metric_name] = _metric(metric_name, candidates)
    return metrics


def _score_saved_case(prepared: dict, arm: str, run: dict, case_id: str, case_dir: Path) -> dict:
    """Load a saved collected record with the pinned loader and score the end state."""
    native = _native_loader()
    try:
        config = native.EvalConfig.from_yaml(str(prepared["arms"][arm]["config_path"]))
        record = native.load_record(
            case_dir, config, run_id=HARNESS_SUBDIR, runs_dir=run["dir"]
        )
    except Exception as exc:  # noqa: BLE001 - an unusable artifact is not a verdict
        return {
            "status": "unscorable",
            "reasons": [f"record_unavailable:{type(exc).__name__}"],
            "facts": None,
            "record": None,
        }
    outcome = _neutral_checks().score_record(outputs=record)
    return {
        "status": outcome.get("status", "unscorable"),
        "reasons": _sanitize_diagnostics(list(outcome.get("reasons") or [])),
        "facts": _sanitize_diagnostics(outcome.get("facts")),
        "record": record,
    }


def _execution_status(exit_code, outcome: str | None) -> str:
    """``completed`` means exit 0 AND a passing end state; never inferred.

    ``exit_code`` is a validated signed integer process status: any nonzero value
    (including a negative spawn/timeout status) is a failed process. A missing or
    malformed status is unknown, and a passing end state alone never completes it.
    """
    if exit_code is None:
        return "unknown"
    if exit_code != 0:
        return "failed"
    if outcome == "pass":
        return "completed"
    if outcome == "fail":
        return "failed"
    return "unknown"


def _case_report(prepared: dict, arm: str, run: dict, case_id: str) -> dict:
    case_dir = run["collected"].get(case_id)
    score = (
        _score_saved_case(prepared, arm, run, case_id, case_dir)
        if case_dir is not None
        else None
    )
    entry = run["per_case"].get(case_id)
    fields = entry if isinstance(entry, dict) else {}
    exit_code = _measured_exit_code(fields.get("exit_code"))
    if score is None:
        outcome = None
        reasons = ["missing_collected_case"]
        facts = None
        record = None
    else:
        outcome = score["status"]
        reasons = score["reasons"]
        facts = score["facts"]
        record = score["record"]
    return {
        "case_id": case_id,
        "present": score is not None,
        "outcome": outcome,
        "execution": _execution_status(exit_code, outcome),
        "exit_code": exit_code,
        "reasons": reasons,
        "facts": facts,
        "metrics": _case_metrics(case_id, run, record),
        "evidence": {
            "collected_case_dir": (
                f"{COLLECTED_SUBDIR}/{COLLECTED_CASES_SUBDIR}/{case_id}"
                if score is not None
                else None
            ),
            "run_result": f"{HARNESS_SUBDIR}/{RUN_RESULT_FILENAME}",
        },
    }


def _coverage(run: dict, expected_ids: tuple[str, ...]) -> dict:
    observed = run["collected"]
    missing = [case_id for case_id in expected_ids if case_id not in observed]
    extra = sorted(set(observed) - set(expected_ids))
    return {
        "observed_case_count": len(expected_ids) - len(missing),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
    }


def _totals(cases: list[dict], expected_ids: tuple[str, ...]) -> dict:
    """Full-set totals: measured only when EVERY expected case has one source."""
    totals = {}
    for metric_name in METRIC_KINDS:
        measured = [
            (case["metrics"][metric_name]["kind"], case["metrics"][metric_name]["value"])
            for case in cases
            if case["metrics"][metric_name]["availability"] == "measured"
        ]
        kinds = sorted({kind for kind, _ in measured if kind})
        if len(measured) == len(expected_ids) and len(kinds) == 1:
            totals[metric_name] = {
                "value": sum(value for _, value in measured),
                "availability": "measured",
                "source": kinds[0],
                "sources": kinds,
                "measured_case_count": len(measured),
                "expected_case_count": len(expected_ids),
            }
        else:
            totals[metric_name] = {
                "value": None,
                "availability": "incomplete" if measured else "unknown",
                "source": None,
                "sources": kinds,
                "measured_case_count": len(measured),
                "expected_case_count": len(expected_ids),
            }
    return totals


def _per_completed(cases: list[dict]) -> dict:
    """Per-completed means; zero completions (or partial data) stay unknown."""
    completed = [case for case in cases if case["execution"] == "completed"]
    result = {}
    for metric_name in METRIC_KINDS:
        measured = [
            (case["metrics"][metric_name]["kind"], case["metrics"][metric_name]["value"])
            for case in completed
            if case["metrics"][metric_name]["availability"] == "measured"
        ]
        kinds = sorted({kind for kind, _ in measured if kind})
        if not completed:
            result[metric_name] = {
                "value": None,
                "availability": "unknown",
                "reason": "no_completed_cases",
                "completed_case_count": 0,
                "measured_case_count": 0,
            }
        elif len(measured) == len(completed) and len(kinds) == 1:
            result[metric_name] = {
                "value": sum(value for _, value in measured) / len(measured),
                "availability": "measured",
                "source": kinds[0],
                "sources": kinds,
                "completed_case_count": len(completed),
                "measured_case_count": len(measured),
            }
        else:
            result[metric_name] = {
                "value": None,
                "availability": "incomplete",
                "source": None,
                "sources": kinds,
                "completed_case_count": len(completed),
                "measured_case_count": len(measured),
            }
    return result


def _aggregate(cases: list[dict], expected_ids: tuple[str, ...]) -> dict:
    outcomes = {"pass": 0, "fail": 0, "unscorable": 0, "missing": 0}
    executions = {"completed": 0, "failed": 0, "unknown": 0}
    for case in cases:
        if case["outcome"] is None:
            outcomes["missing"] += 1
        else:
            outcomes[case["outcome"]] = outcomes.get(case["outcome"], 0) + 1
        executions[case["execution"]] = executions.get(case["execution"], 0) + 1
    return {
        "expected_case_count": len(expected_ids),
        "observed_case_count": sum(1 for case in cases if case["present"]),
        "outcomes": outcomes,
        "executions": executions,
        "totals": _totals(cases, expected_ids),
        "per_completed_mean": _per_completed(cases),
    }


def _pairs(case_rows: list[dict], expected_ids: tuple[str, ...]) -> dict:
    """Paired deltas for comparable completed pairs with both values measured."""
    per_metric: dict[str, list] = {name: [] for name in METRIC_KINDS}
    completed_pairs = 0
    rows = []
    for row in case_rows:
        baseline = row["baseline"]
        candidate = row["candidate"]
        completed = (
            baseline["execution"] == "completed"
            and candidate["execution"] == "completed"
        )
        if completed:
            completed_pairs += 1
        deltas = {}
        for metric_name in METRIC_KINDS:
            before = baseline["metrics"][metric_name]
            after = candidate["metrics"][metric_name]
            delta = None
            if (
                completed
                and before["availability"] == "measured"
                and after["availability"] == "measured"
                and before["kind"] is not None
                and before["kind"] == after["kind"]
            ):
                delta = after["value"] - before["value"]
                per_metric[metric_name].append(
                    {
                        "case_id": row["case_id"],
                        "delta": delta,
                        "source": before["source"],
                    }
                )
            deltas[metric_name] = delta
        rows.append(
            {
                "case_id": row["case_id"],
                "completed_pair": completed,
                "deltas": deltas,
            }
        )

    metrics = {}
    for metric_name, measured in per_metric.items():
        full = len(measured) == len(expected_ids)
        metrics[metric_name] = {
            "delta": sum(entry["delta"] for entry in measured) if full else None,
            "availability": "measured" if full else ("measured_subset" if measured else "unknown"),
            "source": measured[0]["source"] if full else None,
            "measured_pair_count": len(measured),
            "expected_pair_count": len(expected_ids),
            "cases": measured,
        }
    return {
        "expected_pair_count": len(expected_ids),
        "completed_pair_count": completed_pairs,
        "cases": rows,
        "metrics": metrics,
    }


def _suppress_pairs(pairs: dict, state: str) -> None:
    """Non-comparable states expose counts but no deltas (no accidental ranking)."""
    pairs["suppressed_by_state"] = state
    for row in pairs["cases"]:
        row["deltas"] = {name: None for name in METRIC_KINDS}
    for metric_name, entry in pairs["metrics"].items():
        entry["delta"] = None
        entry["availability"] = "suppressed"
        entry["source"] = None
        entry["cases"] = [
            {"case_id": row["case_id"], "delta": None, "source": None}
            for row in entry["cases"]
        ]


def _procedure() -> dict:
    """Procedural counters this runner cannot measure: always null."""
    document = {"status": "not_measured"}
    for field in PROCEDURE_FIELDS:
        document[field] = None
    return document


def _run_inputs(run: dict, provenance: dict) -> dict:
    artifacts = [
        {
            "name": f"{HARNESS_SUBDIR}/{RUN_RESULT_FILENAME}",
            "sha256": run["result_sha256"],
        }
    ] + list(provenance["artifacts"])
    present = {artifact["name"] for artifact in artifacts}
    missing = [
        f"{PROVENANCE_SUBDIR}/{PROVENANCE_RUN_FILENAME}",
        f"{PROVENANCE_SUBDIR}/{_builder().MANIFEST_FILENAME}",
        f"{PROVENANCE_SUBDIR}/{CONFIG_FILENAME}",
    ]
    return {
        "directory": run["name"],
        "model": run["model"],
        "artifacts": artifacts,
        "missing_artifacts": [name for name in missing if name not in present],
    }


def _state(prepared: dict, provenance: dict, coverage: dict) -> tuple[str, list[str]]:
    """Eligibility precedence: incomparable > unverified > same-content > comparable."""
    statuses = {arm: provenance[arm]["status"] for arm in ARMS}
    if any(status == STATE_INCOMPARABLE for status in statuses.values()):
        reasons = [
            f"{arm}:{reason}"
            for arm in ARMS
            if statuses[arm] == STATE_INCOMPARABLE
            for reason in provenance[arm]["reasons"]
        ]
        return STATE_INCOMPARABLE, reasons
    if any(status == STATE_UNVERIFIED for status in statuses.values()):
        reasons = [
            f"{arm}:{reason}"
            for arm in ARMS
            if statuses[arm] == STATE_UNVERIFIED
            for reason in provenance[arm]["reasons"]
        ]
        return STATE_UNVERIFIED, reasons
    baseline_files = prepared["arms"]["baseline"]["files_sha256"]
    candidate_files = prepared["arms"]["candidate"]["files_sha256"]
    if baseline_files == candidate_files or (
        prepared["arms"]["baseline"]["snapshot_id"]
        == prepared["arms"]["candidate"]["snapshot_id"]
    ):
        return STATE_SAME_CONTENT, ["identical_generated_snapshot_files"]
    reasons = []
    for arm in ARMS:
        if coverage[arm]["missing_case_ids"]:
            reasons.append(f"{arm}:missing_cases")
        if coverage[arm]["extra_case_ids"]:
            reasons.append(f"{arm}:extra_cases")
    return STATE_VERIFIED_COMPARABLE, reasons


def compare_runs(experiment: Path, baseline_run: Path, candidate_run: Path) -> dict:
    """Compare two saved runs against one prepared experiment. Pure, offline.

    Reads only existing artifacts (harness result, collected case dirs and the
    saved provenance copies). No model, subprocess, network or transport call; no
    write to either input run directory; no home-cwd fallback.
    """
    prepared = load_experiment(experiment)
    runs = {
        "baseline": _load_run(Path(baseline_run)),
        "candidate": _load_run(Path(candidate_run)),
    }
    provenance = {
        arm: _load_run_provenance(runs[arm], prepared, arm) for arm in ARMS
    }
    expected_ids = prepared["case_ids"]
    coverage = {arm: _coverage(runs[arm], expected_ids) for arm in ARMS}
    case_reports = {
        arm: [_case_report(prepared, arm, runs[arm], case_id) for case_id in expected_ids]
        for arm in ARMS
    }
    case_rows = [
        {
            "case_id": case_id,
            "baseline": case_reports["baseline"][index],
            "candidate": case_reports["candidate"][index],
        }
        for index, case_id in enumerate(expected_ids)
    ]
    aggregates = {
        arm: _aggregate(case_reports[arm], expected_ids) for arm in ARMS
    }
    pairs = _pairs(case_rows, expected_ids)
    state, state_reasons = _state(prepared, provenance, coverage)

    claim_blockers: list[str] = []
    if state != STATE_VERIFIED_COMPARABLE:
        claim_blockers.append(state)
    for arm in ARMS:
        if coverage[arm]["missing_case_ids"]:
            claim_blockers.append(f"{arm}:incomplete_case_coverage")
        if coverage[arm]["extra_case_ids"]:
            claim_blockers.append(f"{arm}:extra_case_coverage")
        executions = aggregates[arm]["executions"]
        if executions.get("failed") or executions.get("unknown"):
            claim_blockers.append(f"{arm}:failed_or_unknown_execution")
    if state != STATE_VERIFIED_COMPARABLE:
        _suppress_pairs(pairs, state)

    report = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "kind": "agent-definition-saved-run-comparison",
        "state": state,
        "state_reasons": state_reasons,
        "efficacy": {
            "claim": None,
            "ranking": None,
            "note": (
                "No efficacy or ranking is computed. Paired deltas, when shown, "
                "describe measured saved artifacts only; they are not evidence of "
                "candidate improvement."
            ),
        },
        "claim_blockers": claim_blockers,
        "experiment": {
            "file": prepared["file"],
            "sha256": prepared["sha256"],
            "dataset": {
                "case_ids": list(expected_ids),
                "content_sha256": prepared["dataset_sha256"],
            },
            "nonarm_sha256": prepared["nonarm_sha256"],
            "pinned": prepared["pinned"],
            "arms": {
                arm: {
                    "snapshot_id": prepared["arms"][arm]["snapshot_id"],
                    "config_sha256": prepared["arms"][arm]["config_sha256"],
                    "nonarm_sha256": prepared["arms"][arm]["nonarm_sha256"],
                    "files_sha256": prepared["arms"][arm]["files_sha256"],
                }
                for arm in ARMS
            },
        },
        "inputs": {
            "experiment": {"file": prepared["file"], "sha256": prepared["sha256"]},
            "runs": {arm: _run_inputs(runs[arm], provenance[arm]) for arm in ARMS},
            "arms": {
                arm: {
                    "config": {
                        "file": prepared["arms"][arm]["config_path"].name,
                        "sha256": prepared["arms"][arm]["config_sha256"],
                    },
                    "manifest": {
                        "file": prepared["arms"][arm]["manifest_path"].name,
                        "sha256": _sha256_file(prepared["arms"][arm]["manifest_path"]),
                    },
                }
                for arm in ARMS
            },
        },
        "provenance": provenance,
        "coverage": {
            "expected_case_count": len(expected_ids),
            "expected_case_ids": list(expected_ids),
            "baseline": coverage["baseline"],
            "candidate": coverage["candidate"],
        },
        "cases": case_rows,
        "aggregate": aggregates,
        "pairs": pairs,
        "procedure": _procedure(),
    }
    return report


def _hex(value) -> str:
    return value[:12] if isinstance(value, str) else "—"


def _metric_cell(metric: dict) -> str:
    if metric["availability"] == "measured":
        return f"{metric['value']} ({metric['source']})"
    if metric["availability"] == "conflicting":
        return "conflicting sources (unknown)"
    return "unknown"


def render_comparison_markdown(report: dict) -> str:
    """Render a deterministic, readable report. No timestamps, no absolute paths."""
    lines = [
        "# Agent-definition saved-run comparison",
        "",
        f"- State: `{report['state']}`",
        f"- Experiment: `{report['experiment']['file']}` "
        f"(sha256 `{_hex(report['experiment']['sha256'])}`)",
        f"- Expected cases: {report['coverage']['expected_case_count']}",
    ]
    reasons = report.get("state_reasons") or []
    if reasons:
        lines.append(f"- State reasons: {', '.join(f'`{reason}`' for reason in reasons)}")
    lines.extend(
        [
            "",
            "## Honesty boundary",
            "",
            report["efficacy"]["note"],
            "",
            "Procedural counters (delegations, reviews, duplicate reviews, reuse, "
            "retries, attempts, length stops) are `not_measured`: no saved artifact "
            "in this milestone measures them.",
            "",
            "## Arms and provenance",
            "",
            "| arm | snapshot id | config sha256 | provenance |",
            "| --- | --- | --- | --- |",
        ]
    )
    for arm in ARMS:
        arm_report = report["experiment"]["arms"][arm]
        provenance = report["provenance"][arm]
        lines.append(
            f"| {arm} | `{_hex(arm_report['snapshot_id'])}` | "
            f"`{_hex(arm_report['config_sha256'])}` | `{provenance['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            "| arm | observed / expected | missing | extra |",
            "| --- | --- | --- | --- |",
        ]
    )
    for arm in ARMS:
        coverage = report["coverage"][arm]
        missing = ", ".join(coverage["missing_case_ids"]) or "—"
        extra = ", ".join(coverage["extra_case_ids"]) or "—"
        lines.append(
            f"| {arm} | {coverage['observed_case_count']} / "
            f"{report['coverage']['expected_case_count']} | {missing} | {extra} |"
        )

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| case | baseline outcome | baseline execution | candidate outcome | "
            "candidate execution | elapsed baseline → candidate | tokens baseline → candidate |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["cases"]:
        baseline = row["baseline"]
        candidate = row["candidate"]
        lines.append(
            f"| {row['case_id']} | {baseline['outcome'] or 'missing'} | "
            f"{baseline['execution']} | {candidate['outcome'] or 'missing'} | "
            f"{candidate['execution']} | "
            f"{_metric_cell(baseline['metrics']['elapsed_seconds'])} → "
            f"{_metric_cell(candidate['metrics']['elapsed_seconds'])} | "
            f"{_metric_cell(baseline['metrics']['token_usage'])} → "
            f"{_metric_cell(candidate['metrics']['token_usage'])} |"
        )

    lines.extend(
        [
            "",
            "## Aggregates",
            "",
            "| arm | completed | pass | fail | unscorable | missing |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for arm in ARMS:
        aggregate = report["aggregate"][arm]
        outcomes = aggregate["outcomes"]
        lines.append(
            f"| {arm} | {aggregate['executions']['completed']} | "
            f"{outcomes.get('pass', 0)} | {outcomes.get('fail', 0)} | "
            f"{outcomes.get('unscorable', 0)} | {outcomes.get('missing', 0)} |"
        )
    lines.extend(
        [
            "",
            "Full-set totals are shown only when every expected case has one measured "
            "source; otherwise the total stays unknown with its measured denominator.",
            "",
            "| arm | metric | total | measured / expected |",
            "| --- | --- | --- | --- |",
        ]
    )
    for arm in ARMS:
        for metric_name, total in report["aggregate"][arm]["totals"].items():
            value = (
                total["value"] if total["availability"] == "measured" else f"unknown ({total['availability']})"
            )
            lines.append(
                f"| {arm} | {metric_name} | {value} | "
                f"{total['measured_case_count']} / {total['expected_case_count']} |"
            )

    lines.extend(
        [
            "",
            "## Paired deltas",
            "",
        ]
    )
    if report["pairs"].get("suppressed_by_state"):
        lines.append(
            f"Deltas suppressed by state `{report['pairs']['suppressed_by_state']}`; "
            "the arms are not comparable enough to show them."
        )
    else:
        lines.extend(
            [
                f"Completed pairs: {report['pairs']['completed_pair_count']} / "
                f"{report['pairs']['expected_pair_count']}.",
                "",
                "| metric | delta | coverage |",
                "| --- | --- | --- |",
            ]
        )
        for metric_name, entry in report["pairs"]["metrics"].items():
            delta = "unknown" if entry["delta"] is None else entry["delta"]
            lines.append(
                f"| {metric_name} | {delta} | {entry['measured_pair_count']} / "
                f"{entry['expected_pair_count']} ({entry['availability']}) |"
            )

    lines.extend(
        [
            "",
            "## Saved artifacts",
            "",
        ]
    )
    for arm in ARMS:
        inputs = report["inputs"]["runs"][arm]
        lines.append(f"- {arm} run directory: `{inputs['directory']}`")
        for artifact in inputs["artifacts"]:
            lines.append(f"  - `{artifact['name']}` sha256 `{_hex(artifact['sha256'])}`")
        if inputs["missing_artifacts"]:
            missing = ", ".join(f"`{name}`" for name in inputs["missing_artifacts"])
            lines.append(f"  - missing linkage artifacts: {missing}")
    lines.extend(
        [
            "",
            "This report is produced by an offline tool over saved artifacts. "
            "It makes no efficacy or ranking claim.",
            "",
        ]
    )
    return "\n".join(lines)


# --- CLI -------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent_definition_eval.py",
        description="Neutral agent-definition evaluation: prepare/compare offline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser(
        "prepare",
        help="build two arm snapshots + neutral configs + experiment.json",
        description=(
            "Prepare baseline and candidate arms from explicit agent sources. "
            "Both sources are required and no model is ever invoked."
        ),
    )
    prepare.add_argument("--baseline-source", type=Path, required=True)
    prepare.add_argument("--candidate-source", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    compare = subparsers.add_parser(
        "compare",
        help="compare two saved runs against a prepared experiment (offline)",
        description=(
            "Compare saved baseline/candidate run artifacts. Reads existing "
            "harness results, collected case dirs and saved run provenance; "
            "never launches a model, agent or subprocess."
        ),
    )
    compare.add_argument("--experiment", type=Path, required=True)
    compare.add_argument("--baseline-run", type=Path, required=True)
    compare.add_argument("--candidate-run", type=Path, required=True)
    compare.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "compare":
        return _compare_cli(args)

    try:
        experiment = prepare_arms(
            args.baseline_source, args.candidate_source, args.out
        )
    except PreparationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = {
        "experiment": str(Path(args.out).expanduser() / EXPERIMENT_FILENAME),
        "arms": {
            arm: entry["snapshot_id"] for arm, entry in experiment["arms"].items()
        },
        "dataset_sha256": experiment["dataset"]["content_sha256"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _compare_cli(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser()
    try:
        _refuse_nonempty(out_dir, action="comparison", error=ComparisonError)
        report = compare_runs(args.experiment, args.baseline_run, args.candidate_run)
    except ComparisonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / COMPARISON_JSON_FILENAME).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / COMPARISON_MD_FILENAME).write_text(
        render_comparison_markdown(report), encoding="utf-8"
    )
    summary = {
        "comparison": str(out_dir / COMPARISON_JSON_FILENAME),
        "markdown": str(out_dir / COMPARISON_MD_FILENAME),
        "state": report["state"],
        "state_reasons": report["state_reasons"],
        "completed_pairs": report["pairs"]["completed_pair_count"],
        "expected_cases": report["coverage"]["expected_case_count"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(_main())
