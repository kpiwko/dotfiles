# AgentGateway Telemetry Architecture

## Goal

Make AgentGateway the authoritative source of resolved provider, upstream model,
token usage, and realized LLM cost. Retain the OpenCode OTel plugin for session,
agent, and tool-workflow visibility. Export both signal streams through the
in-cluster OpenTelemetry Collector to MLflow.

## Routing

OpenCode sends model requests to AgentGateway's OpenAI-compatible endpoint.
AgentGateway performs provider routing and failover:

- `architect`: Enmaas GPT-5.6 Terra, then direct OpenAI.
- `worker` and `reviewer`: Enmaas GPT-5.6 Luna, then direct OpenAI.
- `gemini`: direct Vertex Gemini 3.8 Flash only.

The top-level OpenCode default model and the `orchestrator` and `plan` agents
use `agentgateway/gemini`. Existing sessions retain their selected model; a new
session or OpenCode service restart is required to apply the new default.

## Trace topology

```text
OpenCode service --model request + W3C traceparent--> AgentGateway --> provider
       |                                                |
       | OpenCode session/tool/client spans              | resolved model, usage,
       |                                                | and realized-cost spans
       +------------------- OTLP -----------------------+
                                                    OpenTelemetry Collector
                                                               |
                                                               | MLflow OTLP exporter
                                                               v
                                                            MLflow
```

The OpenCode OTel plugin remains enabled. It supplies session, agent, tool, and
client-call context. AgentGateway emits the LLM spans that identify the chosen
provider and upstream model, including the cost derived from its model catalog.
The plugin injects a W3C `traceparent` header for the `agentgateway` provider so
the two span sets are correlated in one distributed trace.

## Cost source of truth

AgentGateway loads a model-cost catalog plus a repository-managed pricing
overlay for routes whose provider/model names are not in the built-in catalog,
notably Enmaas and the selected Vertex model. Its realized cost attributes are
mapped by the OpenTelemetry Collector into MLflow-compatible LLM cost fields.

OpenCode's plugin-derived cost and per-model metrics are disabled because its
public aliases cannot reliably identify an AgentGateway failover target. The
plugin's non-cost workflow telemetry remains enabled.

## Experiment grouping

MLflow receives both OpenCode and AgentGateway telemetry in one fixed
`opencode` experiment. The experiment ID is an OTLP transport header and cannot
vary safely per OpenCode session in the shared background service, where spans
from concurrent sessions are batched together.

Each trace remains attributable to its OpenCode session through session/span
attributes and trace correlation. Per-session MLflow experiments are explicitly
out of scope. Supporting them later requires a session-aware exporter or an
isolated OpenCode service per invocation.

## Operational documentation

`.config/k8s/README.md` documents the cluster-side trace topology, cost catalog,
fixed-experiment rule, and validation commands. `.config/opencode/README.md`
documents OpenCode's provider/trace propagation role and the restart/new-session
behavior after model configuration changes.

## Safety boundaries

- Do not inspect, rotate, commit, or otherwise modify credentials.
- Do not change MLflow's SQLite/PVC/artifact configuration.
- Do not add Gemini as an automatic fallback for other models.
- Do not use Enmaas for Gemini; `gemini` remains a direct Vertex route.
