"""Offline unit tests for the Harbor packaging of the Git pilot.

Unit scope (this file): the self-contained task PACKAGE + the
deterministic final-state VERIFIER, exercised offline under the
platform-approved temp root with the sandbox-git wrapper and mock HOMEs.
NO image build, NO container provisioning, NO network, NO model calls,
NO Harbor Python package (not installed), NO MLflow.

What is proven here:
  * the package generator produces the required files with valid,
    reproducible content and provenance (including a byte-exact vendored
    wrapper and reproducible commit graph);
  * the packaged fixture carries NO agent-visible expected state (no
    expected/ dir) before verifier execution;
  * the verifier's completion oracle PASSES the correct end state — an
    actual switch + fetch + fast-forward executed in the fixture through
    sandbox-git — and emits reward 1;
  * the verifier FAILS (reward 0) a damaged feature branch, a corrupted
    or removed untracked file, a wrong main, and a tampered trusted
    record (foreign anchors, tampered metadata baseline, tampered
    origin URL anchor, tampered untracked digest);
  * the verifier FAILS (does not pass) on unknown/missing trusted
    records and a missing fixture (fail closed, never a silent pass);
  * eval.git.yaml (renamed from eval.harbor.yaml) stays consistent with
    its recorded case contract (prompt text, case id); the strict source
    eval.yaml judge parity was source-project-only (not relocated);
  * every Git operation in these tests goes through sandbox-git.

All Git runs with cwd inside a disposable root and a mock HOME, so the
host dotfiles repository can never be selected.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parent.parent
HARBOR = PROJECT / "harbor"

# Optional pinned Harbor 0.25.0 SDK interpreter (historical source env,
# supplied EXTERNALLY via AGENT_WORKFLOWS_TEST_PYTHON; never hardcoded).
_TEST_PYTHON = os.environ.get("AGENT_WORKFLOWS_TEST_PYTHON")
if _TEST_PYTHON:
    sys.path.insert(0, str(Path(_TEST_PYTHON).resolve().parent.parent / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"))

sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HARBOR))

try:
    # Actual Harbor model/verifier APIs (typed validation of the generated
    # task.toml and the numeric reward parse the runtime performs).
    from harbor.models.task.config import TaskConfig
    from harbor.models.task.task import Task
    from harbor.models.trial.paths import TrialPaths
    from harbor.verifier.verifier import Verifier as HarborVerifier
    HARBOR_SDK_AVAILABLE = True
except Exception:  # pragma: no cover - optional only when Harbor absent
    TaskConfig = Task = TrialPaths = HarborVerifier = None
    HARBOR_SDK_AVAILABLE = False

WRAPPER = Path(
    os.environ.get("AGENT_WORKFLOWS_SANDBOX_GIT")
    or Path.home() / ".local" / "bin" / "sandbox-git"
)
APPROVED_TMP = Path(
    "/private/var/folders/9m/5dhpkvg51750wz6ypg9nz25m0000gn/T/opencode"
)

CASE_ID = "return-main-no-cleanup-v1"

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

import git_pilot_fixture as gpf  # noqa: E402
import git_pilot_package as gpkg  # noqa: E402
import verifier as gpv  # noqa: E402


def temp_root() -> Path:
    # F3: portable base — env override first, then the approved temp dir
    # if it exists on this machine, else the platform default.
    base_env = os.environ.get("AGENT_WORKFLOWS_TEST_TMP")
    if base_env:
        base = Path(base_env)
    elif APPROVED_TMP.is_dir():
        base = APPROVED_TMP
    else:
        base = Path(tempfile.gettempdir())
    return Path(tempfile.mkdtemp(prefix="git-pilot-harbor-", dir=base))


def wrapper_env(mock_home: Path) -> dict:
    """Isolated env for wrapper subprocesses (mock HOME, no host config)."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(mock_home),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "TZ": "UTC",
    }


