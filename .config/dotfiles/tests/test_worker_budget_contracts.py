"""Task 4A.1 — executable offline contracts for the worker budget fixture.

Scope and limits — MOCK-HARNESS PROOF, NOT RUNTIME VERIFICATION:

These tests execute the inactive fixture plugin
``tests/fixtures/opencode_workflow/worker_budget/worker_budget.ts`` under
plain installed Node (native TypeScript type-stripping, no Bun, no install,
no network) against a mock context that implements ONLY the documented
v2.1.4 hook-registration surface (per-kind hook names, registration with
``dispose()``, readonly ``agent``, ``model.providerID``/``model.id``,
options start empty).

Each test drives the ACTUAL ``context`` hook callback with a context event
and detects REAL mutations by comparing deep-copied before/after snapshots.
They do NOT verify live-server behavior and do NOT claim anything about the
final request body: the harness performs NO protocol lowering (the v2.1.4
``openai-compatible-chat.ts`` mapping is recorded in the fixture README as
source-cited expectation, not mock proof). No registration, activation,
config edit, restart, model call, retry manipulation or deadline logic is
performed or implied; the plugin registers only the ``context`` hook.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from conftest import ROOT

FIXTURE = ROOT / ".config" / "dotfiles" / "tests" / "fixtures" / "opencode_workflow" / "worker_budget"

SCENARIOS = [
    "worker-context",
    "nonworker-agent",
    "same-model-different-provider",
    "worker-different-model",
    "lower-cap-respected",
    "higher-lowered",
    "invalid-ignored",
    "title-generate-compaction",
    "dispose-idempotent",
    "no-extra-mutation",
]


def run_scenario(scenario: str) -> dict:
    """Run one harness scenario with installed Node; return parsed JSON."""
    node = shutil.which("node")
    assert node is not None, "installed Node is required for the offline mock harness"
    proc = subprocess.run(
        [node, "harness.mjs", scenario],
        cwd=FIXTURE,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, f"harness scenario {scenario} failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_worker_agent_and_model_match_applies_cap_in_mock() -> None:
    out = run_scenario("worker-context")
    assert out["agent"] == "worker"
    assert out["maxTokensBefore"] is None
    # MOCK ONLY: the real context callback set the semantic option.
    assert out["maxTokensAfter"] == 8000
    assert out["capApplied"] is True


def test_nonworker_agent_is_untouched() -> None:
    out = run_scenario("nonworker-agent")
    assert out["agent"] == "architect"
    assert out["maxTokensAfter"] == 32000
    assert out["untouched"] is True


def test_same_model_id_under_different_provider_is_untouched() -> None:
    out = run_scenario("same-model-different-provider")
    assert out["providerID"] == "other-provider"
    assert out["maxTokensAfter"] == 32000
    assert out["untouched"] is True


def test_worker_agent_with_different_model_is_untouched() -> None:
    out = run_scenario("worker-different-model")
    assert out["modelID"] == "architect"
    assert out["maxTokensAfter"] == 16000
    assert out["untouched"] is True


def test_existing_lower_cap_is_respected_not_raised() -> None:
    out = run_scenario("lower-cap-respected")
    assert out["maxTokensAfter"] == 4000
    assert out["respected"] is True


def test_existing_higher_limit_is_lowered() -> None:
    out = run_scenario("higher-lowered")
    assert out["maxTokensAfter"] == 8000
    assert out["lowered"] is True


def test_non_finite_or_non_positive_existing_values_are_ignored() -> None:
    out = run_scenario("invalid-ignored")
    assert out["allIgnored"] is True
    assert len(out["cases"]) == 6


def test_only_context_hook_is_registered() -> None:
    out = run_scenario("title-generate-compaction")
    # context/compaction/generate/title are separate per-kind hooks; this
    # plugin registers none of the auxiliary kinds.
    assert out["hookNames"] == ["context"]
    assert out["onlyContext"] is True


def test_dispose_is_idempotent() -> None:
    out = run_scenario("dispose-idempotent")
    assert out["hooksBefore"] == 1
    assert out["hooksAfter"] == 0
    assert out["idempotent"] is True


def test_only_max_tokens_mutates() -> None:
    out = run_scenario("no-extra-mutation")
    assert out["maxTokensAfter"] == 8000
    assert out["systemMessagesToolsIdentityTemperatureUnchanged"] is True
