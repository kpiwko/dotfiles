from __future__ import annotations

from pathlib import Path

import yaml

from conftest import ROOT


OPENCODE = ROOT / ".config" / "k8s" / "openshell" / "opencode"
POLICY = OPENCODE / "sandbox-policy.yaml"


def _policy() -> dict:
    return yaml.safe_load(POLICY.read_text())


def test_policy_denies_by_default_and_admits_only_two_endpoints() -> None:
    endpoints = [e for p in _policy()["network_policies"].values() for e in p["endpoints"]]
    hosts = {(e["host"], e["port"]) for e in endpoints}
    assert hosts == {
        ("agentgateway.ai-dev.svc.cluster.local", 4000),
        ("otel-collector.ai-dev.svc.cluster.local", 4318),
    }


def test_policy_enforces_and_scopes_to_opencode_binary() -> None:
    for p in _policy()["network_policies"].values():
        assert [b["path"] for b in p["binaries"]] == ["/usr/local/bin/opencode"]


def test_policy_requires_hard_landlock() -> None:
    assert _policy()["landlock"]["compatibility"] == "hard_requirement"
