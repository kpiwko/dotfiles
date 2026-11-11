"""Offline tests for the packet-first reviewer workflow.

Two layers, both offline and deterministic:

1. Definition-contract tests parse the checked-in reviewer and orchestrator
   definitions (frontmatter plus body) and prove the approved contract is
   stated. The orchestrator definition is inspected because it owns packet
   assembly and the worker handoff for a missing artifact.
2. Fixture-integrity tests prove every prepared reviewer/orchestrator fixture
   is self-contained: declared content identities match real bytes, diffs
   correspond to the supplied post-image files, and expected finding locations
   point at real lines and tokens.

These tests prove the definitions and fixtures, not live agent behaviour. No
model, network, subprocess or shell command is launched. See
``reviewer-packet-v1/README.md``.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import reviewer_packet_contract as contract

PROJECT = Path(__file__).resolve().parent.parent
SUITE = PROJECT / "reviewer-packet-v1"
FIXTURES = SUITE / "fixtures"
EXPECTATIONS = SUITE / "expectations"
SNAPSHOT_AGENTS = PROJECT / "eval-snapshot" / "agents"
SOURCE_AGENTS = Path(
    os.environ.get(
        "OPENCODE_AGENTS_DIR", str(Path.home() / ".config" / "opencode" / "agents")
    )
)

FORBIDDEN_IN_INPUT = (
    "`PASS`",
    "CHANGES_REQUIRED",
    "NEEDS_CONTEXT",
    "expected verdict",
    "expected finding",
    "expectations/",
)

MARKERS = {
    "revision": r"(?m)^Reviewed revision: content-sha256:[0-9a-f]{64}$",
    "scope": r"(?m)^Scope: ",
    "diff": r"(?mi)^Diff: ",
    "acceptance_criteria": r"(?i)acceptance criteria",
    "implementation_result": r"(?i)implementation result",
    "validation": r"(?i)\bvalidation\b",
    "limitations": r"(?i)\blimitations\b",
}


def expectation_ids() -> list[str]:
    return sorted(path.stem for path in EXPECTATIONS.glob("*.json"))


def load_expectation(case: str) -> dict:
    return json.loads((EXPECTATIONS / f"{case}.json").read_text(encoding="utf-8"))


def load_input(case: str, expectation: dict) -> str:
    return (FIXTURES / case / expectation["input_file"]).read_text(encoding="utf-8")


def post_image_lines(scope_root: Path, relative: str) -> list[str]:
    return (scope_root / relative).read_text(encoding="utf-8").splitlines()


def parse_diff(text: str) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (paths, added, context) with exact (path, line content) pairs."""
    paths: list[str] = []
    added: list[tuple[str, str]] = []
    context: list[tuple[str, str]] = []
    path = None
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/") :]
            paths.append(path)
            in_hunk = False
        elif line.startswith("--- ") or line.startswith("diff --git "):
            in_hunk = False
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            added.append((path, line[1:]))
        elif in_hunk and line.startswith(" "):
            context.append((path, line[1:]))
    return paths, added, context


def mutate(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"mutation anchor not found: {old!r}")
    return text.replace(old, new, 1)


def mutate_all(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"mutation anchor not found: {old!r}")
    return text.replace(old, new)


