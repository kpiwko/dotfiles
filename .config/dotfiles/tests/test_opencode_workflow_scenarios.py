"""Offline scenario-validation tests for the fixed OpenCode workflow scenarios.

Task 4A of the PR-trace remediation plan
(.config/dotfiles/docs/plans/2026-11-02-dotfiles-pr-trace-remediation.md,
common validation baseline) requires the SAME fixed scenario definitions
before and after each affected phase, stored under
``.config/dotfiles/tests/fixtures/opencode_workflow/scenarios.json``.

Scope and limits — this is SCENARIO VALIDATION, NOT RUNTIME PROOF:
these tests validate fixture invariants only (determinism, isolation from
the live repository, and the absence of any live-publication, model-call,
install, or network authorization). Passing them does not demonstrate
plugin hook behavior, worker budget enforcement, provider protocol
lowering, or model adherence. No network, install, Git mutation, or model
call is performed by these tests.
"""

from __future__ import annotations

import json

import pytest

from conftest import ROOT

FIXTURE = ROOT / ".config" / "dotfiles" / "tests" / "fixtures" / "opencode_workflow" / "scenarios.json"
RAW = FIXTURE.read_text()
DATA = json.loads(RAW)
SCENARIOS = {scenario["id"]: scenario for scenario in DATA["scenarios"]}

EXPECTED_IDS = [
    "small-edit",
    "failing-test-debug",
    "reviewer-finding-unchanged-revision",
    "publication-dry-run",
]

# Every fixed scenario must forbid these live side effects; the offline
# fixture suite never authorizes them regardless of phase or arm.
REQUIRED_FORBIDDEN = {"model_call", "network", "install", "git_mutation", "push"}

# Command substrings that would violate the offline/no-install/no-live-
# publication invariant if they appeared in the fixture at all.
FORBIDDEN_TEXT = [
    "git@github.com",
    "https://github.com",
    "git push",
    "git fetch",
    "npm install",
    "pip install",
    "uv sync",
    "uv add",
]


def test_exactly_four_fixed_scenarios_in_stable_order() -> None:
    ids = [scenario["id"] for scenario in DATA["scenarios"]]
    assert ids == EXPECTED_IDS


def test_global_invariants_forbid_live_execution() -> None:
    invariants = DATA["global_invariants"]
    assert invariants["offline_only"] is True
    assert invariants["model_calls_allowed"] is False
    assert invariants["network_allowed"] is False
    assert invariants["installs_allowed"] is False
    assert invariants["git_mutations_allowed"] is False
    assert invariants["push_allowed"] is False
    assert invariants["requires_approved_envelope_before_any_model_run"] is True


def test_worker_identity_and_protocol_are_pinned() -> None:
    invariants = DATA["global_invariants"]
    # Exact agent string used for worker-only hook matching (plan review
    # focus 2: worker-only controls must not affect other agents).
    assert invariants["worker_agent"] == "agentgateway/worker"
    # Installed config fact: the worker model uses the default
    # openai-compatible package, NOT openai-compatible/responses, so
    # Responses-lowering assertions are cross-protocol (optional) for it.
    assert invariants["worker_protocol_package"] == "openai-compatible"
    assert invariants["worker_uses_responses_protocol"] is False


def test_arms_are_only_baseline_and_cap8000() -> None:
    invariants = DATA["global_invariants"]
    assert invariants["default_arms"] == ["baseline", "cap8000"]
    # 4,000/12,000 arms require a second explicit finite envelope
    # (plan line 62); they must never be default-authorizable.
    assert set(invariants["extended_arms_requiring_separate_envelope"]) == {
        "cap4000",
        "cap12000",
    }


def test_no_numeric_budget_ceilings_are_preauthorized() -> None:
    # Numeric aggregate token/monetary ceilings, per-run and whole-envelope
    # wall deadlines, and attempt maxima require separate approval before
    # any model run; the fixture must not bake unapproved numbers in.
    assert DATA["global_invariants"]["numeric_budget_ceilings"] is None


def test_every_scenario_forbids_live_side_effects() -> None:
    for scenario in DATA["scenarios"]:
        assert REQUIRED_FORBIDDEN.issubset(set(scenario["forbidden"])), scenario["id"]
        assert scenario["title"]
        assert scenario["description"]
        assert scenario["expected_outcome"]


def test_small_edit_scenario_uses_disposable_workspace() -> None:
    scenario = SCENARIOS["small-edit"]
    assert scenario["workspace"]["kind"] == "fresh_temp_dir"
    assert scenario["workspace"]["created_per_run"] is True
    # Isolation: the edit target is created inside the per-run workspace,
    # never a path inside the tracked dotfiles work tree.
    assert not scenario["edit_target"].startswith("/")
    # The workspace path is a per-run placeholder expanded at execution
    # time to a fresh disposable directory, never a literal fixed path.
    assert scenario["workspace"]["path"] == "${RUN_DIR}"
    assert scenario["offline_assertion"]
    assert scenario["edit"] == "append_one_fixed_line"


