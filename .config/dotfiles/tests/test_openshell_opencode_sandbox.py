from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from conftest import ROOT, run_script


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


def _config() -> dict:
    return json.loads((OPENCODE / "opencode.json").read_text())


def test_default_model_is_illusionist() -> None:
    assert _config()["model"] == "agentgateway/illusionist"


def test_provider_reads_endpoint_and_key_from_env() -> None:
    settings = _config()["providers"]["agentgateway"]["settings"]
    assert settings["baseURL"] == "{env:AGENTGATEWAY_BASE_URL}"
    assert settings["apiKey"] == "{env:AGENTGATEWAY_API_KEY}"


def test_only_otel_plugin_configured_with_experiment_header() -> None:
    plugins = _config()["plugins"]
    assert len(plugins) == 1
    # A local directory under read-only /usr, not an npm package name: naming the
    # package makes OpenCode run `npm install` at startup, which the deny-by-default
    # policy blocks, and the trace loss is silent (only a WARN in opencode.log).
    assert plugins[0]["package"] == "/usr/local/share/opencode/plugins/opencode-plugin-otel"
    assert plugins[0]["options"]["otlpHeaders"] == "x-mlflow-experiment-id=23"
    assert plugins[0]["options"]["endpoint"] == "{env:OPENCODE_OTLP_ENDPOINT}"
    assert plugins[0]["options"]["protocol"] == "http/protobuf"
    assert plugins[0]["options"]["disabledMetrics"] == [
        "cost.usage",
        "session.cost.total",
    ]


def test_only_illusionist_model_is_exposed() -> None:
    model = _config()["providers"]["agentgateway"]["models"]["illusionist"]
    assert model["modelID"] == "illusionist"
    assert model["capabilities"]["tools"] is True
    assert model["capabilities"]["input"] == ["text"]
    assert model["capabilities"]["output"] == ["text"]
    assert model["limit"] == {"context": 350000, "output": 64000}


def test_no_mcp_or_extra_plugins() -> None:
    cfg = _config()
    assert "mcp" not in cfg
    assert "instructions" not in cfg
    for key in ("agent", "agents", "command", "commands"):
        assert key not in cfg


# --- create-sandbox.sh ------------------------------------------------------
#
# The wrapper is exercised with a fake `openshell` injected through
# OPENSHELL_BIN, so every assertion below is offline: no cluster is contacted.

WRAPPER = OPENCODE / "create-sandbox.sh"

# Distinctive enough that any leak into argv, output, or a committed file is
# unmistakable. It is a sentinel, never a real credential.
SENTINEL_KEY = "sk-agentgateway-sentinel-2f9c1d7b4a"

IMAGE = (
    "ghcr.io/kpiwko/opencode-sandbox@sha256:"
    "23510ec603a56bc2e6e7d7a78c1db27bcb1fe8a3e503f78d9b7b21f48e402ae6"
)


def _fake_openshell(
    tmp_path: Path,
    *,
    get_exit: int = 1,
    opencode_path: str = "/usr/local/bin/opencode",
) -> Path:
    """Write an `openshell` stand-in that records its argv to a file."""
    record = tmp_path / "openshell-argv.log"
    fake = tmp_path / "openshell"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -uo pipefail\n"
        "{\n"
        "    printf 'BEGIN\\n'\n"
        "    for arg in \"$@\"; do printf 'ARG %s\\n' \"$arg\"; done\n"
        "    printf 'END\\n'\n"
        f"}} >> '{record}'\n"
        "# Skip global flags (recorded above in full) to find the subcommand.\n"
        "while [[ $# -ge 2 && ( \"$1\" == --gateway-endpoint || \"$1\" == -g ) ]]; do shift 2; done\n"
        "case \"${1:-} ${2:-}\" in\n"
        "    'sandbox get')\n"
        f"        exit {get_exit}\n"
        "        ;;\n"
        "    'sandbox exec')\n"
        f"        printf '%s\\n' '{opencode_path}'\n"
        "        exit 0\n"
        "        ;;\n"
        "esac\n"
        "exit 0\n"
    )
    fake.chmod(0o755)
    record.touch()
    return fake