class DefinitionContractTests(unittest.TestCase):
    """The checked-in definitions state the approved packet-first contract."""

    @classmethod
    def setUpClass(cls):
        cls.reviewer_path = SOURCE_AGENTS / "reviewer.md"
        cls.orchestrator_path = SOURCE_AGENTS / "orchestrator.md"
        cls.reviewer_document, cls.reviewer_body = contract.load_definition(
            cls.reviewer_path
        )
        cls.orchestrator_document, cls.orchestrator_body = contract.load_definition(
            cls.orchestrator_path
        )

    def test_reviewer_definition_satisfies_contract(self):
        self.assertEqual(
            contract.reviewer_violations(self.reviewer_document, self.reviewer_body),
            [],
        )

    def test_orchestrator_definition_satisfies_contract(self):
        self.assertEqual(
            contract.orchestrator_violations(
                self.orchestrator_document, self.orchestrator_body
            ),
            [],
        )

    def test_reviewer_is_read_only_with_no_shell_allowance(self):
        permissions = self.reviewer_document["permissions"]
        shell = [entry for entry in permissions if entry["action"] == "shell"]
        self.assertTrue(shell, "reviewer must deny shell explicitly")
        self.assertEqual({entry["effect"] for entry in shell}, {"deny"})
        for action in ("edit", "subagent"):
            effects = {
                entry["effect"]
                for entry in permissions
                if entry["action"] == action
            }
            self.assertEqual(effects, {"deny"}, action)

    def test_reviewer_has_no_qodo_surface(self):
        combined = (
            self.reviewer_path.read_text(encoding="utf-8")
            + json.dumps(self.reviewer_document)
        ).lower()
        self.assertNotIn("qodo", combined)

    def test_reviewer_states_three_verdicts_and_lookup_allowance(self):
        for verdict in contract.VERDICTS:
            self.assertIn(f"`{verdict}`", self.reviewer_body)
        self.assertIn("`PASS` | `CHANGES_REQUIRED` | `NEEDS_CONTEXT`", self.reviewer_body)
        self.assertRegex(
            self.reviewer_body.lower(), r"budget of four\s+additional\s+context\s+lookups"
        )

    def test_reviewer_forbids_execution_research_and_retry(self):
        body = self.reviewer_body.lower()
        self.assertIn("run no shell commands", body)
        self.assertIn("web or network research", body)
        self.assertIn("never retry a denied action", body)
        self.assertIn("do not return an unsupported `pass`", body)
        self.assertIn("review once", body)

    def test_orchestrator_packet_and_handoff_rules(self):
        body = self.orchestrator_body
        self.assertIn("not every small change needs one", body)
        self.assertIn("request a missing", body)
        self.assertIn("@worker", body)
        self.assertIn("rather than asking the", body)
        self.assertIn("reviewer runs no shell commands, tests, or research", body.replace("\n", " "))
        self.assertIn("immutable content revision", body)
        self.assertIn("second review of unchanged relevant content", body)

    def test_snapshot_agents_match_source_modulo_model_rewrite(self):
        for role in ("reviewer", "orchestrator"):
            source = (SOURCE_AGENTS / f"{role}.md").read_text(encoding="utf-8")
            snapshot = (SNAPSHOT_AGENTS / f"{role}.md").read_text(encoding="utf-8")
            self.assertEqual(
                contract.normalize_model_line(source), snapshot, role
            )


class ReviewerDefinitionMutationTests(unittest.TestCase):
    """Contract checks must fail on a regression, not just pass on today's text."""

    @classmethod
    def setUpClass(cls):
        cls.text = (SOURCE_AGENTS / "reviewer.md").read_text(encoding="utf-8")

    def violations(self, text: str) -> list[str]:
        return contract.reviewer_violations(*contract.split_frontmatter(text))

    def test_mutations_are_detected(self):
        shell_block = (
            '  - action: shell\n    resource: "*"\n    effect: deny'
        )
        cases = {
            "shell_allow": mutate(self.text, shell_block, shell_block.replace("deny", "allow")),
            "shell_not_denied": mutate(self.text, shell_block + "\n", ""),
            "qodo_present": mutate(
                self.text,
                '  - action: subagent\n    resource: "*"\n    effect: deny',
                '  - action: subagent\n    resource: "*"\n    effect: deny\n'
                '  - action: "Qodo_*"\n    resource: "*"\n    effect: allow',
            ),
            "verdict_missing:CHANGES_REQUIRED": mutate(
                self.text, "`CHANGES_REQUIRED`", "`CHANGES`"
            ),
            "lookup_budget_above_4": mutate(
                self.text, "four additional context", "ten additional context"
            ),
            "packet_field_missing:acceptance_criteria": mutate_all(
                self.text, "acceptance criteria", "task goals"
            ),
            "shell_prohibition_missing": mutate(
                self.text,
                "Run no shell commands of any kind",
                "Prefer not to run shell commands",
            ),
            "retry_prohibition_missing": mutate(
                self.text,
                "Never retry a denied action",
                "Avoid unnecessary retries",
            ),
            "subagent_allow": mutate(
                self.text,
                '  - action: subagent\n    resource: "*"\n    effect: deny',
                '  - action: subagent\n    resource: "*"\n    effect: allow',
            ),
            "steps_above_12": mutate(self.text, "steps: 12", "steps: 20"),
            "description_no_shell_missing": mutate(
                self.text, "with no shell execution", "with shell execution once"
            ),
        }
        for expected, mutated in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(self.violations(mutated), [expected])

    def test_baseline_definition_is_clean(self):
        self.assertEqual(self.violations(self.text), [])