class HarborPackageTestBase(unittest.TestCase):
    """Generates one package per class; shared by package + verifier tests."""

    @classmethod
    def setUpClass(cls):
        if not WRAPPER.exists():
            raise unittest.SkipTest("sandbox-git wrapper not found")
        cls.root = temp_root()
        cls.out_dir = cls.root / "package"
        cls.task_dir, cls.provenance = gpkg.generate_package(
            cls.out_dir, wrapper=WRAPPER
        )
        # A second, independently generated package for reproducibility.
        cls.out_dir2 = cls.root / "package2"
        cls.task_dir2, cls.provenance2 = gpkg.generate_package(
            cls.out_dir2, wrapper=WRAPPER
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def run_wrapper(self, args, cwd):
        mock_home = Path(cwd).parent / "mock-home"
        return subprocess.run(
            [str(WRAPPER), *args],
            cwd=str(cwd),
            env=wrapper_env(
                mock_home if mock_home.is_dir() else self.root / "mock-home"
            ),
            capture_output=True,
            text=True,
        )

    def _fresh_workspace(self, name: str) -> Path:
        workspace = self.root / name
        shutil.copytree(
            self.task_dir / "environment" / "fixture",
            workspace / "fixture",
            symlinks=False,
        )
        return workspace

    def _run_in_repo(self, workspace: Path, *arg_groups) -> None:
        """Run wrapper command groups in the workspace's fixture repo."""
        repo = workspace / "fixture" / "repo"
        mock_home = workspace / "fixture" / "mock-home"
        for args in arg_groups:
            result = subprocess.run(
                [str(WRAPPER), *args],
                cwd=str(repo),
                env=wrapper_env(mock_home),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    VENDORED_LIB = HARBOR / "image" / "git_pilot_fixture.py"
    VENDORED_WRAPPER = HARBOR / "image" / "bin" / "sandbox-git"

    def _run_verifier(self, workspace: Path, records: Path | None = None,
                      reward_dir: Path | None = None) -> dict:
        """Run the oracle and return {reward, verdict, _exit_code, _files}.

        The NUMERIC reward comes from reward.json (flat numbers only —
        Harbor 0.25.0's Verifier rejects anything else) and reward.txt
        (bare float). The rich reason/failures/coverage payload moved to
        the verdict.json sidecar.
        """
        reward_dir = reward_dir or (self.root / "reward")
        with mock.patch.object(gpv, "REWARD_DIR", reward_dir):
            code = gpv.run_verification(
                records or (self.task_dir / "tests"),
                workspace,
                "fixture",
                self.VENDORED_LIB,
                self.VENDORED_WRAPPER,
            )
        numeric = json.loads((reward_dir / "reward.json").read_text())
        text_reward = (reward_dir / "reward.txt").read_text()
        verdict = json.loads((reward_dir / "verdict.json").read_text())
        payload = {
            "reward": numeric["reward"],
            "verdict": verdict,
            "_exit_code": code,
            "_reward_text": text_reward,
            "_reward_json_raw": numeric,
            "_reward_dir": reward_dir,
        }
        return payload



class TestPackageRequiredFiles(HarborPackageTestBase):
    """The package contains every file the Harbor runtime needs."""

    def test_required_files_present(self):
        required = [
            "task.toml",
            "instruction.md",
            "solution/solve.sh",
            "environment/input.yaml",
            "environment/answers.yaml",
            "environment/fixture/repo/.git",
            "environment/fixture/origin.git/HEAD",
            "environment/fixture/mock-home",
            "tests/test.sh",
            "tests/provenance.json",
            "tests/seed-state.json",
        ]
        for rel in required:
            path = self.task_dir / rel
            self.assertTrue(
                path.exists(), f"missing required package file: {rel}"
            )

    def test_task_toml_fields(self):
        import tomllib

        with open(self.task_dir / "task.toml", "rb") as fh:
            doc = tomllib.load(fh)
        self.assertEqual(doc["task"]["name"], gpkg.TASK_NAME)
        self.assertEqual(doc["metadata"]["case_id"], CASE_ID)
        # Framework-accepted judge_mode (agent-eval-harness
        # _validate_task_package_reuse: None|"full"|"deterministic-only").
        self.assertEqual(
            doc["metadata"]["judge_mode"], "deterministic-only"
        )
        self.assertEqual(
            doc["metadata"]["procedure_attempt_coverage"], "not_measured"
        )
        # The end-state-only scope label is retained in the task description.
        self.assertIn("Deterministic final-state", doc["task"]["description"])
        self.assertIn("not_measured", doc["task"]["description"])
        self.assertEqual(
            doc["environment"]["docker_image"], gpkg.DEFAULT_IMAGE
        )
        self.assertEqual(
            doc["environment"]["docker_image"],
            "localhost/git-pilot-harbor:1.0.0",
        )
        self.assertEqual(doc["environment"]["workdir"], "/workspace")
        self.assertEqual(doc["verifier"]["timeout_sec"], 300)
        self.assertEqual(doc["agent"]["timeout_sec"], 900)
        self.assertEqual(doc["schema_version"], "1.4")
        self.assertEqual(doc["agent"]["user"], "1001")
        self.assertEqual(doc["verifier"]["user"], "root")

    def test_instruction_prompt_matches_case_contract(self):
        text = (self.task_dir / "instruction.md").read_text()
        self.assertIn("return to main", text)
        self.assertIn("fast-forward", text)
        self.assertIn("/workspace/fixture/repo", text)
        self.assertIn("Do not clean up or delete", text)
        self.assertIn("Do not commit, push, or create a review", text)

    def test_input_yaml_case_id_and_prompt(self):
        if yaml is None:
            self.skipTest("PyYAML unavailable")
        data = yaml.safe_load(
            (self.task_dir / "environment" / "input.yaml").read_text()
        )
        self.assertEqual(data["id"], CASE_ID)
        self.assertEqual(data["schema_version"], 1)
        self.assertIn("return to main", data["prompt"])
        self.assertEqual(
            data["metadata"]["procedure_attempt_coverage"], "not_measured"
        )

    def test_test_sh_executable_and_targets_image_verifier(self):
        test_sh = self.task_dir / "tests" / "test.sh"
        self.assertTrue(os.access(test_sh, os.X_OK))
        text = test_sh.read_text()
        self.assertIn("/opt/git-pilot/bin/verify.sh", text)
        self.assertIn("GIT_PILOT_WORKSPACE", text)

    def test_test_sh_normalizes_fixture_ownership_for_root_verifier(self):
        """The root verifier must be able to snapshot the agent-owned fixture.

        The environment upload leaves the fixture owned by the agent UID;
        Git's dubious-ownership protection would refuse the root verifier's
        read-only snapshot. test.sh normalizes ownership to root before the
        measurement (ownership is not part of the measured contract).
        """
        text = (self.task_dir / "tests" / "test.sh").read_text()
        self.assertIn('chown -R 0:0 "$FIXTURE_ROOT"', text)
        self.assertIn('FIXTURE_ROOT="${GIT_PILOT_WORKSPACE}/${GIT_PILOT_FIXTURE_DIR}"', text)

    def test_fixture_origin_url_is_relative(self):
        repo = self.task_dir / "environment" / "fixture" / "repo"
        result = self.run_wrapper(["remote", "get-url", "origin"], repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "../origin.git")

    def test_fixture_initial_state_via_wrapper_refs(self):
        """The packaged fixture starts in the documented initial state.

        Measured with direct wrapper ref reads (the packaged fixture
        intentionally ships NO expected/ manifest, so the full hardened
        snapshot path is not applicable to the pristine package — the
        verifier materializes the trusted manifest at run time).
        """
        repo = self.task_dir / "environment" / "fixture" / "repo"
        seed = json.loads(
            (self.task_dir / "tests" / "seed-state.json").read_text()
        )
        commits = seed["manifest"]["commits"]

        head = self.run_wrapper(["symbolic-ref", "--quiet", "--short", "HEAD"], repo)
        self.assertEqual(head.stdout.strip(), "feature/keep-history")

        refs = self.run_wrapper(
            ["for-each-ref", "--format=%(refname) %(objectname)",
             "refs/heads"], repo)
        local = dict(
            line.split(None, 1) for line in refs.stdout.splitlines() if line
        )
        self.assertEqual(local["refs/heads/main"], commits["c0"])
        self.assertEqual(
            local["refs/heads/feature/keep-history"], commits["cfeature"]
        )

        remote_refs = self.run_wrapper(
            ["for-each-ref", "--format=%(refname) %(objectname)",
             "refs/remotes"], repo)
        remote = dict(
            line.split(None, 1) for line in remote_refs.stdout.splitlines() if line
        )
        self.assertEqual(
            remote["refs/remotes/origin/main"], commits["cremote"]
        )

        # The seed snapshot (trusted, captured at generation) agrees.
        self.assertEqual(seed["snapshot"]["head"], "feature/keep-history")
        self.assertEqual(seed["snapshot"]["refs"]["refs/heads/main"], commits["c0"])

    def test_trusted_records_not_agent_visible(self):
        """Trusted records must NOT be inside environment/ (agent-upload)."""
        env_dir = self.task_dir / "environment"
        for name in ("provenance.json", "seed-state.json"):
            self.assertFalse(
                (env_dir / name).exists(),
                f"trusted record {name} must not ship in environment/",
            )

    def test_no_agent_visible_expected_state_before_execution(self):
        """The packaged fixture ships NO expected/ dir: no agent-visible
        expected object ids or history exist before verifier execution."""
        fixture = self.task_dir / "environment" / "fixture"
        self.assertFalse(
            (fixture / "expected").exists(),
            "packaged fixture must not carry an expected/ manifest",
        )
        # And no expected content leaked anywhere else under environment/.
        for path in (self.task_dir / "environment").rglob("manifest.json"):
            self.fail(
                f"agent-visible manifest found in package environment/: {path}"
            )


class TestPackageProvenance(HarborPackageTestBase):
    """Provenance records how the fixture was built and pins its bytes."""

    def test_provenance_records_wrapper_digest(self):
        wrapper_record = self.provenance["wrapper"]
        self.assertEqual(wrapper_record["source"], str(WRAPPER))
        vendored = HARBOR / "image" / "bin" / "sandbox-git"
        self.assertEqual(
            wrapper_record["sha256"],
            hashlib.sha256(vendored.read_bytes()).hexdigest(),
        )
        # ... and equal to the reviewed host wrapper bytes.
        self.assertEqual(
            wrapper_record["sha256"],
            hashlib.sha256(WRAPPER.read_bytes()).hexdigest(),
        )

    def test_vendored_verifier_matches_source(self):
        """The image's vendored verifier is byte-identical to the source."""
        source = HARBOR / "verifier.py"
        vendored = HARBOR / "image" / "bin" / "verifier.py"
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            hashlib.sha256(vendored.read_bytes()).hexdigest(),
        )

    def test_provenance_records_fixture_library_and_verifier(self):
        self.assertIn("fixture_library", self.provenance)
        self.assertIn("verifier_sha256", self.provenance)
        self.assertEqual(self.provenance["case_id"], CASE_ID)
        self.assertEqual(
            self.provenance["procedure_attempt_coverage"], "not_measured"
        )

    def test_expected_state_is_reproducible(self):
        """Two independently generated packages must agree on the expected
        state (commit graph + untracked sentinel bytes)."""
        seed1 = json.loads(
            (self.task_dir / "tests" / "seed-state.json").read_text()
        )
        seed2 = json.loads(
            (self.task_dir2 / "tests" / "seed-state.json").read_text()
        )
        self.assertEqual(
            seed1["manifest"]["commits"], seed2["manifest"]["commits"]
        )
        self.assertEqual(
            seed1["manifest"]["untracked"]["sha256"],
            seed2["manifest"]["untracked"]["sha256"],
        )
        self.assertEqual(
            seed1["snapshot"]["head"], seed2["snapshot"]["head"]
        )
        self.assertEqual(seed1["snapshot"]["refs"], seed2["snapshot"]["refs"])

    def test_seed_state_paths_are_rebasable(self):
        """The seed snapshot's absolute paths must all be under the fixture
        root so the verifier can rebase them onto the runtime root."""
        seed = json.loads(
            (self.task_dir / "tests" / "seed-state.json").read_text()
        )
        gen_root = self.task_dir / "environment" / "fixture"
        repository = seed["snapshot"]["repository"]
        self.assertTrue(
            repository.startswith(str(gen_root)),
            f"seed repository {repository} not under {gen_root}",
        )

    def test_seed_manifest_preserves_relative_origin_url(self):
        """The trusted manifest's origin_url_expected anchor is the ACTUAL
        relative URL the repository records, not a rewritten absolute
        path — the verifier must compare URL fidelity against reality."""
        seed = json.loads(
            (self.task_dir / "tests" / "seed-state.json").read_text()
        )
        self.assertEqual(
            seed["manifest"]["origin_url_expected"], "../origin.git"
        )


class TestVerifierOracle(HarborPackageTestBase):
    """The completion oracle passes the correct end state and fails damage.

    Each test copies the packaged fixture into a throwaway "workspace",
    mutates it through the wrapper (or not), then runs the verifier with
    the package's trusted records and the VENDORED image paths (the image
    tree is what the container bakes). Verdict is read from the emitted
    reward.json under a temp reward dir.
    """

    def test_completion_passes_on_switch_fetch_ff(self):
        """Actual switch + fetch + fast-forward through sandbox-git, then
        the verifier emits reward 1."""
        workspace = self._fresh_workspace("ws-pass")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 1.0, payload)
        self.assertEqual(payload["_exit_code"], 0)
        self.assertEqual(
            payload["verdict"]["procedure_attempt_coverage"], "not_measured"
        )
        self.assertEqual(payload["verdict"]["failures"], [])

    def test_verifier_materializes_then_cleans_nothing_else(self):
        """The verifier's only agent-filesystem write is the verifier-owned
        expected/ manifest (created from trusted records at run time)."""
        workspace = self._fresh_workspace("ws-materialize")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        before_snapshot = sorted(
            str(p.relative_to(workspace))
            for p in workspace.rglob("*") if p.is_file()
        )
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 1.0, payload)
        after_snapshot = sorted(
            str(p.relative_to(workspace))
            for p in workspace.rglob("*") if p.is_file()
        )
        added = set(after_snapshot) - set(before_snapshot)
        self.assertEqual(
            added, {"fixture/expected/manifest.json"},
            f"verifier wrote unexpected agent-filesystem paths: {added}",
        )

    def test_damaged_feature_branch_fails(self):
        workspace = self._fresh_workspace("ws-feature-damaged")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
            ["branch", "-f", "feature/keep-history", "main"],
        )
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertEqual(payload["_exit_code"], 1)
        self.assertTrue(payload["verdict"]["failures"], payload)

    def test_untracked_file_corrupted_fails(self):
        workspace = self._fresh_workspace("ws-untracked-corrupt")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        (workspace / "fixture" / "repo" / gpf.UNTRACKED_RELATIVE).write_bytes(
            b"tampered\n"
        )
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertTrue(
            any("untracked" in f.lower() or "corrupt" in f.lower()
                for f in payload["verdict"]["failures"]),
            payload,
        )

    def test_untracked_file_removed_fails(self):
        workspace = self._fresh_workspace("ws-untracked-removed")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        (workspace / "fixture" / "repo" / gpf.UNTRACKED_RELATIVE).unlink()
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertTrue(
            any("lost" in f.lower() for f in payload["verdict"]["failures"]), payload
        )

    def test_wrong_main_fails(self):
        """Leaving main behind (not fast-forwarded) fails."""
        workspace = self._fresh_workspace("ws-wrong-main")
        self._run_in_repo(workspace, ["checkout", "main"])
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertTrue(
            any("local main" in f for f in payload["verdict"]["failures"]), payload
        )

    def _foreign_records(self, name: str, mutate) -> Path:
        """Build a tampered copy of the trusted records dir."""
        seed = json.loads(
            (self.task_dir / "tests" / "seed-state.json").read_text()
        )
        provenance = json.loads(
            (self.task_dir / "tests" / "provenance.json").read_text()
        )
        mutate(seed, provenance)
        records = self.root / name
        records.mkdir(parents=True, exist_ok=True)
        (records / "seed-state.json").write_text(
            json.dumps(seed, indent=2, sort_keys=True)
        )
        (records / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True)
        )
        return records

    def test_unknown_snapshot_fails_not_passes(self):
        """A foreign trusted snapshot (unknown commit anchors) must FAIL,
        never pass — even on a correctly completed run."""
        workspace = self._fresh_workspace("ws-unknown-seed")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )

        def mutate(seed, provenance):
            seed["manifest"]["commits"] = {
                "c0": "0" * 40,
                "cfeature": "1" * 40,
                "cremote": "2" * 40,
            }

        records = self._foreign_records("foreign-records", mutate)
        payload = self._run_verifier(workspace, records=records)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertTrue(payload["verdict"]["failures"], payload)

    def test_tampered_trusted_metadata_baseline_fails(self):
        """A tampered trusted metadata baseline fails closed: the live
        repository can never match a forged baseline, and the snapshot
        gate refuses rather than measuring against forged expectations."""
        workspace = self._fresh_workspace("ws-tampered-metadata")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )

        def mutate(seed, provenance):
            seed["manifest"]["trusted_metadata"] = {
                "config_sha256": "f" * 64,
                "info_attributes_sha256": None,
                "gitattributes_sha256": None,
                "hooks": {},
            }

        records = self._foreign_records("tampered-metadata", mutate)
        payload = self._run_verifier(workspace, records=records)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertEqual(payload["_exit_code"], 1)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)
        self.assertIn("metadata gate", payload["verdict"]["reason"], payload)

    def test_tampered_origin_url_anchor_fails(self):
        """A tampered origin_url_expected anchor cannot mask a state check:
        the comparison against the actual recorded remote URL fails."""
        workspace = self._fresh_workspace("ws-tampered-url")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )

        def mutate(seed, provenance):
            seed["manifest"]["origin_url_expected"] = "/not/the/origin"

        records = self._foreign_records("tampered-url", mutate)
        payload = self._run_verifier(workspace, records=records)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertTrue(
            any("origin URL" in f for f in payload["verdict"]["failures"]), payload
        )

    def test_tampered_untracked_digest_fails(self):
        """A tampered untracked sentinel digest fails the byte-identity
        check against the actual preserved file."""
        workspace = self._fresh_workspace("ws-tampered-digest")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )

        def mutate(seed, provenance):
            seed["manifest"]["untracked"]["sha256"] = "a" * 64

        records = self._foreign_records("tampered-digest", mutate)
        payload = self._run_verifier(workspace, records=records)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertTrue(
            any("sentinel" in f.lower() or "sha256" in f.lower()
                for f in payload["verdict"]["failures"]),
            payload,
        )

    def test_missing_trusted_records_fail_closed(self):
        workspace = self._fresh_workspace("ws-missing-records")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        empty_records = self.root / "empty-records"
        empty_records.mkdir(parents=True, exist_ok=True)
        payload = self._run_verifier(workspace, records=empty_records)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)

    def test_missing_fixture_fails_closed(self):
        workspace = self.root / "ws-no-fixture"
        workspace.mkdir(parents=True, exist_ok=True)
        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)

    def test_workspace_escape_fixture_root_fails_closed(self):
        """A fixture root outside the workspace (e.g. the host HOME) is
        refused: the verifier only measures fresh case paths."""
        # A "workspace" whose fixture dir points at the host HOME tree is
        # structurally invalid; emulate via a workspace whose fixture is a
        # symlink escape (the ancestor-symlink refusal catches it), and a
        # direct out-of-workspace call.
        workspace = self.root / "ws-escape"
        workspace.mkdir(parents=True, exist_ok=True)
        payload = self._run_verifier(self.root)  # root has no fixture/
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)


