# AgentGateway & MLflow Cost Tracking Implementation Plan

## Goal

Resolve missing cost tracking in the MLflow dashboard for OpenAI models via Enmaas and Gemini via Vertex, ensuring actual realized costs are visible in MLflow traces.

## Prices to configure

Rates are per 1M tokens:

| Model | Input | Output | Cache read |
| --- | ---: | ---: | ---: |
| Claude Opus 5.5 | $4 | $20 | $0.20 |
| GPT-5.6 Luna | $0.20 | $1.20 | $0.02 |
| GPT-5.6 Terra | $2 | $12 | $0.20 |
| Gemini 3.8 Flash | $0.75 | $3.75 | $0.075 |

## Tasks

### Task 1: Add an AgentGateway model catalog overlay

1. [x] Inspect the existing AgentGateway manifests and provider/model naming conventions in `.config/k8s/base/`.
2. [x] Create `.config/k8s/base/catalog-overlay.json` (or an equivalent ConfigMap definition) containing the exact input, output, and cache-read rates above for the relevant providers/models (Enmaas/OpenAI and Vertex/Gemini as applicable).
3. [x] Add `config.modelCatalog` to `.config/k8s/base/agentgateway.yaml`, pointing AgentGateway at the catalog.
4. [x] Mount the catalog into the AgentGateway workload in `.config/k8s/base/agentgateway-deployment.yaml`.
5. [x] Update `.config/k8s/base/kustomization.yaml` so the catalog/configuration is rendered and deployed.
6. [x] Preserve existing manifest style and validate rendered YAML/Kustomize output.

### Task 2: Correct OTel cost transformations

Update `.config/k8s/base/otel-collector.yaml` so that:

1. [x] `agw.ai.usage.cost.total` falls back to `gen_ai.usage.cost` when the AgentGateway cost field is nil.
2. [x] `mlflow.llm.cost` generation works when the realized cost was emitted as `gen_ai.usage.cost` rather than `agw.ai.usage.cost.total`.
3. [x] Zero-cost OpenCode spans (`cost_usd: 0`) do not create `mlflow.llm.cost` with zero-valued input, output, and total costs.
4. [x] Keep transformations type-safe and compatible with the configured OTel Collector transform processor.

### Task 3: Extend and run pytest coverage

1. [x] Update `.config/dotfiles/tests/test_otel_collector_manifests.py` to assert the fallback, MLflow cost generation, and zero-cost OpenCode protections.
2. [x] Update `.config/dotfiles/tests/test_ai_infrastructure_manifests.py` to assert the catalog content, AgentGateway model-catalog configuration, deployment mount, and Kustomize inclusion.
3. [x] Run the relevant suites with `pytest` and fix failures caused by the implementation.
4. [x] If practical, render the affected Kustomize overlay and inspect the resulting manifests in addition to the pytest checks.

## Validation checklist

- [x] Catalog contains all four models and exact per-million-token rates.
- [x] AgentGateway references and mounts the catalog through the Kustomize base.
- [x] OTel transformations preserve realized costs across both AgentGateway and generic GenAI attributes.
- [x] Zero-cost OpenCode spans do not overwrite or fabricate MLflow cost metadata.
- [x] Targeted pytest suites pass.
- [x] Rendered manifests are syntactically valid and include the catalog and transform configuration.
