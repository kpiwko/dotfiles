#!/usr/bin/env python3
"""Offline tests for the neutral agent-definition end-state boundary (Task 1).

Scope of this file: the neutral scorer in ``agent_workflow_checks.py``, the
reproducible snapshot/manifest tests (``SnapshotManifestTests``), the neutral arm
preparation tests (``PreparedArmTests``) for ``agent_definition_eval.py`` and the
saved-run comparison tests (``SavedRunComparisonTests``) for Task 3.

The legacy ``worker_budget_checks.py`` compatibility surface (single-instance
re-export identity and the deferred stress/identity adapters) is regression
coverage in the deferred suite ``tests/test_worker_budget_eval.py``. Nothing in
this file needs the budget policy module, an arm bootstrap, the observer or the
request-evidence modules.

Saved-run comparison is asserted entirely over **synthetic saved-run fixtures**
(hand-written ``harness/``, ``collected/`` and ``provenance/`` artifacts). They
validate the tool, not an experiment: no model ran and no efficacy claim exists.

What is exercised, all offline:

* the three-valued boundary (``pass`` / ``fail`` / ``unscorable``) over the four
  existing worker-budget cases, using the case ``annotations.yaml`` and seed
  bytes as the trusted dataset;
* fail-closed metadata: unknown/missing case, scenario/case mismatch, unsafe
  overlay paths (traversal, absolute, empty, non-string), out-of-project dataset
  root overrides, binary bytecode noise versus binary replacement of a seed;
* the real pinned harness functions — ``_create_per_case_workspace``,
  ``_collect_per_case``, ``load_case_record`` and ``_load_code_judge`` — proving
  the neutral judge works through the actual workspace → collect → load → judge
  path without any model, network or ``opencode`` invocation;
* that the neutral module imports and scores while legacy budget/request modules
  are forbidden by a ``sys.meta_path`` guard.

The only control-plane dependency is git, used by the pinned workspace builder
inside a disposable temp trial directory with ``HOME``/``GIT_CONFIG_GLOBAL``
redirected. The real HOME dotfiles repository is never addressed.

Run with the pinned external interpreter, project cwd, nothing installed:

    /Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
      -m unittest discover -s tests -t tests -p 'test_agent_definition_eval.py'
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

PROJECT = Path(__file__).resolve().parent.parent
CASES = PROJECT / "cases" / "worker-budget-v1"
NEUTRAL_MODULE_PATH = PROJECT / "agent_workflow_checks.py"

HARNESS = Path(
    os.environ.get(
        "AGENT_WORKFLOWS_HARNESS",
        "/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/"
        "vendor/agent-eval-harness-b041d5a6db0b1181d51d95190faf8f2c0808c38d",
    )
)
SCRIPTS = HARNESS / "skills" / "eval-run" / "scripts"

#: The checked-in neutral reference config. It stages only the in-project
#: snapshot and the case seeds — no budget policy module, no arm bootstrap, no
#: observer/SSE staging and no external source root — so these pipeline tests
#: exercise the neutral workflow, not deferred budget research. The judge under
#: test is the neutral module, wired explicitly in ``_judge`` below.
CONFIG = PROJECT / "eval.agent-definition.yaml"

CASE_IDS = (
    "small-edit",
    "failing-test-debug",
    "reviewer-unchanged-handoff",
    "publication-dry-run",
)

FIXED_BOUNDARY = '''"""Page-boundary helper exercised by the seeded failing test."""


def page_bounds(n):
    """Return the page offsets for a document of ``n`` items."""
    return list(range(0, n))
'''

FIXED_DECISION_TABLE = '''"""Revision handoff decision: review need vs validation reuse."""

_RELEVANT = ("worktree_bytes", "index_state", "allowlisted_untracked")
_CHECK_INPUTS = _RELEVANT + ("dependency_inputs", "environment_inputs")


def decide(prior, current):
    """Return {"review_needed": bool, "validation_reusable": bool}."""
    snapshot_changed = any(prior.get(k) != current.get(k) for k in _RELEVANT)
    review_needed = bool(
        snapshot_changed
        or current.get("unclosed_finding")
        or current.get("criteria_changed")
    )
    validation_reusable = all(prior.get(k) == current.get(k) for k in _CHECK_INPUTS)
    return {"review_needed": review_needed, "validation_reusable": validation_reusable}
'''

FIXED_PREFLIGHT = '''"""Publication preflight: ordered stop checks, never a push."""

_CHECKS = (
    ("wrong_root", "root"),
    ("wrong_head", "head"),
    ("wrong_destination", "destination"),
)


def check_preflight(expected, actual):
    """Return {"ok": bool, "stop": str|None, "push_performed": bool}."""
    for name, key in _CHECKS:
        if actual.get(key) != expected.get(key):
            return {"ok": False, "stop": name, "push_performed": False}
    if actual.get("operation") not in {"push-dry-run"}:
        return {"ok": False, "stop": "unauthorized_operation", "push_performed": False}
    return {"ok": True, "stop": None, "push_performed": False}
'''

FIXED_FILES = {
    "failing-test-debug": ("boundary.py", FIXED_BOUNDARY),
    "reviewer-unchanged-handoff": ("decision_table.py", FIXED_DECISION_TABLE),
    "publication-dry-run": ("preflight.py", FIXED_PREFLIGHT),
}

STATUS_KEYS = {"scenario", "ok", "reasons", "facts", "status"}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _neutral():
    return _load(NEUTRAL_MODULE_PATH, "agent_workflow_checks_under_test")


def _annotations(case_id: str) -> dict:
    return yaml.safe_load((CASES / case_id / "annotations.yaml").read_text())


def _record(case_id: str, edits: dict | None = None, files: dict | None = None) -> dict:
    """A collected-record-shaped mapping (synthetic paths; dataset is trusted)."""
    return {
        "case_dir": f"/tmp/collected/cases/{case_id}",
        "annotations": _annotations(case_id),
        "modified_files": dict(edits or {}),
        "files": dict(files or {}),
    }


def _fixed_edits() -> dict:
    """Reference-fixed edits for all four cases (one record per case)."""
    return {
        "small-edit": {
            "notes.txt": (CASES / "small-edit" / "notes.txt").read_text()
            + "worker-budget small edit applied\n"
        },
        "failing-test-debug": {"boundary.py": FIXED_BOUNDARY},
        "reviewer-unchanged-handoff": {"decision_table.py": FIXED_DECISION_TABLE},
        "publication-dry-run": {"preflight.py": FIXED_PREFLIGHT},
    }


def _native():
    """Import the pinned harness config/workspace/collect/score interfaces."""
    if not (HARNESS / "agent_eval" / "config.py").is_file():
        raise unittest.SkipTest(f"pinned harness not available at {HARNESS}")
    for path in (str(HARNESS), str(SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from agent_eval.config import EvalConfig
    from collect import _collect_per_case
    from score import _load_code_judge, load_case_record
    from workspace import _create_per_case_workspace

    return SimpleNamespace(
        EvalConfig=EvalConfig,
        create_workspace=_create_per_case_workspace,
        collect=_collect_per_case,
        load_record=load_case_record,
        load_judge=_load_code_judge,
    )


class ForbiddenImports:
    """``sys.meta_path`` guard: the neutral module must not need these at all."""

    TOKENS = ("worker_budget", "policy", "bootstrap", "observer", "request_evidence")

    def find_module(self, name, path=None):  # pragma: no cover - legacy hook
        return self.find_spec(name, path)

    def find_spec(self, name, path=None, target=None):
        if any(token in name for token in self.TOKENS):
            raise ImportError(f"neutral boundary imported forbidden module {name!r}")
        return None


class NeutralModuleBoundaryTests(unittest.TestCase):
    """No budget/request/policy dependency and no duplicated scorer."""

    def test_neutral_module_imports_only_standard_library(self):
        tree = ast.parse(NEUTRAL_MODULE_PATH.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module)
        for name in imported:
            with self.subTest(module=name):
                self.assertFalse(
                    any(token in name for token in ForbiddenImports.TOKENS),
                    f"neutral module imports {name!r}",
                )
                top = name.split(".", 1)[0]
                self.assertIn(top, sys.stdlib_module_names, f"{name!r} is not stdlib")

    def test_neutral_scores_while_legacy_imports_are_forbidden(self):
        guard = ForbiddenImports()
        with mock.patch.object(sys, "meta_path", [guard, *sys.meta_path]):
            neutral = _neutral()
            record = _record(
                "small-edit", edits={"notes.txt": _fixed_edits()["small-edit"]["notes.txt"]}
            )
            outcome = neutral.score_record(outputs=record)
        self.assertEqual(outcome["status"], "pass", outcome["reasons"])
        self.assertIs(neutral.judge_scenario(outputs=record), True)

    def test_dataset_resolution_is_module_relative_not_cwd_relative(self):
        """A fresh interpreter in an unrelated cwd still finds the trusted dataset."""
        code = """
import importlib.util, json, sys
from pathlib import Path
import yaml