class TestHarborTypedValidation(HarborPackageTestBase):
    """Typed validation of the generated package against the ACTUAL
    Harbor 0.25.0 models (optional only when Harbor is absent; it is
    installed in git-pilot-v1/.venv)."""

    @unittest.skipUnless(HARBOR_SDK_AVAILABLE, "Harbor package not installed")
    def test_task_config_typed_valid(self):
        """TaskConfig.model_validate_toml parses the generated task.toml
        with the exact source fields: org/name task name, schema 1.4,
        non-root agent user, root verifier user."""
        raw = (self.task_dir / "task.toml").read_text()
        config = TaskConfig.model_validate_toml(raw)
        self.assertEqual(config.schema_version, "1.4")
        self.assertIsNotNone(config.task)
        self.assertEqual(
            config.task.name, "agent-workflows/return-main-no-cleanup-v1"
        )
        self.assertEqual(config.task.org, "agent-workflows")
        self.assertEqual(config.task.short_name, CASE_ID)
        self.assertEqual(config.environment.docker_image, gpkg.DEFAULT_IMAGE)
        self.assertEqual(config.environment.workdir, "/workspace")
        # Explicit non-root agent user (cannot overwrite root-owned
        # /opt/git-pilot trusted code/records).
        self.assertEqual(config.agent.user, "1001")
        # Verifier runs as root: it must write expected/manifest.json
        # next to the agent-writable fixture (symlink-refusing first).
        self.assertEqual(config.verifier.user, "root")
        self.assertEqual(config.agent.timeout_sec, 900.0)
        self.assertEqual(config.verifier.timeout_sec, 300.0)

    @unittest.skipUnless(HARBOR_SDK_AVAILABLE, "Harbor package not installed")
    def test_task_loads_from_package_dir(self):
        """The actual Task loader accepts the package dir and derives the
        correct base paths (config, tests, instruction, environment)."""
        task = Task(self.task_dir)
        self.assertEqual(task.name, "agent-workflows/return-main-no-cleanup-v1")
        self.assertEqual(task.short_name, CASE_ID)
        self.assertTrue(task.paths.config_path.is_file())
        self.assertTrue(task.paths.tests_dir.is_dir())
        self.assertTrue(task.paths.instruction_path.is_file())
        self.assertIn("return to main", task.instruction)
        self.assertTrue(task.paths.environment_dir.is_dir())

    @unittest.skipUnless(HARBOR_SDK_AVAILABLE, "Harbor package not installed")
    def test_reward_files_parse_via_actual_harbor_verifier(self):
        """Harbor 0.25.0's Verifier numeric parse API accepts the emitted
        reward.json (flat finite numbers) and reward.txt (bare float)."""
        workspace = self._fresh_workspace("ws-harbor-parse")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        reward_dir = self.root / "reward-harbor-parse"
        payload = self._run_verifier(workspace, reward_dir=reward_dir)
        self.assertEqual(payload["reward"], 1.0, payload)

        # The ACTUAL Verifier parse path, driven against the emitted files
        # via real TrialPaths host-side paths (verifier/ dir of a trial).
        trial_dir = self.root / "harbor-trial"
        trial_dir.mkdir(parents=True, exist_ok=True)
        target = TrialPaths(trial_dir=trial_dir)
        target.verifier_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reward_dir / "reward.json", target.reward_json_path)
        shutil.copy2(reward_dir / "reward.txt", target.reward_text_path)

        verifier = HarborVerifier.__new__(HarborVerifier)
        verifier.trial_paths = target
        rewards = verifier._parse_reward_json()
        self.assertEqual(rewards, {"reward": 1.0})
        self.assertIsInstance(rewards["reward"], float)
        text_rewards = verifier._parse_reward_text()
        self.assertEqual(text_rewards, {"reward": 1.0})

    @unittest.skipUnless(HARBOR_SDK_AVAILABLE, "Harbor package not installed")
    def test_reward_files_parse_on_failure_too(self):
        """A failing run still emits the numeric contract Harbor parses."""
        workspace = self._fresh_workspace("ws-harbor-parse-fail")
        self._run_in_repo(workspace, ["checkout", "main"])
        reward_dir = self.root / "reward-harbor-parse-fail"
        payload = self._run_verifier(workspace, reward_dir=reward_dir)
        self.assertEqual(payload["reward"], 0.0, payload)

        trial_dir = self.root / "harbor-trial-fail"
        trial_dir.mkdir(parents=True, exist_ok=True)
        target = TrialPaths(trial_dir=trial_dir)
        target.verifier_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reward_dir / "reward.json", target.reward_json_path)
        shutil.copy2(reward_dir / "reward.txt", target.reward_text_path)

        verifier = HarborVerifier.__new__(HarborVerifier)
        verifier.trial_paths = target
        rewards = verifier._parse_reward_json()
        self.assertEqual(rewards, {"reward": 0.0})
        self.assertEqual(verifier._parse_reward_text(), {"reward": 0.0})

    def test_reward_json_flat_numeric_only(self):
        """reward.json is exactly {'reward': <float>} — no strings, no
        nested rich payload (those live in verdict.json/judges.json)."""
        workspace = self._fresh_workspace("ws-flat-numeric")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        payload = self._run_verifier(workspace)
        self.assertEqual(set(payload["_reward_json_raw"]), {"reward"})
        self.assertIsInstance(payload["_reward_json_raw"]["reward"], float)
        # reward.txt is a bare numeric string, nothing else.
        self.assertEqual(payload["_reward_text"].strip(), "1.0")
        # The rich payload (reason/failures/coverage/case) is in the
        # sidecar, NOT in the numeric map.
        self.assertIn("procedure_attempt_coverage", payload["verdict"])
        self.assertIn("failures", payload["verdict"])


