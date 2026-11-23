# OpenShell OpenCode Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a disposable OpenShell sandbox that runs OpenCode with `illusionist` inference through AgentGateway and OTEL traces to MLflow experiment 23, under a deny-by-default enforced egress policy.

**Architecture:** Three new artifacts under `.config/k8s/openshell/opencode/` (policy, OpenCode config, create wrapper) plus docs. The policy admits exactly two internal endpoints; the wrapper creates one sandbox from a digest-pinned image with an idle main process, uploads the config, and verifies the OpenCode binary path matches the policy.

**Tech Stack:** Bash wrapper, YAML sandbox policy, OpenCode JSON config, pytest (pyyaml) tests, OpenShell CLI 0.1.8, Kubernetes/Agent Sandbox on k3s.

**Spec:** `.config/dotfiles/docs/superpowers/specs/2026-11-23-openshell-opencode-sandbox-design.md`

## Global Constraints

- Image must be `ghcr.io/anomalyco/opencode@sha256:be38ebc82f8f0858dc703e76e582c1d32bbdf8534ebfd7d3b4aef55585433965`.
- Default model is `agentgateway/illusionist`.
- Sandbox egress: only `agentgateway.ai-dev.svc.cluster.local:4000` and `otel-collector.ai-dev.svc.cluster.local:4318`, both `protocol: rest`, `enforcement: enforce`.
- `landlock.compatibility: hard_requirement`.
- No MCP servers, no `superpowers` or notifier plugins, no `AGENTS.md` in the sandbox config.
- No credential values in argv, logs, repo files, or test output.
- API key enters the sandbox only via `--env-from AGENTGATEWAY_API_KEY`.
- Sandbox: `--cpu 1 --memory 1Gi`, `--detach`, `--restart-policy never`, main process `sleep infinity`, `HOME=/sandbox`.
- All cluster interaction uses `openshell` CLI or `devcluster-kubectl`; never raw `kubectl`, `limactl shell`, `sudo`, `crictl`, `ctr`, `nerdctl`.
- Git operations use `sandbox-git` from `/Users/kpiwko`.

## Review Focus

- **Policy binary path mismatch** — if the OpenCode binary path in the image differs from the policy, every request is denied and the sandbox looks "broken". The wrapper must pre-check and fail with the actual path.
- **OTLP path omission** — `POST /v1/traces` is required; without it traces vanish silently while inference still works. Test pins the path.
- **Stale uploaded config** — editing `opencode.json` must be reflected on the next run; the wrapper re-uploads every invocation.
- **Missing API key** — creating a sandbox without the key produces a working sandbox that fails only at inference time. The wrapper fails before create.
- **Key disclosure** — the key must never reach argv, stdout/stderr, or committed files; tests assert absence.

---

### Task 1: Sandbox network policy

**Files:**
- Create: `.config/k8s/openshell/opencode/sandbox-policy.yaml`
- Test: `.config/dotfiles/tests/test_openshell_opencode_sandbox.py`

**Interfaces:**
- Produces: policy file with `network_policies.<key>.endpoints[]` entries `{host, port, protocol: rest, enforcement: enforce, rules[]}` and `binaries: [{path: /usr/local/bin/opencode}]`; `landlock.compatibility: hard_requirement`.

- [ ] **Step 1: Write the failing test**

```python
import yaml
from pathlib import Path

OPENCODE = Path.home() / ".config/k8s/openshell/opencode"

def _policy():
    return yaml.safe_load((OPENCODE / "sandbox-policy.yaml").read_text())

def test_policy_denies_by_default_and_admits_only_two_endpoints():
    endpoints = [e for p in _policy()["network_policies"].values() for e in p["endpoints"]]
    hosts = {(e["host"], e["port"]) for e in endpoints}
    assert hosts == {
        ("agentgateway.ai-dev.svc.cluster.local", 4000),
        ("otel-collector.ai-dev.svc.cluster.local", 4318),
    }

def test_policy_enforces_and_scopes_to_opencode_binary():
    for p in _policy()["network_policies"].values():
        assert [b["path"] for b in p["binaries"]] == ["/usr/local/bin/opencode"]

def test_policy_requires_hard_landlock():
    assert _policy()["landlock"]["compatibility"] == "hard_requirement"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory /Users/kpiwko/.config/dotfiles --group test pytest tests/test_openshell_opencode_sandbox.py -q`