def test_failing_test_debug_scenario_declares_cause_and_target() -> None:
    scenario = SCENARIOS["failing-test-debug"]
    assert scenario["injected_cause"]
    assert scenario["passing_target"]
    # The cause must be single and known so the debug loop is reproducible.
    assert scenario["injected_cause_kind"] == "single_known_root_cause"


def test_reviewer_scenario_declares_invalidation_and_no_duplicate_review() -> None:
    scenario = SCENARIOS["reviewer-finding-unchanged-revision"]
    assert scenario["invalidation_trigger"]
    assert scenario["unchanged_revision_rule"]
    # Unchanged relevant-scope revisions must not be re-reviewed (plan
    # review focus 3 / Task 2 tiering).
    assert "unchanged" in scenario["unchanged_revision_rule"].lower()
    assert scenario["finding_fixed_once"] is True


def test_publication_dry_run_is_synthetic_only() -> None:
    scenario = SCENARIOS["publication-dry-run"]
    assert scenario["dry_run_only"] is True
    assert set(scenario["stop_paths"]) == {
        "wrong_root",
        "wrong_head",
        "wrong_destination",
        "unauthorized_operation",
    }
    targets = scenario["synthetic_targets"]
    # All publication targets are fixture-local and synthetic: a local
    # bare-repo path pattern, never a real remote host or the review base.
    assert targets["remote_url_pattern"].endswith("fixture-origin.git")
    assert targets["head_branch"] == "fixture-head"
    assert targets["base_branch"] == "fixture-main"
    assert scenario["expected_state_succeeds"]


def test_fixture_text_contains_no_live_remote_or_install_commands() -> None:
    for needle in FORBIDDEN_TEXT:
        assert needle not in RAW, needle


# --- Task 2: offline decision table for the unchanged-revision scenario -----
#
# These checks validate FIXTURE DECISION LOGIC ONLY (plan Task 2, lines
# 147-155): the fixed `reviewer-finding-unchanged-revision` scenario must
# distinguish an unchanged relevant-scope handoff (no duplicate review, prior
# validation reusable) from changed relevant inputs. The decision function
# returns review_needed and validation_reusable SEPARATELY: dependency or
# environment changes invalidate checks but do NOT automatically require
# review absent relevant criteria/code changes; an open finding or changed
# criteria triggers review. Passing these tests proves the fixture's decision
# table, NOT live agent behavior, and the helper is illustrative only.


def _decide_review_and_reuse(prior: dict, current: dict) -> dict:
    """Illustrative offline decision function (NOT a production engine).

    Distinguishes the two coordination decisions:
    - review_needed: a relevant snapshot mismatch, an unclosed finding, or
      changed acceptance criteria requires a focused review.
    - validation_reusable: prior checks stay reusable only when relevant code,
      dependency, environment, and criteria inputs are unchanged.
    """
    snapshot_keys = (
        "worktree_bytes",
        "index_state",
        "allowlisted_untracked",
    )
    snapshot_changed = any(
        prior.get(key) != current.get(key) for key in snapshot_keys
    )
    finding_open = bool(current.get("unclosed_finding"))
    criteria_changed = bool(current.get("criteria_changed"))
    review_needed = snapshot_changed or finding_open or criteria_changed

    check_inputs = (
        "worktree_bytes",
        "index_state",
        "allowlisted_untracked",
        "dependency_inputs",
        "environment_inputs",
        "criteria_changed",
    )
    validation_reusable = all(
        prior.get(key) == current.get(key) for key in check_inputs
    )
    return {
        "review_needed": review_needed,
        "validation_reusable": validation_reusable,
    }


BASE_PRIOR = {
    "worktree_bytes": "sha256:aaaa",
    "index_state": "index:1",
    "allowlisted_untracked": ["tests/fixtures/opencode_workflow/new.json"],
    "dependency_inputs": ["pyproject.toml@v1", "uv.lock@v1"],
    "environment_inputs": ["python=3.12.7", "pytest=9.0.1"],
    "unclosed_finding": False,
    "criteria_changed": False,
}

# Fixture-driven decision rows: each entry is a concrete change against
# BASE_PRIOR with the expected separate review/reuse decisions. Rows follow
# the Task 2 scenario semantics (unchanged handoff, relevant fix, index
# change, allowlisted new file, unclosed finding, changed criteria,
# dependency change, environment change; the irrelevant doc/status/push row
# is covered by its own dedicated test below).
DECISION_ROWS = [
    pytest.param(
        {},
        False,
        True,
        id="unchanged-revision",
    ),
    pytest.param(
        {"worktree_bytes": "sha256:bbbb"},
        True,
        False,
        id="relevant-worktree-fix",
    ),
    pytest.param(
        {"index_state": "index:2"},
        True,
        False,
        id="index-change",
    ),
    pytest.param(
        {
            "allowlisted_untracked": [
                "tests/fixtures/opencode_workflow/new.json",
                "extra.json",
            ]
        },
        True,
        False,
        id="allowlisted-new-file-change",
    ),
    pytest.param(
        {"unclosed_finding": True},
        True,
        True,
        id="unclosed-finding",
    ),
    pytest.param(
        {"criteria_changed": True},
        True,
        False,
        id="changed-criteria",
    ),
    pytest.param(
        {"dependency_inputs": ["pyproject.toml@v2", "uv.lock@v1"]},
        False,
        False,
        id="dependency-change",
    ),
    pytest.param(
        {"environment_inputs": ["python=3.13.0", "pytest=9.0.1"]},
        False,
        False,
        id="environment-change",
    ),
]


