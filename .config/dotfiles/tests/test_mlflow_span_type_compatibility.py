"""Behavioral coverage for the MLflow 3.17.0 SQL span-type Collector workaround.

Why this exists (measured locally against the exact pinned versions below):
MLflow 3.17.0 writes the SQL ``spans.type`` column only from the inbound
canonical ``mlflow.spanType`` while ``openinference.span.kind`` is translated
into stored *display* attributes only. A local A/B measurement against the
pinned MLflow 3.17.0 showed OpenInference-only spans ingested with a NULL SQL
type (dropping them from grouped ``span_type`` metrics) while spans that also
carried the canonical ``mlflow.spanType=TOOL`` were stored with the indexed
TOOL type. The Collector transform copies the canonical attribute from the
OpenInference kind using exactly the upstream ``OpenInferenceTranslator
.SPAN_KIND_TO_MLFLOW_TYPE`` allowlist of the pinned MLflow 3.17.0 image, and
only when the canonical attribute is absent.

Two layers:

* Default (no containers): consistency between the synthetic fixture cases, the manifest
  statements and the verified allowlist, plus stub-Podman unit regressions for the
  lifecycle's cleanup safety (scoped names, partial startup, cleanup failures).
* Opt-in behavioral (``OTEL_SPAN_TYPE_BEHAVIORAL=1``): ONE atomic isolated Collector
  0.123.0 lifecycle on the existing local Podman, observing the attributes actually
  exported by the collector after the real manifest transform runs. No MLflow stack is
  needed: MLflow-side ingestion was measured separately (see above); this layer checks
  the Collector-side export only. Pinned local images only (``--pull=never``), internal
  fixture network only, no host ports; the objects this run created are removed
  afterwards with logs captured before removal.

Fixture safety: per-run UUID-scoped names ``mlflow6t-<run>-*``, a fresh
``tempfile.mkdtemp`` workdir that never deletes preexisting scratch content,
cleanup of only the objects this run created, Collector 0.5 CPU / 512 MiB,
helper 0.25 CPU / 256 MiB, internal 240 s deadline, <=20 synthetic spans,
<=12 OTLP requests, synthetic header 23 only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import ROOT
from test_otel_collector_manifests import OPENINFERENCE_SPAN_KIND_ALLOWLIST

OTEL_MANIFEST = ROOT / ".config" / "k8s" / "base" / "otel-collector.yaml"
FIXTURE_JSON = Path(__file__).parent / "fixtures" / "opencode_telemetry" / "span_type_cases.json"

# Pinned digests (never mutable tags at run time).
COLLECTOR_IMAGE = (
    "otel/opentelemetry-collector-k8s@sha256:"
    "35c948238c9a03c9b02338dea34da024979bae7fd83c85025d7c00006e0887b4"
)
HELPER_IMAGE = (
    "registry.access.redhat.com/ubi9/python-312@sha256:"
    "26533737695d39d003558de435f54f52bd54879d8184a0d7038147d1ff3ea9bd"
)

# Approved OS scratch root for behavioral runs (overridable). Each run creates
# a FRESH workdir inside it via tempfile.mkdtemp and never deletes anything:
# no preexisting directory, file or symlink is removed or replaced, and the
# workdir is kept after the run for diagnosis.
DEFAULT_SCRATCH = Path(
    "/private/var/folders/9m/5dhpkvg51750wz6ypg9nz25m0000gn/T/opencode/"
    "mlflow-empty-header-repro"
)

# Placeholder inside SENDER_PY, replaced with this run's collector container
# name at write time. The per-run name resolves only on this run's network, so
# the sender can never address another run's collector.
SENDER_COLLECTOR_HOST = "SPAN_TYPE_COLLECTOR_HOST"

DEADLINE_SECONDS = 240
MAX_SPANS = 20
MAX_REQUESTS = 12

# Attribute keys the existing manifest transform may legitimately add. Anything else
# appearing in the export would be fabrication.
TRANSFORM_ADDED_KEYS = frozenset(
    {
        "gen_ai.request.model",
        "gen_ai.response.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.cost",
        "agw.ai.usage.cost.total",
        "mlflow.llm.cost",
        "mlflow.spanType",
    }
)

# Behavioral tests are opt-in: they start ONE isolated Collector 0.123.0 lifecycle on
# the existing local Podman. The default offline suite runs only the static,
# container-free consistency tests at the top of this module.
def _requires_behavioral(func):
    """Apply the opt-in gate to an individual behavioral test function."""
    return pytest.mark.skipif(
        os.environ.get("OTEL_SPAN_TYPE_BEHAVIORAL") != "1",
        reason=(
            "opt-in behavioral test: set OTEL_SPAN_TYPE_BEHAVIORAL=1 "
            "(requires the existing local Podman and the pinned images; starts one "
            "isolated Collector lifecycle)"
        ),
    )(func)


# ---------------------------------------------------------------------------
# Static, container-free layer (always runs)
# ---------------------------------------------------------------------------


def _load_cases() -> tuple[dict, list[dict]]:
    doc = json.loads(FIXTURE_JSON.read_text())
    return doc, doc["cases"]


def _case_kind(case: dict) -> str | None:
    for attr in case["attributes"]:
        if attr["key"] == "openinference.span.kind":
            return attr["value"].get("stringValue")
    return None


def test_fixture_covers_verified_allowlist_exactly() -> None:
    doc, cases = _load_cases()

    assert set(doc["_meta"]["allowlist"]) == set(OPENINFERENCE_SPAN_KIND_ALLOWLIST)
    mapped = {
        _case_kind(c)
        for c in cases
        if c["case"].startswith("supported_") and _case_kind(c) is not None
    }
    assert mapped == set(OPENINFERENCE_SPAN_KIND_ALLOWLIST)
    for c in cases:
        if c["case"].startswith("supported_"):
            assert c["expect_mlflow_span_type"] == _case_kind(c)


def test_fixture_covers_guard_and_negative_cases() -> None:
    doc, cases = _load_cases()

    assert len(cases) <= MAX_SPANS
    names = {c["case"] for c in cases}
    assert {
        "canonical_wins_over_conflicting_kind",
        "canonical_empty_preserved",
        "canonical_nonstring_preserved",
        "unsupported_kind_stays_unmapped",
        "missing_kind_stays_unmapped",
        "nonstring_kind_stays_unmapped",
        "json_serialized_kind_stays_unmapped",
    } <= names


def test_fixture_uses_exact_length_hex_ids() -> None:
    _, cases = _load_cases()

    for c in cases:
        assert len(c["trace_id"]) == 32 and int(c["trace_id"], 16) >= 0
        assert len(c["span_id"]) == 16 and int(c["span_id"], 16) >= 0


# ---------------------------------------------------------------------------
# Fixture config generation (exercises the REAL manifest transform)
# ---------------------------------------------------------------------------


def extract_embedded_collector_config(manifest_text: str) -> str:
    lines = manifest_text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "config.yaml: |")
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("---") or (line and not line.startswith(" ")):
            break
        body.append(line[4:] if line.startswith("    ") else "")
    return "\n".join(body) + "\n"


def build_fixture_config(manifest_text: str, helper_host: str) -> str:
    """Copy the real manifest config, rewriting ONLY the exporter endpoint.

    The transform statements (cost rules, token mapping), batch metadata_keys,
    headers_setter strict auth and the debug exporter are preserved verbatim so the
    behavioral run exercises the actual repository pipeline. ``helper_host`` is
    this run's helper container name (DNS-resolvable on the run's network).
    """
    config = extract_embedded_collector_config(manifest_text)
    assert "endpoint: http://mlflow:5000" in config
    config = config.replace("endpoint: http://mlflow:5000", f"endpoint: http://{helper_host}:8099")
    assert "http://mlflow:5000" not in config
    return config


# ---------------------------------------------------------------------------
# Embedded helper-container scripts (stdlib only, mirror of the proven run-3 walker)
# ---------------------------------------------------------------------------


RECEIVER_PY = r'''
"""Attribute-level OTLP protobuf receiver for the Task 6A transform check.

