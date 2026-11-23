from __future__ import annotations

from pathlib import Path

import yaml

from conftest import ROOT


OPENCODE = ROOT / ".config" / "k8s" / "openshell" / "opencode"
POLICY = OPENCODE / "sandbox-policy.yaml"


def _policy() -> dict:
    return yaml.safe_load(POLICY.read_text())


def test_policy_denies_by_default_and_admits_only_two_endpoints() -> None:
    policy = _policy()
    endpoints = [e for p in policy["network_policies"].values() for e in p["endpoints"]]
    assert len(endpoints) == 2
    hosts = {(e["host"], e["port"]) for e in endpoints}
    assert hosts == {
        ("agentgateway.ai-dev.svc.cluster.local", 4000),
        ("otel-collector.ai-dev.svc.cluster.local", 4318),
    }
    # No coarse access preset, no CIDR escape hatch, and no allow rule beyond
    # the four method/path pairs the stage actually needs.
    rules = {
        (rule["allow"]["method"], rule["allow"]["path"])
        for endpoint in endpoints
        for rule in endpoint["rules"]
    }
    assert rules == {
        ("POST", "/v1/chat/completions"),
        ("POST", "/v1/responses"),
        ("GET", "/v1/models"),
        ("POST", "/v1/traces"),
    }
    for endpoint in endpoints:
        assert "allowed_ips" not in endpoint
        assert "access" not in endpoint
    assert policy["filesystem_policy"]["include_workdir"] is True


def test_policy_enforces_and_scopes_to_opencode_binary() -> None:
    for p in _policy()["network_policies"].values():
        assert [b["path"] for b in p["binaries"]] == ["/usr/local/bin/opencode"]
        for e in p["endpoints"]:
            assert e["protocol"] == "rest"
            assert e["enforcement"] == "enforce"


def test_policy_requires_hard_landlock() -> None:
    assert _policy()["landlock"]["compatibility"] == "hard_requirement"