def _assert_decision_table(decide) -> None:
    """Assert every DECISION_ROWS expectation against ``decide``.

    In-memory mutation harness for the malformed-function tests: a decision
    function whose output disagrees with any expected row raises here, so
    false positives/negatives are caught rather than passing by construction.
    """
    for row in DECISION_ROWS:
        changes, review_needed, validation_reusable = row.values
        current = dict(BASE_PRIOR)
        current.update(changes)
        assert decide(BASE_PRIOR, current) == {
            "review_needed": review_needed,
            "validation_reusable": validation_reusable,
        }, row.id


@pytest.mark.parametrize(
    ("changes", "review_needed", "validation_reusable"),
    DECISION_ROWS,
)
def test_review_and_reuse_decisions_separated(
    changes: dict, review_needed: bool, validation_reusable: bool
) -> None:
    """Fixture decision table: review and validation reuse are decided
    separately, keyed by which relevant input changed.

    Dependency/environment changes invalidate checks but do NOT automatically
    require review absent a relevant snapshot/criteria change; a relevant
    fix, open finding, or changed criteria triggers review and blocks reuse.
    """
    current = dict(BASE_PRIOR)
    current.update(changes)
    assert _decide_review_and_reuse(BASE_PRIOR, current) == {
        "review_needed": review_needed,
        "validation_reusable": validation_reusable,
    }


def test_irrelevant_doc_status_or_push_change_requires_no_review() -> None:
    """Irrelevant documentation or a status/push update touches no relevant
    snapshot input: no review and validation stays reusable. The row is
    asserted against the fixture's own rule text, not just the helper."""
    scenario = SCENARIOS["reviewer-finding-unchanged-revision"]
    assert scenario["finding_fixed_once"] is True
    assert "must NOT be re-reviewed" in scenario["unchanged_revision_rule"]
    # The scenario's invalidation trigger must stay about relevant
    # dependency/environment inputs, not status/push bookkeeping.
    assert "dependency/environment" in scenario["invalidation_trigger"]
    # Irrelevant changes are absent from the relevant snapshot keys, so the
    # decision function is not sensitive to them by construction.
    irrelevant = dict(BASE_PRIOR)
    irrelevant["irrelevant_doc_or_status_push"] = "changed"
    assert _decide_review_and_reuse(BASE_PRIOR, irrelevant) == {
        "review_needed": False,
        "validation_reusable": True,
    }


def test_malformed_decision_function_false_positive_is_caught() -> None:
    """A malformed decision function that collapses the two decisions (any
    change means review) would flag a dependency-only change as
    review-needed; the decision table must catch that false positive rather
    than pass by construction."""
    def malformed(prior: dict, current: dict) -> dict:
        return {
            "review_needed": prior != current,
            "validation_reusable": prior == current,
        }

    # Unchanged handoff still decides correctly...
    unchanged = dict(BASE_PRIOR)
    assert malformed(BASE_PRIOR, unchanged) == {
        "review_needed": False,
        "validation_reusable": True,
    }
    # ...but the dependency-only row is a review false positive...
    dependency_changed = dict(BASE_PRIOR)
    dependency_changed["dependency_inputs"] = [
        "pyproject.toml@v2",
        "uv.lock@v1",
    ]
    assert malformed(BASE_PRIOR, dependency_changed) == {
        "review_needed": True,
        "validation_reusable": False,
    }
    # ...so the decision table rejects this mutation.
    with pytest.raises(AssertionError):
        _assert_decision_table(malformed)


def test_malformed_decision_function_validation_blindness_is_caught() -> None:
    """A malformed function that decides only review (never reuse state)
    would let stale validations be reused across changed dependency inputs;
    the decision table must catch that blindness too."""
    def malformed(prior: dict, current: dict) -> dict:
        snapshot_keys = (
            "worktree_bytes",
            "index_state",
            "allowlisted_untracked",
        )
        snapshot_changed = any(
            prior.get(key) != current.get(key) for key in snapshot_keys
        )
        return {
            "review_needed": snapshot_changed,
            "validation_reusable": True,  # blind to check-input changes
        }

    dependency_changed = dict(BASE_PRIOR)
    dependency_changed["dependency_inputs"] = [
        "pyproject.toml@v2",
        "uv.lock@v1",
    ]
    # The malformed function wrongly reuses validation on changed deps...
    assert malformed(BASE_PRIOR, dependency_changed) == {
        "review_needed": False,
        "validation_reusable": True,
    }
    # ...so the decision table rejects this mutation.
    with pytest.raises(AssertionError):
        _assert_decision_table(malformed)
