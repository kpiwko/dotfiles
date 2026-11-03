#!/usr/bin/env node
/**
 * Task 4A.1 offline harness — executes the worker_budget.ts plugin fixture
 * against a mock context that implements the DOCUMENTED v2.1.4 hook surface
 * ONLY. No network, no model transport, no install, no Bun, no wire lowering.
 *
 * Usage: node harness.mjs <scenario>
 * Scenarios: worker-context, nonworker-agent, same-model-different-provider,
 *            worker-different-model, lower-cap-respected, higher-lowered,
 *            invalid-ignored, title-generate-compaction, dispose-idempotent,
 *            no-extra-mutation
 * Prints one JSON object to stdout.
 *
 * Mock surface (v2.1.4 docs, ./v2.1.4.plugins-index.mdx): registration with
 * dispose() (L264), per-kind hook names context/compaction/generate/title
 * (L1399–1405), readonly agent (L1643), model.providerID/.id (L1641),
 * options start empty per call (L1425). The mock implements ONLY hook
 * registration/dispatch; it performs NO protocol lowering and asserts
 * NOTHING about the final request body.
 */

import plugin, { WORKER_AGENT } from "./worker_budget.ts"

const scenarios = {}

/** Mock registration per docs L264: dispose() removes the hook. */
class MockRegistration {
  constructor(hookStore, name, callback) {
    this.hookStore = hookStore
    this.name = name
    this.callback = callback
    this.disposed = false
  }
  async dispose() {
    if (this.disposed) return
    this.disposed = true
    const list = this.hookStore.get(this.name) ?? []
    const index = list.indexOf(this.callback)
    if (index >= 0) list.splice(index, 1)
  }
}

/** Mock ctx implementing the documented hook-registration surface. */
function makeMockCtx() {
  const hookStore = new Map() // name -> callbacks[]
  const ctx = {
    session: {
      hook: async (name, callback) => {
        const list = hookStore.get(name) ?? []
        list.push(callback)
        hookStore.set(name, list)
        return new MockRegistration(hookStore, name, callback)
      },
    },
  }
  return { ctx, hookStore }
}

/**
 * Build a context event and run it through the ACTUAL registered context
 * callbacks. Returns deep-copied before/after snapshots so tests can detect
 * real mutations rather than trusting the plugin's own reporting.
 */
async function runContextEvent(hookStore, overrides = {}) {
  const event = {
    sessionID: "ses_test",
    agent: overrides.agent ?? WORKER_AGENT,
    model: overrides.model ?? { providerID: "agentgateway", id: "worker" },
    system: [{ type: "text", text: "system" }],
    messages: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
    tools: { read: { description: "read", input: {} } },
    options: structuredClone(overrides.options ?? {}), // documented: starts empty (L1425)
  }
  const before = structuredClone(event)
  for (const callback of hookStore.get("context") ?? []) await callback(event)
  return { event, before, after: event }
}

const result = (scenario, data) => JSON.stringify({ scenario, ...data })

// --- Scenario: worker match applies the cap via the real hook callback ----
scenarios["worker-context"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { before, after } = await runContextEvent(hookStore)
  await dispose()
  return result("worker-context", {
    agent: before.agent,
    maxTokensBefore: before.options.maxTokens ?? null,
    maxTokensAfter: after.options.maxTokens ?? null,
    capApplied: after.options.maxTokens === 8000,
  })
}

// --- Scenario: non-worker agent is untouched ------------------------------
scenarios["nonworker-agent"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { before, after } = await runContextEvent(hookStore, {
    agent: "architect",
    options: { maxTokens: 32000 },
  })
  await dispose()
  return result("nonworker-agent", {
    agent: after.agent,
    maxTokensAfter: after.options.maxTokens,
    untouched: after.options.maxTokens === 32000,
  })
}