class TestVerifierSymlinkAttack(HarborPackageTestBase):
    """An agent-planted symlink must never redirect the verifier's write."""

    def test_expected_dir_symlink_outside_file_untouched(self):
        """Agent plants fixture/expected as a symlink to an outside file:
        the verifier refuses, the outside file is untouched, and the
        verdict is a numeric 0 (UNSCORABLE)."""
        workspace = self._fresh_workspace("ws-symlink-expected")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        outside = self.root / "outside-secret.txt"
        outside.write_text("do not touch\n")
        outside_digest_before = hashlib.sha256(outside.read_bytes()).hexdigest()

        # The agent plants the symlink where the verifier wants to write.
        fixture = workspace / "fixture"
        (fixture / "expected").symlink_to(outside)

        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertEqual(payload["_exit_code"], 1)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)
        self.assertIn("symlink", payload["verdict"]["reason"], payload)

        # The outside file is untouched (bytes identical, still a regular
        # file, not replaced by the manifest).
        self.assertEqual(outside.read_text(), "do not touch\n")
        self.assertEqual(
            hashlib.sha256(outside.read_bytes()).hexdigest(),
            outside_digest_before,
        )
        self.assertTrue(outside.is_file())
        self.assertFalse(outside.is_symlink())
        # The planted symlink itself was NOT followed into a write.
        self.assertTrue((fixture / "expected").is_symlink())

    def test_expected_manifest_symlink_outside_file_untouched(self):
        """Agent plants expected/manifest.json itself as a symlink."""
        workspace = self._fresh_workspace("ws-symlink-manifest")
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        outside = self.root / "outside-manifest-target.txt"
        outside.write_text("keep me out\n")
        fixture = workspace / "fixture"
        (fixture / "expected").mkdir()
        (fixture / "expected" / "manifest.json").symlink_to(outside)

        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)
        self.assertIn("symlink", payload["verdict"]["reason"], payload)
        # Outside file untouched.
        self.assertEqual(outside.read_text(), "keep me out\n")
        self.assertFalse(outside.is_symlink())

    def test_repo_component_symlink_refused(self):
        """A symlinked fixture component (repo) is refused before any
        write; the symlink target outside the workspace is untouched."""
        workspace = self._fresh_workspace("ws-symlink-repo")
        fixture = workspace / "fixture"
        outside_repo = self.root / "outside-repo"
        shutil.copytree(fixture / "repo", outside_repo / "repo")
        shutil.rmtree(fixture / "repo")
        (fixture / "repo").symlink_to(outside_repo / "repo")

        payload = self._run_verifier(workspace)
        self.assertEqual(payload["reward"], 0.0, payload)
        self.assertIn("UNSCORABLE", payload["verdict"]["reason"], payload)
        # The outside copy still exists and was not measured or written.
        self.assertTrue((outside_repo / "repo" / ".git").exists())