Extends the proven receiver3.py minimal stdlib protobuf walker (exact 32/16 hex IDs)
to also extract span attributes. Writes ONE JSON line per received POST to
/data/exports.jsonl:

  {"path","header","content_type","bytes","spans":[{"trace_id","span_id","name",
   "attributes":{key:{"s"|"i"|"d"|"b": value}}}]}

Never logs raw bodies. Values outside string/bool/int/double become {"skip": ...}.
"""
import gzip
import http.server
import json
import struct
import sys

LOG = "/data/exports.jsonl"


def read_varint(buf, i):
    val = shift = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, i
        shift += 7


def fields(buf):
    """Yield (field_number, wire_type, value) for length-delimited/fixed/varint."""
    i, n = 0, len(buf)
    while i < n:
        tag, i = read_varint(buf, i)
        fn, wt = tag >> 3, tag & 7
        if wt == 2:
            ln, i = read_varint(buf, i)
            yield fn, wt, buf[i:i + ln]
            i += ln
        elif wt == 0:
            v, i = read_varint(buf, i)
            yield fn, wt, v
        elif wt == 1:
            yield fn, wt, buf[i:i + 8]
            i += 8
        elif wt == 5:
            yield fn, wt, buf[i:i + 4]
            i += 4
        else:
            raise ValueError("unsupported wire type %d" % wt)


def parse_any_value(buf):
    # AnyValue: string_value=1, bool_value=2, int_value=3, double_value=4 (fixed64),
    # array=5, kvlist=6, bytes=7 (oneof: first recognized field wins).
    for fn, wt, v in fields(buf):
        if fn == 1 and wt == 2:
            return {"s": v.decode("utf-8", "replace")}
        if fn == 2 and wt == 0:
            return {"b": bool(v)}
        if fn == 3 and wt == 0:
            return {"i": int(v)}
        if fn == 4 and wt == 1:
            return {"d": struct.unpack("<d", v)[0]}
        if fn in (5, 6, 7):
            return {"skip": "field%d" % fn}
    return {"skip": "empty"}


def parse_span(span):
    # Span: trace_id=1, span_id=2, name=5, attributes=9 (repeated KeyValue).
    out = {"trace_id": None, "span_id": None, "name": None, "attributes": {}}
    for fn, wt, v in fields(span):
        if fn == 1 and wt == 2 and len(v) == 16:
            out["trace_id"] = v.hex()
        elif fn == 2 and wt == 2 and len(v) == 8:
            out["span_id"] = v.hex()
        elif fn == 5 and wt == 2:
            out["name"] = v.decode("utf-8", "replace")
        elif fn == 9 and wt == 2:
            key, val = None, None
            for kfn, kwt, kv in fields(v):  # KeyValue: key=1, value=2
                if kfn == 1 and kwt == 2:
                    key = kv.decode("utf-8", "replace")
                elif kfn == 2 and kwt == 2:
                    val = parse_any_value(kv)
            if key is not None:
                out["attributes"][key] = val or {"skip": "empty"}
    return out


def parse_export_proto(body):
    spans = []
    for fn_rs, wt_rs, rs in fields(body):  # resourceSpans = 1
        if fn_rs != 1 or wt_rs != 2:
            continue
        for fn_ss, wt_ss, ss in fields(rs):  # scopeSpans = 2
            if fn_ss != 2 or wt_ss != 2:
                continue
            for fn_sp, wt_sp, sp in fields(ss):  # spans = 2
                if fn_sp == 2 and wt_sp == 2:
                    spans.append(parse_span(sp))
    return spans


def parse_export_json(body):
    doc = json.loads(body)
    spans = []
    for rs in doc.get("resourceSpans") or []:
        for ss in rs.get("scopeSpans") or []:
            for sp in ss.get("spans") or []:
                attrs = {}
                for a in sp.get("attributes") or []:
                    v = a.get("value") or {}
                    if "stringValue" in v:
                        attrs[a["key"]] = {"s": v["stringValue"]}
                    elif "intValue" in v:
                        attrs[a["key"]] = {"i": int(v["intValue"])}
                    elif "doubleValue" in v:
                        attrs[a["key"]] = {"d": v["doubleValue"]}
                    elif "boolValue" in v:
                        attrs[a["key"]] = {"b": v["boolValue"]}
                    else:
                        attrs[a["key"]] = {"skip": "type"}
                spans.append(
                    {
                        "trace_id": sp.get("traceId"),
                        "span_id": sp.get("spanId"),
                        "name": sp.get("name"),
                        "attributes": attrs,
                    }
                )
    return spans


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _read_body(self):
        te = (self.headers.get("transfer-encoding") or "").lower()
        if "chunked" in te:
            body = b""
            while True:
                line = self.rfile.readline().strip()
                size = int(line.split(b";")[0], 16)
                if size == 0:
                    self.rfile.readline()
                    break
                body += self.rfile.read(size)
                self.rfile.readline()
        else:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else b""
        if "gzip" in (self.headers.get("content-encoding") or "").lower():
            body = gzip.decompress(body)
        return body

    def do_POST(self):
        body = self._read_body()
        vals = self.headers.get_all("x-mlflow-experiment-id")
        header = "ABSENT" if vals is None else vals
        ctype = self.headers.get("content-type") or ""
        try:
            spans = parse_export_json(body) if "json" in ctype else parse_export_proto(body)
            err = None
        except Exception as exc:  # bounded: never crash the receiver
            spans, err = [], "%s: %s" % (type(exc).__name__, exc)
        with open(LOG, "a") as f:
            f.write(
                json.dumps(
                    {
                        "path": self.path,
                        "header": header,
                        "content_type": ctype,
                        "bytes": len(body),
                        "spans": spans,
                        "parse_error": err,
                    }
                )
                + "\n"
            )
        resp = json.dumps({}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("receiver listening on 8099", file=sys.stderr)
    http.server.ThreadingHTTPServer(("0.0.0.0", 8099), H).serve_forever()
'''


SENDER_PY = r'''
"""Synthetic OTLP/JSON sender for the Task 6A transform behavioral check.

