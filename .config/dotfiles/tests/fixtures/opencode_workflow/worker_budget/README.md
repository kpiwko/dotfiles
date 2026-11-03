# Task 4A.1 — worker budget plugin fixture (OFFLINE MOCK HARNESS ONLY)

**This directory is NOT an installed/activated OpenCode plugin.** It is a
test fixture under `tests/fixtures/opencode_workflow/`. Nothing loads it at
runtime: it is referenced only by
`tests/test_worker_budget_contracts.py` through a mock harness, per Task 4A.1
of the PR-trace remediation plan (plan lines 110–119). No registration,
activation, config edit, restart, or model call is performed or implied.
Activation (if ever approved) is Task 4B scope.

## What this fixture IS and IS NOT

- IS: a minimal, documented, **inactive** context-hook prototype plus
  non-vacuous mock tests that call the actual hook callback and detect real
  event mutations.
- IS NOT: a simulation of unverified runtime behavior. The harness performs
  **no wire lowering**, no model-default resolution, no retry logic, and no
  raw-body-overlay collision detection. Those were removed as unverified.

## Provenance (official, version-pinned)

All doc facts below are from the official anomalyco/opencode **v2.1.4**
repository file
`services/www/src/docs/content/build/plugins/index.mdx`
(https://github.com/anomalyco/opencode/blob/v2.1.4/services/www/src/docs/content/build/plugins/index.mdx),
saved verbatim as `./v2.1.4.plugins-index.mdx` in this directory,
SHA-256 `e505931a59faa9a6685be195ccf42fcd8e3ddb9bb1d9e52f95d3b6c862cb83a5`.
Line numbers below refer to that saved copy:

- L21 (`.opencode/plugins/` auto-load), L27–46 (`plugins[]` config forms).
- L59 (`setup` may return a cleanup function), L264 (registration
  `dispose()`).
- L1341, L1399–1405, L1408–1414 (context hook registration; per-kind hooks
  `context`/`compaction`/`generate`/`title`; documented
  `event.options.maxTokens = 8_000` mutation).
- L1420 (options affect only the outgoing model call, not persisted
  history), L1425 (options start empty per call).
- L1450 (`maxTokens` is the semantic output-token limit).
- L1625–1643 (`SessionRequestHook` / `SessionContextHook` interfaces);
  `readonly agent: string` on the **context** hook is **L1643**;
  `event.model` carries `providerID`/`id` at **L1627**.
- L1796–1824 (V1/V2 export shape; V2 reads `id` + `setup()`).

### Protocol lowering (source-cited expectation, NOT mock-proven)

`packages/ai/src/protocols/openai-compatible-chat.ts` @ v2.1.4 reuses
`openai-chat.ts` `fromRequest`, which maps the semantic `maxTokens` option
to the wire key `max_completion_tokens` by default, or to `max_tokens` when
the `compatibility.maxTokensField` setting selects it. (Selection is
performed by an internal `detectMaxTokensField` function; there is no
public `compatibility.detectMaxTokensField` setting.) This is recorded as
a **source-cited expected mapping only**; the compatibility configuration
actually in effect for the local `agentgateway` provider remains
**unverified** (not exercised here).

The docs describe the hook's request as a **Request-like object** (one-shot
stream; no `HTTPRequest` type is defined and the actual body is not a
parsed object); the earlier prototype's `http.request` body-overlay
collision detection was therefore **removed as
unimplementable-on-unverified-shape**, not implemented.

## Residual integration gap (honest boundary)

- **Agent identity is inferred, not observed.** `event.agent === "worker"`
  is inferred from the agent filename/docs only; the live `event.agent`
  value is **unverified**. The AND-provider/model checks (`providerID` /
  `modelID`) narrow matching but do **NOT** compensate a wrong agent
  identity.
- No live-server behavior is claimed. The mock implements only the
  documented hook-registration surface; mock tests prove the plugin's own
  hook logic (guard + cap arithmetic + teardown), nothing about what the
  official runtime emits.
- The plugin does NOT stop budget expiration or enforce any runtime
  deadline; no such claim is made.
- Real registration, the 8,000 cap arm, and smoke remain Task 4B scope,
  gated on the unverified compatibility configuration and the unset numeric
  ceiling.

## File map

- `worker_budget.ts` — the inactive, dependency-free plugin module. Default
  export is the V2 shape (`{ id, setup(ctx) }`); `setup` registers ONLY the
  `context` hook, guarded by agent name `worker` AND
  `model.providerID === "agentgateway"` AND `model.id === "worker"`, and
  applies `Math.min(existing, 8000)` without ever raising an existing
  finite positive limit. Returns a disposer.
- `harness.mjs` — Node test harness: loads `worker_budget.ts` via native TS
  type-stripping (no Bun, no install, no network), builds a mock `ctx` that
  registers/dispatches the documented per-kind hooks, runs each context
  event through the ACTUAL registered callbacks, and reports deep-copied
  before/after snapshots. 10 scenarios.
- `v2.1.4.plugins-index.mdx` — verbatim local copy of the official doc for
  provenance (SHA-256 above).

## Why plain Node

The plugin module is dependency-free and structurally typed (no
`@opencode/plugin` import needed at runtime — the harness's mock `ctx`
provides the documented surface). Node ≥22.18 runs `.ts` by stripping types
natively. Bun is not installed and not needed.