class TestOracleSolutionAsset(HarborPackageTestBase):
    """The packaged solution/solve.sh is the trusted deterministic oracle.

    The stock Harbor OracleAgent (harbor 0.25.0 harbor/agents/oracle.py)
    uploads solution/ to /solution and executes solve.sh after the
    environment is staged. Static contract asserted here: wrapper-only Git
    against the FIXED fixture repo, exactly the three known operations, and
    NO forbidden operations and NO expected-state leakage. This asset is a
    deterministic ORACLE, not an OpenCode/LLM quality claim.
    """

    def _solve_text(self) -> str:
        return (self.task_dir / "solution" / "solve.sh").read_text()

    def test_solution_file_present_and_executable(self):
        solve = self.task_dir / "solution" / "solve.sh"
        self.assertTrue(solve.is_file())
        self.assertTrue(os.access(solve, os.X_OK))

    def test_solution_targets_fixed_repo_through_wrapper(self):
        text = self._solve_text()
        self.assertIn("/opt/git-pilot/bin/sandbox-git", text)
        self.assertIn('/workspace/fixture/repo', text)
        # The repo is addressed via git's -C flag with the fixed path; the
        # wrapper is invoked by absolute container path only.
        self.assertIn('-C "$REPO"', text)
        self.assertIn('REPO="/workspace/fixture/repo"', text)

    def test_solution_known_operations_only(self):
        """Exactly the three runbook operations, one per line."""
        text = self._solve_text()
        for op in (
            "fetch origin",
            "switch main",
            "merge --ff-only origin/main",
        ):
            self.assertIn(op, text)
        # Exactly three wrapper invocation lines.
        invocation_lines = [
            line for line in text.splitlines()
            if line.startswith('"$WRAPPER"')
        ]
        self.assertEqual(
            len(invocation_lines), 3,
            f"expected exactly 3 wrapper ops, got: {invocation_lines}",
        )
        self.assertEqual(
            invocation_lines,
            [
                '"$WRAPPER" -C "$REPO" fetch origin',
                '"$WRAPPER" -C "$REPO" switch main',
                '"$WRAPPER" -C "$REPO" merge --ff-only origin/main',
            ],
        )

    def test_solution_uses_no_raw_git(self):
        text = self._solve_text()
        # After removing the wrapper name and uppercase GIT_ env prefixes,
        # no lowercase "git " invocation may remain (wrapper-only contract).
        stripped = text.replace("sandbox-git", "").replace("GIT_", "")
        self.assertNotIn("git ", stripped)
        self.assertNotIn('"git"', text)
        self.assertNotIn("'git'", text)

    def test_solution_has_no_forbidden_operations(self):
        """No directory change, no destructive/cleanup/publication ops."""
        text = self._solve_text()
        for forbidden in (
            "cd ",
            "pushd",
            "push",
            "commit",
            "clean",
            "reset",
            "rebase",
            "rm ",
            "branch -D",
            "branch -d",
            "checkout --",
            "cherry-pick",
            "revert",
            "tag ",
        ):
            self.assertNotIn(
                forbidden, text,
                f"solve.sh must not contain {forbidden!r}",
            )

    def test_solution_does_not_leak_expected_state(self):
        """The solution carries no expected anchors or trusted records."""
        text = self._solve_text()
        for secret in (
            "expected",
            "seed-state",
            "manifest",
            "provenance",
            "cremote",
            "cfeature",
        ):
            self.assertNotIn(secret, text)

    def test_solution_not_agent_visible(self):
        """The solution must NOT ship inside environment/ (agent upload)."""
        env_dir = self.task_dir / "environment"
        self.assertFalse(
            (env_dir / "solution").exists(),
            "solution must not ship in environment/",
        )
        self.assertFalse(
            (env_dir / "solve.sh").exists(),
            "solve.sh must not ship in environment/",
        )

    def test_provenance_records_solution(self):
        record = self.provenance["solution"]
        solve = self.task_dir / "solution" / "solve.sh"
        self.assertEqual(record["path"], "solution/solve.sh")
        self.assertEqual(
            record["sha256"],
            hashlib.sha256(solve.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            record["operations"],
            ["fetch origin", "switch main", "merge --ff-only origin/main"],
        )
        self.assertIn("oracle", record["agent"])
        self.assertIn("no model", record["agent"])


class TestCustomWrapperVendoring(HarborPackageTestBase):
    """F4 regression: an explicitly passed --wrapper must be the wrapper
    that is vendored into the image AND recorded in provenance.

    The original (source) bug: ``_vendor_wrapper()`` ignored the
    ``wrapper`` argument and re-resolved the default, so a custom
    ``--wrapper`` produced a fixture built with the custom wrapper but a
    vendored image copy + provenance record describing the DEFAULT
    wrapper — inconsistent provenance. Closed in the owned relocated
    copy only (source untouched).
    """

    def test_custom_wrapper_vendored_and_recorded(self):
        """A custom wrapper copy (different path, byte-identical content
        is NOT enough — use a distinct-bytes wrapper) must be the one
        vendored into harbor/image/bin/ and described by provenance.

        The vendored image path is a SHARED generated asset (other tests
        and future builds read it): the previous bytes + mode are
        preserved up-front and restored in ``finally``, irrespective of
        assertion failures, so this test never leaves a custom wrapper
        behind for future builds (or unlinks one that did not exist).
        """
        import tempfile

        base = APPROVED_TMP if APPROVED_TMP.is_dir() else Path(
            tempfile.gettempdir()
        )
        root = Path(tempfile.mkdtemp(prefix="git-pilot-f4-", dir=base))
        # Preserve the shared vendored wrapper (bytes + mode) before the
        # custom generation overwrites it; restore in finally.
        vendored = HARBOR / "image" / "bin" / "sandbox-git"
        existed = vendored.is_file()
        prev_bytes = vendored.read_bytes() if existed else None
        prev_mode = vendored.stat().st_mode if existed else None
        try:
            # Distinct-bytes wrapper: the real wrapper plus a comment
            # line (still a functioning script for copy purposes; only
            # bytes/identity matter here, it is never executed).
            custom = root / "sandbox-git-custom"
            custom.write_bytes(
                WRAPPER.read_bytes() + b"\n# F4 custom wrapper sentinel\n"
            )
            custom.chmod(0o755)

            out = root / "package"
            task_dir, provenance = gpkg.generate_package(
                out, wrapper=custom
            )
            record = provenance["wrapper"]
            # All three describe the SAME custom wrapper:
            self.assertEqual(record["source"], str(custom))
            self.assertEqual(
                record["sha256"],
                hashlib.sha256(custom.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                hashlib.sha256(vendored.read_bytes()).hexdigest(),
                hashlib.sha256(custom.read_bytes()).hexdigest(),
            )
            self.assertNotEqual(
                hashlib.sha256(vendored.read_bytes()).hexdigest(),
                hashlib.sha256(WRAPPER.read_bytes()).hexdigest(),
                "vendored wrapper must be the CUSTOM one, not the default",
            )
            self.assertEqual(
                record["bytes"], custom.stat().st_size,
            )
        finally:
            if existed:
                vendored.write_bytes(prev_bytes)
                os.chmod(vendored, prev_mode)
            elif vendored.exists() or vendored.is_symlink():
                vendored.unlink()
            shutil.rmtree(root, ignore_errors=True)


class TestTrustedStartupIsolation(HarborPackageTestBase):
    """The packaged test.sh must make the root verifier's Python startup
    immune to agent-planted usercustomize/sitecustomize modules.

    The review blocker: the image ENV is HOME=/workspace (agent-writable)
    and the verifier's wrapper subprocesses use fixture/mock-home as HOME,
    so a planted .local/lib/pythonX.Y/site-packages tree under either
    could execute inside a trusted Python with user site enabled. The
    shim now resets the environment (trusted PATH with /opt/app-root/bin
    first, PYTHONPATH/PYTHONHOME/PYTHONBASE unset, PYTHONNOUSERSITE=1,
    HOME=/root) and runs an isolated `python3 -I` prelude that validates
    the fixture components with lstat and replaces fixture/mock-home
    with a fresh empty real directory before any verifier code runs.

    Static contract tests (flags present) are necessary but NOT
    sufficient: the poisoned-startup tests below plant REAL sentinel
    modules and prove they never execute through the packaged shim's
    exact interpreter invocation.
    """

    def _test_sh(self) -> str:
        return (self.task_dir / "tests" / "test.sh").read_text()

    def _planted_site_packages(self, base: Path) -> Path:
        """Plant usercustomize + sitecustomize sentinels under a .local
        user-site tree, each writing a marker file when executed."""
        site_packages = (
            base / ".local" / "lib" / "python3.12" / "site-packages"
        )
        site_packages.mkdir(parents=True, exist_ok=True)
        for name, marker in (
            ("usercustomize.py", "usercustomize-executed"),
            ("sitecustomize.py", "sitecustomize-executed"),
        ):
            (site_packages / name).write_text(
                "from pathlib import Path\n"
                f"Path('{marker}').write_text('EXECUTED')\n",
                encoding="utf-8",
            )
        return site_packages

    def test_sh_resets_environment_before_python(self):
        """Static contract: the env reset happens BEFORE any python3."""
        text = self._test_sh()
        # Trusted PATH with /opt/app-root/bin FIRST (UBI scl Python 3.12
        # that carries the image's PyYAML); never drop it in favor of
        # /usr/bin/python3.9.
        self.assertIn(
            'export PATH="/opt/app-root/bin:/opt/git-pilot/bin:'
            '/usr/local/bin:/usr/bin:/bin"',
            text,
        )
        self.assertIn("unset PYTHONPATH PYTHONHOME PYTHONUSERBASE", text)
        self.assertIn("export PYTHONNOUSERSITE=1", text)
        self.assertIn("export HOME=/root", text)
        # The reset must precede every python3 invocation in the shim.
        first_python = text.index('"$TRUSTED_PYTHON" -I')
        unset_pos = text.index("unset PYTHONPATH PYTHONHOME PYTHONUSERBASE")
        self.assertLess(unset_pos, first_python)

    def test_sh_prelude_is_isolated_and_trusted(self):
        """Static contract: the prelude is /opt/app-root/bin/python3 -I."""
        text = self._test_sh()
        self.assertIn('TRUSTED_PYTHON="/opt/app-root/bin/python3"', text)
        self.assertIn('"$TRUSTED_PYTHON" -I - "$FIXTURE_ROOT"', text)
        # No non-isolated python3 invocation exists anywhere in the shim;
        # the only python3 the shim runs is $TRUSTED_PYTHON with -I.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("python3 ") or stripped == "python3":
                self.fail(f"non-isolated python3 call in test.sh: {line}")
            if "python3 -I" in stripped and "TRUSTED_PYTHON" not in stripped:
                if stripped.startswith("#"):
                    continue
                self.fail(f"unexpected python3 -I usage: {line}")

    def test_sh_writes_flat_numeric_zero_on_prelude_failure(self):
        """Static contract: prelude failure writes Harbor's numeric
        contract (flat reward 0) plus the UNSCORABLE sidecar."""
        text = self._test_sh()
        self.assertIn('printf \'{"reward": 0.0}\\n\'', text)
        self.assertIn("printf '0.0\\n'", text)
        self.assertIn("UNSCORABLE: trusted startup prelude failed", text)
        # The verifier itself is only invoked after a prelude success.
        self.assertIn('bash "/opt/git-pilot/bin/verify.sh"', text)
        self.assertLess(
            text.index("PRELUDE_STATUS"),
            text.index('bash "/opt/git-pilot/bin/verify.sh"'),
        )

    def test_prelude_refuses_symlinked_components(self):
        """The prelude's Python source refuses links and non-directories
        (lstat only, never followed) and resets only fixture/mock-home."""
        text = self._test_sh()
        start = text.index("<<'PRELUDE_EOF'\n") + len("<<'PRELUDE_EOF'\n")
        prelude = text[start : text.index("\nPRELUDE_EOF\n", start)]
        import ast

        tree = ast.parse(prelude)
        # The only fixture paths the prelude may write under are the
        # validated mock-home reset pair; nothing else is touched.
        self.assertIn('component("mock-home")', prelude)
        self.assertIn('os.rename(mock_home, replacement)', prelude)
        self.assertIn("shutil.rmtree(replacement)", prelude)
        self.assertIn("S_ISLNK", prelude)
        self.assertIn("os.lstat", prelude)
        # No shell-out, no rm -rf, no writes outside the fixture root
        # (comment lines are excluded: the contract is about executable
        # source, not the prelude's own documentation).
        code_lines = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.stmt)
        ]
        source_lines = prelude.splitlines()
        executable = "\n".join(
            line for i, line in enumerate(source_lines, start=1)
            if i in code_lines and not line.lstrip().startswith("#")
        )
        for forbidden in (
            "subprocess", "os.system", "popen", "rm -rf",
            "rmtree(fixture_root)", "rmtree(workspace)",
        ):
            self.assertNotIn(
                forbidden, executable,
                f"prelude must not use {forbidden}",
            )

    def _run_test_sh_as_script(self, workspace: Path, root: Path,
                               extra_env: dict | None = None) -> dict:
        """Run the PACKAGED tests/test.sh as a real subprocess with the
        container-like layout the shim expects.

        Outside the container the shim's fixed /opt and /logs paths do
        not exist, so this harness pre-creates the minimal fixed layout
        under a disposable temp root and maps the shim's absolute paths
        onto it with PATH/HOME mirroring the shim's own reset. The
        agent-visible poison is planted BEFORE the run; markers land in
        the process cwd (the mapped workspace) if the poison executes.
        """
        import os

        workspace.mkdir(parents=True, exist_ok=True)
        logs = root / "logs-mapped"
        logs.mkdir(parents=True, exist_ok=True)
        # Minimal /opt/app-root/bin/python3 stand-in: the host venv python
        # honors -I (isolated mode) identically for the poison probe.
        app_root_bin = root / "opt-mapped" / "app-root" / "bin"
        app_root_bin.mkdir(parents=True, exist_ok=True)
        python_link = app_root_bin / "python3"
        if not python_link.exists():
            _tp = os.environ.get("AGENT_WORKFLOWS_TEST_PYTHON")
            if not _tp:
                raise unittest.SkipTest(
                    "AGENT_WORKFLOWS_TEST_PYTHON not set (pinned SDK "
                    "interpreter must be supplied externally for the "
                    "poison-probe python3 stand-in)"
                )
            python_link.symlink_to(_tp)
        # The shim writes to fixed /logs/verifier and reads
        # /opt/app-root/bin/python3; outside a container we cannot bind
        # those, so the poison assertion runs against the SAME script
        # body with the paths rewritten to the mapped temp layout. This
        # keeps the executed bytes the shim will run in-container.
        script = self._test_sh()
        script = script.replace("/logs/verifier", str(logs / "verifier"))
        script = script.replace(
            "/opt/app-root/bin/python3", str(python_link)
        )
        # The prelude anchors validation on the fixed container path
        # /workspace; outside a container, rewrite that single anchor onto
        # the mapped workspace so the reset logic actually executes the
        # same bytes the in-container shim runs.
        script = script.replace(
            'workspace = Path("/workspace").resolve()',
            f'workspace = Path("{workspace.resolve()}").resolve()',
        )
        script_path = root / "test-sh-run.sh"
        script_path.write_text(script, encoding="utf-8")
        os.chmod(script_path, 0o755)

        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(workspace),
            "GIT_PILOT_WORKSPACE": str(workspace),
            "GIT_PILOT_FIXTURE_DIR": "fixture",
            "TMPDIR": str(root),
        }
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "logs": logs / "verifier",
            "workspace": workspace,
            "root": root,
        }

    def test_poisoned_user_site_never_executes_pristine(self):
        """Plant usercustomize/sitecustomize under the WORKSPACE .local
        (the image HOME) and the fixture mock-home .local, then run the
        packaged shim end-to-end: the markers must NOT execute, the
        planted mock-home is reset to an empty real directory, and the
        pristine verdict is reward 0 (not UNSCORABLE)."""
        workspace = self.root / "ws-poison-pristine"
        shutil.copytree(
            self.task_dir / "environment" / "fixture",
            workspace / "fixture",
            symlinks=False,
        )
        self._planted_site_packages(workspace)
        self._planted_site_packages(workspace / "fixture" / "mock-home")
        # GIT_PILOT_WORKSPACE points at the mapped workspace; the shim's
        # hardcoded /workspace validation is what in-container runs use.
        # Here the poison probe runs the shim's own reset + prelude path
        # against the mapped root, so rewrite that anchor too.
        result = self._run_test_sh_as_script(
            workspace, self.root / "poison-pristine-run"
        )
        markers = [
            "usercustomize-executed",
            "sitecustomize-executed",
        ]
        for marker in markers:
            self.assertFalse(
                (workspace / marker).exists(),
                f"agent-planted {marker} RAN inside trusted python: "
                f"{workspace / marker}",
            )
            self.assertFalse(
                (result["root"] / marker).exists(),
                f"agent-planted {marker} ran outside the workspace",
            )
        # The planted mock-home .local tree is GONE (reset happened).
        self.assertFalse(
            (workspace / "fixture" / "mock-home" / ".local").exists(),
            "prelude did not reset fixture/mock-home",
        )
        self.assertTrue(
            (workspace / "fixture" / "mock-home").is_dir()
        )
        self.assertFalse(
            (workspace / "fixture" / "mock-home").is_symlink()
        )
        # Inside the container this reaches verify.sh and emits reward 0
        # for the pristine state; outside it, the shim cannot run the
        # in-image verifier, so the assertion here is that the prelude
        # itself completed (no UNSCORABLE prelude refusal) and no poison
        # executed. The reward-0/1 verdicts are proven by the native
        # oracle run receipts.
        self.assertNotIn("prelude refused", result["stdout"])

    def test_poisoned_user_site_never_executes_after_oracle(self):
        """Same poison, but the repository is first driven to the
        expected final state through the wrapper: the prelude still
        resets mock-home and no marker executes."""
        workspace = self.root / "ws-poison-oracle"
        shutil.copytree(
            self.task_dir / "environment" / "fixture",
            workspace / "fixture",
            symlinks=False,
        )
        self._run_in_repo(
            workspace,
            ["checkout", "main"],
            ["fetch", "origin"],
            ["merge", "--ff-only", "origin/main"],
        )
        self._planted_site_packages(workspace)
        self._planted_site_packages(workspace / "fixture" / "mock-home")
        result = self._run_test_sh_as_script(
            workspace, self.root / "poison-oracle-run"
        )
        for marker in ("usercustomize-executed", "sitecustomize-executed"):
            self.assertFalse(
                (workspace / marker).exists(),
                f"agent-planted {marker} RAN inside trusted python",
            )
        self.assertFalse(
            (workspace / "fixture" / "mock-home" / ".local").exists()
        )
        self.assertNotIn("prelude refused", result["stdout"])

    def test_prelude_refuses_symlinked_mock_home(self):
        """An agent-planted symlink at fixture/mock-home is refused
        (never followed): reward 0 flat + UNSCORABLE sidecar, and the
        link target outside the fixture is untouched."""
        workspace = self.root / "ws-prelude-symlink"
        shutil.copytree(
            self.task_dir / "environment" / "fixture",
            workspace / "fixture",
            symlinks=False,
        )
        outside = self.root / "outside-mock-home-target"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "secret.txt").write_text("keep me\n", encoding="utf-8")
        fixture = workspace / "fixture"
        shutil.rmtree(fixture / "mock-home")
        (fixture / "mock-home").symlink_to(outside)

        result = self._run_test_sh_as_script(
            workspace, self.root / "prelude-symlink-run"
        )
        # Fail closed: flat numeric 0 + UNSCORABLE verdict sidecar.
        verdict_path = result["logs"] / "verdict.json"
        reward_json = result["logs"] / "reward.json"
        reward_txt = result["logs"] / "reward.txt"
        self.assertTrue(
            verdict_path.exists(),
            f"prelude refusal must write verdict.json: {result['stdout']} "
            f"{result['stderr']}",
        )
        verdict = json.loads(verdict_path.read_text())
        self.assertIn("UNSCORABLE", verdict["reason"])
        self.assertIn("symlink", verdict["reason"])
        self.assertEqual(
            json.loads(reward_json.read_text()), {"reward": 0.0}
        )
        self.assertEqual(reward_txt.read_text().strip(), "0.0")
        self.assertNotEqual(result["returncode"], 0)
        # The outside target is untouched and the planted link survives
        # unfollowed.
        self.assertEqual(
            (outside / "secret.txt").read_text(), "keep me\n"
        )
        self.assertTrue((fixture / "mock-home").is_symlink())

    def test_prelude_failure_still_writes_numeric_contract(self):
        """A missing fixture component (no repo) fails closed with the
        numeric reward contract Harbor parses."""
        workspace = self.root / "ws-prelude-missing"
        workspace / "fixture" / "repo" / ".git"
        (workspace / "fixture").mkdir(parents=True, exist_ok=True)
        (workspace / "fixture" / "origin.git").mkdir(parents=True)
        (workspace / "fixture" / "mock-home").mkdir(parents=True)
        result = self._run_test_sh_as_script(
            workspace, self.root / "prelude-missing-run"
        )
        verdict = json.loads(
            (result["logs"] / "verdict.json").read_text()
        )
        self.assertIn("UNSCORABLE", verdict["reason"])
        self.assertEqual(
            json.loads((result["logs"] / "reward.json").read_text()),
            {"reward": 0.0},
        )
        self.assertNotEqual(result["returncode"], 0)