Modes:
  send cases.json      -> ONE POST containing every fixture span (pass 1)
  roundtrip FILE       -> re-send the first captured export verbatim (idempotency)

Uses the proven exact-length IDs (traceId 32 hex / spanId 16 hex) required by
Collector 0.123.0 pdata. On non-2xx prints the status and first 2 KiB of the body,
then exits 1.
"""
import http.client
import json
import sys

# Substituted with this run's unique collector container name by the harness.
COLLECTOR = ("SPAN_TYPE_COLLECTOR_HOST", 4318)
NOW = "1793130745000000000"


def wrap(spans):
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "span-type-fixture"}}
                    ]
                },
                "scopeSpans": [{"scope": {"name": "span-type-check"}, "spans": spans}],
            }
        ]
    }


def value_back(v):
    if "s" in v:
        return {"stringValue": v["s"]}
    if "i" in v:
        return {"intValue": str(v["i"])}
    if "d" in v:
        return {"doubleValue": v["d"]}
    if "b" in v:
        return {"boolValue": v["b"]}
    return None


def build_from_cases(path):
    cases = json.load(open(path))["cases"]
    spans = []
    for c in cases:
        spans.append(
            {
                "traceId": c["trace_id"],
                "spanId": c["span_id"],
                "name": "span-type." + c["case"],
                "kind": 1,
                "startTimeUnixNano": NOW,
                "endTimeUnixNano": "1793130746000000000",
                "status": {"code": 1},
                "attributes": c["attributes"],
            }
        )
    return wrap(spans)


def build_from_export(path):
    with open(path) as f:
        line = next(l for l in f if l.strip())
    export = json.loads(line)
    spans = []
    for sp in export["spans"]:
        attrs = []
        for k, v in sp["attributes"].items():
            back = value_back(v)
            if back is not None:  # skip unparsed kinds rather than fabricate values
                attrs.append({"key": k, "value": back})
        spans.append(
            {
                "traceId": sp["trace_id"],
                "spanId": sp["span_id"],
                "name": sp["name"],
                "kind": 1,
                "startTimeUnixNano": NOW,
                "endTimeUnixNano": "1793130746000000000",
                "status": {"code": 1},
                "attributes": attrs,
            }
        )
    return wrap(spans)


def post(payload):
    body = json.dumps(payload).encode()
    headers = {"content-type": "application/json", "x-mlflow-experiment-id": "23"}
    conn = http.client.HTTPConnection(*COLLECTOR, timeout=15)
    conn.request("POST", "/v1/traces", body=body, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    if not 200 <= r.status < 300:
        print("send status=%s reason=%s" % (r.status, r.reason))
        print("body_first_2k=%s" % data[:2048].decode("utf-8", "replace"))
        sys.exit(1)
    print("send ok status=%s spans=%d" % (r.status, len(payload["resourceSpans"][0]["scopeSpans"][0]["spans"])))


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    post(build_from_cases(path) if mode == "send" else build_from_export(path))
'''


# ---------------------------------------------------------------------------
# Opt-in lifecycle
# ---------------------------------------------------------------------------


def _podman(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["podman", *args], text=True, capture_output=True, check=False, timeout=timeout
    )


@dataclass
class _RunObjects:
    """This run's fresh scratch workdir, unique object names and owned labels.

    Created lazily by :func:`new_run_objects`; never shared with other runs.
    """

    run_id: str
    workdir: Path
    network: str
    helper: str
    collector: str

    def own_labels(self) -> list[str]:
        """Podman ``--label`` filters matching ONLY this run's objects."""
        return [f"mlflow6t.run={self.run_id}"]

    def all_names(self) -> list[str]:
        return [self.network, self.helper, self.collector]