Expected: FAIL (FileNotFoundError)

- [ ] **Step 3: Write the policy**

Two `network_policies` entries, each `protocol: rest` and `enforcement: enforce`; AgentGateway allows `POST /v1/chat/completions`, `POST /v1/responses`, `GET /v1/models`; collector allows `POST /v1/traces`. Include the documented `filesystem_policy` baseline with `include_workdir: true`, and `landlock: {compatibility: hard_requirement}`.

- [ ] **Step 4: Run test to verify it passes**

Run the Step 2 command. Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
sandbox-git add .config/k8s/openshell/opencode/sandbox-policy.yaml .config/dotfiles/tests/test_openshell_opencode_sandbox.py
sandbox-git commit -m "feat(openshell): add OpenCode sandbox egress policy"
```

---

### Task 2: Sandbox OpenCode configuration

**Files:**
- Create: `.config/k8s/openshell/opencode/opencode.json`
- Test: same test module as Task 1

**Interfaces:**
- Produces: JSON config with `model: "agentgateway/illusionist"`, provider `agentgateway` reading `{env:AGENTGATEWAY_BASE_URL}` and `{env:AGENTGATEWAY_API_KEY}`, one plugin entry for OTEL reading `{env:OPENCODE_OTLP_ENDPOINT}`.

- [ ] **Step 1: Write the failing test**

```python
import json

def _config():
    return json.loads((OPENCODE / "opencode.json").read_text())

def test_default_model_is_illusionist():
    assert _config()["model"] == "agentgateway/illusionist"

def test_provider_reads_endpoint_and_key_from_env():
    settings = _config()["providers"]["agentgateway"]["settings"]
    assert settings["baseURL"] == "{env:AGENTGATEWAY_BASE_URL}"
    assert settings["apiKey"] == "{env:AGENTGATEWAY_API_KEY}"

def test_only_otel_plugin_configured_with_experiment_header():
    plugins = _config()["plugins"]
    assert len(plugins) == 1
    assert plugins[0]["package"] == "@devtheops/opencode-plugin-otel"
    assert plugins[0]["options"]["otlpHeaders"] == "x-mlflow-experiment-id=23"
    assert plugins[0]["options"]["endpoint"] == "{env:OPENCODE_OTLP_ENDPOINT}"

def test_no_mcp_or_extra_plugins():
    cfg = _config()
    assert "mcp" not in cfg
    assert "instructions" not in cfg
```

- [ ] **Step 2: Run tests, expect FAIL** (missing file)

- [ ] **Step 3: Write `opencode.json`** with the schema URL, `model`, one `agentgateway` provider exposing `illusionist` (`modelID: illusionist`, tools enabled, text input/output, context 350000/output 64000), and the single OTEL plugin entry mirroring the host's `http/protobuf` settings with `tracePropagationProviders: ["agentgateway"]`.

- [ ] **Step 4: Run tests, expect PASS**

- [ ] **Step 5: Commit**

```bash
sandbox-git add .config/k8s/openshell/opencode/opencode.json .config/dotfiles/tests/test_openshell_opencode_sandbox.py
sandbox-git commit -m "feat(openshell): add sandbox OpenCode config"
```

---

### Task 3: Create wrapper

**Files:**
- Create: `.config/k8s/openshell/opencode/create-sandbox.sh`
- Test: same test module (fake `openshell` on `PATH` via `OPENSHELL_BIN`)

**Interfaces:**
- Consumes: `sandbox-policy.yaml` and `opencode.json` from Tasks 1–2.
- Produces: `create-sandbox.sh [--name NAME]`; exit 0 on success, non-zero with an actionable message on any precondition failure.

- [ ] **Step 1: Write the failing tests** covering: missing `AGENTGATEWAY_API_KEY` exits non-zero before any `openshell` call; existing sandbox name refused; argv contains `--env-from AGENTGATEWAY_API_KEY` and never the key value; `--policy` path, digest pin, `--cpu 1`, `--memory 1Gi`, `--detach`, `sleep infinity` present; config re-uploaded on every run; policy binary path equals the wrapper's `OPENCODE_BINARY` constant.

- [ ] **Step 2: Run tests, expect FAIL**

- [ ] **Step 3: Implement the wrapper**

`set -euo pipefail`; `OPENSHELL_BIN="${OPENSHELL_BIN:-openshell}"`; constants `IMAGE`, `OPENCODE_BINARY=/usr/local/bin/opencode`; preconditions (files exist, key non-empty, binary present); refuse existing name via `sandbox get`; create with the Global Constraints flags and `--env` values `HOME=/sandbox`, `AGENTGATEWAY_BASE_URL=http://agentgateway.ai-dev.svc.cluster.local:4000/v1`, `OPENCODE_OTLP_ENDPOINT=http://otel-collector.ai-dev.svc.cluster.local:4318`; upload `opencode.json` to `/sandbox/.config/opencode/opencode.json --no-git-ignore`; resolve `command -v opencode` in the sandbox and fail with the observed path if it differs from `$OPENCODE_BINARY`; print the follow-up `exec`/`stop`/`start`/`delete` commands.

