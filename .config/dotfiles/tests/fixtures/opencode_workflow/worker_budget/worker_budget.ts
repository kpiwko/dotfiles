/**
 * Task 4A.1 fixture: worker-only outgoing `maxTokens` cap (INACTIVE).
 *
 * NOT installed, NOT registered, NOT activated. Loaded only by
 * tests/fixtures/opencode_workflow/worker_budget/harness.mjs through a mock
 * context implementing the DOCUMENTED v2.1.4 hook surface, per the PR-trace
 * remediation plan Task 4A.1.
 *
 * Source provenance — official anomalyco/opencode v2.1.4
 * `services/www/src/docs/content/build/plugins/index.mdx` (verbatim local
 * copy: ./v2.1.4.plugins-index.mdx in this directory; lines cited below):
 *
 * - Default export `{ id, setup(ctx) }` is the V2 plugin shape (L1796–1824);
 *   `setup` may return a cleanup function (L59).
 * - `await ctx.session.hook("context", cb)` registers the agent-loop model
 *   request hook (L1341, L1408–1414); the returned registration has
 *   `dispose()` (L264).
 * - `event.options.maxTokens = 8_000` is the documented mutation (L1412);
 *   `maxTokens` is the semantic output-token limit (L1450). Options affect
 *   only the outgoing model call, not persisted history (L1420).
 * - `event.agent` is `readonly agent: string` on SessionContextHook
 *   (L1643; interface L1625–1640) — read comparison only.
 * - `event.model` carries `providerID` and `id` (L1627) — read only.
 * - `context` / `compaction` / `generate` / `title` are separate per-kind
 *   hooks (L1399–1405). This plugin registers ONLY `context`; it applies no
 *   registrations for title/generate/compaction.
 *
 * NOT proven and NOT claimed here (see README residual-gap section):
 * the final wire key produced by the standard `openai-compatible` protocol
 * lowering, and any live-server behavior. This module never lowers a request
 * body, never sets model defaults, and registers no retry/http machinery.
 *
 * Dependency-free and structurally typed so it runs under plain Node (>=22.18)
 * type-stripping without installing @opencode/plugin.
 */

/**
 * Agent name (NOT a model id): matches readonly `event.agent` only.
 * Truth: "worker" is INFERRED from the agent filename/docs; the live
 * `event.agent` value is UNVERIFIED. The AND-provider/model checks below
 * narrow matching but do NOT compensate a wrong agent identity.
 */
export const WORKER_AGENT = "worker"

/** Provider + model identity the cap is additionally guarded on. */
export const WORKER_PROVIDER_ID = "agentgateway"
export const WORKER_MODEL_ID = "worker"

/** Hypothetical Task 4B arm, offline-mock only. NOT a production setting. */
export const WORKER_CAP_MAX_TOKENS = 8_000

export interface SessionRequestEvent {
  readonly sessionID: string
  readonly model: { providerID: string; id: string; variant?: string }
  system: Array<{ type: string; text: string }>
  messages: Array<{ role: string; content: unknown }>
  options: {
    maxTokens?: number
    temperature?: number
    topP?: number
    topK?: number
    frequencyPenalty?: number
    presencePenalty?: number
    seed?: number
    stop?: string[]
  } & Record<string, unknown>
}

export interface SessionContextEvent extends SessionRequestEvent {
  readonly agent: string
  tools: Record<string, { description: string; input: unknown }>
}

export interface Registration {
  dispose(): Promise<void>
}

/** Documented, used surface: only the `context` hook. */
export interface PluginContext {
  session: {
    hook(
      name: "context",
      callback: (event: SessionContextEvent) => Promise<void> | void,
    ): Promise<Registration>
  }
}

export interface WorkerBudgetOptions {
  /** Exact agent name to match (readonly field on the hook event). */
  agent?: string
  /** Provider/model identity additionally required for the cap. */
  providerID?: string
  modelID?: string
  /** Semantic output-token ceiling applied to matching agent requests. */
  maxTokens?: number
}

function isFinitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
}

/** Apply the cap without ever RAISING an existing explicit limit. */
export function applyCap(current: unknown, cap: number): number | undefined {
  if (!isFinitePositive(current)) return cap
  return Math.min(current, cap)
}

/**
 * Build the setup body. Separated from the default export so the harness
 * can exercise the exact registration/teardown sequence with mocks.
 */
export function makeWorkerBudgetPlugin(overrides: WorkerBudgetOptions = {}) {
  const agent = overrides.agent ?? WORKER_AGENT
  const providerID = overrides.providerID ?? WORKER_PROVIDER_ID
  const modelID = overrides.modelID ?? WORKER_MODEL_ID
  const maxTokens = overrides.maxTokens ?? WORKER_CAP_MAX_TOKENS

  return {
    id: "worker-budget",
    async setup(ctx: PluginContext): Promise<() => Promise<void>> {
      const registration = await ctx.session.hook("context", (event) => {
        if (event.agent !== agent) return
        if (event.model.providerID !== providerID) return
        if (event.model.id !== modelID) return
        const capped = applyCap(event.options.maxTokens, maxTokens)
        if (capped !== undefined) event.options.maxTokens = capped
      })
      return async () => {
        await registration.dispose()
      }
    },
  }
}

const plugin = makeWorkerBudgetPlugin()
export default plugin