def new_run_objects(scratch_root: Path | None = None, run_id: str | None = None) -> _RunObjects:
    """Allocate a fresh, uniquely named run: workdir + UUID-scoped object names.

    Safety properties (unit-regression locked below):

    * The workdir is a fresh ``tempfile.mkdtemp`` inside the approved scratch
      root: per-run, and it never deletes or replaces preexisting content
      (no ``rmtree`` of any existing path, and ``mkdtemp`` never follows an
      existing symlink or reuses an existing name).
    * Container/network names embed the run UUID, so a name collision with
      another run (or any preexisting Podman object) cannot happen.
    * ``mkdtemp`` failure raises instead of falling back to a shared path.
    """
    root = Path(
        os.environ.get("OTEL_SPAN_TYPE_SCRATCH") or DEFAULT_SCRATCH
        if scratch_root is None
        else scratch_root
    )
    run = run_id or uuid.uuid4().hex[:12]
    # mkdtemp: creates a NEW unique directory (fails if it cannot), never
    # deletes or reuses anything preexisting. Prefix ties it to this harness.
    workdir = Path(tempfile.mkdtemp(prefix=f"span-type-{run}-", dir=root))
    return _RunObjects(
        run_id=run,
        workdir=workdir,
        network=f"mlflow6t-{run}-net",
        helper=f"mlflow6t-{run}-helper",
        collector=f"mlflow6t-{run}-collector",
    )


def network_create_args(run: _RunObjects) -> list[str]:
    """Podman argv creating this run's network, labeled with the run id.

    The scoped leftover check filters by ``mlflow6t.run=<run_id>``; creation
    must apply the SAME label (like the container runs do), otherwise a
    network whose removal failed would be invisible to the leftover check.
    """
    return [
        "network", "create", "--internal",
        "--label", f"mlflow6t.run={run.run_id}",
        run.network,
    ]


class _Deadline:
    def __init__(self, seconds: int) -> None:
        self.stop_at = time.monotonic() + seconds

    def check(self, where: str) -> None:
        if time.monotonic() >= self.stop_at:
            raise AssertionError(f"internal {DEADLINE_SECONDS}s deadline hit at {where}")