- [ ] **Step 4: Run tests, expect PASS**, plus `bash -n create-sandbox.sh`

- [ ] **Step 5: Commit**

```bash
sandbox-git add .config/k8s/openshell/opencode/create-sandbox.sh .config/dotfiles/tests/test_openshell_opencode_sandbox.py
sandbox-git commit -m "feat(openshell): add OpenCode sandbox create wrapper"
```

---

### Task 4: Documentation

**Files:**
- Create: `.config/k8s/openshell/opencode/README.md`
- Modify: `.config/k8s/openshell/README.md` (link the new stage)
- Test: same module (assert README documents digest pin, key handling, image fallback, and non-goals)

**Interfaces:**
- Produces: operator instructions for create, exec, stop/start, delete, and policy editing.

- [ ] **Step 1: Write failing doc assertions** for the digest, `--env-from`, the NVIDIA fallback image, and the Landlock/deny-by-default statements.

- [ ] **Step 2: Run tests, expect FAIL**

- [ ] **Step 3: Write README(s)** including a Troubleshooting section: all-denied → check binary path; missing traces → check `/v1/traces`; suspended sandbox → main process exited.

- [ ] **Step 4: Run full focused suite**

Run: `uv run --directory /Users/kpiwko/.config/dotfiles --group test pytest tests/test_openshell_opencode_sandbox.py tests/test_openshell_gateway.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

---

### Task 5: Live validation (operational, not TDD)

**Files:** none — record results in the stage README or a dated note.

- [ ] **Step 1: Export the key and create**

```bash
set -a; . ~/.config/k8s/.env; set +a
~/.config/k8s/openshell/opencode/create-sandbox.sh
```

- [ ] **Step 2: Confirm isolation from the sandbox log**

`openshell logs opencode-dev --source sandbox` must show a Landlock ruleset built event. Absence blocks progression.

- [ ] **Step 3: Inference**

`openshell sandbox exec -n opencode-dev -- opencode run "reply with the word ready"` returns a response attributed to `illusionist`.

- [ ] **Step 4: Telemetry**

Confirm a trace for that call in MLflow experiment 23.

- [ ] **Step 5: Denial proof**

`openshell sandbox exec -n opencode-dev -- curl -sS https://example.com` must fail, and the supervisor log must record a denied request.

- [ ] **Step 6: Persistence**

`sandbox stop` then `sandbox start`; confirm `~/.local/share/opencode` session state and the workspace survive.

- [ ] **Step 7: Record outcome and clean up** with `openshell sandbox delete opencode-dev` only after the results are captured.

## Self-Review

- Spec coverage: policy (Task 1), config (Task 2), wrapper with credential handling (Task 3), docs (Task 4), the five acceptance checks (Task 5).
- Every Review Focus line has a test: binary path (Task 3), `/v1/traces` (Task 1), re-upload (Task 3), missing key (Task 3), key disclosure (Task 3).
- Names consistent: `OPENCODE_BINARY`, `IMAGE`, `OPENSHELL_BIN` used identically across tasks.