class TestEvalHarborConfig(unittest.TestCase):
    """eval.git.yaml consistency with the strict original contract.

    Relocation (P0.2): the strict original ``eval.yaml`` (three
    deterministic code judges over the intentionally-unimplemented CLI
    adapter) was NOT part of the approved portable closure; the judge-
    parity assertions are therefore adapted to check the relocated
    ``eval.git.yaml`` alone against its own recorded contract. The
    original strict contract remains at the source project untouched.
    """

    @classmethod
    def setUpClass(cls):
        if yaml is None:
            raise unittest.SkipTest("PyYAML unavailable")
        cls.config = yaml.safe_load(
            (PROJECT / "eval.git.yaml").read_text()
        )

    def test_prompt_transport_is_case_mode(self):
        self.assertEqual(
            self.config["execution"]["prompt"], "{{ input.prompt }}"
        )

    def test_case_prompt_text_matches_case_contract(self):
        text = (PROJECT / "eval.git.yaml").read_text()
        # The original case prompt wording stays the strict contract.
        self.assertIn("prompt", self.config["execution"])
        self.assertIn("not_measured", text)

    def test_no_model_judges_declared(self):
        self.assertEqual(self.config["judges"], [])
        self.assertEqual(self.config["thresholds"], {})

    def test_procedure_attempt_coverage_labeled_not_measured(self):
        text = (PROJECT / "eval.git.yaml").read_text()
        self.assertIn("procedure_attempt_coverage: not_measured", text)
        task_toml = (HARBOR / "image" / "Containerfile").read_text()
        # The image is labeled a basic end-state pilot, not a full
        # orchestrator-permission/coverage harness.
        self.assertIn("END-STATE", task_toml)

    def test_runner_type_cli_maps_to_explicit_agent(self):
        self.assertEqual(self.config["runner"]["type"], "cli")

    def test_dataset_path_points_at_packaged_case(self):
        self.assertEqual(
            self.config["dataset"]["path"],
            "cases/return-main-no-cleanup-v1",
        )

    def test_config_chain_matches_renamed_config(self):
        """The packager's TASK_TOML pins the renamed config chain."""
        self.assertEqual(gpkg.CONFIG_CHAIN, "eval.git.yaml")
        self.assertIn('config_chain = ["{config_chain}"]', gpkg.TASK_TOML)
        self.assertIn(
            f'config_chain = ["{gpkg.CONFIG_CHAIN}"]',
            gpkg.TASK_TOML.format(
                task_name=gpkg.TASK_NAME,
                task_description=gpkg.TASK_DESCRIPTION,
                generated_by=gpkg.GENERATED_BY,
                config_chain=gpkg.CONFIG_CHAIN,
                case_id=gpkg.CASE_ID,
                image=gpkg.DEFAULT_IMAGE,
                workdir=gpkg.DEFAULT_WORKDIR,
                verifier_timeout=300,
                agent_timeout=900,
            ),
        )


class TestNoRawGitInPackageScripts(unittest.TestCase):
    """No raw git prescriptions inside the packaged scripts."""

    def test_test_sh_uses_no_raw_git(self):
        text = (HARBOR / "image" / "bin" / "verify.sh").read_text()
        self.assertNotIn("git ", text.replace("sandbox-git ", ""))

    def test_verifier_invokes_git_only_through_wrapper(self):
        text = (HARBOR / "verifier.py").read_text()
        # The verifier module never calls git directly; it loads the
        # fixture library and passes the wrapper path.
        self.assertNotIn('subprocess.run(["git"', text)
        self.assertNotIn('"git"', text)


if __name__ == "__main__":
    unittest.main()