def _calls(record: Path) -> list[list[str]]:
    calls: list[list[str]] = []
    current: list[str] | None = None
    for line in record.read_text().splitlines():
        if line == "BEGIN":
            current = []
        elif line == "END":
            if current is not None:
                calls.append(current)
            current = None
        elif current is not None and line.startswith("ARG "):
            current.append(line[len("ARG ") :])
    return calls


GATEWAY_NAME_FLAG = "-g"
GATEWAY_NAME = "devcluster-k8s"
GATEWAY_FLAG = "--gateway-endpoint"
GATEWAY_DEFAULT = "https://127.0.0.1:17910"

# Both flags lead every call: the registration name is where the CLI finds the
# mTLS material, and the endpoint override points it at the live NodePort. A bare
# `--gateway-endpoint` fails with "failed to read TLS CA from .../mtls/ca.crt".
GATEWAY_PREFIX = [GATEWAY_NAME_FLAG, GATEWAY_NAME, GATEWAY_FLAG, GATEWAY_DEFAULT]


def _strip_global_flags(call: list[str]) -> list[str]:
    rest = call
    while rest and rest[0] in (GATEWAY_FLAG, GATEWAY_NAME_FLAG):
        rest = rest[2:]
    return rest


def _call_starting(calls: list[list[str]], *prefix: str) -> list[str]:
    for call in calls:
        rest = _strip_global_flags(call)
        if rest[: len(prefix)] == list(prefix):
            return rest
    raise AssertionError(f"no openshell call starting with {prefix!r}; got {calls!r}")