// --- Scenario: worker agent + same model id, different provider ------------
scenarios["same-model-different-provider"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { after } = await runContextEvent(hookStore, {
    options: { maxTokens: 32000 },
    model: { providerID: "other-provider", id: "worker" },
  })
  await dispose()
  return result("same-model-different-provider", {
    providerID: after.model.providerID,
    maxTokensAfter: after.options.maxTokens,
    untouched: after.options.maxTokens === 32000,
  })
}

// --- Scenario: worker agent + different model ------------------------------
scenarios["worker-different-model"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { after } = await runContextEvent(hookStore, {
    options: { maxTokens: 16000 },
    model: { providerID: "agentgateway", id: "architect" },
  })
  await dispose()
  return result("worker-different-model", {
    modelID: after.model.id,
    maxTokensAfter: after.options.maxTokens,
    untouched: after.options.maxTokens === 16000,
  })
}

// --- Scenario: existing LOWER cap is respected (never raised) --------------
scenarios["lower-cap-respected"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { after } = await runContextEvent(hookStore, {
    options: { maxTokens: 4000 },
  })
  await dispose()
  return result("lower-cap-respected", {
    maxTokensAfter: after.options.maxTokens,
    respected: after.options.maxTokens === 4000,
  })
}

// --- Scenario: existing HIGHER limit is lowered, not ignored ---------------
scenarios["higher-lowered"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { after } = await runContextEvent(hookStore, {
    options: { maxTokens: 32000 },
  })
  await dispose()
  return result("higher-lowered", {
    maxTokensAfter: after.options.maxTokens,
    lowered: after.options.maxTokens === 8000,
  })
}

// --- Scenario: non-finite / non-positive existing values are ignored -------
scenarios["invalid-ignored"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const cases = []
  for (const value of [Number.NaN, Number.POSITIVE_INFINITY, 0, -5, "8000", null]) {
    const { after } = await runContextEvent(hookStore, { options: { maxTokens: value } })
    cases.push({ given: String(value), applied: after.options.maxTokens === 8000 })
  }
  await dispose()
  return result("invalid-ignored", { cases, allIgnored: cases.every((c) => c.applied) })
}

// --- Scenario: title/generate/compaction kinds are NOT registered ----------
scenarios["title-generate-compaction"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const registered = [...hookStore.keys()].sort()
  await dispose()
  return result("title-generate-compaction", {
    hookNames: registered,
    onlyContext: registered.length === 1 && registered[0] === "context",
  })
}

// --- Scenario: dispose is idempotent on the supported mock -----------------
scenarios["dispose-idempotent"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const before = hookStore.get("context")?.length ?? 0
  await dispose()
  await dispose() // second call must be a no-op, not an error
  const after = hookStore.get("context")?.length ?? 0
  return result("dispose-idempotent", {
    hooksBefore: before,
    hooksAfter: after,
    idempotent: before === 1 && after === 0,
  })
}

// --- Scenario: only options.maxTokens mutates; nothing else ----------------
scenarios["no-extra-mutation"] = async () => {
  const { ctx, hookStore } = makeMockCtx()
  const dispose = await plugin.setup(ctx)
  const { before, after } = await runContextEvent(hookStore, {
    options: { maxTokens: 32000, temperature: 0.2 },
  })
  await dispose()
  const restSame =
    JSON.stringify(before.system) === JSON.stringify(after.system) &&
    JSON.stringify(before.messages) === JSON.stringify(after.messages) &&
    JSON.stringify(before.tools) === JSON.stringify(after.tools) &&
    before.agent === after.agent &&
    JSON.stringify(before.model) === JSON.stringify(after.model) &&
    before.options.temperature === after.options.temperature
  return result("no-extra-mutation", {
    maxTokensAfter: after.options.maxTokens,
    systemMessagesToolsIdentityTemperatureUnchanged: restSame,
  })
}

const name = process.argv[2]
const scenario = scenarios[name]
if (!scenario) {
  console.error(`unknown scenario: ${name}`)
  process.exit(2)
}
scenario().then(
  (out) => console.log(out),
  (error) => {
    console.error(error?.stack ?? String(error))
    process.exit(1)
  },
)