@pytest.fixture(scope="module")
def span_type_run():
    """One atomic isolated Collector lifecycle; cleanup always runs.

    Returns a dict with the captured exports, per-pass span maps, the run log and the
    post-cleanup state so tests can assert on both behavior and cleanup.
    """
    if os.environ.get("OTEL_SPAN_TYPE_BEHAVIORAL") != "1":
        pytest.skip("opt-in behavioral fixture")
    doc, cases = _load_cases()
    assert len(cases) <= MAX_SPANS

    run_obj = new_run_objects()
    workdir = run_obj.workdir
    (workdir / "data").mkdir()

    config = build_fixture_config(OTEL_MANIFEST.read_text(), run_obj.helper)
    (workdir / "collector-fixture.yaml").write_text(config)
    (workdir / "helper_receiver.py").write_text(RECEIVER_PY)
    (workdir / "otlp_sender.py").write_text(SENDER_PY.replace(SENDER_COLLECTOR_HOST, run_obj.collector))
    (workdir / "cases.json").write_text(json.dumps(doc))

    run_log: list[str] = []

    def say(message: str) -> None:
        entry = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}"
        run_log.append(entry)
        _RUN_LOG_STASH[:] = run_log

    deadline = _Deadline(DEADLINE_SECONDS)
    exports_path = workdir / "data" / "exports.jsonl"

    def _read_exports() -> list[dict]:
        if not exports_path.exists():
            return []
        return [json.loads(line) for line in exports_path.read_text().splitlines() if line.strip()]

    def _wait_exports(count: int, seconds: int, what: str) -> list[dict]:
        stop = time.monotonic() + seconds
        while time.monotonic() < stop:
            exports = _read_exports()
            if len(exports) >= count and not any(e.get("parse_error") for e in exports):
                say(f"{what}: {len(exports)} export(s), {sum(len(e['spans']) for e in exports)} spans")
                return exports
            time.sleep(1)
        raise AssertionError(
            f"{what} did not arrive within {seconds}s; run log: {run_log}; exports: {_read_exports()}"
        )

    try:
        say(f"lifecycle start; workdir={workdir}")
        say(f"collector={COLLECTOR_IMAGE}")
        say(f"helper={HELPER_IMAGE}")

        r = _podman(*network_create_args(run_obj))
        say(f"network create rc={r.returncode} {r.stdout.strip()}{r.stderr.strip()}")
        if r.returncode != 0:
            raise AssertionError(f"network create failed: {r.stderr}")

        r = _podman(
            "run", "-d", "--pull=never", "--name", run_obj.helper,
            "--label", f"mlflow6t.run={run_obj.run_id}",
            "--network", run_obj.network,
            "--cpus", "0.25", "--memory", "256m",
            "-v", f"{workdir}:/fixture:ro", "-v", f"{workdir / 'data'}:/data",
            HELPER_IMAGE, "python3", "/fixture/helper_receiver.py",
        )
        say(f"helper run rc={r.returncode} {r.stdout.strip()}{r.stderr.strip()}")
        if r.returncode != 0:
            raise AssertionError(f"helper run failed: {r.stderr}")

        r = _podman(
            "run", "-d", "--pull=never", "--name", run_obj.collector,
            "--label", f"mlflow6t.run={run_obj.run_id}",
            "--network", run_obj.network,
            "--cpus", "0.5", "--memory", "512m",
            "-v", f"{workdir / 'collector-fixture.yaml'}:/etc/otelcol/config.yaml:ro",
            COLLECTOR_IMAGE, "--config=/etc/otelcol/config.yaml",
        )
        say(f"collector run rc={r.returncode} {r.stdout.strip()}{r.stderr.strip()}")
        if r.returncode != 0:
            raise AssertionError(f"collector run failed: {r.stderr}")

        ready = False
        stop = time.monotonic() + 60
        while time.monotonic() < stop:
            code = _podman(
                "exec", run_obj.helper, "python3", "-c",
                "import http.client\n"
                "try:\n"
                f"    c=http.client.HTTPConnection('{run_obj.collector}',4318,timeout=5)\n"
                "    c.request('GET','/')\n"
                "    r=c.getresponse(); r.read(); print(r.status)\n"
                "except Exception as e:\n"
                "    print('ERR',type(e).__name__)\n",
                timeout=30,
            )
            status = code.stdout.strip()
            if status in {"200", "400", "404", "405"}:
                say(f"collector otlp receiver responding (status {status})")
                ready = True
                break
            time.sleep(3)
        if not ready:
            logs = _podman("logs", "--tail", "60", run_obj.collector)
            raise AssertionError(
                f"collector readiness timeout; collector log tail:\n{logs.stdout}{logs.stderr}"
            )
        deadline.check("readiness")

        # Pass 1: every fixture case in ONE OTLP request (header 23, synthetic only).
        r = _podman("exec", run_obj.helper, "python3", "/fixture/otlp_sender.py", "send", "/fixture/cases.json", timeout=30)
        say(f"pass1 send rc={r.returncode} {r.stdout.strip()}{r.stderr.strip()}")
        if r.returncode != 0:
            raise AssertionError(f"pass1 send failed: {r.stdout}{r.stderr}")
        deadline.check("pass1")

        first_pass = _wait_exports(1, 20, "pass1 export")
        deadline.check("pass1 export")

        # Pass 2 (idempotency): re-send the exact captured export body.
        (workdir / "roundtrip.json").write_text(exports_path.read_text())
        r = _podman("exec", run_obj.helper, "python3", "/fixture/otlp_sender.py", "roundtrip", "/fixture/roundtrip.json", timeout=30)
        say(f"pass2 (roundtrip) send rc={r.returncode} {r.stdout.strip()}{r.stderr.strip()}")
        if r.returncode != 0:
            raise AssertionError(f"pass2 send failed: {r.stdout}{r.stderr}")

        exports = _wait_exports(2, 20, "pass2 export")
        deadline.check("pass2 export")

        return {
            "workdir": workdir,
            "run_log": run_log,
            "exports": exports,
            "first": _spans_by_id(exports[0]),
            "second": _spans_by_id(exports[1]),
            "cases": {c["case"]: c for c in cases},
        }
    finally:
        # Cleanup removes ONLY the objects this run created. Ownership is
        # tracked two ways: the unique per-run names created above, and the
        # ``mlflow6t.run=<run_id>`` labels applied at creation. Failure paths
        # that raise before a resource exists never attempt to remove it,
        # cleanup failures are recorded but cannot mask the original failure,
        # and nothing outside this run's names/labels is ever touched.
        cleanup = cleanup_run_objects(run_obj, _podman, say)
        _LAST_CLEANUP.update(cleanup)