spec = importlib.util.spec_from_file_location("agent_workflow_checks", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
annotations = yaml.safe_load(Path(sys.argv[2]).read_text())
seed = Path(sys.argv[3]).read_text()
record = {
    "case_dir": "/tmp/collected/cases/small-edit",
    "annotations": annotations,
    "modified_files": {"notes.txt": seed + "worker-budget small edit applied\\n"},
    "files": {},
}
print(json.dumps(module.score_record(outputs=record)))
"""
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(NEUTRAL_MODULE_PATH),
                    str(CASES / "small-edit" / "annotations.yaml"),
                    str(CASES / "small-edit" / "notes.txt"),
                ],
                cwd=tmp,  # unrelated to the eval project
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["status"], "pass", outcome["reasons"])
        self.assertEqual(outcome["facts"]["dataset_root"], "cases/worker-budget-v1")
        self.assertNotIn(str(Path.cwd()), completed.stdout)


class ScoreRecordUnitTests(unittest.TestCase):
    """Three-valued boundary over collected-record-shaped inputs."""

    def setUp(self):
        self.neutral = _neutral()

    def test_result_shape_and_procedure_is_never_measured(self):
        outcome = self.neutral.score_record(outputs=_record("small-edit"))
        self.assertEqual(set(outcome), STATUS_KEYS)
        self.assertIsInstance(outcome["ok"], bool)
        self.assertIsInstance(outcome["reasons"], list)
        self.assertIsInstance(outcome["facts"], dict)
        self.assertEqual(outcome["scenario"], "small-edit")
        self.assertEqual(outcome["facts"]["procedure"], "not_measured")
        json.dumps(outcome)  # report-safe, no exotic objects

    def test_pristine_seeds_fail_each_case_with_reasons(self):
        for case_id in CASE_IDS:
            with self.subTest(case=case_id):
                outcome = self.neutral.score_record(outputs=_record(case_id))
                self.assertEqual(outcome["status"], "fail")
                self.assertIs(outcome["ok"], False)
                self.assertTrue(outcome["reasons"], "fail must explain itself")
                self.assertEqual(outcome["facts"]["case_id"], case_id)
                self.assertFalse(self.neutral.judge_scenario(outputs=_record(case_id)))

    def test_reference_fixes_pass_each_case(self):
        edits = _fixed_edits()
        for case_id in CASE_IDS:
            with self.subTest(case=case_id):
                record = _record(case_id, edits=edits[case_id])
                outcome = self.neutral.score_record(outputs=record)
                self.assertEqual(outcome["status"], "pass", outcome["reasons"])
                self.assertEqual(outcome["reasons"], [])
                self.assertIs(outcome["ok"], True)
                self.assertIs(self.neutral.judge_scenario(outputs=record), True)

    def test_unusable_records_are_unscorable_never_pass(self):
        base = _record("small-edit")
        unusable = {
            "none": None,
            "empty": {},
            "not-a-mapping": ["nope"],
            "no_case_dir": dict(base, case_dir=None),
            "blank_case_dir": dict(base, case_dir="   "),
            "unknown_case": dict(base, case_dir="/tmp/cases/not-a-case"),
            "annotations_missing": {k: v for k, v in base.items() if k != "annotations"},
            "annotations_list": dict(base, annotations=["scenario"]),
            "scenario_missing": dict(base, annotations={"target": "notes.txt"}),
            "scenario_mismatch": dict(base, annotations={"scenario": "publication-dry-run"}),
            "scenario_blank": dict(base, annotations={"scenario": " "}),
        }
        for label, record in unusable.items():
            with self.subTest(record=label):
                outcome = self.neutral.score_record(outputs=record)
                self.assertEqual(outcome["status"], "unscorable", label)
                self.assertIs(outcome["ok"], False)
                self.assertTrue(outcome["reasons"])
                self.assertIs(self.neutral.judge_scenario(outputs=record), False)

    def test_unsafe_overlay_paths_are_unscorable(self):
        base = _record("small-edit")
        for label, edits in {
            "traversal": {"../escape.txt": "x"},
            "absolute": {"/abs.txt": "x"},
            "empty": {"": "x"},
            "non_string_value": {"notes.txt": 7},
            "list_source": ["notes.txt"],
        }.items():
            with self.subTest(overlay=label):
                outcome = self.neutral.score_record(
                    outputs=dict(base, modified_files=edits)
                )
                self.assertEqual(outcome["status"], "unscorable", label)
                self.assertIs(self.neutral.judge_scenario(outputs=dict(base, modified_files=edits)), False)
        for key in ("_modified/../escape.txt", "_modified//abs.txt", "_modified/"):
            with self.subTest(binary_key=key):
                record = dict(base, files={key: {"_binary": True}})
                outcome = self.neutral.score_record(outputs=record)
                self.assertEqual(outcome["status"], "unscorable")

    def test_dataset_root_override_must_stay_in_project(self):
        record = _record("small-edit")
        for override in ("../../..", "/etc", "..", "cases/does-not-exist-v1"):
            with self.subTest(root=override):
                outcome = self.neutral.score_record(outputs=record, dataset_root=override)
                self.assertEqual(outcome["status"], "unscorable")
                self.assertIs(
                    self.neutral.judge_scenario(outputs=record, dataset_root=override), False
                )

    def test_binary_bytecode_noise_is_ignored_but_seed_replacement_fails(self):
        edits = _fixed_edits()["failing-test-debug"]
        noise = {"_modified/__pycache__/boundary.cpython-312.pyc": {"_binary": True}}
        outcome = self.neutral.score_record(
            outputs=_record("failing-test-debug", edits=edits, files=noise)
        )
        self.assertEqual(outcome["status"], "pass", outcome["reasons"])
        self.assertEqual(
            outcome["facts"]["ignored_binary_artifacts"],
            ["__pycache__/boundary.cpython-312.pyc"],
        )

        tampered = {"_modified/unrelated.py": {"_binary": True}}
        outcome = self.neutral.score_record(
            outputs=_record("failing-test-debug", edits=edits, files=tampered)
        )
        self.assertEqual(outcome["status"], "fail")
        self.assertIs(outcome["ok"], False)
        self.assertIn("binary replacement of protected seed: unrelated.py", outcome["reasons"])

    def test_missing_pristine_seed_is_unscorable(self):
        # In-project override, but the trusted case directory is absent there.
        outcome = self.neutral.score_record(
            outputs=_record("small-edit"), dataset_root="cases"
        )
        self.assertEqual(outcome["status"], "unscorable")
        self.assertIn("no pristine seed files", " ".join(outcome["reasons"]))

    def test_fixture_sys_exit_is_contained_as_a_failed_case(self):
        """Every code-loading checker contains a fixture ``sys.exit``.

        A fixture that exits raises ``SystemExit`` (a ``BaseException``), which a
        plain ``except Exception`` misses; uncontained it would terminate the
        whole scoring process instead of scoring the case. Both the module-import
        and the post-import call boundary are covered, and a scoring process that
        dies here would fail this test rather than assert.
        """
        exits = {
            "failing-test-debug": {
                "import": {"boundary.py": "import sys\nsys.exit(3)\n"},
                "call": {
                    "boundary.py": "def page_bounds(n):\n    raise SystemExit(7)\n"
                },
            },
            "reviewer-unchanged-handoff": {
                "import": {"decision_table.py": "import sys\nsys.exit(4)\n"},
                "call": {
                    "decision_table.py": (
                        "def decide(prior, current):\n    raise SystemExit(8)\n"
                    )
                },
            },
            "publication-dry-run": {
                "import": {"preflight.py": "import sys\nsys.exit(5)\n"},
                "call": {
                    "preflight.py": (
                        "def check_preflight(expected, actual):\n"
                        "    raise SystemExit(9)\n"
                    )
                },
            },
        }
        for case_id, variants in exits.items():
            for boundary, edits in variants.items():
                with self.subTest(case=case_id, boundary=boundary):
                    record = _record(case_id, edits=edits)
                    outcome = self.neutral.score_record(outputs=record)
                    self.assertEqual(outcome["status"], "fail", outcome["reasons"])
                    self.assertIs(outcome["ok"], False)
                    self.assertTrue(outcome["reasons"])
                    self.assertIn("SystemExit", " ".join(outcome["reasons"]))
                    json.dumps(outcome)
                    self.assertIs(self.neutral.judge_scenario(outputs=record), False)

    def test_keyboard_interrupt_from_a_fixture_is_not_swallowed(self):
        """Operator cancellation must still propagate out of the scorer."""
        record = _record(
            "failing-test-debug", edits={"boundary.py": "raise KeyboardInterrupt\n"}
        )
        with self.assertRaises(KeyboardInterrupt):
            self.neutral.score_record(outputs=record)

    def test_overlay_path_collisions_are_unscorable_not_fatal(self):
        """A relative overlay path can still collide with the materialized tree."""
        collisions = {
            "parent_is_seed_file": {"notes.txt/x": "x"},
            "names_created_directory": {"pkg/mod.py": "x", "pkg": "y"},
        }
        for label, edits in collisions.items():
            with self.subTest(collision=label):
                record = _record("small-edit", edits=edits)
                outcome = self.neutral.score_record(outputs=record)
                self.assertEqual(outcome["status"], "unscorable", label)
                self.assertIs(outcome["ok"], False)
                reason = " ".join(outcome["reasons"])
                self.assertIn("materialized as real files", reason)
                self.assertNotIn("agent-workflow-case-", reason)
                self.assertLess(len(reason), 200)
                self.assertIs(self.neutral.judge_scenario(outputs=record), False)

    def test_pristine_seed_identity_ignores_interpreter_cache_noise(self):
        """Bytecode cache noise is artifact identity, not a protected seed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "small-edit"
            (case / "__pycache__").mkdir(parents=True)
            (case / "notes.txt").write_text("seed\n")
            (case / "__pycache__" / "notes.cpython-312.pyc").write_bytes(b"\x00")
            (case / "legacy.pyc").write_bytes(b"\x00")
            seeds = self.neutral._pristine_files("small-edit", root)
        self.assertEqual(sorted(seeds), ["notes.txt"])


class NeutralMetricsTests(unittest.TestCase):
    """Usage helpers stay UNKNOWN-preserving in the neutral module."""

    def test_absent_partial_and_unreadable_metrics_never_become_zero(self):
        neutral = _neutral()
        self.assertEqual(neutral.collect_metrics({})["status"], "unknown")
        partial = neutral.collect_metrics(
            {"files": {"output/metrics.json": '{"cost_usd": 0.25}'}}
        )
        self.assertEqual(partial["status"], "reported")
        self.assertEqual(partial["cost_usd"], 0.25)
        for key in ("token_usage", "num_turns", "attempts"):
            self.assertIsNone(partial[key])
        unreadable = neutral.collect_metrics({"files": {"output/metrics.json": "{not json"}})
        self.assertEqual(unreadable["status"], "unreadable")
        self.assertIsNone(unreadable["cost_usd"])
        self.assertIsNone(unreadable["token_usage"])
        self.assertIsNone(neutral.read_metrics_document(None)["cost_usd"])


class NativeNeutralPipelineTests(unittest.TestCase):
    """Real pinned workspace → collect → load → neutral judge, no agent execution."""

    def _build(self, tmp_root: Path):
        native = _native()
        config = native.EvalConfig.from_yaml(str(CONFIG))
        workspace = tmp_root / "workspace"
        workspace.mkdir()
        case_dirs = [CASES / case_id for case_id in CASE_IDS]
        # Disposable mock HOME for the git control plane: no real ~/.gitconfig is
        # read and every repository is created inside the temp trial root.
        mock_home = tmp_root / "mock-home"
        mock_home.mkdir()
        (mock_home / ".config").symlink_to(Path.home() / ".config")
        env = {
            "HOME": str(mock_home),
            "GIT_CONFIG_GLOBAL": str(mock_home / ".gitconfig"),
            "GIT_CONFIG_SYSTEM": str(mock_home / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "eval-test",
            "GIT_AUTHOR_EMAIL": "eval-test@example.invalid",
            "GIT_COMMITTER_NAME": "eval-test",
            "GIT_COMMITTER_EMAIL": "eval-test@example.invalid",
        }
        # The cwd stays the eval project on purpose: the harness resolves
        # project-relative `workspace.files` sources against the config's project
        # root, derived from the process cwd (the suite is run from P).
        with mock.patch.dict(os.environ, env):
            native.create_workspace(
                workspace,
                case_dirs,
                config,
                SimpleNamespace(symlinks=""),
            )
        return native, config, workspace

    def _judge(self, native, config, workspace, tmp_root):
        collected = tmp_root / "collected"
        runs = tmp_root / "runs"
        runs.mkdir(exist_ok=True)
        native.collect(workspace, collected, config)
        # Authentic `_load_code_judge` wiring, pointed at the neutral module.
        judge = native.load_judge(
            SimpleNamespace(
                module="agent_workflow_checks",
                function="judge_scenario",
                arguments={},
            ),
            str(PROJECT),
        )
        self.assertEqual(getattr(judge, "__module__", None), "agent_workflow_checks")
        records = {
            case_id: native.load_record(
                collected / "cases" / case_id, config, runs_dir=runs
            )
            for case_id in CASE_IDS
        }
        return records, {case_id: judge(outputs=record) for case_id, record in records.items()}

    def _fix_workspace(self, workspace: Path) -> None:
        (workspace / "cases" / "small-edit" / "notes.txt").write_text(
            _fixed_edits()["small-edit"]["notes.txt"]
        )
        for case_id, (filename, text) in FIXED_FILES.items():
            (workspace / "cases" / case_id / filename).write_text(text)

    def test_reference_fixes_pass_all_four_cases_through_real_pipeline(self):
        neutral = _neutral()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            native, config, workspace = self._build(tmp_root)
            self._fix_workspace(workspace)
            records, verdicts = self._judge(native, config, workspace, tmp_root)
            self.assertEqual(verdicts, {case_id: True for case_id in CASE_IDS})
            for case_id, record in records.items():
                with self.subTest(case=case_id):
                    self.assertNotIn("workspace", record)
                    outcome = neutral.score_record(outputs=record)
                    self.assertEqual(outcome["status"], "pass", outcome["reasons"])
                    self.assertEqual(outcome["reasons"], [])
                    self.assertEqual(outcome["scenario"], case_id)
                    self.assertEqual(outcome["facts"]["procedure"], "not_measured")

    def test_untouched_seeds_fail_all_four_cases_with_reasons(self):
        neutral = _neutral()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            native, config, workspace = self._build(tmp_root)
            records, verdicts = self._judge(native, config, workspace, tmp_root)
            self.assertEqual(verdicts, {case_id: False for case_id in CASE_IDS})
            for case_id, record in records.items():
                with self.subTest(case=case_id):
                    outcome = neutral.score_record(outputs=record)
                    self.assertEqual(outcome["status"], "fail")
                    self.assertTrue(outcome["reasons"])

    def test_observed_protected_file_tamper_fails(self):
        neutral = _neutral()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            native, config, workspace = self._build(tmp_root)
            self._fix_workspace(workspace)
            # Weaken the reproduction instead of fixing the cause.
            (workspace / "cases" / "failing-test-debug" / "test_boundary.py").write_text(
                "import unittest\n"
            )
            records, verdicts = self._judge(native, config, workspace, tmp_root)
            self.assertFalse(verdicts["failing-test-debug"])
            outcome = neutral.score_record(outputs=records["failing-test-debug"])
            self.assertEqual(outcome["status"], "fail")
            self.assertIn("unrelated file changed: test_boundary.py", outcome["reasons"])

    def test_binary_bytecode_noise_keeps_correct_fix_passing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            native, config, workspace = self._build(tmp_root)
            self._fix_workspace(workspace)
            pycache = workspace / "cases" / "failing-test-debug" / "__pycache__"
            pycache.mkdir()
            (pycache / "boundary.cpython-312.pyc").write_bytes(
                b"\x00\x0d\x0a\xff\xfe binary bytecode"
            )
            _, verdicts = self._judge(native, config, workspace, tmp_root)
            self.assertTrue(verdicts["failing-test-debug"])

    def test_binary_replacement_of_protected_seed_is_observed_tamper(self):
        neutral = _neutral()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            native, config, workspace = self._build(tmp_root)
            self._fix_workspace(workspace)
            (workspace / "cases" / "failing-test-debug" / "unrelated.py").write_bytes(
                b"\xff\xfe\x00\x80 binary replacement"
            )
            records, verdicts = self._judge(native, config, workspace, tmp_root)
            self.assertFalse(verdicts["failing-test-debug"])
            entry = records["failing-test-debug"]["files"]["_modified/unrelated.py"]
            self.assertNotIsInstance(entry, str)
            self.assertIs(entry.get("_binary"), True)
            outcome = neutral.score_record(outputs=records["failing-test-debug"])
            self.assertEqual(outcome["status"], "fail")
            self.assertIn(
                "binary replacement of protected seed: unrelated.py", outcome["reasons"]
            )

    def test_malformed_collected_record_is_unscorable(self):
        neutral = _neutral()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            native, config, workspace = self._build(tmp_root)
            self._fix_workspace(workspace)
            records, _ = self._judge(native, config, workspace, tmp_root)
            record = records["small-edit"]
            for label, damaged in {
                "overlay_not_mapping": dict(record, modified_files=["notes.txt"]),
                "annotations_dropped": {k: v for k, v in record.items() if k != "annotations"},
                "unknown_case": dict(record, case_dir=str(tmp_root / "cases" / "unknown-case")),
            }.items():
                with self.subTest(damaged=label):
                    outcome = neutral.score_record(outputs=damaged)
                    self.assertEqual(outcome["status"], "unscorable")
                    self.assertIs(outcome["ok"], False)
                    self.assertTrue(outcome["reasons"])
            self.assertEqual(neutral.score_record(outputs=record)["status"], "pass")


class SnapshotManifestTests(unittest.TestCase):
    """Task 2 slice: reproducible, verifiable snapshot manifests.

    Everything here is offline: fixture role sources are plain markdown written
    into disposable temp directories, and the checked-in reference snapshot is
    only read (never regenerated by these tests).
    """

    ROLES = ("orchestrator", "worker", "reviewer", "architect", "planner", "zweistein")
    SNAPSHOT = PROJECT / "eval-snapshot"
    HOME_AGENTS = Path.home() / ".config" / "opencode" / "agents"

    def _builder(self):
        spec = importlib.util.spec_from_file_location(
            "eval_snapshot_builder_manifest", self.SNAPSHOT / "build_snapshot.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _agent_text(role: str, *, model: str, marker: str = "") -> str:
        return (
            "---\n"
            f"description: fixture {role}\n"
            f"model: {model}\n"
            "mode: primary\n"
            "permission:\n"
            "  edit: allow\n"
            "  bash: deny\n"
            "---\n"
            "\n"
            f"{role} prompt body {marker}\n"
        )

    def _source(self, root, *, model="agentgateway/architect", marker=""):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        for role in self.ROLES:
            (root / f"{role}.md").write_text(
                self._agent_text(role, model=model, marker=marker), encoding="utf-8"
            )
        return root

    def test_manifest_schema_has_no_machine_specific_identity(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp) / "src")
            dest = Path(tmp) / "out"
            manifest = builder.build_manifest(source)
            builder.build(dest=dest, source=source)
            text = (dest / "manifest.json").read_text(encoding="utf-8")
            self.assertEqual(
                set(manifest),
                {
                    "schema_version",
                    "snapshot_id",
                    "model",
                    "roles",
                    "source_sha256",
                    "files_sha256",
                },
            )
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["model"], builder.ILLUSIONIST)
            self.assertEqual(manifest["roles"], list(builder.ROLES))
            self.assertEqual(
                set(manifest["source_sha256"]), {f"{r}.md" for r in builder.ROLES}
            )
            self.assertEqual(
                set(manifest["files_sha256"]),
                {f"agents/{r}.md" for r in builder.ROLES} | {"opencode.jsonc"},
            )
            self.assertEqual(manifest["snapshot_id"], builder.snapshot_id(manifest))
            self.assertEqual(builder.validate_manifest(manifest), [])
            # No absolute source/destination paths, HOME, or timestamps inside.
            self.assertNotIn(str(source), text)
            self.assertNotIn(str(dest), text)
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("/Users/", text)
            self.assertNotIn("timestamp", text)
            self.assertNotIn("created", text)

    def test_identity_is_stable_across_source_and_destination_locations(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            source_a = self._source(Path(first) / "src")
            source_b = self._source(Path(second) / "nested" / "elsewhere" / "src")
            dest_a = Path(first) / "out-a"
            dest_b = Path(second) / "deep" / "out-b"
            self.assertEqual(
                builder.build_manifest(source_a), builder.build_manifest(source_b)
            )
            builder.build(dest=dest_a, source=source_a)
            builder.build(dest=dest_b, source=source_b)
            self.assertEqual(
                (dest_a / "manifest.json").read_bytes(),
                (dest_b / "manifest.json").read_bytes(),
            )
            self.assertEqual(
                builder.verify_snapshot(dest_a)["snapshot_id"],
                builder.verify_snapshot(dest_b)["snapshot_id"],
            )

    def test_prompt_byte_change_changes_identity(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp) / "src")
            before = builder.build_manifest(source)
            (source / "worker.md").write_text(
                self._agent_text(
                    "worker", model="agentgateway/architect", marker="changed"
                ),
                encoding="utf-8",
            )
            after = builder.build_manifest(source)
            self.assertNotEqual(before["snapshot_id"], after["snapshot_id"])
            self.assertNotEqual(
                before["source_sha256"]["worker.md"],
                after["source_sha256"]["worker.md"],
            )
            self.assertNotEqual(
                before["files_sha256"]["agents/worker.md"],
                after["files_sha256"]["agents/worker.md"],
            )
            for role in self.ROLES:
                if role == "worker":
                    continue
                self.assertEqual(
                    before["source_sha256"][f"{role}.md"],
                    after["source_sha256"][f"{role}.md"],
                )
            self.assertEqual(
                before["files_sha256"]["opencode.jsonc"],
                after["files_sha256"]["opencode.jsonc"],
            )

    def test_model_only_rewrite_preserves_bytes_and_permission_order(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._source(root / "one", model="agentgateway/architect")
            second = self._source(root / "two", model="otherprovider/other-model")
            one, two = builder.build_manifest(first), builder.build_manifest(second)
            # Pre-rewrite source model differs, so identities stay distinct even
            # though the generated agents are byte-identical.
            self.assertNotEqual(one["snapshot_id"], two["snapshot_id"])
            self.assertNotEqual(one["source_sha256"]["worker.md"], two["source_sha256"]["worker.md"])
            self.assertEqual(one["files_sha256"], two["files_sha256"])
            dest_one, dest_two = root / "out-one", root / "out-two"
            builder.build(dest=dest_one, source=first)
            builder.build(dest=dest_two, source=second)
            for role in self.ROLES:
                generated = (dest_one / "agents" / f"{role}.md").read_bytes()
                self.assertEqual(
                    generated, (dest_two / "agents" / f"{role}.md").read_bytes(), role
                )
                original = (first / f"{role}.md").read_text(encoding="utf-8")
                expected = (
                    original.replace(
                        "model: agentgateway/architect",
                        f"model: {builder.ILLUSIONIST}",
                        1,
                    ).encode("utf-8")
                )
                self.assertEqual(generated, expected, role)
            self.assertEqual(
                (dest_one / "opencode.jsonc").read_bytes(),
                (dest_two / "opencode.jsonc").read_bytes(),
            )
            config = json.loads((dest_one / "opencode.jsonc").read_text())
            self.assertEqual(config["permissions"], builder._PERMISSIONS)
            self.assertEqual(config["model"], builder.ILLUSIONIST)
            self.assertEqual(builder.verify_snapshot(dest_one)["roles"], list(builder.ROLES))

    def test_missing_role_and_ambiguous_model_publish_nothing(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = self._source(root / "missing")
            (missing / "architect.md").unlink()
            dest = root / "out-missing"
            with self.assertRaises(builder.SnapshotError) as caught:
                builder.build(dest=dest, source=missing)
            self.assertIn("missing source agent", str(caught.exception))
            self.assertFalse(dest.exists())

            ambiguous = self._source(root / "ambiguous")
            worker = ambiguous / "worker.md"
            worker.write_text(
                worker.read_text(encoding="utf-8").replace(
                    "model: agentgateway/architect",
                    "model: one/model\nmodel: two/model",
                ),
                encoding="utf-8",
            )
            dest = root / "out-ambiguous"
            with self.assertRaises(builder.SnapshotError) as caught:
                builder.build(dest=dest, source=ambiguous)
            self.assertIn("exactly one frontmatter model line", str(caught.exception))
            self.assertFalse(dest.exists())

    def test_tampered_snapshot_and_stale_manifest_are_rejected(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root / "src")
            dest = root / "out"
            builder.build(dest=dest, source=source)
            self.assertEqual(
                builder.verify_snapshot(dest)["snapshot_id"],
                builder.build_manifest(source)["snapshot_id"],
            )

            worker = dest / "agents" / "worker.md"
            worker.write_bytes(worker.read_bytes() + b"tampered\n")
            with self.assertRaises(builder.SnapshotError) as caught:
                builder.verify_snapshot(dest)
            self.assertIn("agents/worker.md", str(caught.exception))

            builder.build(dest=dest, source=source, overwrite=True)
            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["snapshot_id"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(builder.validate_manifest(manifest))
            with self.assertRaises(builder.SnapshotError):
                builder.verify_snapshot(dest)

            manifest = builder.build_manifest(source)
            manifest["files_sha256"]["opencode.jsonc"] = "f" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(builder.SnapshotError):
                builder.verify_snapshot(dest)

            builder.build(dest=dest, source=source, overwrite=True)
            (dest / "opencode.jsonc").unlink()
            with self.assertRaises(builder.SnapshotError) as caught:
                builder.verify_snapshot(dest)
            self.assertIn("opencode.jsonc", str(caught.exception))

    def test_nonempty_destination_requires_explicit_overwrite(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root / "src")
            dest = root / "out"
            written = builder.build(dest=dest, source=source)
            self.assertEqual(
                written,
                [dest / "agents" / f"{role}.md" for role in self.ROLES]
                + [dest / "opencode.jsonc"],
            )
            self.assertTrue((dest / "manifest.json").is_file())

            expected_config = (dest / "opencode.jsonc").read_bytes()
            expected_manifest = (dest / "manifest.json").read_bytes()
            (dest / "agents" / "worker.md").write_text("local edit\n", encoding="utf-8")
            with self.assertRaises(builder.SnapshotError) as caught:
                builder.build(dest=dest, source=source)
            self.assertIn("not empty", str(caught.exception))
            self.assertIn("overwrite=True", str(caught.exception))
            # The refusal happens before any write: local content untouched.
            self.assertEqual(
                (dest / "agents" / "worker.md").read_text(encoding="utf-8"),
                "local edit\n",
            )
            self.assertEqual((dest / "opencode.jsonc").read_bytes(), expected_config)
            self.assertEqual((dest / "manifest.json").read_bytes(), expected_manifest)

            builder.build(dest=dest, source=source, overwrite=True)
            self.assertEqual(builder.verify_snapshot(dest)["snapshot_id"], builder.build_manifest(source)["snapshot_id"])
            self.assertNotEqual(
                (dest / "agents" / "worker.md").read_text(encoding="utf-8"),
                "local edit\n",
            )

    def test_legacy_default_destination_regenerates_in_place(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root / "src", marker="v1")
            dest = root / "legacy"
            builder.build(dest=dest, source=source)
            # The documented default destination keeps its regeneration behavior:
            # a nonempty snapshot dir equal to SNAPSHOT_DIR needs no flag.
            builder.SNAPSHOT_DIR = dest
            changed = self._source(root / "src2", marker="v2")
            builder.build(dest=dest, source=changed)
            self.assertEqual(
                builder.verify_snapshot(dest)["snapshot_id"],
                builder.build_manifest(changed)["snapshot_id"],
            )

    @unittest.skipUnless(HOME_AGENTS.is_dir(), "production agent roles unavailable")
    def test_checked_in_manifest_verifies_and_corresponds_to_source(self):
        builder = self._builder()
        manifest = builder.verify_snapshot(self.SNAPSHOT)
        self.assertEqual(builder.validate_manifest(manifest), [])
        self.assertEqual(manifest, builder.build_manifest(builder.SOURCE_AGENTS))
        self.assertEqual(
            set(manifest["files_sha256"]),
            {f"agents/{r}.md" for r in builder.ROLES} | {"opencode.jsonc"},
        )

    @unittest.skipUnless(HOME_AGENTS.is_dir(), "production agent roles unavailable")
    def test_reference_manifest_verifies_without_rewriting_generated_bytes(self):
        builder = self._builder()
        rebuilt = builder.build_manifest(builder.SOURCE_AGENTS)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "snapshot"
            shutil.copytree(self.SNAPSHOT, dest)
            (dest / "manifest.json").unlink()
            before = {
                path.relative_to(dest).as_posix(): path.read_bytes()
                for path in dest.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            }
            written = builder.write_reference_manifest(
                dest=dest, source=builder.SOURCE_AGENTS
            )
            self.assertEqual(written, dest / "manifest.json")
            self.assertEqual(
                json.loads(written.read_text(encoding="utf-8")), rebuilt
            )
            after = {
                path.relative_to(dest).as_posix(): path.read_bytes()
                for path in dest.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.name != "manifest.json"
            }
            self.assertEqual(before, after)

    @unittest.skipUnless(HOME_AGENTS.is_dir(), "production agent roles unavailable")
    def test_reference_manifest_refuses_to_regenerate_mismatched_bytes(self):
        builder = self._builder()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "snapshot"
            shutil.copytree(self.SNAPSHOT, dest)
            (dest / "manifest.json").unlink()
            worker = dest / "agents" / "worker.md"
            worker.write_text(worker.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
            with self.assertRaises(builder.SnapshotError) as caught:
                builder.write_reference_manifest(dest=dest, source=builder.SOURCE_AGENTS)
            self.assertIn("refusing to regenerate", str(caught.exception))
            self.assertFalse((dest / "manifest.json").exists())
            self.assertTrue(worker.read_text(encoding="utf-8").endswith("drift\n"))


AGENT_DEFINITION_MODULE_PATH = PROJECT / "agent_definition_eval.py"
TEMPLATE = PROJECT / "eval.agent-definition.yaml"
ARM_ROLES = ("orchestrator", "worker", "reviewer", "architect", "planner", "zweistein")

#: The pinned runner argv the neutral template must carry verbatim.
PINNED_ARGV = [
    "/usr/bin/env",
    "-u",
    "PWD",
    "opencode",
    "run",
    "--standalone",
    "--agent",
    "orchestrator",
    "--model",
    "agentgateway/illusionist",
    "--format",
    "json",
    "{args}",
]

#: Seeds that `_copy_input_files` may stage (metadata is never listed).
SEED_NAMES = (
    "notes.txt",
    "boundary.py",
    "test_boundary.py",
    "unrelated.py",
    "decision_table.py",
    "state.json",
    "preflight.py",
    "repos.json",
)


def _agent_definition():
    return _load(AGENT_DEFINITION_MODULE_PATH, "agent_definition_eval_under_test")


def _snapshot_builder():
    return _load(
        PROJECT / "eval-snapshot" / "build_snapshot.py", "eval_snapshot_builder_prepared"
    )


def _source_agent_text(role: str, *, model: str, marker: str) -> str:
    """A synthetic role definition: ordered permissions, body marker, one model."""
    return (
        "---\n"
        f"description: synthetic {role} arm fixture\n"
        f"model: {model}\n"
        "mode: primary\n"
        "permission:\n"
        "  edit: allow\n"
        "  bash: deny\n"
        "  skill: ask\n"
        "  subagent:\n"
        "    reviewer: allow\n"
        "---\n"
        "\n"
        f"{role} prompt body for {marker}\n"
    )


def _arm_source(root, *, marker: str, model: str = "agentgateway/architect") -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for role in ARM_ROLES:
        (root / f"{role}.md").write_text(
            _source_agent_text(role, model=model, marker=marker), encoding="utf-8"
        )
    return root


def _flatten(document, prefix: str = ""):
    """Flatten a config document to ``path -> leaf`` for exact diffs."""
    flat = {}
    if isinstance(document, dict):
        for key, value in document.items():
            flat.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            flat.update(_flatten(value, f"{prefix}[{index}]"))
    else:
        flat[prefix] = document
    return flat


def _pinned_workspace(case, tmp_root: Path, config_path: Path, run_id: str):
    """Run the pinned runtime's own case discovery and materialization.

    ``workspace.py`` is the actual selector: it enumerates every subdirectory
    of ``dataset.path`` and, with no ``--cases`` filter (exactly what a real
    run passes), writes ``case_order.yaml`` for execution/collection. No model
    is launched here; only file staging and disposable git repositories run.

    ``case`` is the calling ``unittest.TestCase`` (it owns the assertions), so
    the prepared-arm and end-to-end integration tests drive the same real path.
    """
    tmp_dir = tmp_root / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    mock_home = tmp_root / "mock-home"
    mock_home.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "HOME": str(mock_home),
        "TMPDIR": str(tmp_dir),
        "GIT_CONFIG_GLOBAL": str(mock_home / ".gitconfig"),
        "GIT_CONFIG_SYSTEM": str(mock_home / ".gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "eval-test",
        "GIT_AUTHOR_EMAIL": "eval-test@example.invalid",
        "GIT_COMMITTER_NAME": "eval-test",
        "GIT_COMMITTER_EMAIL": "eval-test@example.invalid",
        "PYTHONPATH": os.pathsep.join([str(HARNESS), str(SCRIPTS)]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "workspace.py"),
            "--config",
            str(config_path),
            "--run-id",
            run_id,
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    case.assertEqual(completed.returncode, 0, completed.stderr)
    case.assertIn("CASES: 4", completed.stdout)
    workspace = tmp_dir / "agent-eval" / run_id
    order = yaml.safe_load((workspace / "case_order.yaml").read_text())
    return workspace, order


class PreparedArmTests(unittest.TestCase):
    """Task 2 slice: neutral reference config and reproducible arm preparation.

    Everything here is offline. The synthetic role sources, the dataset copy and
    the prepared experiment live in disposable temp directories; no model,
    agent, network call or ``opencode`` process is invoked. The subprocess cases
    run explicit caller cwds (``HOME`` and the project) purely to prove that the
    generated config resolves and materializes without a cwd hint.

    The synthetic fixtures are tool validation, not experiment evidence: a
    prepared experiment only proves which inputs *would* run.
    """

    def setUp(self):
        self.definition = _agent_definition()
        self.builder = _snapshot_builder()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _prepare(
        self,
        *,
        baseline_marker="baseline",
        candidate_marker="candidate",
        name="exp",
        out_name=None,
    ):
        baseline = _arm_source(self.root / f"{name}-baseline-src", marker=baseline_marker)
        candidate = _arm_source(self.root / f"{name}-candidate-src", marker=candidate_marker)
        out = self.root / (out_name or name)
        experiment = self.definition.prepare_arms(baseline, candidate, out)
        return baseline, candidate, out, experiment

    # --- checked-in neutral template -------------------------------------

    def test_neutral_template_loads_with_pinned_argv_and_no_budget_or_policy(self):
        native = _native()
        config = native.EvalConfig.from_yaml(str(TEMPLATE))
        self.assertEqual(list(config.runner.command), PINNED_ARGV)
        self.assertEqual(config.runner.command[-1], "{args}")
        argv = " ".join(config.runner.command)
        for forbidden in ("--auto", "--pure", "{model}", "{subagent_model}"):
            self.assertNotIn(forbidden, argv)
        # No budget instrument and no external source root in the neutral config.
        self.assertIsNone(config.execution.max_budget_usd)
        self.assertFalse(list(config.runner.plugin_dirs or []))
        self.assertEqual(config.execution.mode, "case")
        self.assertEqual(str(config.dataset.path), "cases/worker-budget-v1")
        self.assertEqual(config.judges[0].module, "agent_workflow_checks")
        self.assertEqual(config.judges[0].function, "judge_scenario")
        self.assertEqual(
            config.judges[0].arguments, {"dataset_root": "cases/worker-budget-v1"}
        )

        document = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        entries = document["dataset"]["workspace"]["files"]
        sources = {
            entry["dest"]: entry["source"] for entry in entries if isinstance(entry, dict)
        }
        self.assertEqual(
            sources,
            {
                "opencode.jsonc": "eval-snapshot/opencode.jsonc",
                ".opencode/agents": "eval-snapshot/agents",
            },
        )
        strings = [entry for entry in entries if isinstance(entry, str)]
        self.assertEqual(tuple(strings), SEED_NAMES)
        # The staging surface (not the prose) carries no evaluation-only companion
        # and no external source root.
        pinned_surface = json.dumps(document["dataset"]["workspace"])
        for absent in (
            "worker-budget",
            "policies",
            "plugins",
            "observer",
            "bootstrap",
            "answers.yaml",
            ".config/opencode",
        ):
            self.assertNotIn(absent, pinned_surface)
        self.assertNotIn("plugin_dirs", json.dumps(document["runner"]))
        for source in sources.values():
            self.assertTrue(source.startswith("eval-snapshot/"), source)

    # --- preparation ------------------------------------------------------

    def test_prepare_writes_two_reproducible_arms_without_launching_anything(self):
        # A prepared experiment is a pure file operation: any process launch is a bug.
        with mock.patch(
            "subprocess.run",
            side_effect=AssertionError("preparation must not launch a process"),
        ):
            baseline, candidate, out, experiment = self._prepare()

        self.assertEqual(experiment["schema_version"], 1)
        self.assertEqual(set(experiment["arms"]), {"baseline", "candidate"})
        arms = experiment["arms"]
        self.assertNotEqual(arms["baseline"]["snapshot_id"], arms["candidate"]["snapshot_id"])
        self.assertEqual(arms["baseline"]["nonarm_sha256"], arms["candidate"]["nonarm_sha256"])
        self.assertEqual(arms["baseline"]["nonarm_sha256"], experiment["nonarm_sha256"])
        self.assertNotEqual(arms["baseline"]["config_sha256"], arms["candidate"]["config_sha256"])

        for arm in ("baseline", "candidate"):
            with self.subTest(arm=arm):
                arm_dir = out / arm
                manifest = self.builder.verify_snapshot(arm_dir / "snapshot")
                self.assertEqual(arms[arm]["snapshot_id"], manifest["snapshot_id"])
                self.assertEqual(arms[arm]["manifest"], f"{arm}/snapshot/manifest.json")
                config_path = out / arms[arm]["config"]
                self.assertEqual(config_path, arm_dir / "eval.agent-definition.yaml")
                self.assertEqual(
                    arms[arm]["config_sha256"],
                    hashlib.sha256(config_path.read_bytes()).hexdigest(),
                )
                for role in ARM_ROLES:
                    generated = (arm_dir / "snapshot" / "agents" / f"{role}.md").read_text()
                    self.assertIn(f"model: {self.builder.ILLUSIONIST}\n", generated)
                    self.assertIn(f"{role} prompt body for {arm}\n", generated)
                self.assertTrue((arm_dir / "snapshot" / "opencode.jsonc").is_file())

        dataset = experiment["dataset"]
        self.assertEqual(dataset["path"], "cases/worker-budget-v1")
        self.assertEqual(
            dataset["case_ids"],
            ["failing-test-debug", "publication-dry-run", "reviewer-unchanged-handoff", "small-edit"],
        )
        self.assertEqual(len(dataset["content_sha256"]), 64)
        pinned = experiment["pinned"]
        self.assertEqual(pinned["runner_argv"], PINNED_ARGV)
        self.assertEqual(pinned["model"], "agentgateway/illusionist")
        self.assertEqual(pinned["judge"], {"module": "agent_workflow_checks", "function": "judge_scenario"})

        text = (out / "experiment.json").read_text(encoding="utf-8")
        # No absolute path, HOME, timestamp or machine-specific state.
        self.assertNotIn(str(out), text)
        self.assertNotIn(str(Path.home()), text)
        self.assertNotIn(str(baseline), text)
        self.assertNotIn("timestamp", text)
        self.assertNotIn("created", text)
        self.assertEqual(json.loads(text), experiment)

        # Preparing the same inputs elsewhere keeps the location-independent
        # identity byte-identical: snapshot manifests, dataset hash, non-arm hash
        # and pinned metadata. `config_sha256` is per-location by design because a
        # prepared config embeds its arm snapshot's absolute path.
        _, _, out_again, experiment_again = self._prepare(out_name="exp-again")
        for arm in ("baseline", "candidate"):
            self.assertEqual(
                (out / arm / "snapshot" / "manifest.json").read_bytes(),
                (out_again / arm / "snapshot" / "manifest.json").read_bytes(),
            )
            self.assertEqual(
                experiment["arms"][arm]["snapshot_id"],
                experiment_again["arms"][arm]["snapshot_id"],
            )
            self.assertEqual(
                (out / arm / "eval.agent-definition.yaml")
                .read_text(encoding="utf-8")
                .replace(str((out / arm / "snapshot").resolve()), "<snapshot>")
                .replace(str((out / "dataset").resolve()), "<dataset>"),
                (out_again / arm / "eval.agent-definition.yaml")
                .read_text(encoding="utf-8")
                .replace(str((out_again / arm / "snapshot").resolve()), "<snapshot>")
                .replace(str((out_again / "dataset").resolve()), "<dataset>"),
            )
        for key in ("dataset", "nonarm_sha256", "pinned", "schema_version"):
            self.assertEqual(experiment[key], experiment_again[key], key)

    def test_same_content_sources_prepare_identical_arms(self):
        """Identical source bytes at different locations are one content, one arm.

        This is a same-content smoke pair only: equal generated `files_sha256`
        maps mean the two arms cannot support an efficacy comparison (that
        eligibility state belongs to the saved-run comparison, Task 3).
        """
        first = _arm_source(self.root / "one" / "agents", marker="same")
        second = _arm_source(self.root / "deep" / "two" / "agents", marker="same")
        out = self.root / "same-content"
        experiment = self.definition.prepare_arms(first, second, out)
        arms = experiment["arms"]
        self.assertEqual(arms["baseline"]["snapshot_id"], arms["candidate"]["snapshot_id"])
        self.assertEqual(arms["baseline"]["nonarm_sha256"], arms["candidate"]["nonarm_sha256"])
        baseline_files = self.builder.verify_snapshot(out / "baseline" / "snapshot")
        candidate_files = self.builder.verify_snapshot(out / "candidate" / "snapshot")
        self.assertEqual(baseline_files["files_sha256"], candidate_files["files_sha256"])

        def _without_snapshot_paths(arm: str) -> str:
            text = (out / arm / "eval.agent-definition.yaml").read_text(encoding="utf-8")
            return text.replace(str((out / arm / "snapshot").resolve()), "<snapshot>")

        # The only difference left is which arm directory holds the snapshot.
        self.assertEqual(_without_snapshot_paths("baseline"), _without_snapshot_paths("candidate"))
        self.assertNotEqual(arms["baseline"]["config_sha256"], arms["candidate"]["config_sha256"])

    def test_prepare_refuses_unsafe_destinations_and_untrusted_sources(self):
        baseline = _arm_source(self.root / "src-baseline", marker="baseline")
        candidate = _arm_source(self.root / "src-candidate", marker="candidate")
        definition = self.definition

        nonempty = self.root / "nonempty-out"
        nonempty.mkdir()
        sentinel = nonempty / "keep.txt"
        sentinel.write_text("previous experiment\n", encoding="utf-8")
        with self.assertRaises(definition.PreparationError) as caught:
            definition.prepare_arms(baseline, candidate, nonempty)
        self.assertIn("not empty", str(caught.exception))
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "previous experiment\n")
        self.assertEqual(sorted(p.name for p in nonempty.iterdir()), ["keep.txt"])

        out_as_file = self.root / "out-is-a-file"
        out_as_file.write_text("nope\n", encoding="utf-8")
        with self.assertRaises(definition.PreparationError) as caught:
            definition.prepare_arms(baseline, candidate, out_as_file)
        self.assertIn("not a directory", str(caught.exception))

        with self.assertRaises(definition.PreparationError) as caught:
            definition.prepare_arms(baseline, baseline, self.root / "same-source")
        self.assertIn("same directory", str(caught.exception))
        self.assertFalse((self.root / "same-source").exists())

        missing = _arm_source(self.root / "src-missing", marker="candidate")
        (missing / "architect.md").unlink()
        out = self.root / "out-missing"
        with self.assertRaises(definition.PreparationError) as caught:
            definition.prepare_arms(baseline, missing, out)
        self.assertIn("missing source agent", str(caught.exception))
        self.assertFalse(out.exists())

        ambiguous = _arm_source(self.root / "src-ambiguous", marker="candidate")
        worker = ambiguous / "worker.md"
        worker.write_text(
            worker.read_text(encoding="utf-8").replace(
                "model: agentgateway/architect", "model: one/model\nmodel: two/model"
            ),
            encoding="utf-8",
        )
        out = self.root / "out-ambiguous"
        with self.assertRaises(definition.PreparationError) as caught:
            definition.prepare_arms(baseline, ambiguous, out)
        self.assertIn("exactly one frontmatter model line", str(caught.exception))
        self.assertFalse(out.exists())

    def test_arm_configs_differ_only_in_snapshot_locations(self):
        baseline, candidate, out, experiment = self._prepare()
        documents = {
            arm: yaml.safe_load((out / arm / "eval.agent-definition.yaml").read_text())
            for arm in ("baseline", "candidate")
        }
        baseline_flat = _flatten(documents["baseline"])
        candidate_flat = _flatten(documents["candidate"])
        differing = {
            key
            for key in set(baseline_flat) | set(candidate_flat)
            if baseline_flat.get(key) != candidate_flat.get(key)
        }
        self.assertEqual(
            differing,
            {
                "dataset.workspace.files[0].source",
                "dataset.workspace.files[1].source",
                "runner.plugin_dirs[0]",
            },
        )
        self.assertEqual(
            documents["baseline"]["dataset"]["path"],
            documents["candidate"]["dataset"]["path"],
        )
        self.assertEqual(
            documents["baseline"]["runner"]["plugin_dirs"],
            [str((out / "baseline" / "snapshot").resolve())],
        )
        self.assertEqual(
            self.definition.normalized_config_document(documents["baseline"]),
            self.definition.normalized_config_document(documents["candidate"]),
        )
        self.assertEqual(
            self.definition.nonarm_config_hash(documents["baseline"]),
            self.definition.nonarm_config_hash(documents["candidate"]),
        )
        # The reference template has the same non-arm remainder: prepared configs
        # differ from it only in snapshot/dataset locations.
        self.assertEqual(
            self.definition.nonarm_config_hash(
                yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
            ),
            experiment["nonarm_sha256"],
        )

    # --- staging and cwd independence -------------------------------------

    def test_generated_config_resolves_from_home_and_project_cwd(self):
        _, _, out, experiment = self._prepare()
        for config_path, cwd in (
            (out / "baseline" / "eval.agent-definition.yaml", Path.home()),
            (out / "candidate" / "eval.agent-definition.yaml", PROJECT),
        ):
            with self.subTest(cwd=str(cwd)):
                target = self.root / f"materialized-{cwd.name}-{config_path.parent.name}"
                code = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from agent_eval.config import EvalConfig
from agent_eval.workspace_provisioning import materialize_shared_files

config = EvalConfig.from_yaml(sys.argv[3])
target = Path(sys.argv[4])
target.mkdir(parents=True)
materialize_shared_files(target, config)
print(json.dumps({
    "cwd": str(Path.cwd()),
    "dataset_ok": config.resolve_path(config.dataset.path).is_dir(),
    "files": sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file()
    ),
    "class": type(config).__name__,
}))
"""
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        code,
                        str(HARNESS),
                        str(SCRIPTS),
                        str(config_path),
                        str(target),
                    ],
                    cwd=cwd,  # explicit caller cwd: HOME or the eval project
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                staged = json.loads(completed.stdout)
                self.assertEqual(staged["cwd"], str(cwd))
                self.assertEqual(staged["class"], "EvalConfig")
                self.assertIs(staged["dataset_ok"], True)
                self.assertIn("opencode.jsonc", staged["files"])
                for role in ARM_ROLES:
                    self.assertIn(f".opencode/agents/{role}.md", staged["files"])
                self.assertFalse(
                    [name for name in staged["files"] if name.startswith(".opencode/policies")]
                )
                self.assertFalse(
                    [name for name in staged["files"] if name.startswith(".opencode/plugins")]
                )
        self.assertEqual(experiment["arms"]["baseline"]["config"], "baseline/eval.agent-definition.yaml")

    def _pinned_workspace(self, tmp_root: Path, config_path: Path, run_id: str):
        """Delegate to the module-level pinned workspace/materializer driver."""
        return _pinned_workspace(self, tmp_root, config_path, run_id)

    def test_pinned_runner_selects_exactly_four_cases_for_both_arms(self):
        """The runner itself selects four cases: no manual `--cases`/list filter.

        The prepared dataset copy is what makes the runtime selection correct. Any
        non-case directory in the source dataset (a deferred research ``bootstrap/``
        staging dir, or the synthetic one covered elsewhere) would be enumerated as
        a case by the pinned selector, so the generated config points at the
        verified four-case copy. This test drives the pinned selector and
        materializer for both arms, then runs the real workspace -> collect ->
        load -> neutral judge path.
        """
        _, _, out, _ = self._prepare()
        native = _native()
        trusted_hash = self.definition.dataset_content_hash()
        runs = self.root / "runs"
        runs.mkdir()
        for arm in ("baseline", "candidate"):
            with self.subTest(arm=arm):
                config_path = out / arm / "eval.agent-definition.yaml"
                config = native.EvalConfig.from_yaml(str(config_path))
                dataset_dir = config.resolve_path(config.dataset.path)
                self.assertEqual(dataset_dir.resolve(), (out / "dataset").resolve())
                self.assertEqual(
                    self.definition.dataset_content_hash(dataset_dir)["content_sha256"],
                    trusted_hash["content_sha256"],
                )
                self.assertFalse((dataset_dir / "bootstrap").exists())

                workspace, order = self._pinned_workspace(
                    self.root, config_path, f"synthetic-{arm}"
                )
                ids = [entry["case_id"] for entry in order]
                self.assertEqual(ids, sorted(CASE_IDS))
                self.assertNotIn("bootstrap", ids)

                for case_id in CASE_IDS:
                    case_ws = workspace / "cases" / case_id
                    self.assertTrue((case_ws / "opencode.jsonc").is_file())
                    for role in ARM_ROLES:
                        self.assertTrue(
                            (case_ws / ".opencode" / "agents" / f"{role}.md").is_file()
                        )
                    staged = {
                        path.relative_to(case_ws).as_posix()
                        for path in case_ws.rglob("*")
                        if path.is_file()
                        and ".git/" not in path.relative_to(case_ws).as_posix()
                    }
                    # Native harness staging keeps input.yaml; evaluation metadata
                    # and budget/observer research staging are never staged.
                    self.assertIn("input.yaml", staged)
                    self.assertNotIn("answers.yaml", staged)
                    self.assertNotIn("annotations.yaml", staged)
                    self.assertFalse([name for name in staged if "policies" in name])
                    self.assertFalse([name for name in staged if "plugins" in name])
                    self.assertFalse([name for name in staged if "worker-budget" in name])
                    self.assertFalse([name for name in staged if "bootstrap" in name])
                    for seed in SEED_NAMES:
                        if (CASES / case_id / seed).is_file():
                            self.assertIn(seed, staged)

                collected = self.root / f"collected-{arm}"
                native.collect(workspace, collected, config)
                for case_id in CASE_IDS:
                    record = native.load_record(
                        collected / "cases" / case_id, config, runs_dir=runs
                    )
                    outcome = _neutral().score_record(outputs=record)
                    # Untouched seeded state is a trustworthy negative, not unscorable.
                    self.assertEqual(outcome["status"], "fail", outcome["reasons"])

                # The run dataset is the prepared copy; the judged dataset stays the
                # trusted in-project path.
                self.assertEqual(
                    config.judges[0].arguments,
                    {"dataset_root": "cases/worker-budget-v1"},
                )

    # --- prepared dataset copy --------------------------------------------

    def test_prepared_dataset_is_a_verified_four_case_byte_copy(self):
        trusted = self.definition.dataset_content_hash()
        trusted_files = {
            path.relative_to(CASES).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(CASES.rglob("*"))
            if path.is_file()
            and path.relative_to(CASES).parts[0] not in {"bootstrap", "__pycache__"}
            and not path.name.endswith((".pyc", ".pyo"))
        }
        _, _, out, experiment = self._prepare()
        prepared = out / "dataset"
        copied = {
            path.relative_to(prepared).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(prepared.rglob("*"))
            if path.is_file()
        }
        # Byte-identical to the trusted metadata/seed set, real copies (never
        # links), only the four case directories, no `bootstrap/` staging.
        self.assertEqual(copied, trusted_files)
        self.assertFalse((prepared / "bootstrap").exists())
        self.assertEqual(
            sorted(entry.name for entry in prepared.iterdir() if entry.is_dir()),
            sorted(CASE_IDS),
        )
        for path in prepared.rglob("*"):
            self.assertFalse(path.is_symlink(), str(path))
        self.assertEqual(
            experiment["dataset"]["content_sha256"], trusted["content_sha256"]
        )
        self.assertEqual(
            self.definition.dataset_content_hash(prepared)["content_sha256"],
            trusted["content_sha256"],
        )
        # Excluded research staging is proven with a SYNTHETIC `bootstrap/`
        # directory: a fresh checkout has no real one, and no test may require a
        # deferred module or directory to exist. An unfiltered pinned enumeration
        # would select it as a fifth case, which is why arms point at the copy.
        synthetic = self.root / "dataset-with-synthetic-bootstrap"
        shutil.copytree(CASES, synthetic)
        (synthetic / "bootstrap").mkdir(exist_ok=True)
        (synthetic / "bootstrap" / "synthetic-observer.ts").write_text(
            "// synthetic: not a real deferred module\n", encoding="utf-8"
        )
        self.assertEqual(
            self.definition.dataset_content_hash(synthetic)["content_sha256"],
            trusted["content_sha256"],
        )
        staged = self.root / "staged-synthetic"
        self.definition.stage_prepared_dataset(synthetic, staged)
        self.assertFalse((staged / "bootstrap").exists())
        self.assertEqual(
            sorted(entry.name for entry in staged.iterdir() if entry.is_dir()),
            sorted(CASE_IDS),
        )
        # The trusted dataset was not written while preparing.
        self.assertEqual(
            self.definition.dataset_content_hash()["content_sha256"],
            trusted["content_sha256"],
        )

    def test_refused_prepare_leaves_published_experiment_untouched(self):
        _, _, out, _ = self._prepare()
        before = {
            path.relative_to(out).as_posix(): path.read_bytes()
            for path in out.rglob("*")
            if path.is_file()
        }
        baseline = _arm_source(self.root / "again-baseline-src", marker="baseline")
        candidate = _arm_source(self.root / "again-candidate-src", marker="candidate")
        with self.assertRaises(self.definition.PreparationError) as caught:
            self.definition.prepare_arms(baseline, candidate, out)
        self.assertIn("not empty", str(caught.exception))
        after = {
            path.relative_to(out).as_posix(): path.read_bytes()
            for path in out.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_harness_only_dataset_fixtures_are_refused_not_dropped(self):
        dataset_copy = self.root / "dataset-with-harness-fixtures"
        shutil.copytree(CASES, dataset_copy)
        (dataset_copy / "small-edit" / "environment").mkdir()
        (dataset_copy / "small-edit" / "environment" / "setup.sh").write_text(
            "#!/bin/sh\n", encoding="utf-8"
        )
        (dataset_copy / "small-edit" / "task.toml").write_text("[task]\n", encoding="utf-8")
        baseline = _arm_source(self.root / "fixture-baseline-src", marker="baseline")
        candidate = _arm_source(self.root / "fixture-candidate-src", marker="candidate")
        out = self.root / "fixture-out"
        with self.assertRaises(self.definition.PreparationError) as caught:
            self.definition.prepare_arms(
                baseline, candidate, out, dataset_root=dataset_copy
            )
        self.assertIn("harness-only files", str(caught.exception))
        # Fail closed: no finished snapshot and no half-published experiment.
        self.assertFalse((out / "dataset").exists())
        self.assertFalse((out / "baseline").exists())
        self.assertFalse((out / "experiment.json").exists())
        self.assertEqual(sorted(out.iterdir()), [])

    # --- dataset identity -------------------------------------------------

    def test_dataset_hash_covers_metadata_and_seeds_but_not_bootstrap(self):
        original = self.definition.dataset_content_hash()
        self.assertEqual(
            original["case_ids"],
            ["failing-test-debug", "publication-dry-run", "reviewer-unchanged-handoff", "small-edit"],
        )
        self.assertGreater(original["files_sha256_count"], 0)

        copy_root = self.root / "dataset-copy"
        shutil.copytree(CASES, copy_root)
        self.assertEqual(
            self.definition.dataset_content_hash(copy_root)["content_sha256"],
            original["content_sha256"],
        )

        bootstrap = copy_root / "bootstrap" / "synthetic-arm.ts"
        bootstrap.parent.mkdir(exist_ok=True)
        bootstrap.write_text("// synthetic research staging\n", encoding="utf-8")
        (copy_root / "bootstrap" / "extra-observer.ts").write_text("//\n", encoding="utf-8")
        pycache = copy_root / "small-edit" / "__pycache__"
        pycache.mkdir()
        (pycache / "notes.cpython-312.pyc").write_bytes(b"\x00binary")
        self.assertEqual(
            self.definition.dataset_content_hash(copy_root)["content_sha256"],
            original["content_sha256"],
        )

        annotations = copy_root / "small-edit" / "annotations.yaml"
        annotations.write_text(
            annotations.read_text(encoding="utf-8") + "\n# note\n", encoding="utf-8"
        )
        changed_metadata = self.definition.dataset_content_hash(copy_root)["content_sha256"]
        self.assertNotEqual(changed_metadata, original["content_sha256"])

        seed = copy_root / "small-edit" / "notes.txt"
        seed.write_text(seed.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
        self.assertNotEqual(
            self.definition.dataset_content_hash(copy_root)["content_sha256"],
            changed_metadata,
        )

        empty = self.root / "not-a-dataset"
        empty.mkdir()
        with self.assertRaises(self.definition.PreparationError):
            self.definition.dataset_content_hash(empty)

    # --- CLI --------------------------------------------------------------

    def test_cli_prepare_prepares_arms_and_reports_refusals(self):
        baseline = _arm_source(self.root / "cli-baseline", marker="baseline")
        candidate = _arm_source(self.root / "cli-candidate", marker="candidate")
        out = self.root / "cli-out"
        command = [
            sys.executable,
            str(AGENT_DEFINITION_MODULE_PATH),
            "prepare",
            "--baseline-source",
            str(baseline),
            "--candidate-source",
            str(candidate),
            "--out",
            str(out),
        ]
        completed = subprocess.run(
            command,
            cwd=PROJECT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["experiment"], str(out / "experiment.json"))
        self.assertEqual(set(summary["arms"]), {"baseline", "candidate"})
        written = json.loads((out / "experiment.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["arms"]["baseline"], written["arms"]["baseline"]["snapshot_id"])
        self.assertEqual(summary["dataset_sha256"], written["dataset"]["content_sha256"])

        experiment_bytes = (out / "experiment.json").read_bytes()
        again = subprocess.run(
            command, cwd=PROJECT, capture_output=True, text=True, check=False
        )
        self.assertEqual(again.returncode, 2)
        self.assertIn("not empty", again.stderr)
        self.assertEqual((out / "experiment.json").read_bytes(), experiment_bytes)

        missing_argument = subprocess.run(
            [sys.executable, str(AGENT_DEFINITION_MODULE_PATH), "prepare", "--out", str(out)],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(missing_argument.returncode, 2)
        self.assertIn("--baseline-source", missing_argument.stderr)


def _write_json(path: Path, document) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


#: Distinguishes "use the pinned model" from an explicit absent/None record.
_UNSET = object()


class SavedRunComparisonTests(unittest.TestCase):
    """Task 3 slice: compare saved runs. Synthetic fixtures, entirely offline.

    The run directories here are **synthetic**: hand-written ``harness/``,
    ``collected/`` and ``provenance/`` artifacts shaped like saved runs. They are
    tool validation only. No model, agent, subprocess, SSE decoder or observer is
    involved, and an asserted ``pass`` outcome is a fixture end state, never an
    efficacy result.
    """

    def setUp(self):
        self.definition = _agent_definition()
        self.builder = _snapshot_builder()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.experiment_dir = self.root / "experiment"
        self.baseline_source = _arm_source(
            self.root / "baseline-src", marker="baseline"
        )
        self.candidate_source = _arm_source(
            self.root / "candidate-src", marker="candidate"
        )
        self.experiment = self.definition.prepare_arms(
            self.baseline_source, self.candidate_source, self.experiment_dir
        )
        self._runs = 0

    # --- saved-run fixtures ----------------------------------------------

    def _run(
        self,
        arm,
        *,
        outcomes="fixed",
        exit_codes=None,
        durations=None,
        token_usage=None,
        cost_usd=None,
        num_turns=None,
        provenance=True,
        config_text=None,
        dataset_sha256=None,
        case_ids=None,
        provenance_overrides=None,
        missing_case=None,
        metrics_json=None,
        malformed_result=False,
        experiment_dir=None,
        reverse=False,
        name=None,
        result_model=_UNSET,
    ):
        """Write one synthetic saved run and return its directory."""
        experiment_dir = Path(experiment_dir or self.experiment_dir)
        experiment = json.loads(
            (experiment_dir / "experiment.json").read_text(encoding="utf-8")
        )
        entry = experiment["arms"][arm]
        self._runs += 1
        run_dir = self.root / "runs" / (name or f"{arm}-run-{self._runs}")
        run_dir.mkdir(parents=True)
        ids = list(case_ids or experiment["dataset"]["case_ids"])
        order = list(reversed(ids)) if reverse else ids

        result = {
            "exit_code": 0,
            "duration_s": 0.0,
            "per_case": {},
        }
        harness_recorded_model = (
            experiment["pinned"]["model"] if result_model is _UNSET else result_model
        )
        if harness_recorded_model is not None:
            result["model"] = harness_recorded_model
        for case_id in order:
            result["per_case"][case_id] = {
                "exit_code": 0 if exit_codes is None else exit_codes.get(case_id, 0),
                "duration_s": None if durations is None else durations.get(case_id),
                "token_usage": (
                    None if token_usage is None else token_usage.get(case_id)
                ),
                "cost_usd": None if cost_usd is None else cost_usd.get(case_id),
                "num_turns": None if num_turns is None else num_turns.get(case_id),
                "error_class": None,
            }
        result_path = run_dir / "harness" / "run_result.json"
        result_path.parent.mkdir(parents=True)
        if malformed_result:
            result_path.write_text("{not json", encoding="utf-8")
        else:
            _write_json(result_path, result)

        for case_id in order:
            if case_id == missing_case:
                continue
            case_dir = run_dir / "collected" / "cases" / case_id
            (case_dir / "output").mkdir(parents=True)
            (case_dir / "output" / "stdout.log").write_text(
                "synthetic fixture stdout\n", encoding="utf-8"
            )
            # Empty events stay empty evidence: they must never upgrade counters.
            (case_dir / "events.json").write_text("[]", encoding="utf-8")
            decision = outcomes if isinstance(outcomes, str) else outcomes.get(case_id)
            if decision == "fixed":
                for relative, content in _fixed_edits()[case_id].items():
                    target = case_dir / "_modified" / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
            if metrics_json and case_id in metrics_json:
                (case_dir / "output" / "metrics.json").write_text(
                    metrics_json[case_id], encoding="utf-8"
                )

        if provenance:
            provenance_dir = run_dir / "provenance"
            provenance_dir.mkdir()
            (provenance_dir / "manifest.json").write_bytes(
                (
                    experiment_dir / arm / "snapshot" / "manifest.json"
                ).read_bytes()
            )
            saved_config = (
                config_text
                if config_text is not None
                else (experiment_dir / entry["config"]).read_text(encoding="utf-8")
            )
            (provenance_dir / "eval.agent-definition.yaml").write_text(
                saved_config, encoding="utf-8"
            )
            run_document = {
                "schema_version": 1,
                "arm": arm,
                "snapshot_id": entry["snapshot_id"],
                "config_sha256": entry["config_sha256"],
                "nonarm_sha256": entry["nonarm_sha256"],
                "dataset_content_sha256": (
                    dataset_sha256 or experiment["dataset"]["content_sha256"]
                ),
                "case_ids": list(ids),
                "model": experiment["pinned"]["model"],
            }
            if provenance_overrides:
                run_document.update(provenance_overrides)
            if provenance == "malformed":
                (provenance_dir / "run.json").write_text("{not json", encoding="utf-8")
            else:
                _write_json(provenance_dir / "run.json", run_document)
        return run_dir

    def _case(self, report, case_id):
        return next(row for row in report["cases"] if row["case_id"] == case_id)

    # --- state and outcome coverage --------------------------------------

    def test_verified_pair_reports_outcomes_and_measured_deltas_by_case_id(self):
        durations = dict(zip(CASE_IDS, (10.0, 11.0, 12.0, 13.0)))
        candidate_durations = dict(zip(CASE_IDS, (6.0, 9.0, 14.0, 19.0)))
        baseline = self._run(
            "baseline",
            durations=durations,
            token_usage={case_id: 100 for case_id in CASE_IDS},
            cost_usd={case_id: 0.5 for case_id in CASE_IDS},
            num_turns={case_id: 4 for case_id in CASE_IDS},
        )
        # Collected dirs are written in reverse order: pairing must use case ids.
        candidate = self._run(
            "candidate",
            durations=candidate_durations,
            token_usage={case_id: 90 for case_id in CASE_IDS},
            cost_usd={case_id: 0.4 for case_id in CASE_IDS},
            num_turns={case_id: 3 for case_id in CASE_IDS},
            reverse=True,
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["state"], self.definition.STATE_VERIFIED_COMPARABLE)
        self.assertEqual(report["state_reasons"], [])
        self.assertIsNone(report["efficacy"]["claim"])
        self.assertIsNone(report["efficacy"]["ranking"])
        self.assertEqual(report["coverage"]["expected_case_count"], 4)
        for arm in ("baseline", "candidate"):
            self.assertEqual(report["provenance"][arm]["status"], "verified_comparable")
            self.assertEqual(report["coverage"][arm]["observed_case_count"], 4)
            self.assertEqual(report["coverage"][arm]["missing_case_ids"], [])
            self.assertEqual(report["aggregate"][arm]["executions"]["completed"], 4)
            self.assertEqual(report["aggregate"][arm]["outcomes"]["pass"], 4)

        for case_id in CASE_IDS:
            row = self._case(report, case_id)
            self.assertEqual(row["baseline"]["outcome"], "pass")
            self.assertEqual(row["baseline"]["execution"], "completed")
            self.assertEqual(row["candidate"]["outcome"], "pass")
            self.assertEqual(row["candidate"]["execution"], "completed")

        expected_deltas = {
            case_id: candidate_durations[case_id] - durations[case_id]
            for case_id in CASE_IDS
        }
        elapsed = report["pairs"]["metrics"]["elapsed_seconds"]
        self.assertEqual(elapsed["availability"], "measured")
        self.assertEqual(elapsed["measured_pair_count"], 4)
        self.assertEqual(
            {entry["case_id"]: entry["delta"] for entry in elapsed["cases"]},
            expected_deltas,
        )
        self.assertEqual(elapsed["delta"], sum(expected_deltas.values()))
        self.assertEqual(report["pairs"]["metrics"]["token_usage"]["delta"], -40)
        self.assertEqual(report["aggregate"]["baseline"]["totals"]["elapsed_seconds"]["value"], 46.0)
        self.assertEqual(report["aggregate"]["candidate"]["totals"]["token_usage"]["value"], 360)

        # Procurements are never invented, even for four passing synthetic cases.
        self.assertEqual(report["procedure"]["status"], "not_measured")
        for field in self.definition.PROCEDURE_FIELDS:
            self.assertIsNone(report["procedure"][field])
        for absent in ("winner", "efficacy_claim", "ranking"):
            self.assertNotIn(absent, report)

    def test_pristine_baseline_has_no_completed_pairs_or_deltas(self):
        baseline = self._run(
            "baseline", outcomes="pristine", durations={c: 10.0 for c in CASE_IDS}
        )
        candidate = self._run(
            "candidate", outcomes="fixed", durations={c: 8.0 for c in CASE_IDS}
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        self.assertEqual(report["state"], self.definition.STATE_VERIFIED_COMPARABLE)
        self.assertEqual(report["aggregate"]["baseline"]["executions"]["completed"], 0)
        self.assertEqual(report["aggregate"]["baseline"]["outcomes"]["fail"], 4)
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["completed"], 4)
        for case_id in CASE_IDS:
            row = self._case(report, case_id)
            self.assertEqual(row["baseline"]["outcome"], "fail")
            self.assertEqual(row["baseline"]["execution"], "failed")
            self.assertEqual(row["candidate"]["outcome"], "pass")
        self.assertEqual(report["pairs"]["completed_pair_count"], 0)
        for metric_name, entry in report["pairs"]["metrics"].items():
            self.assertIsNone(entry["delta"], metric_name)
        self.assertIsNone(
            report["aggregate"]["baseline"]["per_completed_mean"]["elapsed_seconds"]["value"]
        )
        self.assertEqual(
            report["aggregate"]["baseline"]["per_completed_mean"]["elapsed_seconds"][
                "reason"
            ],
            "no_completed_cases",
        )
        self.assertIn("baseline:failed_or_unknown_execution", report["claim_blockers"])
        self.assertIsNone(report["efficacy"]["claim"])

    def test_passing_edit_from_failed_process_is_not_completed(self):
        candidate = self._run(
            "candidate",
            outcomes="fixed",
            exit_codes={case_id: 124 for case_id in CASE_IDS},
            durations={case_id: 180.0 for case_id in CASE_IDS},
        )
        baseline = self._run("baseline", outcomes="fixed")
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        for case_id in CASE_IDS:
            row = self._case(report, case_id)
            # The end state is still reported as observed ...
            self.assertEqual(row["candidate"]["outcome"], "pass")
            # ... but a timed-out process never completed the task.
            self.assertEqual(row["candidate"]["execution"], "failed")
            self.assertEqual(row["candidate"]["exit_code"], 124)
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["completed"], 0)
        self.assertEqual(report["pairs"]["completed_pair_count"], 0)
        for entry in report["pairs"]["metrics"].values():
            self.assertIsNone(entry["delta"])
        self.assertIn("candidate:failed_or_unknown_execution", report["claim_blockers"])
        self.assertIsNone(report["efficacy"]["claim"])

    def test_negative_or_noninteger_exit_status_is_never_completed(self):
        """Exit status is a signed integer status, not a nonnegative metric."""
        candidate = self._run(
            "candidate",
            outcomes="fixed",
            exit_codes={
                # The pinned harness records -1 for a spawn/timeout failure.
                "small-edit": -1,
                "failing-test-debug": 137,
                # A float, a bool and a missing value are malformed statuses.
                "reviewer-unchanged-handoff": 0.0,
                "publication-dry-run": True,
            },
        )
        baseline = self._run("baseline", outcomes="fixed")
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        expected = {
            "small-edit": (-1, "failed"),
            "failing-test-debug": (137, "failed"),
            "reviewer-unchanged-handoff": (None, "unknown"),
            "publication-dry-run": (None, "unknown"),
        }
        for case_id, (exit_code, execution) in expected.items():
            row = self._case(report, case_id)
            self.assertEqual(row["candidate"]["outcome"], "pass", case_id)
            self.assertEqual(row["candidate"]["exit_code"], exit_code, case_id)
            self.assertEqual(row["candidate"]["execution"], execution, case_id)
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["completed"], 0)
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["failed"], 2)
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["unknown"], 2)
        self.assertEqual(report["pairs"]["completed_pair_count"], 0)
        self.assertIn("candidate:failed_or_unknown_execution", report["claim_blockers"])
        self.assertIsNone(report["efficacy"]["claim"])

    def test_missing_exit_status_is_unknown_even_with_a_passing_end_state(self):
        candidate = self._run(
            "candidate",
            outcomes="fixed",
            exit_codes={case_id: None for case_id in CASE_IDS},
        )
        report = self.definition.compare_runs(
            self.experiment_dir, self._run("baseline"), candidate
        )

        for case_id in CASE_IDS:
            row = self._case(report, case_id)
            self.assertEqual(row["candidate"]["outcome"], "pass")
            self.assertIsNone(row["candidate"]["exit_code"])
            self.assertEqual(row["candidate"]["execution"], "unknown")
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["completed"], 0)
        self.assertEqual(report["pairs"]["completed_pair_count"], 0)

    def test_missing_case_is_reported_not_paired_or_totaled(self):
        candidate = self._run(
            "candidate",
            missing_case="small-edit",
            durations={case_id: 8.0 for case_id in CASE_IDS},
            token_usage={
                case_id: 90 for case_id in CASE_IDS if case_id != "small-edit"
            },
        )
        baseline = self._run(
            "baseline",
            durations={case_id: 10.0 for case_id in CASE_IDS},
            token_usage={case_id: 100 for case_id in CASE_IDS},
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        self.assertEqual(report["coverage"]["candidate"]["observed_case_count"], 3)
        self.assertEqual(report["coverage"]["candidate"]["missing_case_ids"], ["small-edit"])
        row = self._case(report, "small-edit")
        self.assertIsNone(row["candidate"]["outcome"])
        self.assertFalse(row["candidate"]["present"])
        self.assertEqual(row["candidate"]["execution"], "unknown")
        self.assertIn("missing_collected_case", row["candidate"]["reasons"])

        elapsed = report["pairs"]["metrics"]["token_usage"]
        self.assertIsNone(elapsed["delta"])
        self.assertEqual(elapsed["availability"], "measured_subset")
        self.assertEqual(elapsed["measured_pair_count"], 3)
        self.assertEqual(elapsed["expected_pair_count"], 4)
        total = report["aggregate"]["candidate"]["totals"]["token_usage"]
        self.assertIsNone(total["value"])
        self.assertEqual(total["availability"], "incomplete")
        self.assertEqual(total["measured_case_count"], 3)
        self.assertIn("candidate:incomplete_case_coverage", report["claim_blockers"])

    def test_unknown_metrics_never_become_zero_costs_or_bogus_deltas(self):
        baseline = self._run(
            "baseline", durations={case_id: 10.0 for case_id in CASE_IDS}
        )
        candidate = self._run(
            "candidate",
            durations={case_id: 8.0 for case_id in CASE_IDS},
            metrics_json={case_id: '{"token_usage": -5, "cost_usd": NaN}'
                          for case_id in CASE_IDS},
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        for case_id in CASE_IDS:
            metrics = self._case(report, case_id)["candidate"]["metrics"]
            for metric_name in ("token_usage", "cost_usd", "num_turns"):
                self.assertIsNone(metrics[metric_name]["value"], metric_name)
                self.assertEqual(metrics[metric_name]["availability"], "unknown")
            self.assertEqual(metrics["elapsed_seconds"]["availability"], "measured")
        for arm in ("baseline", "candidate"):
            total = report["aggregate"][arm]["totals"]["token_usage"]
            self.assertIsNone(total["value"])
            self.assertIsNone(report["aggregate"][arm]["totals"]["cost_usd"]["value"])
        self.assertIsNone(report["pairs"]["metrics"]["cost_usd"]["delta"])
        self.assertIsNone(report["aggregate"]["candidate"]["per_completed_mean"]["token_usage"]["value"])

    def test_reported_collected_metrics_are_measured_with_explicit_source(self):
        metrics = {
            case_id: json.dumps(
                {"token_usage": 1000, "cost_usd": 0.25, "num_turns": 5}
            )
            for case_id in CASE_IDS
        }
        run = self._run(
            "candidate", durations={c: 8.0 for c in CASE_IDS}, metrics_json=metrics
        )
        report = self.definition.compare_runs(
            self.experiment_dir, self._run("baseline"), run
        )
        row = self._case(report, "small-edit")
        tokens = row["candidate"]["metrics"]["token_usage"]
        self.assertEqual(tokens["value"], 1000)
        self.assertEqual(tokens["availability"], "measured")
        # A reported scalar stays a labelled scalar total, never a fake split.
        self.assertEqual(tokens["kind"], "token_total:reported_scalar")
        self.assertNotIn("input", tokens)
        self.assertNotIn("output", tokens)
        self.assertTrue(tokens["source"].endswith("output/metrics.json"))
        self.assertEqual(report["aggregate"]["candidate"]["totals"]["token_usage"]["value"], 4000)

    def test_harness_usage_mapping_is_compared_as_one_normalized_total(self):
        """Actual runner telemetry is ``{"input": N, "output": N}``, not a scalar."""
        baseline = self._run(
            "baseline",
            durations={c: 10.0 for c in CASE_IDS},
            token_usage={c: {"input": 60, "output": 40} for c in CASE_IDS},
        )
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            token_usage={c: {"input": 50, "output": 40} for c in CASE_IDS},
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        for case_id in CASE_IDS:
            row = self._case(report, case_id)
            for arm, expected in (("baseline", 100), ("candidate", 90)):
                tokens = row[arm]["metrics"]["token_usage"]
                self.assertEqual(tokens["value"], expected, (case_id, arm))
                self.assertEqual(tokens["availability"], "measured", (case_id, arm))
                # The mapping's components are summed into one labelled total;
                # no per-component value is invented or exposed.
                self.assertEqual(
                    tokens["kind"], "token_total:input_output_total", (case_id, arm)
                )
                self.assertTrue(tokens["source"].endswith(".token_usage"))
                self.assertNotIn("input", tokens)
                self.assertNotIn("output", tokens)

        pairs = report["pairs"]["metrics"]["token_usage"]
        self.assertEqual(pairs["availability"], "measured")
        self.assertEqual(pairs["delta"], -40)
        self.assertEqual(report["aggregate"]["baseline"]["totals"]["token_usage"]["value"], 400)
        self.assertEqual(report["aggregate"]["candidate"]["totals"]["token_usage"]["value"], 360)
        self.assertIn("verified_comparable", str(report["state"]))

    def test_partial_invalid_or_bool_usage_mapping_is_unknown_except_recorded_zero(self):
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            token_usage={
                "small-edit": {"input": 10},
                "failing-test-debug": {"input": 10, "output": True},
                "reviewer-unchanged-handoff": {"input": -1, "output": 5.0},
                "publication-dry-run": {"input": 0, "output": 0},
            },
        )
        report = self.definition.compare_runs(
            self.experiment_dir, self._run("baseline"), candidate
        )

        for case_id in (
            "small-edit",
            "failing-test-debug",
            "reviewer-unchanged-handoff",
        ):
            tokens = self._case(report, case_id)["candidate"]["metrics"]["token_usage"]
            self.assertIsNone(tokens["value"], case_id)
            self.assertEqual(tokens["availability"], "unknown", case_id)
            self.assertTrue(
                any(note.startswith("invalid_token_usage@") for note in tokens["notes"]),
                case_id,
            )
        zero = self._case(report, "publication-dry-run")["candidate"]["metrics"][
            "token_usage"
        ]
        self.assertEqual(zero["value"], 0)
        self.assertEqual(zero["availability"], "measured")
        total = report["aggregate"]["candidate"]["totals"]["token_usage"]
        self.assertIsNone(total["value"])
        self.assertEqual(total["availability"], "incomplete")
        self.assertEqual(total["measured_case_count"], 1)
        self.assertIsNone(report["pairs"]["metrics"]["token_usage"]["delta"])

    def test_disagreeing_usage_sources_conflict_instead_of_merging(self):
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            token_usage={c: {"input": 60, "output": 40} for c in CASE_IDS},
            metrics_json={c: json.dumps({"token_usage": 90}) for c in CASE_IDS},
        )
        report = self.definition.compare_runs(
            self.experiment_dir, self._run("baseline"), candidate
        )

        for case_id in CASE_IDS:
            tokens = self._case(report, case_id)["candidate"]["metrics"]["token_usage"]
            self.assertIsNone(tokens["value"], case_id)
            self.assertEqual(tokens["availability"], "conflicting", case_id)
            self.assertIn("conflicting_token_usage_sources", tokens["notes"], case_id)
            self.assertEqual(len(tokens["sources"]), 2, case_id)
        total = report["aggregate"]["candidate"]["totals"]["token_usage"]
        self.assertIsNone(total["value"])
        self.assertEqual(total["availability"], "unknown")
        self.assertIsNone(report["pairs"]["metrics"]["token_usage"]["delta"])

    def test_agreeing_usage_sources_keep_one_comparable_normalized_unit(self):
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            token_usage={c: {"input": 60, "output": 40} for c in CASE_IDS},
            metrics_json={
                c: json.dumps({"token_usage": {"input": 60, "output": 40}})
                for c in CASE_IDS
            },
        )
        report = self.definition.compare_runs(
            self.experiment_dir, self._run("baseline"), candidate
        )

        tokens = self._case(report, "small-edit")["candidate"]["metrics"]["token_usage"]
        self.assertEqual(tokens["value"], 100)
        self.assertEqual(tokens["kind"], "token_total:input_output_total")
        self.assertEqual(len(tokens["sources"]), 2)
        # Equivalent normalized units from two agreeing sources still aggregate.
        total = report["aggregate"]["candidate"]["totals"]["token_usage"]
        self.assertEqual(total["availability"], "measured")
        self.assertEqual(total["value"], 400)

    def test_mapping_total_and_reported_scalar_are_labelled_and_never_paired(self):
        baseline = self._run(
            "baseline",
            durations={c: 10.0 for c in CASE_IDS},
            token_usage={c: {"input": 60, "output": 40} for c in CASE_IDS},
        )
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            token_usage={c: 100 for c in CASE_IDS},
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        row = self._case(report, "small-edit")
        self.assertEqual(
            row["baseline"]["metrics"]["token_usage"]["kind"],
            "token_total:input_output_total",
        )
        self.assertEqual(
            row["candidate"]["metrics"]["token_usage"]["kind"],
            "token_total:reported_scalar",
        )
        # Both are totals, but different accounting shapes are not paired.
        pairs = report["pairs"]["metrics"]["token_usage"]
        self.assertIsNone(pairs["delta"])
        self.assertEqual(pairs["measured_pair_count"], 0)
        self.assertEqual(report["aggregate"]["baseline"]["totals"]["token_usage"]["value"], 400)
        self.assertEqual(report["aggregate"]["candidate"]["totals"]["token_usage"]["value"], 400)

    # --- provenance and comparability states -----------------------------

    def test_absent_provenance_is_unverified_with_outcomes_but_no_deltas(self):
        baseline = self._run("baseline", durations={c: 10.0 for c in CASE_IDS})
        candidate = self._run(
            "candidate", durations={c: 8.0 for c in CASE_IDS}, provenance=False
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)

        self.assertEqual(report["state"], self.definition.STATE_UNVERIFIED)
        self.assertIn("missing_run_provenance", report["provenance"]["candidate"]["reasons"])
        self.assertEqual(report["pairs"]["suppressed_by_state"], "unverified")
        for entry in report["pairs"]["metrics"].values():
            self.assertIsNone(entry["delta"])
            self.assertEqual(entry["availability"], "suppressed")
        for case_id in CASE_IDS:
            self.assertEqual(self._case(report, case_id)["candidate"]["outcome"], "pass")
        self.assertIsNone(report["efficacy"]["claim"])
        self.assertIn("unverified", report["claim_blockers"])

    def test_same_generated_content_is_a_smoke_pair_only(self):
        first = _arm_source(self.root / "smoke-a", marker="shared", model="provider/one")
        second = _arm_source(self.root / "smoke-b", marker="shared", model="provider/two")
        experiment_dir = self.root / "smoke-experiment"
        experiment = self.definition.prepare_arms(first, second, experiment_dir)
        self.assertNotEqual(
            experiment["arms"]["baseline"]["snapshot_id"],
            experiment["arms"]["candidate"]["snapshot_id"],
        )
        baseline = self._run(
            "baseline",
            durations={c: 10.0 for c in CASE_IDS},
            experiment_dir=experiment_dir,
        )
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            experiment_dir=experiment_dir,
        )
        report = self.definition.compare_runs(experiment_dir, baseline, candidate)

        self.assertEqual(report["state"], self.definition.STATE_SAME_CONTENT)
        self.assertEqual(
            report["state_reasons"], ["identical_generated_snapshot_files"]
        )
        self.assertEqual(
            report["experiment"]["arms"]["baseline"]["files_sha256"],
            report["experiment"]["arms"]["candidate"]["files_sha256"],
        )
        for metric_name, entry in report["pairs"]["metrics"].items():
            self.assertIsNone(entry["delta"], metric_name)
        self.assertIsNone(report["efficacy"]["claim"])
        self.assertIsNone(report["efficacy"]["ranking"])

    def test_different_config_or_dataset_is_incomparable(self):
        baseline = self._run("baseline", durations={c: 10.0 for c in CASE_IDS})
        prepared_config = (
            self.experiment_dir / "candidate" / "eval.agent-definition.yaml"
        ).read_text(encoding="utf-8")
        tampered = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            config_text=prepared_config + "# local config edit\n",
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, tampered)
        self.assertEqual(report["state"], self.definition.STATE_INCOMPARABLE)
        self.assertIn(
            "saved_config_bytes_do_not_match_run_json",
            report["provenance"]["candidate"]["reasons"],
        )

        other_dataset = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            dataset_sha256="0" * 64,
            name="candidate-other-dataset",
        )
        report = self.definition.compare_runs(
            self.experiment_dir, baseline, other_dataset
        )
        self.assertEqual(report["state"], self.definition.STATE_INCOMPARABLE)
        self.assertIn("dataset_mismatch", report["provenance"]["candidate"]["reasons"])
        self.assertIsNone(report["efficacy"]["claim"])

    def test_malformed_required_result_is_a_tool_error(self):
        baseline = self._run("baseline")
        candidate = self._run("candidate", malformed_result=True)
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self.definition.compare_runs(self.experiment_dir, baseline, candidate)
        self.assertIn("run_result.json", str(caught.exception))

        with self.assertRaises(self.definition.ComparisonError):
            self.definition.compare_runs(
                self.experiment_dir, baseline, self.root / "missing-run"
            )

    def test_malformed_provenance_stays_diagnostic_not_a_verdict(self):
        baseline = self._run("baseline")
        candidate = self._run("candidate", provenance="malformed")
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)
        self.assertEqual(report["state"], self.definition.STATE_UNVERIFIED)
        self.assertEqual(
            report["provenance"]["candidate"]["reasons"], ["malformed_run_provenance"]
        )
        self.assertEqual(self._case(report, "small-edit")["candidate"]["outcome"], "pass")

    def test_saved_provenance_manifest_is_validated_wholly_not_by_subset(self):
        # A partial manifest that still carries the two fields this tool reads is
        # not saved provenance: the whole document must validate.
        baseline = self._run("baseline", durations={c: 10.0 for c in CASE_IDS})
        candidate = self._run("candidate", durations={c: 8.0 for c in CASE_IDS})
        manifest_path = candidate / "provenance" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["source_sha256"]
        _write_json(manifest_path, manifest)
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)
        self.assertEqual(report["state"], self.definition.STATE_UNVERIFIED)
        self.assertEqual(
            report["provenance"]["candidate"]["reasons"], ["malformed_run_provenance"]
        )
        self.assertIsNone(report["efficacy"]["claim"])

    def test_saved_provenance_manifest_must_be_the_prepared_bytes(self):
        # A well-formed but different manifest (other source hashes, self-consistent
        # id) is not this arm's saved provenance even if its files map matches.
        baseline = self._run("baseline", durations={c: 10.0 for c in CASE_IDS})
        candidate = self._run("candidate", durations={c: 8.0 for c in CASE_IDS})
        manifest_path = candidate / "provenance" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_sha256"] = {
            role: "0" * 64 for role in manifest["source_sha256"]
        }
        manifest["snapshot_id"] = self.builder.snapshot_id(manifest)
        self.assertEqual(self.builder.validate_manifest(manifest), [])
        _write_json(manifest_path, manifest)
        run_path = candidate / "provenance" / "run.json"
        run_document = json.loads(run_path.read_text(encoding="utf-8"))
        run_document["snapshot_id"] = manifest["snapshot_id"]
        _write_json(run_path, run_document)
        report = self.definition.compare_runs(self.experiment_dir, baseline, candidate)
        self.assertEqual(report["state"], self.definition.STATE_INCOMPARABLE)
        self.assertIn(
            "saved_manifest_not_prepared",
            report["provenance"]["candidate"]["reasons"],
        )

    # --- harness-recorded model identity (I4) ----------------------------

    def test_observed_run_model_must_match_the_pinned_model(self):
        baseline = self._run("baseline", durations={c: 10.0 for c in CASE_IDS})
        mismatched = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            result_model="otherprovider/other-model",
        )
        report = self.definition.compare_runs(self.experiment_dir, baseline, mismatched)

        self.assertEqual(report["state"], self.definition.STATE_INCOMPARABLE)
        self.assertIn(
            "run_model_mismatch", report["provenance"]["candidate"]["reasons"]
        )
        # provenance/run.json still self-asserts the pinned model; the
        # harness-recorded (configured) model identity — not runtime attestation —
        # is what makes the pair incomparable.
        self.assertEqual(
            report["provenance"]["candidate"]["model"], self.definition.MODEL
        )
        self.assertEqual(
            report["provenance"]["candidate"]["run_model"],
            "otherprovider/other-model",
        )
        self.assertEqual(
            report["inputs"]["runs"]["candidate"]["model"],
            "otherprovider/other-model",
        )
        self.assertEqual(report["pairs"]["suppressed_by_state"], "incomparable")
        self.assertIsNone(report["efficacy"]["claim"])

    def test_absent_observed_run_model_is_unverified_with_reason(self):
        baseline = self._run("baseline", durations={c: 10.0 for c in CASE_IDS})
        missing_model = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            result_model=None,
        )
        report = self.definition.compare_runs(
            self.experiment_dir, baseline, missing_model
        )
        self.assertEqual(report["state"], self.definition.STATE_UNVERIFIED)
        self.assertEqual(
            report["provenance"]["candidate"]["reasons"], ["run_model_missing"]
        )
        self.assertIsNone(report["provenance"]["candidate"]["run_model"])
        self.assertEqual(report["pairs"]["suppressed_by_state"], "unverified")

    def test_same_content_smoke_pair_still_requires_an_observed_model(self):
        first = _arm_source(
            self.root / "smoke-model-a", marker="shared", model="provider/one"
        )
        second = _arm_source(
            self.root / "smoke-model-b", marker="shared", model="provider/two"
        )
        experiment_dir = self.root / "smoke-model-experiment"
        self.definition.prepare_arms(first, second, experiment_dir)
        baseline = self._run(
            "baseline",
            durations={c: 10.0 for c in CASE_IDS},
            experiment_dir=experiment_dir,
        )
        unverified = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            experiment_dir=experiment_dir,
            result_model=None,
        )
        report = self.definition.compare_runs(experiment_dir, baseline, unverified)
        self.assertEqual(report["state"], self.definition.STATE_UNVERIFIED)

        verified = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            experiment_dir=experiment_dir,
            name="smoke-model-candidate-observed",
        )
        report = self.definition.compare_runs(experiment_dir, baseline, verified)
        self.assertEqual(report["state"], self.definition.STATE_SAME_CONTENT)
        self.assertEqual(
            report["state_reasons"], ["identical_generated_snapshot_files"]
        )

    def test_zero_completions_and_no_measurements_produce_no_deltas(self):
        both_failed = {
            "baseline": self._run(
                "baseline", exit_codes={c: 1 for c in CASE_IDS}
            ),
            "candidate": self._run(
                "candidate", exit_codes={c: 1 for c in CASE_IDS}
            ),
        }
        report = self.definition.compare_runs(
            self.experiment_dir, both_failed["baseline"], both_failed["candidate"]
        )
        self.assertEqual(report["pairs"]["completed_pair_count"], 0)
        for arm in ("baseline", "candidate"):
            aggregate = report["aggregate"][arm]
            self.assertEqual(aggregate["executions"]["completed"], 0)
            for metric_name, mean in aggregate["per_completed_mean"].items():
                self.assertIsNone(mean["value"], metric_name)
                self.assertEqual(mean["reason"], "no_completed_cases")
        for entry in report["pairs"]["metrics"].values():
            self.assertIsNone(entry["delta"])

    # --- CLI and report rendering ----------------------------------------

    def test_cli_compare_writes_deterministic_json_and_readable_markdown(self):
        baseline = self._run(
            "baseline",
            durations={c: 10.0 for c in CASE_IDS},
            token_usage={c: 100 for c in CASE_IDS},
        )
        candidate = self._run(
            "candidate",
            durations={c: 8.0 for c in CASE_IDS},
            token_usage={c: 90 for c in CASE_IDS},
        )
        outs = [self.root / "report-1", self.root / "report-2"]
        for out in outs:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = self.definition._main(
                    [
                        "compare",
                        "--experiment",
                        str(self.experiment_dir / "experiment.json"),
                        "--baseline-run",
                        str(baseline),
                        "--candidate-run",
                        str(candidate),
                        "--out",
                        str(out),
                    ]
                )
            self.assertEqual(code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["state"], "verified_comparable")
            self.assertEqual(summary["completed_pairs"], 4)
            self.assertEqual(summary["expected_cases"], 4)

        first = (outs[0] / "comparison.json").read_bytes()
        self.assertEqual(first, (outs[1] / "comparison.json").read_bytes())
        report = json.loads(first)
        for key in (
            "schema_version",
            "state",
            "efficacy",
            "experiment",
            "inputs",
            "provenance",
            "coverage",
            "cases",
            "aggregate",
            "pairs",
            "procedure",
        ):
            self.assertIn(key, report)
        self.assertEqual(report["schema_version"], 1)

        markdown = (outs[0] / "comparison.md").read_text(encoding="utf-8")
        self.assertEqual(markdown, (outs[1] / "comparison.md").read_text(encoding="utf-8"))
        self.assertIn("verified_comparable", markdown)
        self.assertIn("not_measured", markdown)
        self.assertIn("no efficacy or ranking claim", markdown)
        self.assertNotIn(str(self.root), markdown)

        nonempty = self.root / "report-nonempty"
        nonempty.mkdir()
        (nonempty / "keep.txt").write_text("keep\n", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = self.definition._main(
                [
                    "compare",
                    "--experiment",
                    str(self.experiment_dir),
                    "--baseline-run",
                    str(baseline),
                    "--candidate-run",
                    str(candidate),
                    "--out",
                    str(nonempty),
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("not empty", stderr.getvalue())
        self.assertEqual(sorted(p.name for p in nonempty.iterdir()), ["keep.txt"])


class ExperimentIntegrityTests(unittest.TestCase):
    """B1: dataset and staged-location integrity checked before anything is scored.

    The trusted dataset here is a **temp copy** of the checked-in cases, patched
    into the module global for this test only, so a deliberately corrupted fixture
    never touches the real case inputs. The synthetic arm sources and prepared
    experiment are disposable; no model, agent or subprocess runs.
    """

    def setUp(self):
        self.definition = _agent_definition()
        self.builder = _snapshot_builder()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.trusted = self.root / "trusted-dataset"
        shutil.copytree(CASES, self.trusted)
        original_root = self.definition.DATASET_ROOT
        self.addCleanup(setattr, self.definition, "DATASET_ROOT", original_root)
        self.definition.DATASET_ROOT = self.trusted
        self.experiment_dir = self.root / "experiment"
        self.experiment = self.definition.prepare_arms(
            _arm_source(self.root / "baseline-src", marker="baseline"),
            _arm_source(self.root / "candidate-src", marker="candidate"),
            self.experiment_dir,
            dataset_root=self.trusted,
        )
        self.recorded = self.experiment["dataset"]["content_sha256"]

    # --- helpers ----------------------------------------------------------

    def _load(self):
        return self.definition.load_experiment(self.experiment_dir)

    def _rewrite_arm_config(self, arm, mutate):
        """Edit one arm config and keep experiment.json's config hash truthful."""
        config_path = self.experiment_dir / self.experiment["arms"][arm]["config"]
        document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        mutate(document)
        text = self.definition.render_config(document)
        config_path.write_text(text, encoding="utf-8")
        experiment_path = self.experiment_dir / "experiment.json"
        experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
        experiment["arms"][arm]["config_sha256"] = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
        experiment_path.write_text(
            json.dumps(experiment, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    # --- dataset identity -------------------------------------------------

    def test_same_content_trusted_fixture_matches_recorded_identity(self):
        self.assertEqual(
            self.definition.dataset_content_hash(CASES)["content_sha256"],
            self.recorded,
        )
        self.assertEqual(
            self.definition.dataset_content_hash(self.trusted)["content_sha256"],
            self.recorded,
        )
        self.assertEqual(self._load()["dataset_sha256"], self.recorded)

    def test_prepared_dataset_annotation_mutation_fails_before_scoring(self):
        annotations = (
            self.experiment_dir / "dataset" / "small-edit" / "annotations.yaml"
        )
        annotations.write_text(
            annotations.read_text(encoding="utf-8") + "\n# mutated\n",
            encoding="utf-8",
        )
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("prepared dataset", str(caught.exception))

    def test_trusted_seed_mutation_fails_without_touching_real_cases(self):
        seed = self.trusted / "small-edit" / "notes.txt"
        seed.write_text(
            seed.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8"
        )
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("trusted dataset", str(caught.exception))
        # The checked-in case inputs are untouched by the patched fixture.
        self.assertEqual(
            self.definition.dataset_content_hash(CASES)["content_sha256"],
            self.recorded,
        )

    def test_missing_prepared_dataset_fails_closed(self):
        shutil.rmtree(self.experiment_dir / "dataset")
        with self.assertRaises(self.definition.ComparisonError):
            self._load()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_prepared_dataset_file_fails_closed(self):
        os.symlink(
            self.experiment_dir / "dataset" / "small-edit" / "notes.txt",
            self.experiment_dir / "dataset" / "small-edit" / "linked-notes.txt",
        )
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("symlink", str(caught.exception))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_trusted_case_directory_fails_closed(self):
        (self.trusted / "linked-case").symlink_to(
            self.trusted / "small-edit", target_is_directory=True
        )
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("symlink", str(caught.exception))

    # --- staged absolute locations ---------------------------------------

    def test_config_dataset_path_must_resolve_to_current_prepared_dataset(self):
        def mutate(document):
            document["dataset"]["path"] = str(CASES)

        self._rewrite_arm_config("candidate", mutate)
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("dataset.path", str(caught.exception))

    def test_config_snapshot_staging_source_must_name_this_arm(self):
        def mutate(document):
            for entry in document["dataset"]["workspace"]["files"]:
                if isinstance(entry, dict) and entry.get("dest") == ".opencode/agents":
                    entry["source"] = str(
                        self.experiment_dir / "baseline" / "snapshot" / "agents"
                    )

        self._rewrite_arm_config("candidate", mutate)
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("staging source", str(caught.exception))

    def test_config_plugin_dirs_must_name_this_arm_snapshot(self):
        def mutate(document):
            document["runner"]["plugin_dirs"] = [
                str(self.experiment_dir / "baseline" / "snapshot")
            ]

        self._rewrite_arm_config("candidate", mutate)
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self._load()
        self.assertIn("plugin_dirs", str(caught.exception))

    def test_copied_experiment_with_stale_absolute_paths_fails_closed(self):
        copied = self.root / "copied-experiment"
        shutil.copytree(self.experiment_dir, copied)
        with self.assertRaises(self.definition.ComparisonError) as caught:
            self.definition.load_experiment(copied)
        self.assertIn("dataset.path", str(caught.exception))


class EndToEndCliIntegrationTests(unittest.TestCase):
    """One real offline pipeline: prepare → pinned workspace → collect → compare CLI.

    This is the Task 3 acceptance integration test, and it is deliberately
    **partly synthetic**: the two agent-source directories, the reference-fixed
    edits and the saved ``harness/run_result.json`` process metadata are fixture
    inputs, marked ``synthetic`` in the saved artifacts and never produced by a
    model. Nothing is launched: no model, provider, network, ``opencode`` run or
    SSE/observer code is involved, and no efficacy statement is made.

    What is *real* is the pipeline: ``prepare_arms`` writes two distinct
    snapshot/config arms, the pinned ``workspace.py`` performs actual case
    discovery (four cases, no ``--cases`` filter) and materialization, the pinned
    ``_collect_per_case`` collects the edited workspaces, and the ``compare`` CLI
    entry point loads those artifacts through the pinned ``load_case_record`` and
    the neutral scorer to write ``comparison.json``/``comparison.md``.
    """

    def setUp(self):
        self.definition = _agent_definition()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.native = _native()

    def _saved_run(self, arm, run_dir, experiment_dir, experiment):
        """Write the explicitly synthetic saved-run shell around real artifacts."""
        (run_dir / "harness").mkdir(parents=True)
        # Process metadata is synthetic: no runner process executed. Exit codes
        # are recorded (0 = "the simulated arm finished"), while usage/cost/turns
        # stay null because nothing measured them.
        result = {
            "exit_code": 0,
            "duration_s": sum(self.DURATIONS[arm].values()),
            "model": experiment["pinned"]["model"],
            "synthetic": True,
            "per_case": {
                case_id: {
                    "exit_code": 0,
                    "duration_s": duration,
                    "token_usage": None,
                    "cost_usd": None,
                    "num_turns": None,
                    "error_class": None,
                }
                for case_id, duration in self.DURATIONS[arm].items()
            },
        }
        _write_json(run_dir / "harness" / "run_result.json", result)

        provenance = run_dir / "provenance"
        provenance.mkdir()
        entry = experiment["arms"][arm]
        # Saved copies of the prepared, real arm bytes: the only honest linkage.
        (provenance / "manifest.json").write_bytes(
            (experiment_dir / entry["manifest"]).read_bytes()
        )
        (provenance / "eval.agent-definition.yaml").write_bytes(
            (experiment_dir / entry["config"]).read_bytes()
        )
        _write_json(
            provenance / "run.json",
            {
                "schema_version": 1,
                "synthetic": True,
                "synthetic_note": (
                    "Tool-validation fixture: simulated edits and process "
                    "metadata, no agent or model was executed."
                ),
                "arm": arm,
                "snapshot_id": entry["snapshot_id"],
                "config_sha256": entry["config_sha256"],
                "nonarm_sha256": entry["nonarm_sha256"],
                "dataset_content_sha256": experiment["dataset"]["content_sha256"],
                "case_ids": list(experiment["dataset"]["case_ids"]),
                "model": experiment["pinned"]["model"],
            },
        )
        (run_dir / "SYNTHETIC.txt").write_text(
            "synthetic saved-run fixture: collected artifacts are real, the "
            "edits and process metadata are simulated; not experiment evidence\n",
            encoding="utf-8",
        )
        return run_dir

    def test_prepared_arms_run_the_real_offline_pipeline_and_compare_cli(self):
        baseline_source = _arm_source(self.root / "baseline-src", marker="baseline")
        candidate_source = _arm_source(self.root / "candidate-src", marker="candidate")
        experiment_dir = self.root / "experiment"
        experiment = self.definition.prepare_arms(
            baseline_source, candidate_source, experiment_dir
        )
        self.assertNotEqual(
            experiment["arms"]["baseline"]["snapshot_id"],
            experiment["arms"]["candidate"]["snapshot_id"],
        )
        fixed = _fixed_edits()

        runs = {}
        collected_dirs = {}
        for arm in ("baseline", "candidate"):
            with self.subTest(arm=arm):
                config_path = experiment_dir / experiment["arms"][arm]["config"]
                workspace, order = _pinned_workspace(
                    self, self.root, config_path, f"synthetic-e2e-{arm}"
                )
                # Real pinned discovery: four cases, bootstrap never selected.
                self.assertEqual([entry["case_id"] for entry in order], sorted(CASE_IDS))

                if arm == "candidate":
                    # Simulated reference fix of the simulated candidate arm. The
                    # baseline arm keeps the pristine seeds (a trusted negative).
                    for case_id, edits in fixed.items():
                        for relative, content in edits.items():
                            target = workspace / "cases" / case_id / relative
                            self.assertTrue(target.is_file(), target)
                            target.write_text(content, encoding="utf-8")

                config = self.native.EvalConfig.from_yaml(str(config_path))
                run_dir = self.root / "saved-runs" / f"synthetic-{arm}"
                collected = run_dir / "collected"
                self.native.collect(workspace, collected, config)
                self.assertTrue((collected / "collection.json").is_file())
                collected_dirs[arm] = collected
                for case_id in CASE_IDS:
                    self.assertTrue((collected / "cases" / case_id).is_dir(), case_id)
                    # No usage artifact exists: absent metrics must stay UNKNOWN.
                    self.assertFalse(
                        (collected / "cases" / case_id / "output" / "metrics.json").exists()
                    )
                runs[arm] = self._saved_run(arm, run_dir, experiment_dir, experiment)

        # The real collector observed exactly the simulated candidate edits.
        for case_id in CASE_IDS:
            self.assertFalse(
                (collected_dirs["baseline"] / "cases" / case_id / "_modified").exists()
            )
        for case_id, edits in fixed.items():
            modified = collected_dirs["candidate"] / "cases" / case_id / "_modified"
            self.assertEqual(
                sorted(p.relative_to(modified).as_posix() for p in modified.rglob("*") if p.is_file()),
                sorted(edits),
            )
            for relative, content in edits.items():
                self.assertEqual((modified / relative).read_text(encoding="utf-8"), content)

        before = {
            arm: sorted(p.relative_to(runs[arm]).as_posix() for p in runs[arm].rglob("*"))
            for arm in runs
        }
        out = self.root / "comparison"
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT / "agent_definition_eval.py"),
                "compare",
                "--experiment",
                str(experiment_dir / "experiment.json"),
                "--baseline-run",
                str(runs["baseline"]),
                "--candidate-run",
                str(runs["candidate"]),
                "--out",
                str(out),
            ],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "AGENT_WORKFLOWS_HARNESS": str(HARNESS),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["state"], "verified_comparable")
        self.assertEqual(summary["state_reasons"], [])
        self.assertEqual(summary["completed_pairs"], 0)
        self.assertEqual(summary["expected_cases"], 4)
        # Comparing saved artifacts is read-only with respect to both run dirs.
        for arm in runs:
            self.assertEqual(
                before[arm],
                sorted(p.relative_to(runs[arm]).as_posix() for p in runs[arm].rglob("*")),
            )

        report = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
        markdown = (out / "comparison.md").read_text(encoding="utf-8")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["state"], self.definition.STATE_VERIFIED_COMPARABLE)
        # Eligibility is verified, but a pristine baseline never completed a case,
        # so the tool records that blocker and still makes no claim.
        self.assertEqual(report["claim_blockers"], ["baseline:failed_or_unknown_execution"])

        self.assertIsNone(report["efficacy"]["claim"])
        self.assertIsNone(report["efficacy"]["ranking"])

        # Verified arm/config/dataset identities come from the prepared inputs.
        prepared = json.loads((experiment_dir / "experiment.json").read_text(encoding="utf-8"))
        self.assertEqual(report["coverage"]["expected_case_count"], 4)
        self.assertEqual(sorted(report["coverage"]["expected_case_ids"]), sorted(CASE_IDS))
        for arm in ("baseline", "candidate"):
            with self.subTest(arm=arm):
                self.assertEqual(
                    report["experiment"]["arms"][arm]["snapshot_id"],
                    prepared["arms"][arm]["snapshot_id"],
                )
                self.assertEqual(
                    report["experiment"]["arms"][arm]["config_sha256"],
                    prepared["arms"][arm]["config_sha256"],
                )
                self.assertEqual(report["provenance"][arm]["status"], "verified_comparable")
                self.assertEqual(report["provenance"][arm]["reasons"], [])
                self.assertEqual(
                    report["provenance"][arm]["dataset_content_sha256"],
                    prepared["dataset"]["content_sha256"],
                )
                self.assertEqual(report["coverage"][arm]["observed_case_count"], 4)
                self.assertEqual(report["coverage"][arm]["missing_case_ids"], [])

        # Known end-state difference; the baseline is a real pristine negative.
        self.assertEqual(report["aggregate"]["baseline"]["outcomes"]["fail"], 4)
        self.assertEqual(report["aggregate"]["baseline"]["outcomes"]["pass"], 0)
        self.assertEqual(report["aggregate"]["candidate"]["outcomes"]["pass"], 4)
        self.assertEqual(report["aggregate"]["candidate"]["executions"]["completed"], 4)
        for case_id in CASE_IDS:
            row = next(row for row in report["cases"] if row["case_id"] == case_id)
            self.assertEqual(row["baseline"]["outcome"], "fail")
            self.assertTrue(row["baseline"]["reasons"])
            self.assertEqual(row["baseline"]["execution"], "failed")
            self.assertEqual(row["candidate"]["outcome"], "pass")
            self.assertEqual(row["candidate"]["reasons"], [])
            self.assertEqual(row["candidate"]["execution"], "completed")
            self.assertEqual(row["candidate"]["exit_code"], 0)
            self.assertEqual(
                row["candidate"]["metrics"]["elapsed_seconds"]["availability"], "measured"
            )
            for metric in ("token_usage", "cost_usd", "num_turns"):
                with self.subTest(case=case_id, metric=metric):
                    entry = row["candidate"]["metrics"][metric]
                    self.assertEqual(entry["availability"], "unknown")
                    self.assertIsNone(entry["value"])

        # The baseline arm never completed a case, so the verified pair reports
        # coverage but NO paired deltas — for any metric, elapsed included.
        pairs = report["pairs"]
        self.assertEqual(pairs["expected_pair_count"], 4)
        self.assertEqual(pairs["completed_pair_count"], 0)
        for metric in ("elapsed_seconds", "token_usage", "cost_usd", "num_turns"):
            with self.subTest(metric=metric):
                entry = pairs["metrics"][metric]
                self.assertIsNone(entry["delta"])
                self.assertEqual(entry["availability"], "unknown")
                self.assertEqual(entry["measured_pair_count"], 0)
                self.assertIsNone(entry["source"])
        self.assertEqual(
            report["aggregate"]["baseline"]["per_completed_mean"]["elapsed_seconds"]["reason"],
            "no_completed_cases",
        )
        # Full-set elapsed totals are measured for both arms (exit 0 + recorded
        # durations), while usage totals remain unknown everywhere.
        self.assertEqual(
            report["aggregate"]["candidate"]["totals"]["elapsed_seconds"]["value"],
            sum(self.DURATIONS["candidate"].values()),
        )
        for arm in ("baseline", "candidate"):
            for metric in ("token_usage", "cost_usd", "num_turns"):
                with self.subTest(arm=arm, metric=metric):
                    total = report["aggregate"][arm]["totals"][metric]
                    self.assertIsNone(total["value"])
                    self.assertEqual(total["availability"], "unknown")

        # No procedure counters and no efficacy wording are ever invented.
        self.assertEqual(report["procedure"]["status"], "not_measured")
        for field in self.definition.PROCEDURE_FIELDS:
            self.assertIsNone(report["procedure"][field])
        self.assertIn("verified_comparable", markdown)
        self.assertIn("not_measured", markdown)
        self.assertIn("no efficacy or ranking claim", markdown)
        self.assertNotIn(str(self.root), markdown)
        self.assertNotIn(str(self.root), (out / "comparison.json").read_text(encoding="utf-8"))

    #: Synthetic per-case durations (seconds); only elapsed_seconds is measured.
    DURATIONS = {
        "baseline": dict(zip(CASE_IDS, (12.5, 13.5, 14.5, 15.5))),
        "candidate": dict(zip(CASE_IDS, (9.0, 10.0, 11.0, 12.0))),
    }


if __name__ == "__main__":
    unittest.main()