def _run(
    wrapper: Path,
    tmp_path: Path,
    env: dict[str, str],
    *,
    key: str | None = SENTINEL_KEY,
    args: list[str] | None = None,
    fake: Path | None = None,
    endpoint: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    fake = fake or _fake_openshell(tmp_path)
    env = env.copy()
    env["OPENSHELL_BIN"] = str(fake)
    env.pop("OPENSHELL_GATEWAY_ENDPOINT", None)
    if endpoint is not None:
        env["OPENSHELL_GATEWAY_ENDPOINT"] = endpoint
    if key is not None:
        env["AGENTGATEWAY_API_KEY"] = key
    proc = run_script(wrapper, *(args or []), env=env)
    return proc, _calls(tmp_path / "openshell-argv.log")


def test_create_sandbox_requires_key_before_any_openshell_call(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    proc, calls = _run(WRAPPER, tmp_path, clean_env, key=None)
    assert proc.returncode != 0
    assert "AGENTGATEWAY_API_KEY" in proc.stderr
    assert calls == [], "wrapper must not touch openshell when the key is missing"
    assert SENTINEL_KEY not in proc.stdout + proc.stderr


def test_create_sandbox_requires_policy_and_config_before_any_openshell_call(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    # Run the real script bytes from a directory that lacks the policy/config.
    lone = tmp_path / "lone"
    lone.mkdir()
    copied = lone / "create-sandbox.sh"
    copied.write_text(WRAPPER.read_text())
    copied.chmod(0o755)

    proc, calls = _run(copied, tmp_path, clean_env)
    assert proc.returncode != 0
    assert calls == [], "wrapper must not touch openshell when its inputs are missing"
    assert "sandbox-policy.yaml" in proc.stderr or "opencode.json" in proc.stderr


def test_create_sandbox_refuses_existing_name(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    fake = _fake_openshell(tmp_path, get_exit=0)
    proc, calls = _run(WRAPPER, tmp_path, clean_env, fake=fake)

    assert proc.returncode != 0
    assert "opencode-dev" in proc.stderr
    assert calls == [GATEWAY_PREFIX + ["sandbox", "get", "opencode-dev"]]


def test_create_sandbox_dispatches_pinned_create_argv(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    proc, calls = _run(WRAPPER, tmp_path, clean_env)
    assert proc.returncode == 0, proc.stderr

    create = _call_starting(calls, "sandbox", "create")
    assert create[2:4] == ["--from", IMAGE]
    # Digest pin, not a tag: a retagged image would move the binary out from
    # under the policy's pinned path.
    repository, _, digest = create[3].rpartition("@sha256:")
    assert repository == "ghcr.io/kpiwko/opencode-sandbox"
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert create[4:6] == ["--name", "opencode-dev"]
    assert create[6:8] == ["--cpu", "1"]
    assert create[8:10] == ["--memory", "1Gi"]
    assert "--detach" in create
    assert create[create.index("--restart-policy") + 1] == "never"
    assert create[create.index("--policy") + 1] == str(POLICY)
    assert create[create.index("--env-from") + 1] == "AGENTGATEWAY_API_KEY"

    envs = [create[i + 1] for i, arg in enumerate(create) if arg == "--env"]
    assert "HOME=/sandbox" in envs
    assert (
        "AGENTGATEWAY_BASE_URL=http://agentgateway.ai-dev.svc.cluster.local:4000/v1"
        in envs
    )
    assert (
        "OPENCODE_OTLP_ENDPOINT=http://otel-collector.ai-dev.svc.cluster.local:4318"
        in envs
    )
    # Everything after `--` is the sandbox's main process: `sleep infinity`,
    # passed as the command plus its argument rather than one shell string.
    assert create[-3:] == ["--", "sleep", "infinity"]


def test_create_sandbox_honours_name_flag(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    proc, calls = _run(WRAPPER, tmp_path, clean_env, args=["--name", "opencode-scratch"])
    assert proc.returncode == 0, proc.stderr

    assert GATEWAY_PREFIX + ["sandbox", "get", "opencode-scratch"] in calls
    create = _call_starting(calls, "sandbox", "create")
    assert create[create.index("--name") + 1] == "opencode-scratch"
    upload = _call_starting(calls, "sandbox", "upload")
    assert upload[2] == "opencode-scratch"
    assert _call_starting(calls, "sandbox", "exec")[3] == "opencode-scratch"


def test_create_sandbox_passes_key_by_reference_never_by_value(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    proc, calls = _run(WRAPPER, tmp_path, clean_env)
    assert proc.returncode == 0, proc.stderr

    create = _call_starting(calls, "sandbox", "create")
    assert "--env-from" in create
    assert SENTINEL_KEY not in " ".join(arg for call in calls for arg in call)
    assert SENTINEL_KEY not in proc.stdout
    assert SENTINEL_KEY not in proc.stderr
    # The wrapper must not carry a literal key either.
    assert SENTINEL_KEY not in WRAPPER.read_text()


def test_create_sandbox_uploads_config_after_create_every_run(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    fake = _fake_openshell(tmp_path, get_exit=1)
    record = tmp_path / "openshell-argv.log"

    first, calls = _run(WRAPPER, tmp_path, clean_env, fake=fake)
    assert first.returncode == 0, first.stderr
    record.unlink()
    record.touch()
    second, calls = _run(WRAPPER, tmp_path, clean_env, fake=fake)
    assert second.returncode == 0, second.stderr

    kinds = [_strip_global_flags(call)[:2] for call in calls]
    assert kinds == [
        ["sandbox", "get"],
        ["sandbox", "create"],
        ["sandbox", "upload"],
        ["sandbox", "exec"],
    ]
    upload = _strip_global_flags(calls[2])
    assert upload[2] == "opencode-dev"
    assert upload[3] == str(OPENCODE / "opencode.json")
    assert upload[4] == "/sandbox/.config/opencode/opencode.json"
    assert upload[5] == "--no-git-ignore"


def test_create_sandbox_fails_on_binary_path_mismatch(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    fake = _fake_openshell(tmp_path, opencode_path="/usr/bin/opencode")
    proc, _ = _run(WRAPPER, tmp_path, clean_env, fake=fake)

    assert proc.returncode != 0
    assert "/usr/bin/opencode" in proc.stderr
    assert "/usr/local/bin/opencode" in proc.stderr


def test_wrapper_binary_constant_matches_policy() -> None:
    source = WRAPPER.read_text()
    matches = [
        line.split("=", 1)[1].strip().strip('"')
        for line in source.splitlines()
        if line.startswith("OPENCODE_BINARY=")
    ]
    assert len(matches) == 1, source
    declared = matches[0]
    paths = {b["path"] for p in _policy()["network_policies"].values() for b in p["binaries"]}
    assert paths == {declared}


# --- documentation ----------------------------------------------------------
#
# The stage README is operator-facing. These assertions pin the statements a
# future edit must not quietly drop: the digest pin, reference-only credential
# handling, the absence of a silent image fallback, the deny-by-default and
# hard-Landlock posture, and the limits an operator has to know about. Each
# assertion is scoped to the section it belongs to, so unrelated prose cannot
# satisfy it.

STAGE_README = OPENCODE / "README.md"


def _stage_readme() -> str:
    return STAGE_README.read_text()


def _section(readme: str, heading: str) -> str:
    match = re.search(r"(?ms)^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", readme)
    assert match, f"README has no '## {heading}' section"
    return match.group(1)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n[ \t]*\n", text) if p.strip()]


def test_readme_documents_digest_pin_and_wrapper_interfaces() -> None:
    readme = _stage_readme()

    assert IMAGE in readme
    repository, _, digest = IMAGE.rpartition("@sha256:")
    assert repository == "ghcr.io/kpiwko/opencode-sandbox"
    assert digest in readme

    # Wrapper interfaces an operator needs to reproduce the invocation.
    assert "create-sandbox.sh" in readme
    assert "--name" in readme
    assert "opencode-dev" in readme
    assert "OPENSHELL_BIN" in readme


def test_readme_documents_reference_only_key_handling() -> None:
    readme = _stage_readme()

    assert "--env-from AGENTGATEWAY_API_KEY" in readme
    assert "AGENTGATEWAY_API_KEY" in readme

    # No literal credential may reach the documentation: no assignment of a
    # value to the key variable (in a shell, an env file, or a hand-rolled
    # `--env` pass-through) and no key-shaped token anywhere in the prose.
    assert not re.search(r"AGENTGATEWAY_API_KEY=", readme)
    assert not re.search(r"AGENTGATEWAY_API_KEY\s+[=:]\s*\S", readme)
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{8,}", readme)


def test_readme_documents_no_silent_image_fallback() -> None:
    fallback = _section(_stage_readme(), "Image fallback (manual, not automatic)")

    # The wrapper fails closed on anything unexpected; replacing the image is a
    # deliberate, manual edit, never automatic.
    assert "no automatic fallback" in fallback.lower()
    assert "fails closed" in fallback
    assert "NVIDIA" in fallback
    assert "Image/Containerfile" in fallback or "image/Containerfile" in fallback
    # The step has to name the files an operator actually edits, not rely on the
    # layout table at the top of the document.
    assert "opencode.json" in fallback
    assert "sandbox-policy.yaml" in fallback


def test_readme_forbids_relaxing_landlock_wherever_it_names_it() -> None:
    readme = _stage_readme()
    posture = _section(readme, "Posture")

    assert "deny-by-default" in posture
    assert "landlock.compatibility: hard_requirement" in posture
    assert "enforcement: enforce" in posture
    assert "/usr/local/bin/opencode" in posture
    assert "sandbox-policy.yaml" in readme

    # Merely containing the word `best_effort` must never read as advice: every
    # paragraph that names it has to forbid it.
    offending = [
        paragraph
        for paragraph in _paragraphs(readme)
        if "best_effort" in paragraph
        and not any(word in paragraph.lower() for word in ("never", "do not"))
    ]
    assert offending == [], f"best_effort mentioned without a prohibition: {offending}"


def test_readme_troubleshooting_maps_symptoms_to_causes() -> None:
    troubleshooting = _section(_stage_readme(), "Troubleshooting")

    # Every symptom an operator will actually hit, with its real cause.
    assert "every request is denied" in troubleshooting.lower()
    assert "binary path" in troubleshooting
    assert "/v1/traces" in troubleshooting
    assert "main process" in troubleshooting
    assert "Landlock" in troubleshooting

    # The probe has to run through a shell: `command` is a builtin, so the
    # documented command uses `-- sh -c`, not a bare `-- command ...`.
    probes = [
        block
        for block in re.findall(r"```text\n(.*?)```", troubleshooting, re.S)
        if "command -v opencode" in block
    ]
    assert len(probes) == 1, probes
    assert "-- sh -c 'command -v opencode'" in probes[0]


def test_readme_lists_what_the_stage_does_not_include() -> None:
    readme = _stage_readme()

    excluded = _section(readme, "Not included")
    for item in (
        "repositories",
        "GitHub",
        "GitLab",
        "workspace",
        "MCP",
        "Dex",
        "OIDC",
        "Caddy",
    ):
        assert item in excluded


def test_readme_documents_lifecycle_and_evidence_status() -> None:
    readme = _stage_readme()

    for command in (
        "sandbox create",
        "sandbox exec",
        "sandbox stop",
        "sandbox start",
        "sandbox delete",
    ):
        assert command in readme

    # A live run happened, so the doc may assert CLI behaviour — but only the
    # parts it exercised, and the untested duplicate-name path must stay honest.
    section = _section(readme, "Verified and unverified")
    assert "Verified in a live run" in section
    assert "sleep infinity" in section
    assert "/usr/local/bin/opencode" in section
    assert "Still unverified" in section
    assert "Duplicate-name" in section


def test_readme_records_that_telemetry_and_state_path_were_observed() -> None:
    readme = _stage_readme()

    section = _section(readme, "Verified and unverified")
    # Both were listed as assumptions before the live run; the trace that landed
    # in experiment 23 and the observed state directory settle them.
    assert "OTLP endpoint shape" in section
    assert "/v1/traces" in section
    assert "/sandbox/.local/share/opencode" in section

    telemetry = _section(readme, "Telemetry")
    assert "confirmed" in telemetry
    assert "unverified assumption" not in telemetry


def _gateway_flags(calls: list[list[str]]) -> list[list[str]]:
    return [
        call[:4]
        for call in calls
        if len(call) >= 4 and call[0] == GATEWAY_NAME_FLAG and call[2] == GATEWAY_FLAG
    ]


def test_create_sandbox_names_the_kubernetes_gateway_on_every_call(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    # Without an explicit gateway the CLI would use whatever registration is
    # current for the operator — on this machine the host gateway — and the
    # sandbox would land in the wrong place. The registration name carries the
    # mTLS material; the endpoint points it at the live Kubernetes NodePort.
    proc, calls = _run(WRAPPER, tmp_path, clean_env)
    assert proc.returncode == 0, proc.stderr

    assert [_strip_global_flags(call)[:2] for call in calls] == [
        ["sandbox", "get"],
        ["sandbox", "create"],
        ["sandbox", "upload"],
        ["sandbox", "exec"],
    ]
    assert _gateway_flags(calls) == [GATEWAY_PREFIX] * 4
    # The printed follow-ups must reach the same gateway as the create did.
    follow_ups = [
        line
        for line in proc.stdout.splitlines()
        if line.strip().startswith(("exec:", "stop:", "start:", "delete:"))
    ]
    assert len(follow_ups) == 4
    for line in follow_ups:
        assert f"{GATEWAY_NAME_FLAG} {GATEWAY_NAME} {GATEWAY_FLAG} {GATEWAY_DEFAULT}" in line


def test_create_sandbox_gateway_endpoint_flag_overrides_every_call(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    flag_endpoint = "https://10.42.7.9:19999"
    proc, calls = _run(
        WRAPPER,
        tmp_path,
        clean_env,
        args=[GATEWAY_FLAG, flag_endpoint],
        endpoint="https://env-should-lose.example:1",
    )
    assert proc.returncode == 0, proc.stderr

    assert _gateway_flags(calls) == [
        [GATEWAY_NAME_FLAG, GATEWAY_NAME, GATEWAY_FLAG, flag_endpoint]
    ] * 4
    recorded = " ".join(arg for call in calls for arg in call)
    assert "env-should-lose.example" not in recorded, "flag must win over the env default"


def test_create_sandbox_gateway_endpoint_env_override(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    env_endpoint = "https://10.42.7.9:18888"
    proc, calls = _run(WRAPPER, tmp_path, clean_env, endpoint=env_endpoint)
    assert proc.returncode == 0, proc.stderr

    assert _gateway_flags(calls) == [
        [GATEWAY_NAME_FLAG, GATEWAY_NAME, GATEWAY_FLAG, env_endpoint]
    ] * 4


def test_create_sandbox_help_documents_gateway_endpoint(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    proc, calls = _run(WRAPPER, tmp_path, clean_env, args=["--help"])

    assert proc.returncode == 0
    assert calls == []
    assert GATEWAY_FLAG in proc.stderr
    assert GATEWAY_DEFAULT in proc.stderr
    # The registration supplying the mTLS material is part of the interface the
    # operator has to know, not an implementation detail.
    assert GATEWAY_NAME_FLAG in proc.stderr
    assert GATEWAY_NAME in proc.stderr
    assert "OPENSHELL_GATEWAY_NAME" in proc.stderr


def test_create_sandbox_existing_name_error_names_the_effective_gateway(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    # The cleanup hint must carry the endpoint this run used, or an operator
    # would delete the same-named sandbox on the host gateway.
    endpoint = "https://10.42.7.9:19999"
    fake = _fake_openshell(tmp_path, get_exit=0)
    proc, calls = _run(
        WRAPPER,
        tmp_path,
        clean_env,
        args=[GATEWAY_FLAG, endpoint],
        fake=fake,
    )

    assert proc.returncode != 0
    assert f"{GATEWAY_FLAG} {endpoint} sandbox delete opencode-dev" in proc.stderr
    assert calls == [
        [GATEWAY_NAME_FLAG, GATEWAY_NAME, GATEWAY_FLAG, endpoint, "sandbox", "get", "opencode-dev"]
    ]


def test_create_sandbox_binary_mismatch_error_names_the_effective_gateway(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    endpoint = "https://10.42.7.9:19999"
    fake = _fake_openshell(tmp_path, opencode_path="/usr/bin/opencode")
    proc, _ = _run(
        WRAPPER,
        tmp_path,
        clean_env,
        args=[GATEWAY_FLAG, endpoint],
        fake=fake,
    )

    assert proc.returncode != 0
    assert "/usr/bin/opencode" in proc.stderr
    assert f"{GATEWAY_FLAG} {endpoint} sandbox delete opencode-dev" in proc.stderr


def test_create_sandbox_help_shows_the_literal_default_not_the_env_value(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    # The help text documents the shipped default; printing the operator's
    # environment value there would present a local override as the default.
    env_endpoint = "https://env-should-not-be-the-default.example:1"
    proc, calls = _run(
        WRAPPER, tmp_path, clean_env, args=["--help"], endpoint=env_endpoint
    )

    assert proc.returncode == 0
    assert calls == []
    assert GATEWAY_DEFAULT in proc.stderr
    assert env_endpoint not in proc.stdout + proc.stderr
    assert "OPENSHELL_GATEWAY_ENDPOINT" in proc.stderr


def test_create_sandbox_rejects_endpoint_value_starting_with_a_dash(
    tmp_path: Path, clean_env: dict[str, str]
) -> None:
    # A dashed value is another flag, never an endpoint; fail on usage instead of
    # handing the CLI something meaningless.
    proc, calls = _run(
        WRAPPER, tmp_path, clean_env, args=[GATEWAY_FLAG, "--not-an-endpoint"]
    )

    assert proc.returncode == 2
    assert calls == []
    assert "usage:" in proc.stderr


# The workload image is built here because the published OpenCode image ships
# OpenCode 1.x, which silently discards V2 configuration. These tests pin the
# build inputs that make the image usable under the sandbox policy.
IMAGE_DIR = OPENCODE / "image"


def test_image_is_built_on_the_pinned_openshell_sandbox_base() -> None:
    containerfile = (IMAGE_DIR / "Containerfile").read_text()

    assert (
        "ghcr.io/nvidia/openshell-community/sandboxes/base@sha256:"
        "aeef1c63f00e2913ea002ccb3aaf925f338b5c5d70e63576f0d95c16a138044e"
        in containerfile
    )
    # A floating tag would silently change the base under the pinned policy.
    assert "FROM ghcr.io/nvidia/openshell-community/sandboxes/base:" not in containerfile


def test_image_installs_opencode_v2_at_the_policy_path() -> None:
    containerfile = (IMAGE_DIR / "Containerfile").read_text()

    # The V1 installer rejects 2.x outright; using it would build a broken image.
    assert "registry.npmjs.org/@opencode/cli-" in containerfile
    assert "ARG OPENCODE_VERSION=2.3.0" in containerfile
    assert "install -m 0755" in containerfile
    assert "/usr/local/bin/opencode" in containerfile


def test_image_runs_as_the_sandbox_user() -> None:
    containerfile = (IMAGE_DIR / "Containerfile").read_text()

    assert "USER sandbox" in containerfile
    assert "WORKDIR /sandbox" in containerfile


def test_build_script_publishes_both_architectures() -> None:
    build = (IMAGE_DIR / "build.sh").read_text()

    assert "linux/amd64,linux/arm64" in build
    assert "podman manifest create" in build
    assert "podman manifest push --all" in build
    assert "ghcr.io/kpiwko/opencode-sandbox" in build


def test_image_pins_a_checksum_per_architecture() -> None:
    containerfile = (IMAGE_DIR / "Containerfile").read_text()

    assert "ARG OPENCODE_SHA256_AMD64=" in containerfile
    assert "ARG OPENCODE_SHA256_ARM64=" in containerfile
    # The checksum, not a version string printed by a freshly downloaded binary, is
    # what guarantees the pulled artifact is the expected one.
    assert "sha256sum -c -" in containerfile
    assert "linux-x64" in containerfile and "linux-arm64" in containerfile


def test_image_clears_the_base_entrypoint() -> None:
    # The base image's ENTRYPOINT is /bin/bash, which turns the wrapper's
    # `-- sleep infinity` into `bash sleep infinity`: bash reads "sleep" as a
    # script path and the sandbox's main process dies immediately.
    containerfile = (IMAGE_DIR / "Containerfile").read_text()

    assert "\nENTRYPOINT []\n" in containerfile


def test_image_binary_check_is_opt_in() -> None:
    # CI cross-builds under QEMU, where Bun aborts when executed. The check must
    # therefore be off by default and switched on only for a native build.
    containerfile = (IMAGE_DIR / "Containerfile").read_text()
    build = (IMAGE_DIR / "build.sh").read_text()

    assert "ARG VERIFY_BINARY=0" in containerfile
    assert '--build-arg "VERIFY_BINARY=$verify"' in build


WORKFLOW = ROOT / ".github" / "workflows" / "opencode-sandbox-image.yml"


def test_ci_publishes_the_image_with_package_write_access() -> None:
    # A developer's gh token has no write:packages, so the registry push has to
    # happen where GITHUB_TOKEN carries that scope.
    workflow = WORKFLOW.read_text()

    assert "packages: write" in workflow
    assert "secrets.GITHUB_TOKEN" in workflow
    assert "docker/login-action" in workflow
    assert "push: true" in workflow


def test_ci_builds_both_architectures_for_the_pinned_image_name() -> None:
    workflow = WORKFLOW.read_text()

    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "ghcr.io/${{ github.repository_owner }}/opencode-sandbox" in workflow
    assert "VERIFY_BINARY=0" in workflow
    # The operator needs the digest, because create-sandbox.sh pins one.
    assert "steps.build.outputs.digest" in workflow


def test_image_bakes_the_pinned_otel_plugin_into_read_only_usr() -> None:
    containerfile = (IMAGE_DIR / "Containerfile").read_text()

    # The plugin is fetched at build time only, at a pinned version, so the
    # runtime needs no npm access.
    assert "FROM node:22-slim AS otel-plugin" in containerfile
    assert "ARG OTEL_PLUGIN_VERSION=2.0.1" in containerfile
    assert (
        "COPY --from=otel-plugin /out/otel "
        "/usr/local/share/opencode/plugins/opencode-plugin-otel" in containerfile
    )


def test_baked_plugin_path_is_covered_by_the_filesystem_policy() -> None:
    # Landlock hard_requirement + a fixed path list: a plugin under /opt or /root
    # would be invisible to the sandbox. /usr is read_only in sandbox-policy.yaml.
    package = _config()["plugins"][0]["package"]
    policy = _policy()["filesystem_policy"]

    assert any(package.startswith(prefix + "/") for prefix in policy["read_only"])
    assert not any(package.startswith(prefix + "/") for prefix in policy["read_write"])