def cleanup_run_objects(
    run: _RunObjects,
    podman: Callable[..., subprocess.CompletedProcess[str]],
    log: Callable[[str], None] = lambda message: None,
) -> dict:
    """Capture logs, then remove ONLY the objects this run created.

    Returns the cleanup state for in-test assertions. Never raises: cleanup
    failures are recorded so they cannot mask the original test failure, and
    the original exception (if any) propagates from the caller's ``finally``.
    """
    workdir = run.workdir
    owned_containers: list[str] = []
    owned_network: str | None = None
    errors: list[str] = []

    # 1. Capture collector logs BEFORE any removal (caps: 200 lines / 64 KiB).
    try:
        logs = podman("logs", "--tail", "200", run.collector, timeout=60)
        (workdir / "collector.log").write_text(logs.stdout[-65536:] + logs.stderr[-65536:])
        exports = workdir / "data" / "exports.jsonl"
        if exports.exists():
            shutil.copy(exports, workdir / "exports-final.jsonl")
        log("logs captured before removal")
    except Exception as exc:  # noqa: BLE001 - capture failure must not stop cleanup
        errors.append(f"log capture: {exc}")
        log(f"log capture error: {exc}")

    # 2. Remove ONLY this run's named containers. The name embeds the run UUID
    #    and the label records ownership; both were created by this run. A
    #    container that never started (partial startup failure) is simply
    #    reported as "no such container" by Podman, which is not an error.
    for name in (run.collector, run.helper):
        try:
            r = podman("rm", "-f", "-t", "5", name, timeout=60)
            if r.returncode == 0:
                owned_containers.append(name)
                log(f"removed container {name}")
            else:
                log(f"container {name} not removed rc={r.returncode} {r.stderr.strip()}")
                if "no such" not in (r.stderr or "").lower():
                    errors.append(f"rm {name}: rc={r.returncode} {r.stderr.strip()}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"rm {name}: {exc}")
            log(f"container removal error {name}: {exc}")

    # 3. Remove ONLY this run's named network (same ownership rule).
    try:
        r = podman("network", "rm", run.network, timeout=60)
        if r.returncode == 0:
            owned_network = run.network
            log(f"removed network {run.network}")
        else:
            log(f"network {run.network} not removed rc={r.returncode} {r.stderr.strip()}")
            if "no such" not in (r.stderr or "").lower():
                errors.append(f"network rm: rc={r.returncode} {r.stderr.strip()}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"network rm: {exc}")
        log(f"network removal error: {exc}")

    # 4. Exact scoped leftover check: only this run's names may be absent, and
    #    only this run's names are queried. Other runs' mlflow6t-* objects
    #    (different run UUID) are not listed and never deleted.
    left_containers: list[str] = []
    left_networks: list[str] = []
    try:
        remain = podman("ps", "-a", "--filter", f"label=mlflow6t.run={run.run_id}", "--format", "{{.Names}}")
        left_containers = remain.stdout.split()
        remain_n = podman("network", "ls", "--filter", f"label=mlflow6t.run={run.run_id}", "--format", "{{.Name}}")
        left_networks = remain_n.stdout.split()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"leftover check: {exc}")

    log(
        f"cleanup done; owned removed containers={owned_containers} "
        f"network={owned_network}; remaining labeled containers={left_containers} "
        f"networks={left_networks}; errors={errors}"
    )
    try:
        (workdir / "run.log").write_text("\n".join(_RUN_LOG_STASH) + "\n")
    except Exception:
        pass
    return {
        "run_id": run.run_id,
        "run_names": run.all_names(),
        "containers": left_containers,
        "networks": left_networks,
        "removed_containers": owned_containers,
        "removed_network": owned_network,
        "errors": errors,
        "run_log": list(_RUN_LOG_STASH),
    }


# Module-level log stash so cleanup_run_objects can persist the run log even
# though the fixture's say() closure is not always available (unit stubs).
_RUN_LOG_STASH: list[str] = []


_LAST_CLEANUP: dict = {}


def _spans_by_id(export: dict) -> dict[tuple[str, str], dict]:
    return {(sp["trace_id"], sp["span_id"]): sp for sp in export["spans"]}


# ---------------------------------------------------------------------------
# Behavioral assertions
# ---------------------------------------------------------------------------


@_requires_behavioral
def test_supported_kinds_mapped(span_type_run) -> None:
    for name, case in span_type_run["cases"].items():
        if not name.startswith("supported_"):
            continue
        attrs = span_type_run["first"][(case["trace_id"], case["span_id"])]["attributes"]
        assert attrs.get("mlflow.spanType") == {"s": case["expect_mlflow_span_type"]}, name
        # The OpenInference kind itself is never rewritten.
        assert attrs.get("openinference.span.kind") == {"s": case["expect_mlflow_span_type"]}, name


@_requires_behavioral
def test_canonical_type_wins(span_type_run) -> None:
    run = span_type_run
    conflicting = run["cases"]["canonical_wins_over_conflicting_kind"]
    attrs = run["first"][(conflicting["trace_id"], conflicting["span_id"])]["attributes"]
    assert attrs["mlflow.spanType"] == {"s": "CHAIN"}
    assert attrs["openinference.span.kind"] == {"s": "TOOL"}

    empty = run["cases"]["canonical_empty_preserved"]
    attrs = run["first"][(empty["trace_id"], empty["span_id"])]["attributes"]
    assert attrs["mlflow.spanType"] == {"s": ""}

    nonstring = run["cases"]["canonical_nonstring_preserved"]
    attrs = run["first"][(nonstring["trace_id"], nonstring["span_id"])]["attributes"]
    assert attrs["mlflow.spanType"] == {"i": 42}


@_requires_behavioral
def test_unsupported_missing_and_nonstring_kinds_stay_unmapped(span_type_run) -> None:
    run = span_type_run
    for name in (
        "unsupported_kind_stays_unmapped",
        "missing_kind_stays_unmapped",
        "nonstring_kind_stays_unmapped",
        "json_serialized_kind_stays_unmapped",
    ):
        case = run["cases"][name]
        attrs = run["first"][(case["trace_id"], case["span_id"])]["attributes"]
        assert "mlflow.spanType" not in attrs, name


@_requires_behavioral
def test_existing_io_tokens_cost_and_other_attrs_unchanged(span_type_run) -> None:
    run = span_type_run
    for name, case in run["cases"].items():
        sent = {a["key"]: a["value"] for a in case["attributes"]}
        attrs = run["first"][(case["trace_id"], case["span_id"])]["attributes"]

        # No fabricated attributes beyond the manifest's known mapping surface.
        added = set(attrs) - set(sent)
        assert added <= TRANSFORM_ADDED_KEYS, f"{name}: unexpected added keys {added}"

        for key, value in sent.items():
            expected = (
                {"s": value["stringValue"]}
                if "stringValue" in value
                else {"i": int(value["intValue"])}
                if "intValue" in value
                else {"d": value["doubleValue"]}
                if "doubleValue" in value
                else {"b": value["boolValue"]}
            )
            assert attrs.get(key) == expected, f"{name}: {key} changed"

    # Existing token/cost mappings still apply alongside the new statements.
    agent = run["cases"]["supported_agent"]
    attrs = run["first"][(agent["trace_id"], agent["span_id"])]["attributes"]
    assert attrs["gen_ai.usage.input_tokens"] == {"i": 11}
    assert attrs["gen_ai.usage.output_tokens"] == {"i": 7}
    assert attrs["gen_ai.usage.cost"] == {"d": 0.011}
    assert attrs["mlflow.llm.cost"]["s"].startswith('{"input_cost": 0, "output_cost": 0')


@_requires_behavioral
def test_transform_is_idempotent(span_type_run) -> None:
    run = span_type_run
    assert set(run["first"]) == set(run["second"])
    for key, first in run["first"].items():
        assert run["second"][key]["attributes"] == first["attributes"], key


@_requires_behavioral
def test_exporter_header_and_batch_metadata_preserved(span_type_run) -> None:
    for export in span_type_run["exports"]:
        assert export["header"] == ["23"]
        assert export["parse_error"] is None


@_requires_behavioral
def test_no_fixture_objects_remain(span_type_run) -> None:
    # Exact scoped leftovers: this run's labeled objects are all gone...
    assert _LAST_CLEANUP["containers"] == []
    assert _LAST_CLEANUP["networks"] == []
    # ...every created object was actually removed...
    assert sorted(_LAST_CLEANUP["removed_containers"]) == sorted(
        [n for n in _LAST_CLEANUP["run_names"] if n.endswith(("-helper", "-collector"))]
    )
    assert _LAST_CLEANUP["removed_network"] == f"mlflow6t-{_LAST_CLEANUP['run_id']}-net"
    # ...and no cleanup step failed silently.
    assert _LAST_CLEANUP["errors"] == []


# ---------------------------------------------------------------------------
# Cleanup-safety unit regressions (stub Podman; no containers are ever started)
# ---------------------------------------------------------------------------


class _StubPodman:
    """Records podman commands; answers from a canned result table.

    ``fail_exact`` maps a FULL argument tuple to a nonzero CompletedProcess
    (target-specific Podman failure, e.g. "no such container"); ``fail`` maps
    a command verb to a blanket failure; ``raise_on`` maps a verb to an
    exception (transport/timeout). Unlisted commands succeed with empty output.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail: dict[str, subprocess.CompletedProcess[str]] = {}
        self.fail_exact: dict[tuple[str, ...], subprocess.CompletedProcess[str]] = {}
        self.raise_on: dict[str, Exception] = {}

    def __call__(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        self.calls.append(tuple(args))
        if args[0] in self.raise_on:
            raise self.raise_on[args[0]]
        if tuple(args) in self.fail_exact:
            return self.fail_exact[tuple(args)]
        if args[0] in self.fail:
            return self.fail[args[0]]
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="", stderr="")


def _stub_run(tmp_path: Path, run_id: str = "abc123def456") -> tuple[_RunObjects, _StubPodman]:
    workdir = tmp_path / f"span-type-{run_id}-workdir"
    workdir.mkdir()
    return (
        _RunObjects(
            run_id=run_id,
            workdir=workdir,
            network=f"mlflow6t-{run_id}-net",
            helper=f"mlflow6t-{run_id}-helper",
            collector=f"mlflow6t-{run_id}-collector",
        ),
        _StubPodman(),
    )


def test_run_names_are_per_run_unique_and_scoped(tmp_path: Path) -> None:
    # Two runs never share a container/network name: the fixed "mlflow6t-*"
    # prefix collided across runs; per-run UUID names cannot.
    first = new_run_objects(scratch_root=tmp_path)
    second = new_run_objects(scratch_root=tmp_path)
    assert first.run_id != second.run_id
    assert {first.network, first.helper, first.collector}.isdisjoint(
        {second.network, second.helper, second.collector}
    )
    for name in (*first.all_names(), *second.all_names()):
        assert name.startswith("mlflow6t-")
    # Labels scope ownership queries to exactly one run.
    assert first.own_labels() == [f"mlflow6t.run={first.run_id}"]
    assert second.own_labels() == [f"mlflow6t.run={second.run_id}"]


def test_network_create_argv_carries_run_label() -> None:
    # The scoped leftover check filters networks by label, so creation MUST
    # apply the same label; an unlabeled network would silently escape the
    # leftover check if its removal ever failed.
    run = _RunObjects(
        run_id="abc123def456",
        workdir=Path("/tmp/signature-only"),
        network="mlflow6t-abc123def456-net",
        helper="mlflow6t-abc123def456-helper",
        collector="mlflow6t-abc123def456-collector",
    )
    argv = network_create_args(run)
    assert argv[0] == "network" and argv[1] == "create"
    # Actual creation argv contains the run's own label (not just queries).
    assert "--label" in argv
    assert argv[argv.index("--label") + 1] == "mlflow6t.run=abc123def456"
    # ...and creates this run's (and only this run's) network.
    assert argv[-1] == run.network
    # Label value must match the leftover-check filter format exactly.
    assert argv[argv.index("--label") + 1] == run.own_labels()[0]


def test_run_workdir_is_fresh_and_never_deletes_preexisting_content(tmp_path: Path) -> None:
    preexisting = tmp_path / "old-run-artifacts"
    preexisting.mkdir()
    (preexisting / "run.log").write_text("other run's diagnostics\n")

    run = new_run_objects(scratch_root=tmp_path)

    # Fresh, per-run, inside the approved root, distinct from any preexisting dir.
    assert run.workdir != preexisting
    assert run.workdir.parent == tmp_path
    assert run.workdir.is_dir()
    assert run.workdir.name.startswith(f"span-type-{run.run_id}-")
    # The preexisting content is untouched: no rmtree of anything preexisting.
    assert (preexisting / "run.log").read_text() == "other run's diagnostics\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [preexisting.name, run.workdir.name]
    )
    # No scratch subdirectory replacement: each run gets its own directory.
    other = new_run_objects(scratch_root=tmp_path)
    assert other.workdir != run.workdir


def test_run_workdir_does_not_follow_preexisting_symlink(tmp_path: Path) -> None:
    target = tmp_path / "precious"
    target.mkdir()
    (target / "keep.txt").write_text("do not delete\n")
    # A preexisting symlink whose name matches the mkdtemp prefix must not be
    # followed or deleted by a new run.
    (tmp_path / "span-type-collide").symlink_to(target)

    run = new_run_objects(scratch_root=tmp_path)

    assert not run.workdir.is_symlink()
    assert (target / "keep.txt").read_text() == "do not delete\n"
    assert (tmp_path / "span-type-collide").is_symlink()


def test_partial_startup_failure_removes_only_created_objects(tmp_path: Path) -> None:
    # Simulate: network created, helper created, collector run FAILED, so the
    # fixture raises "collector run failed" before the collector ever exists.
    # Podman answers "no such container" for the collector rm.
    run, podman = _stub_run(tmp_path)
    podman.fail_exact[("rm", "-f", "-t", "5", run.collector)] = subprocess.CompletedProcess(
        args=[], returncode=125, stdout="", stderr="no such container"
    )

    state = cleanup_run_objects(run, podman)

    # Only this run's names are ever touched... ("rm -f -t 5 NAME" -> index 4)
    rm_targets = [c[4] for c in podman.calls if c[0] == "rm"]
    net_rm = [c[2] for c in podman.calls if c[0] == "network" and c[1] == "rm"]
    assert set(rm_targets) <= {run.helper, run.collector}
    assert net_rm == [run.network]
    # ...the never-started collector's "no such container" is not an error...
    assert state["errors"] == []
    # ...and the original "collector run failed" would propagate unmasked
    # (cleanup_run_objects itself must not raise).
    assert state["removed_containers"] == [run.helper]
    assert state["removed_network"] == run.network


def test_cleanup_failure_is_recorded_and_does_not_mask_original_failure(tmp_path: Path) -> None:
    # Original failure: network create failed (fixture raises AssertionError).
    # Cleanup failure: every network verb raises (timeout mid-cleanup).
    run, podman = _stub_run(tmp_path)
    podman.raise_on["network"] = RuntimeError("network rm timed out")

    state = cleanup_run_objects(run, podman)

    # cleanup_run_objects returned instead of raising, so the caller's original
    # AssertionError ("network create failed") propagates to the test.
    assert any("network rm timed out" in e for e in state["errors"])
    assert state["removed_containers"] == [run.collector, run.helper]
    assert state["removed_network"] is None
    # The leftover check also failed (network ls raised) but was recorded, not
    # raised, so cleanup still returned its partial state.
    assert sum("network rm timed out" in e for e in state["errors"]) >= 2


def test_cleanup_failure_during_log_capture_still_removes_containers(tmp_path: Path) -> None:
    run, podman = _stub_run(tmp_path)
    podman.raise_on["logs"] = RuntimeError("log capture exploded")

    state = cleanup_run_objects(run, podman)

    assert any("log capture" in e for e in state["errors"])
    # Removal still proceeded after the capture failure.
    assert run.collector in [c[4] for c in podman.calls if c[0] == "rm"]
    assert state["removed_containers"] == [run.collector, run.helper]


def test_cleanup_removes_only_this_run_and_never_other_named_objects(tmp_path: Path) -> None:
    run, podman = _stub_run(tmp_path)

    state = cleanup_run_objects(run, podman)

    # Every rm/network-rm command names ONLY this run's objects
    # ("rm -f -t 5 NAME" -> index 4; "network rm NAME" -> index 2).
    for call in podman.calls:
        if call[0] == "rm":
            assert call[4] in {run.helper, run.collector}
        if call[0] == "network" and call[1] == "rm":
            assert call[2] == run.network
    # Leftover listing is label-scoped to this run, not a global "mlflow6t*"
    # prefix sweep that would report (or tempt deleting) other runs' objects.
    label = f"mlflow6t.run={run.run_id}"
    ps = [c for c in podman.calls if c[0] == "ps"]
    assert ps and all(any(label in arg for arg in call) for call in ps)
    net_ls = [c for c in podman.calls if c[0] == "network" and c[1] == "ls"]
    assert net_ls and all(any(label in arg for arg in call) for call in net_ls)
    # Nothing that deletes by prefix/prune/ System Prune appears anywhere.
    for call in podman.calls:
        assert "prune" not in call
    assert state["errors"] == []
    assert state["containers"] == []
    assert state["networks"] == []


def test_name_collision_cannot_affect_another_run(tmp_path: Path) -> None:
    # Two runs coexist (e.g. a stuck earlier run); the second run's cleanup
    # must only remove its own objects even though both share the prefix.
    earlier_id = "111111111111"
    run, podman = _stub_run(tmp_path, run_id="222222222222")

    state = cleanup_run_objects(run, podman)

    earlier = (f"mlflow6t-{earlier_id}-net", f"mlflow6t-{earlier_id}-helper", f"mlflow6t-{earlier_id}-collector")
    for call in podman.calls:
        assert not any(name in call for name in earlier)
    assert state["containers"] == []
    assert state["networks"] == []


def test_fixture_source_has_no_unscoped_deletion() -> None:
    # Source-level guard: workdirs are kept for diagnosis (never rmtree'd) and
    # no file deletion exists in the lifecycle; container removal goes only
    # through the owned-name path in cleanup_run_objects. Only the fixture /
    # lifecycle half of the module is scanned, so this test never matches its
    # own text.
    source = Path(__file__).read_text()
    lifecycle = source.split("# Behavioral assertions")[0]
    assert "shutil.rmtree" not in lifecycle
    assert "os.rmdir" not in lifecycle and "os.remove" not in lifecycle
    # Container rm calls name only this run's objects: the container loop is
    # bound to (run.collector, run.helper) and the network rm names
    # run.network; no other object name can appear in an rm command.
    assert "for name in (run.collector, run.helper):" in lifecycle
    for line in lifecycle.splitlines():
        if '"rm"' in line:
            assert (
                "run.collector" in line or "run.helper" in line or "name," in line or "run.network" in line
            ), line.strip()


def test_run_commands_use_local_images_only() -> None:
    # The behavioral lifecycle must not pull: --pull=never precedes the image
    # in every container start, so a missing local image fails fast instead.
    source = Path(__file__).read_text()
    lifecycle = source.split("# Behavioral assertions")[0]
    run_calls = [
        line.strip()
        for line in lifecycle.splitlines()
        if '"run", "-d"' in line
    ]
    assert run_calls, "expected container run commands in the lifecycle"
    for line in run_calls:
        assert "--pull=never" in line, line