class OrchestratorDefinitionMutationTests(unittest.TestCase):
    """Orchestrator regressions: automatic review and reviewer reconstruction."""

    @classmethod
    def setUpClass(cls):
        cls.text = (SOURCE_AGENTS / "orchestrator.md").read_text(encoding="utf-8")

    def violations(self, text: str) -> list[str]:
        return contract.orchestrator_violations(*contract.split_frontmatter(text))

    def test_mutations_are_detected(self):
        cases = {
            "automatic_review_implied": mutate(
                self.text,
                "not every small change needs one",
                "every small change needs a review",
            ),
            "worker_artifact_request_missing": mutate(
                self.text,
                "revision from `@worker` and reissue the review",
                "revision from the repository and reissue the review",
            ),
            "reviewer_reconstruction_rule_missing": mutate(
                self.text,
                "reviewer to reconstruct it",
                "reviewer to discover it",
            ),
            "reviewer_subagent_not_allowed": mutate(
                self.text,
                '  - action: subagent\n    resource: "reviewer"\n    effect: allow',
                '  - action: subagent\n    resource: "reviewer"\n    effect: deny',
            ),
        }
        for expected, mutated in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(self.violations(mutated), [expected])

    def test_baseline_definition_is_clean(self):
        self.assertEqual(self.violations(self.text), [])


class FixtureIntegrityTests(unittest.TestCase):
    """Every prepared fixture must be self-contained and internally consistent."""

    def test_expectation_set_matches_fixture_set(self):
        fixture_names = sorted(path.name for path in FIXTURES.iterdir() if path.is_dir())
        self.assertEqual(expectation_ids(), fixture_names)

    def test_expectations_stay_outside_agent_inputs(self):
        stray = list(FIXTURES.rglob("*.json"))
        self.assertEqual(stray, [], "expectations must not sit in fixture inputs")
        for case in expectation_ids():
            expectation = load_expectation(case)
            packet = load_input(case, expectation)
            for forbidden in FORBIDDEN_IN_INPUT:
                with self.subTest(case=case, forbidden=forbidden):
                    self.assertNotIn(forbidden, packet)

    def test_metadata_is_honest_and_typed(self):
        for case in expectation_ids():
            expectation = load_expectation(case)
            with self.subTest(case=case):
                self.assertEqual(expectation["case"], case)
                self.assertEqual(expectation["status"], "prepared_not_executed")
                self.assertIn(expectation["actor"], {"reviewer", "orchestrator"})
                self.assertIsInstance(expectation["packet_fields"], list)
                self.assertIn("tool_attempts", expectation["observation"])
                self.assertIn("telemetry_gap", expectation["observation"])
                self.assertIn("final_prose_only", expectation["observation"])
                self.assertFalse(
                    (FIXTURES / case / "expectations").exists(),
                    "expectations must not live inside the fixture",
                )

    def test_verdict_semantics_are_consistent(self):
        for case in expectation_ids():
            expectation = load_expectation(case)
            expected = expectation["expected"]
            with self.subTest(case=case):
                verdict = expected["verdict"]
                if expectation["actor"] == "orchestrator":
                    self.assertIsNone(verdict)
                    self.assertFalse(expected["reviewer_invoked"])
                    self.assertTrue(expected["action"])
                    continue
                self.assertIn(verdict, contract.VERDICTS)
                if verdict == "PASS":
                    self.assertEqual(expected["findings"], [])
                    self.assertEqual(expected["missing"], [])
                elif verdict == "CHANGES_REQUIRED":
                    self.assertGreater(len(expected["findings"]), 0)
                    self.assertEqual(expected["missing"], [])
                else:
                    self.assertGreater(len(expected["missing"]), 0)
                    self.assertEqual(expected["findings"], [])

    def test_immutable_revision_is_genuine_content_identity(self):
        for case in expectation_ids():
            expectation = load_expectation(case)
            packet = load_input(case, expectation)
            scope_root = FIXTURES / case / "scope"
            with self.subTest(case=case):
                if expectation["immutable_revision"]:
                    identity = contract.content_identity(scope_root)
                    self.assertTrue(identity.startswith("content-sha256:"))
                    self.assertIn(f"Reviewed revision: {identity}", packet)
                    self.assertIn("not a Git commit", packet)
                else:
                    self.assertNotIn("content-sha256:", packet)

    def test_diff_matches_supplied_post_image(self):
        for case in expectation_ids():
            expectation = load_expectation(case)
            fixture = FIXTURES / case
            diff_path = fixture / "diff.patch"
            with self.subTest(case=case):
                if not expectation["has_diff"]:
                    self.assertFalse(diff_path.exists())
                    packet = load_input(case, expectation)
                    self.assertNotIn("diff --git", packet)
                    self.assertNotIn("@@", packet)
                    continue
                self.assertTrue(diff_path.exists())
                diff_text = diff_path.read_text(encoding="utf-8")
                paths, added, context = parse_diff(diff_text)
                self.assertEqual(sorted(paths), sorted(expectation["scope"]))
                scope_root = fixture / "scope"
                for relative in paths:
                    self.assertTrue((scope_root / relative).is_file(), relative)
                cache = {path: post_image_lines(scope_root, path) for path in paths}
                for path, content in added + context:
                    stripped = content.rstrip()
                    if not stripped:
                        continue
                    self.assertIn(
                        stripped,
                        [line.rstrip() for line in cache[path]],
                        f"{case}: diff line not in supplied post-image: {content!r}",
                    )

    def test_expected_findings_point_at_real_locations(self):
        for case in expectation_ids():
            expectation = load_expectation(case)
            scope_root = FIXTURES / case / "scope"
            for finding in expectation["expected"]["findings"]:
                with self.subTest(case=case, location=finding["location"]):
                    relative, _, raw_line = finding["location"].rpartition(":")
                    self.assertTrue(relative, "finding needs a path:line location")
                    path = scope_root / relative
                    self.assertTrue(path.is_file(), relative)
                    line_number = int(raw_line)
                    lines = post_image_lines(scope_root, relative)
                    self.assertGreaterEqual(line_number, 1)
                    self.assertLessEqual(line_number, len(lines))
                    self.assertIn(finding["token"], lines[line_number - 1])
                    self.assertTrue(finding["problem"].strip())

    def test_lookup_requirements_are_inside_the_allowance(self):
        for case in expectation_ids():
            expectation = load_expectation(case)
            scope_root = FIXTURES / case / "scope"
            for requirement in expectation["lookup_requirements"]:
                with self.subTest(case=case, file=requirement["file"]):
                    self.assertTrue((scope_root / requirement["file"]).is_file())
                    self.assertLessEqual(requirement["max_lookups"], 4)
                    self.assertTrue(requirement["required"])
                    self.assertIn(
                        requirement["file"], load_input(case, expectation)
                    )

    def test_content_identity_tracks_bytes_not_metadata(self):
        case = "seeded-bug-changes-required"
        scope_root = FIXTURES / case / "scope"
        first = contract.content_identity(scope_root)
        self.assertEqual(first, contract.content_identity(scope_root))
        with tempfile.TemporaryDirectory() as tmp:
            copy_root = Path(tmp) / "scope"
            copy_root.mkdir()
            for path in scope_root.rglob("*"):
                if path.is_file():
                    target = copy_root / path.relative_to(scope_root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            self.assertEqual(first, contract.content_identity(copy_root))
            mutated = copy_root / "src" / "backoff.py"
            mutated.write_text(
                mutated.read_text(encoding="utf-8").replace("1, 2, 4, 8", "1, 2, 4"),
                encoding="utf-8",
            )
            self.assertNotEqual(first, contract.content_identity(copy_root))

    def test_orchestrator_fixture_has_no_usable_review_packet(self):
        case = "orchestrator-missing-artifact"
        expectation = load_expectation(case)
        inputs = load_input(case, expectation)
        self.assertIn("No diff artifact path", inputs)
        self.assertIn("immutable reviewed revision", inputs)
        self.assertFalse((FIXTURES / case / "diff.patch").exists())
        self.assertFalse(expectation["expected"]["reviewer_invoked"])
        self.assertEqual(expectation["expected"]["action"], "request_diff_artifact_and_revision_from_worker")

    def test_missing_input_cases_cover_diff_and_revision(self):
        cases = {case: load_expectation(case) for case in expectation_ids()}
        diff_case = cases["missing-diff-needs-context"]
        revision_case = cases["missing-revision-needs-context"]
        self.assertEqual(diff_case["expected"]["verdict"], "NEEDS_CONTEXT")
        self.assertFalse(diff_case["has_diff"])
        self.assertEqual(revision_case["expected"]["verdict"], "NEEDS_CONTEXT")
        self.assertTrue(revision_case["has_diff"])
        self.assertFalse(revision_case["immutable_revision"])
        for expectation in (diff_case, revision_case):
            self.assertIn("git discovery", expectation["forbidden_actions"])
            self.assertIn("shell", expectation["forbidden_actions"])

    def test_clean_and_seeded_cases_are_distinct(self):
        clean = load_expectation("clean-packet-pass")
        seeded = load_expectation("seeded-bug-changes-required")
        self.assertEqual(clean["expected"]["verdict"], "PASS")
        self.assertEqual(seeded["expected"]["verdict"], "CHANGES_REQUIRED")
        clean_identity = contract.content_identity(FIXTURES / "clean-packet-pass" / "scope")
        seeded_identity = contract.content_identity(
            FIXTURES / "seeded-bug-changes-required" / "scope"
        )
        self.assertNotEqual(clean_identity, seeded_identity)


if __name__ == "__main__":
    unittest.main()
