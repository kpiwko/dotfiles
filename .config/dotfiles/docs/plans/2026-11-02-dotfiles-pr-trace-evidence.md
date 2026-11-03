# Dotfiles PR Trace Remediation — Evidence Artifact

Single evidence artifact for `.config/dotfiles/docs/plans/2026-11-02-dotfiles-pr-trace-remediation.md`.
Sections by phase/task. Facts below are recorded from actual installed files on
this machine (2026-11-02) unless explicitly labelled *documented-only* (Context7
docs for `/anomalyco/opencode/v2.1.2`, plan lines 41–47) or *unverified*.

---

## Task 4A — Installed controls and offline capability tests (Phase 1)

Status: **PARTIAL — diagnostic gate outcome.** Capability matrix delivered from
installed sources; executable offline scenario validation delivered. Native
hook *behavior* against the v2.1.4 server is NOT executable-verified (see
Blockers). No activation, no config edit, no model call, no Git command.

### 1. Installed versions (actual, local)

| Component | Version | Actual source path |
|---|---|---|
| OpenCode server/CLI | **v2.1.4** | `/opt/homebrew/bin/opencode` → `/opt/homebrew/Cellar/opencode-v2/2.1.4/bin/opencode` (single 214 MB Mach-O arm64 binary; compiled, no readable server source) |
| Plugin: `devtheops.otel` | 2.0.1 | `~/.cache/opencode/npm/@devtheops/opencode-plugin-otel@latest/1791365043555/node_modules/@devtheops/opencode-plugin-otel/` (ships `dist/` only) |
| Plugin: `opencode-notifier` | 0.8.0 | `~/.cache/opencode/npm/@mohak34/` |
| Plugin: `superpowers` | 8ca22db | `~/.cache/opencode/npm/git-superpowers-0958a5557860` |
| `@opencode-ai/plugin` + `@opencode-ai/sdk` | **1.15.13 — LEGACY, not authoritative** | `~/.config/opencode/node_modules/@opencode-ai/plugin/` |
| OTEL plugin's own dev-tooling peer | `@opencode/plugin` **2.0.20** (devDependencies only, not shipped in dist) | OTEL plugin `package.json` |
| Worker agent | `agentgateway/worker`, provider package **default `openai-compatible`** — NOT `openai-compatible/responses` | `~/.config/opencode/opencode.jsonc` lines 131–143 |
| Architect/Spade | `openai-compatible/responses` (Responses lowering path) | same, lines 92–129, 170–190 |

**Version reconciliation:** three surfaces exist — server **2.1.4** (compiled),
config-dir SDK **1.15.13** (legacy dependency predating the v2 runtime; do
NOT infer v2 hook presence/absence from it), and OTEL plugin peer
**2.0.20** (dev-only). The only locally executable code actually running
against the v2.1.4 runtime is the installed OTEL plugin `dist/index.js`.

### 2. Installed v2 plugin API surface (observed in OTEL plugin dist, lines 72042–72132)

Actually used by the running telemetry plugin on this machine:

- Entry point: `async function setup(ctx)` exported from the plugin module
  (v2 `"oc-plugin": ["server"]` manifest in `package.json`).
- `ctx.options` — per-plugin options from `opencode.jsonc` plugin entry.
- `ctx.location.directory`, `ctx.location.project.directory` — plugin origin.
- `ctx.session.get({ sessionID })` — session lookup.
- `ctx.session.hook("context", async (event) => { ... })` — **context hook
  confirmed present in installed v2-running code** (used for
  `captureModelContext`).
- `ctx.session.hook("model.request", async (event) => { ... })` — outbound
  request hook confirmed present (used by `handleModelRequest`).
- `ctx.session.hook("experimental.ws.handshake", ...)` — experimental hook,
  conditional.
- Plugin options normalization (`loadConfig(ctx.options)`), a teardown
  function returned from `setup`, and a global exit-hook guard pattern.

**Documented-only (NOT found in any installed local code — Context7 docs for
v2.1.2, plan lines 43–44):** `event.options.maxTokens` mutation inside the
`context` hook; retry hook input
`{sessionID, agent, model, error: {type, message, status?}, attempt}` /
decision `{retry: false} | {retry: true, delay}`; initial-attempt = 1
numbering. The retry hook and attempt numbering are therefore
**documented-not-installed-verified** for v2.1.4.

**Absent from installed evidence (unverified, candidate-only):** native
interrupt/cancel API, per-task assignment deadline, and any mechanism
distinguishing retries from length continuations. Not found in the readable
local surface; **not verified in this task** — no executable check was run,
and the lack of readable local source is not proof that verification is
impossible.

### 3. Four-control capability matrix (Task 4A deliverable)

Legend: MECHANISM = owning supported mechanism per installed/config evidence;
CANCEL = cancellation coverage. "documented-only" = Context7 v2.1.2 docs, not
verified against installed v2.1.4.

| Control | Owning mechanism (installed evidence) | Cancellation coverage | Status |
|---|---|---|---|
| **1. Per-generation output cap** | Context hook `ctx.session.hook("context")` mutating `event.options.maxTokens` (hook installed-confirmed; the `maxTokens` field itself documented-only). Worker today: `limit.output: 32000` in `opencode.jsonc`; no hook sets `maxTokens`. | None needed — bound is on the request itself | Partially verified: hook exists; cap semantics unverified |
| **2. Per-request/attempt wall deadline** | Provider settings `headerTimeout`/`chunkTimeout`/`timeout` (documented-only; **none set** in installed `opencode.jsonc` for any provider). Chunk timeout ≠ wall deadline (documented). | Provider timeouts abort the request; retry policy then applies | Not configured locally; capabilities documented-only |
| **3. Whole delegated-task deadline (across turns/retries/continuations)** | **NO installed mechanism found.** `steps: 40` in `agents/worker.md` bounds tool/model loop iterations, not wall time; neither chunk inactivity nor steps substitutes for task wall time (plan line 94) | **None.** No native task-deadline/cancel API found in readable installed code | **Gap — blocker for enforceable task wall deadlines** |
| **4. Progress budget (tool-count checkpoint + elapsed/first-useful-action)** | No runtime mechanism; only the agent-instruction 6–8-tool-call checkpoint in `agents/worker.md` (pre-tool, cannot constrain initial generation — plan line 27) | None | Instruction-only; not enforcement |

**Retry vs continuation separation (plan lines 44, 47, 119):** the retry hook
(documented-only) fires on proposed error/timeout retries with attempt
numbering from 1; `finish_reason=length` and model/tool continuations are
separate paths that may not invoke it. "Three timeout retries" is **not
verified in this task** — no executable check was run; the installed policy
is not readable from the compiled binary, which is not proof it cannot be
verified by other means.

**Responses lowering + raw-body precedence:** worker uses the default
`openai-compatible` package (chat-completions style), NOT `/responses`.
Outgoing-cap verification for the worker is therefore a plain
`max_tokens`-style assertion; Responses-protocol lowering + raw-body override
collisions apply to architect/spade and are **cross-protocol (optional)**
tests for the worker canary. Raw-body overlays applying after protocol
lowering and potentially overriding semantic settings remains
documented-only (v2.1.2 docs).

### 4. Supported local plugin integration path — NOT yet confirmed

Proposed owned file `.config/opencode/plugins/worker-budgets.ts` (plan line 96)
remains **unconfirmed**: no local plugin in the `plugins/` directory form was
observed on this machine (all three installed plugins come from
`opencode.jsonc` `plugins[]` entries resolved into the npm cache), and the
compiled server source is unavailable for local-directory verification.
**Exact next path needed:** confirm the local plugin directory name and load
order from the official v2.1.4 docs (`plugins` vs `plugins/` vs config entry)
BEFORE any implementation; if unsupported, register via the existing
`opencode.jsonc` `plugins[]` mechanism — which is a config edit requiring the
separately approved Task 4B scope.

### 5. Offline capability tests delivered (scenario validation, NOT runtime proof)

New fixed-scenario fixture (common baseline, plan lines 53–60) and validator:

- `tests/fixtures/opencode_workflow/scenarios.json` — the four fixed scenarios
  (small-edit, failing-test-debug, reviewer-finding-unchanged-revision,
  publication-dry-run) with global invariants: worker agent/protocol pinned,
  arms limited to baseline + cap8000, numeric ceilings deliberately `null`
  (require separate envelope approval), all live side effects forbidden.
- `tests/test_opencode_workflow_scenarios.py` — 11 tests validating fixture
  invariants, isolation (per-run `${RUN_DIR}` disposable workspaces, no
  tracked-tree edits), no live remote/install command text, and the
  no-duplicate-review/invalidation and dry-run stop-path contracts.

Explicit scope statement: these are **scenario validation only**. They do not
demonstrate plugin hook behavior, worker budget enforcement, protocol
lowering, or model adherence; static fixture tests are not proof of hooks
(plan line 60). `tests/test_worker_budget_contracts.py` was NOT created —
there is no confirmed executable budget logic to test yet; creating
prose-asserting or fabricated integration tests was forbidden by this
assignment.

Validation performed (offline, installed deps only, `--offline --no-sync`,
no install):

```
uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles --group test \
  pytest tests/test_opencode_workflow_scenarios.py tests/test_git_workflow_contracts.py
→ 47 passed
```

Red/green demonstrated for the new assertions: before the fixture existed,
the suite failed at collection with
`FileNotFoundError: .../scenarios.json` (red); after writing the fixture it
passes 11/11 (green). One intermediate genuine failure (placeholder-vs-literal
workspace-path assertion) was corrected in the test, not hidden.

### 6. Blockers (concrete, honest)

1. **No readable v2.1.4 server source.** OpenCode is a single compiled
   Mach-O binary; context/retry hook *runtime behavior*, attempt numbering,
   retry policy, and interrupt/cancel capabilities were **not verified in
   this task** — no executable check was run. Lack of readable local source
   is not proof that they cannot be verified. Evidence is limited to the
   installed OTEL plugin's use of the API plus v2.1.2 docs (version
   mismatch to be closed by doc check against v2.1.4).
2. **No native plugin test runner found in this task.** The OTEL plugin
   ships only `dist/` (no tests); its bun-based dev tooling is not
   installed. `~/.cache/opencode/bin/` and `repos/` are empty. So no local
   plugin-test runner was found (not proof none exists) — mock-backed hook
   tests would need bun/node + a plugin harness that was not present. This
   is why Task 4A delivers scenario validation rather than mock hook tests.
3. **Whole-task deadline + progress-budget cancellation: no installed
   mechanism found** (matrix rows 3–4). Any enforceable task wall deadline
   needs either an upstream capability confirmation or a plan amendment
   (e.g., orchestrator-side watch + abort), which is the planner's decision.
4. **Local plugin registration path unconfirmed** (section 4) — required
   before Task 4B implementation.

### 7. Safe-smoke proposal (for orchestrator approval — NOT activation)

Per plan lines 62–64, before any model run the orchestrator must approve:
fixed worker alias `agentgateway/worker`; the four scenarios above; arms
baseline + cap8000 only (8 runs); numeric aggregate token/monetary ceiling;
per-run and whole-envelope wall deadlines; maximum actual HTTP attempts
(derived from installed retry policy — **currently unreadable**, blocker 1);
and a safe supported cancellation mechanism (**not found**, blocker 3).
**Given blockers 1 and 3, the safe recommendation is to stop at this offline
capability evidence** and not start unbounded model calls; smoke requires the
retry-policy/cancellation gaps to be closed or explicitly accepted by the
planner first.

### 8. Next actions (Task 4B prerequisites, planner-owned)

1. Close the v2.1.2-docs vs v2.1.4-runtime gap for: `maxTokens` mutation,
   retry hook shape/numbering, raw-body overlay precedence, local plugin
   directory. (Read-only doc/source verification.)
2. Decide the plan amendment for whole-task deadline + progress-budget
   cancellation (no installed mechanism).
3. Only then: Task 4B implementation of the worker-only cap hook on the
   confirmed path, with `tests/test_worker_budget_contracts.py` against real
   installed APIs.

---

## Task 1 — Exact debugging skill allow (Phase 1)

Status: **COMPLETE (offline scope).** Static contract tests green; fresh-session
load proof intentionally deferred to the approved Phase 2 smoke envelope. No Git
commands, no restart, no live model call, no skill install/copy.

### 1. Exact effective skill ID

- **ID: `systematic-debugging`** (unnamespaced). Advertised by the running
  OpenCode v2.1.4 server's skill listing (`opencode api GET /api/skill`),
  path `~/.cache/opencode/npm/git-superpowers-0958a5557860/1790778151070/node_modules/superpowers/skills/systematic-debugging/SKILL.md`
  (installed plugin `superpowers` 8ca22db per `opencode plugin list`;
  `SKILL.md` frontmatter `name: systematic-debugging`; the plugin registers
  its skills dir via `config.skills.paths`, no namespacing anywhere).
- Discovery deliberately did NOT rely on local `~/.config/opencode/skills`
  directories (skill deny hides skills, so local absence proves nothing).
- **Visibility corroboration (not fresh-session load proof):** after adding
  the allow, the already-running session received a system update
  advertising `<id>systematic-debugging</id>` alongside the existing
  init-change/publish-change entries. This shows the running server now
  exposes the skill to the worker agent; it does not prove a fresh worker
  session loads it (that awaits the approved Phase 2 smoke).

### 2. Changes

- `~/.config/opencode/agents/worker.md`: added exactly one permission entry
  `skill / "systematic-debugging" / allow` after the wildcard skill deny and
  the existing init-change/publish-change allows; added a "Conditional
  debugging workflow" section (load only for a stateable concrete failure —
  reproducible failing test, failing build, unexpected command output,
  runtime doc-vs-observed mismatch; root-cause phases; evidence bounded to
  the failing case; no repo-wide archaeology; stop and report bounded
  evidence + candidate causes + blocker instead of guessing a fix).
  Shell/model/steps/publication/subagent rules untouched.
- `tests/test_git_workflow_contracts.py`: new "Skill permission boundary"
  section — `resolve_skill_permission` (last-match-wins, `*` wildcard
  matches any ID) + `assert_worker_skill_decision_table`, and tests:
  exact debugging allow resolves after wildcard deny; wildcard deny
  precedes each exact allow; synthetic reorder moving the wildcard deny to
  the end is detected; synthetic widening mutation appending a broad skill
  allow is detected; nested subagents remain denied.

### 3. Validation (actual results)

- `uv run --offline --no-sync --project ~/.config/dotfiles --group test
  pytest tests/test_git_workflow_contracts.py
  tests/test_opencode_workflow_scenarios.py -q` → **53 passed** = 47
  pre-existing (36 git-workflow contract tests + 11 scenario tests) + 5
  skill-boundary tests from this task + 1 added during review closure
  (exact allowed skill-ID set assertion).
- **RED/GREEN via in-memory policy mutation** (live worker.md NOT touched):
  removing the new allow entry from the parsed frontmatter rule list makes
  `systematic-debugging` resolve to `deny`, and
  `assert_worker_skill_decision_table` rejects the mutated policy
  (`AssertionError: systematic-debugging`); the live policy passes the same
  table. Combined with the two synthetic reorder/widening mutation tests,
  the regressions are order-sensitive, not just effect-value presence.
- Two new-test bugs found and fixed during this task (wildcard `*` never
  matched a concrete skill ID; `rule_index` missing `action="skill"`).
  No production change beyond the intended allow/workflow edit.

### 5. Reviewer finding closure (2026-11-02, recorded once)

Reviewer PASS with no blockers; all findings addressed in this closure
(no model/steps changes; no new test added for the count fix itself):

- Test-count breakdown corrected (section 3): 52 = 47 prior (36 contract +
  11 scenario tests) + 5 new skill-boundary tests. Re-validated after the
  optional take: **53 passed** with 1 added exact-allowed-skill-ID-set test.
- "cannot verify" overclaims in sections 2, 3, and 6 (blockers 1–2) reworded
  to *not verified in this task, no executable check run*; absence of local
  source/runner is not stated as proof of impossibility.
- `NONEXISTENT_SKILL` test constant renamed to `SECOND_UNRELATED_PLUGIN_SKILL`
  with a truthful comment: `verification-before-completion` is a real skill
  shipped by the installed superpowers plugin (its `SKILL.md` exists
  locally) and it must remain denied — the allow is exact, not plugin-wide.
- Broad-allow skill test docstring rewritten to describe what the test
  actually does (synthetic widening, not a hoist reorder).
- New test pins the allowed skill set to exactly `init-change`,
  `publish-change`, `systematic-debugging`, preventing a silent extra
  exact allow.
- `agents/worker.md` gained the reviewer-suggested sentence: skill
  cross-references never expand the permission list; denied/unexposed skill
  or subagent steps are returned as blockers, not retried; local denial is
  not claimed as global unavailability.
- Actual final result (single run, this closure):
  `uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles
  --group test pytest tests/test_git_workflow_contracts.py
  tests/test_opencode_workflow_scenarios.py -q` → **53 passed**.

### 6. Limitations / deferred

- Static tests prove frontmatter semantics under the documented ordered
  interpretation; they do not prove a fresh worker session's runtime skill
  discovery/load (Phase 2 approved smoke, per plan Task 1 bullet 4).
- The in-session visibility corroboration depends on the already-running
  server; no restart was performed (and none was permitted).

---

## Task 4A.1 — Official 2.1.4 API map + worker-path offline proof (Phase 1)

Status: **PARTIAL-Delivered.** Official v2.1.4 source mapping closed most
documented-only gaps; executable offline mock proof delivered for the worker
cap/isolation/collision path. The final wire-field gate remains OPEN (below).
No registration, no runtime/config edit, no cap activation, no retry
manipulation, no deadline logic, no model call, no install, no Git command.

### 1. Bounded official-source reads (8/8 used, checkpoint at 6 honored)

All read-only against the public `anomalyco/opencode` **tag v2.1.4**
(tag verified: repo public, 20,798 commits at tag):

1. `https://github.com/anomalyco/opencode/tree/v2.1.4` — tag exists.
2. `.../blob/v2.1.4/services/www/src/docs/content/build/plugins/index.mdx`
   (raw) — full 1,830-line doc retrieved; verbatim copy at
   `tests/fixtures/opencode_workflow/worker_budget/v2.1.4.plugins-index.mdx`,
   SHA-256 `e505931a59faa9a6685be195ccf42fcd8e3ddb9bb1d9e52f95d3b6c862cb83a5`.
3. `.../v2.1.4/services/www/src/docs/content/build/providers.mdx` (raw) —
   **404**: the 2.1.2 providers doc path does NOT exist at v2.1.4. Provider
   timeout facts (`headerTimeout`/`chunkTimeout`/`timeout`) therefore remain
   **documented-only at 2.1.2**, unreconciled to 2.1.4.
4. `.../tree/v2.1.4/.../build/providers` — 404.
5. `.../tree/v2.1.4/.../build` — contains only `client/`, `plugins/`,
   `sdk/`; no providers doc there.
6. `.../tree/v2.1.4/packages/ai/src/providers/openai-compatible` — contains
   only `responses.ts`.
7. `.../tree/v2.1.4/packages/ai/src/providers` — full listing.
8. `https://raw.githubusercontent.com/anomalyco/opencode/v2.1.4/packages/ai/src/providers/openai-compatible.ts`
   — full file read: the standard package registers exactly ONE route,
   `OpenAICompatibleChat.route` (imported from
   `../protocols/openai-compatible-chat.js`), and `model(...)` maps config
   `body` → `http: { body }` (raw-body overlay plumbing).

### 2. Proven at v2.1.4 (doc line numbers = saved verbatim copy)

- **Local registration path (was blocker 4, now CLOSED):** plugins under
  `.opencode/plugins/` are loaded automatically (L21); published packages or
  other directories load via `plugins[]` in `opencode.json(c)`, including
  `"./plugins/local"`, relative/absolute paths and `file:///` forms, or the
  object form `{ "package": ..., "options": ... }` (L27–46, L96). Minimal
  package manifest form at L1770–1771. V2 reads the default export's `id` +
  `setup()` and ignores `server()` (L1796–1824); `setup` may return a
  cleanup function (L59).
- **Context hook / maxTokens (was documented-only, now CLOSED at doc
  level):** `ctx.session.hook("context", ...)` runs for the agent loop
  including tool-driven continuations (L1399–1400); `event.options.maxTokens
  = 8_000` is the documented mutation (L1408–1414) and `maxTokens` is the
  semantic output-token limit (L1450). Changes affect only the outgoing
  model call, not persisted history or configuration (L1420). `options`
  starts empty per call (L1425); request overrides take precedence over
  model defaults, which take precedence over route defaults (L1428) — so a
  hook cap overrides the configured 32,000 `limit.output`. Provider option
  objects merge recursively; arrays/scalars replace (L1429).
- **Agent shape/matching:** `event.agent` is `readonly agent: string` on
  `SessionContextHook` (L1643, interface L1625–1640). Installed corroboration
  (runs against v2.1.4): OTel dist `captureModelContext` reads
  `event.agent`, `event.model.providerID/.id`, `event.sessionID`, and
  registers `ctx.session.hook("context"|"model.request", ...)` (dist lines
  71477–71496, 72123–72132).
- **Dispatch boundaries:** `context`/`compaction`/`generate`/`title` are
  separate per-kind hooks (L1399–1405); `title` has NO `agent` or `tools`
  (L1405). A hook applying to every request kind must register for each
  (L1420–1421). `http.request`/`http.response` run for EVERY request with
  `event.kind` ∈ {primary, compaction, title, generate}; docs say to use
  `kind`, not agent ID, to tell auxiliary requests apart (L1473–1475).
- **Raw-body precedence (was documented-only, now CLOSED at doc level):**
  raw HTTP body overlays apply AFTER protocol lowering and can override the
  resulting fields (L1431).
- **Retry hook (was documented-only, now CLOSED at doc level):** shape
  `{sessionID, agent, model, error: {type, message, status?}, attempt,
  decision}` (interface L1616–1623); hooks run in registration order and
  later hooks see the current decision; the built-in maximum attempt count
  remains a hard limit; `attempt` is the physical attempt — initial request
  1, first retry 2 (L1563–1565); invalid delays fall back to the computed
  delay; context-overflow recovery is separate (compacts instead of
  retrying) (L1566–1567).
- **Interrupt/cancel (mapped, capability level):** `await
  ctx.session.interrupt({ sessionID, resume: false })` exists (L823);
  `ctx.session.remove` stops active execution and recursively deletes child
  sessions (L827); tool executors receive `context.signal` — passing it to
  cancellable work stops the underlying operation when the Session stops
  (L998–1003). Whole-task wall-deadline scheduling is still NOT provided by
  any mapped API (matrix row 3 gap stands; no watchdog/fork added).

### 3. Deliverables (offline mock proof, NOT runtime verification)

- `tests/fixtures/opencode_workflow/worker_budget/worker_budget.ts` —
  **INACTIVE** dependency-free plugin module (default export
  `{ id: "worker-budget", setup(ctx) }`, registers exactly `context` +
  `http.request` hooks, worker-only via readonly `event.agent` comparison,
  returns disposer). NOT registered anywhere; runs under installed Node 24
  native TS type-stripping (verified probe: interfaces, numeric separators,
  async setup import+execute OK). No Bun, no `@opencode/plugin` import
  needed (structurally typed against the documented ctx surface).
- `.../worker_budget/harness.mjs` — Node harness with mock ctx/transport
  implementing the documented v2.1.4 semantics (registration order,
  options-start-empty, override-over-model-default, raw overlay AFTER
  lowering, readonly agent, kind-tagged http events, retry attempt
  numbering, built-in max-attempt hard limit). 8 scenarios.
- `.../worker_budget/README.md` — provenance + residual-gap statement.
- `.../worker_budget/v2.1.4.plugins-index.mdx` — verbatim doc copy (SHA-256
  above).
- `tests/test_worker_budget_contracts.py` — 10 tests, each invoking
  `node harness.mjs <scenario>` and asserting the JSON contract; explicit
  MOCK-ONLY labels in module docstring and asserts; verifies the fixture is
  NOT registered in `opencode.jsonc` and no auto-load plugin dir exists.

### 4. Validation (actual commands and results)

- `node harness.mjs <scenario>` for all 8 scenarios (cwd = fixture dir,
  installed node v24.17.0): all exit 0. Key outputs: worker-context →
  `resolvedMaxTokens 8000`, mock body `max_tokens 8000`; other-agent-unchanged
  → architect 32000 / reviewer 16000 / spade 32000 (configured defaults
  preserved); raw-overlay-collision → overlay `max_tokens 32000` wins AND
  collision reported `{field: max_tokens, overlayValue: 32000,
  semanticValue: 8000}`; retry-attempt → decisions `[retry@1, retry@2,
  stop@3]` and `pluginRegistersRetryHook: false`; dispose-isolation →
  hooks 1→0, cap falls back to 32000; no-persist-mutation → history
  unchanged.
- **RED (actual, not fabricated):** before the fix, `node harness.mjs
  retry-attempt` failed with `ReferenceError: hookStore is not defined`
  (exit 1) — the scenario referenced a stale binding; fixed by probing the
  actual plugin in its own mock context (`pluginRegistersRetryHook` now
  correctly `false`, derived from the real plugin's registrations, not the
  scenario's own hook). This is the recorded bug→fixed sequence; no
  missing-test-file collection trick was used.
- Focused offline suite (exact plan command):
  `uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles
  --group test pytest /Users/kpiwko/.config/dotfiles/tests/test_worker_budget_contracts.py
  /Users/kpiwko/.config/dotfiles/tests/test_git_workflow_contracts.py
  /Users/kpiwko/.config/dotfiles/tests/test_opencode_workflow_scenarios.py -q`
  → **63 passed** (53 prior: 36 git-workflow + 11 scenario + 6
  skill-boundary; + 10 new worker-budget tests). 0.62s, no skips.

### 5. Unverified gate / exact remaining references (Task 4A.1 blocker)

- **Final wire field NOT proven.** The standard `openai-compatible` provider
  package registers `OpenAICompatibleChat.route`, whose lowering lives in
  `packages/ai/src/protocols/openai-compatible-chat.ts` @ v2.1.4 — **NOT
  READ** (8-read HTTP budget exhausted on the doc + provider files). The
  harness's `maxTokens → max_tokens` lowering is an explicitly labelled
  SIMULATION; `worker-context`/`other-agent-unchanged`/`raw-overlay-collision`
  assertions are mock-contract proofs, NOT claims that the official runtime
  emits `max_tokens`. Narrower continuation needs exactly:
  `https://raw.githubusercontent.com/anomalyco/opencode/v2.1.4/packages/ai/src/protocols/openai-compatible-chat.ts`
  (plus, if needed for overlays, the route/client body-merge code it
  references).
- **Provider timeout docs unreconciled:** 2.1.2 `providers.mdx` path is 404
  at v2.1.4; `headerTimeout`/`chunkTimeout`/`timeout` facts stay
  documented-only at 2.1.2 until the relocated v2.1.4 doc is found.
- **No runtime claim:** mock harness proves hook logic and documented
  semantics only. Task 4B (real registration + cap 8,000 arm + smoke)
  remains gated on the unread protocol file, the unset numeric ceiling, and
  the still-missing whole-task deadline mechanism (matrix row 3).

### 6. Four-control matrix update (source confidence)

| Control | Status after 4A.1 |
|---|---|
| 1. Per-generation output cap | Hook + semantic `maxTokens` + precedence + registration path **proven at v2.1.4 doc level** and exercised in offline mock; **final wire key unverified** (protocol file unread) |
| 2. Per-request/attempt deadline | **Unchanged/unreconciled** — v2.1.2 providers doc 404 at v2.1.4; retry hook semantics now doc-proven at v2.1.4 (attempt numbering, hard max, overflow separation) |
| 3. Whole-task deadline | **Gap stands.** `session.interrupt`/`remove`/`context.signal` exist (cancel capability), but no whole-task wall-deadline scheduler; no watchdog/fork added per contract |
| 4. Progress budget | Unchanged (instruction-only) |

---

## Task 4A.1 correction — prototype shrink to honest minimal mock proof

Status: **CORRECTION-DELivered.** This section **supersedes** the earlier
Task 4A.1 prototype claims in sections 3–5 above (hook set, guard value,
wire/collision/retry machinery, model-default simulation, test count, and
the "8-read budget exhausted" framing). The historical record above is kept
verbatim; read it through this correction. No production registration,
config edit, model call, or Git command was performed; no cap activation.

### 1. What was removed (unverified / invented, fixed by removal)

- **Agent guard was wrong.** `WORKER_AGENT = "agentgateway/worker"` is the
  MODEL reference, not the agent. The installed registry
  (`~/.config/opencode/opencode.jsonc`) defines the model under
  `agentgateway` with `"modelID": "worker"` (lines 131–132). The `GET
  /api/agent` opencode API check could NOT be run: no supported read-only
  agent tool exists in the available opencode surface (only
  `models`/MCP-resources/sessions/worktrees), so `agent.name === "worker"`
  remains **explicitly unverified against the live API**; the fixture now
  uses the plain agent name `"worker"` guarded additionally by
  `event.model.providerID === "agentgateway"` AND
  `event.model.id === "worker"` (an exact agent-AND-provider/model guard).
- **Invented `http.request` interface/hook removed entirely**, including the
  raw-body-overlay collision factory options (`rawBodyOverlay`,
  `onCollision`, `collisions`, `registrations`), the fake wire lowering
  (`max_tokens` simulation), the model-default table
  (32000/16000/32000), and all retry machinery/scenarios.
- Hook names in the mock are exactly the documented per-kind hooks
  (`context`/`compaction`/`generate`/`title`); `http.request` no longer
  appears anywhere.
- Removed from code/tests: "process '8 reads exhausted'" framing and all
  wire-body assertions (`capReachedWire`, `outgoingBody.max_tokens`,
  model-default fallbacks, post-dispose default 32000).
- Removed tests: the 8-scenario-name projection count test and the
  global directory-absence assertions
  (`test_fixture_files_present_and_plugin_not_registered`).
- README provenance now cites the repo `.mdx` path + SHA-256/URL only (no
  user-local tool-output path), and cites the readonly `agent` field at
  **L1643** (SessionContextHook), not L1591.

### 2. What the shrunken fixture now is

- `worker_budget.ts` — inactive module, V2 shape `{ id, setup }`, registers
  ONLY the `context` hook; guard = agent name AND providerID AND model id;
  cap applies `Math.min(existing, 8000)` only when the existing value is
  finite and positive (never raises an explicit limit); setup returns a
  disposer whose `dispose()` is idempotent.
- `harness.mjs` — 10 scenarios; each drives the ACTUAL context callback and
  reports deep-copied before/after snapshots so tests detect real
  mutations. Mock implements only the documented hook-registration surface;
  no lowering, no defaults, no transport.
- `tests/test_worker_budget_contracts.py` — 10 tests: worker match applies
  8000; non-worker agent / same-model-different-provider /
  worker-different-model untouched; lower cap (4000) respected; higher
  (32000) lowered; NaN/Infinity/0/-5/"8000"/null ignored; only `context`
  registered; dispose idempotent; only `options.maxTokens` mutates
  (system/messages/tools/identity/temperature unchanged).

### 3. Source-cited expected wire mapping (resolved gap, NOT mock proof)

Reviewer-verified at v2.1.4:
`packages/ai/src/protocols/openai-compatible-chat.ts` reuses
`openai-chat.ts` `fromRequest`, which maps semantic `maxTokens` to
`max_completion_tokens` by default, or `max_tokens` when
`compatibility.maxTokensField` is set or `compatibility.detectMaxTokensField`
selects it. Recorded as **source-cited expected mapping only**; the
compatibility config actually in effect for `agentgateway` remains
unverified (never asserted in any mock). The earlier unread-file gap is
resolved; the README's residual-gap section was updated accordingly.
`HTTPRequest` documents the request as a one-shot stream whose actual body
is not a parsed object — the removed `http.request` collision detection is
recorded as **removed-as-unverified-risk, not implemented**.

### 4. Validation (actual commands and results)

- **RED (actual):** a verbatim copy of the pre-correction prototype run
  against the new agent-name contract returned
  `"agent":"worker","maxTokensAfter":null,"capApplied":false` and
  `hookNames:["context","http.request"]` — the old model-id guard failed to
  cap the real agent event and still registered the invented `http.request`
  hook. Temp reproduction deleted after the run.
- **GREEN (actual):** all 10 harness scenarios exit 0 with correct JSON
  (worker 8000; non-worker 32000; other-provider 32000; different-model
  16000; lower-cap 4000; higher 8000; 6 invalid inputs ignored; only
  `context` registered; dispose 1→0 twice; no extra mutation).
- Focused offline suite (exact plan command):
  `uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles
  --group test pytest .../test_worker_budget_contracts.py
  .../test_git_workflow_contracts.py
  .../test_opencode_workflow_scenarios.py -q` → **63 passed** (53 prior
  unaffected + 10 corrected worker-budget tests), 0.72s, 0 skips.

### 5. Residual gate (unchanged in substance)

- `agent.name === "worker"` is **unverified against the live API** (no
  supported read-only `/api/agent` surface available to this session).
- No runtime/wire claim: the mock proves the plugin's own hook logic only.
  Compatibility config for `agentgateway` unverified; final wire key
  remains a source-cited expectation.
- No claim that the plugin stops budget expiration or enforces any runtime
  deadline. Task 4B (registration, 8,000 cap arm, smoke) remains gated on
  the unverified agent identity + compatibility config and the unset
  numeric ceiling; no cap activation occurred.

---

## Task 4A.1 closure — review corrections (DOC-ONLY)

Status: **CLOSED (doc-only).** No code-behavior change, no Git command, no
model call, no new source investigation. The following truths are now
recorded exactly in the fixture README and `worker_budget.ts`:

- **Agent identity:** `event.agent === "worker"` is INFERRED from the agent
  filename/docs; the live `event.agent` value is UNVERIFIED. The
  AND-provider/model checks narrow matching but do **NOT** compensate a
  wrong agent identity.
- **Line citation fix:** `event.model` (`providerID`/`id`) is at **L1627**,
  not L1641 (readonly `agent` remains L1643).
- **Compatibility setting:** only `compatibility.maxTokensField` selects
  `max_tokens`; `detectMaxTokensField` is an internal function, not a
  public setting.
- **HTTPRequest:** no `HTTPRequest` type is defined; the docs describe a
  **Request-like object** (one-shot stream, body not a parsed object).
- **Rename:** scenario `higher-ignored` → `higher-lowered` (harness +
  pytest, consistent).

Validation (actual): focused offline 3-file suite
`uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles
--group test pytest .../test_worker_budget_contracts.py
.../test_git_workflow_contracts.py
.../test_opencode_workflow_scenarios.py -q` → **63 passed**, 0 skips.

No runtime proof is claimed; all residual gates in the correction section
above stand unchanged.

---

## Task 2 — Three-tier coordination (offline contract deliverable)

Status: **offline complete; live behavior unproven.** Scope: agent contract
text, contract tests, and the offline scenario decision table only. No Git
command, branch/commit/push, model call, install, service restart, or cap
change was performed. Base remains `origin = git@github.com:kpiwko/dotfiles.git`,
review base `main`; branch/HEAD were not read, so this is an uncommitted
worktree snapshot deliverable. Unrelated changes were preserved; the Task 1
skill-allow and Task 4A.1 inactive budget fixture were not touched
(66 prior tests still pass byte-for-byte).

### What changed

- `.config/opencode/agents/worker.md` — new `Handoff tiers` section
  (performed/validated/reviewed; small → lightweight, substantive → exact
  immutable snapshot, publication → full envelope; no receipt engine, no
  mandatory per-action review; validation reuse rules; compact
  Failure/Hypothesis/Evidence/Change/Verification/Remaining uncertainty with
  "not applicable"; end with completed edits/blocker/next action). The
  `Execution discipline` checkpoint now notes it cannot bound generation or
  tool calls that already happened before it fires (pre-tool limitation).
- `.config/opencode/agents/orchestrator.md` — new `Review keying` section:
  reviews keyed by relevant scope and immutable content revision; focused
  review on relevant fix/unclosed finding/changed criteria; no re-review of
  unchanged content after status/push or irrelevant docs; tiered evidence
  requests and reused-vs-newly-executed validation tracking.
- `.config/opencode/agents/reviewer.md` — `Review boundaries` now states an
  unchanged relevant-scope revision must not trigger a duplicate review
  while a relevant fix/unclosed finding/changed criteria does; `Output` now
  requires the reviewed revision (snapshot identity), finding IDs/closure,
  and verdict.
- `tests/test_git_workflow_contracts.py` — 13 new Task 2 contract tests
  (worker tiers/snapshot/reuse/fields/checkpoint, orchestrator review keying,
  reviewer snapshot-findings-verdict and no-duplicate-review).
- `tests/test_opencode_workflow_scenarios.py` — 3 new decision-table tests
  for the fixed `reviewer-finding-unchanged-revision` scenario: unchanged
  snapshot → no extra review; relevant fix → focused review; dependency or
  environment change → validation invalidated.
- The existing scenario fixture `scenarios.json` was NOT modified; the new
  tests exercise its existing `unchanged_revision_rule` and
  `invalidation_trigger` fields plus local decision logic.

### Validation (actual commands and results)

- **RED (actual):** new tests against the unchanged agents/fixtures via the
  exact plan command → **13 failed, 66 passed** (all 13 failures were the
  new Task 2 assertions; no prior test regressed).
- **GREEN (actual):** `uv run --offline --no-sync --project
  /Users/kpiwko/.config/dotfiles --group test pytest
  .../test_git_workflow_contracts.py .../test_opencode_workflow_scenarios.py
  .../test_worker_budget_contracts.py -q` → **79 passed**, 0.94s, 0 skips
  (66 prior + 13 new; prior baseline was 63 across these three files plus
  the scenarios file's share, all unchanged).

> **T2-F2 correction (supersedes the counts above):** the RED-run
> breakdown "13 failed, 66 passed" double-counted: the 66 passing tests
> already included the 3 new scenario tests, which passed from the start
> (GREEN on first run, never RED), so only 13 tests were genuinely RED and
> the prior baseline remained 63. The "63 prior + 13 new = 79" arithmetic
> also omitted those 3 scenario tests (16 new total). The reported timings
> (0.94s vs later 0.87s) were not reliable run-to-run and are not reused as
> evidence; see the closure section below for the authoritative fresh
> result after the focused fix.

### Limits (fixture logic, not live-agent proof)

- These are contract assertions on instruction text and an offline decision
  table over fixture fields. Passing them does not prove agents follow the
  tiers at runtime, that duplicate reviews stop, or that validation reuse
  fires; prompts do not mechanically enforce runtime behavior.
- The decision-table tests use a local `_decide_review_and_reuse` fixture
  function and synthetic snapshot values, not live agent output.
- Enforceable runtime budgets, the separately authorized smoke envelope,
  Task 1 live skill-load proof, Task 4B registration, and Task 3 publication
  gates remain out of scope and unchanged.

### Task 2 focused review closure (T2-F1, T2-F2)

Status: **both findings CLOSED (offline).** Reviewer reported no blockers
and two important findings; this focused fix addresses exactly those IDs.
No Git command, model call, install, or production framework was added; the
decision helper remains illustrative test logic, not agent behavior.

**T2-F1 — tautological decision tests / review-vs-validation conflation
(closed):** the three `_revision_unchanged` tests were replaced by an
explicit fixture-driven decision table whose helper returns `review_needed`
and `validation_reusable` separately. Nine rows are asserted:
`unchanged-revision`, `relevant-worktree-fix`, `index-change`,
`allowlisted-new-file-change`, `unclosed-finding`, `changed-criteria`,
`dependency-change`, `environment-change` (8 parametrized rows) plus the
irrelevant doc/status/push row (dedicated test that also asserts the
fixture's own `unchanged_revision_rule`/`invalidation_trigger` text).
Semantics fixed: dependency/environment changes make validation
NON-reusable but do NOT set `review_needed` absent relevant code/criteria
changes; an unclosed finding triggers review but does NOT block validation
reuse by itself (an open finding changes no test inputs); changed criteria
triggers review and can invalidate reuse when the criteria affect test
inputs; irrelevant doc/status/push changes trigger neither. Two
malformed in-memory decision-function mutations (any-change⇒review
collapse; validation-blindness) are demonstrated to be CAUGHT by the
decision table (`pytest.raises(AssertionError)`), so the rows are not
dictionaries equal by construction. Matching reviewer scope wording was
added: dependency/environment changes invalidate reported validation
without automatically triggering a review absent a relevant code or
criteria change, with a matching contract test
(`test_reviewer_dependency_or_environment_change_is_not_automatic_review`).
The reviewer Output now reports the reviewed revision AND relevant scope;
the existing test was extended to match. No `scenarios.json` change was
needed; its existing fields already carry the rule text. Routine small
work remains conditional lightweight per the worker tiers section.

**T2-F2 — count/timing arithmetic reconciliation (closed):** the original
"66 prior + 13 new = 79" breakdown was wrong in two ways. First, 66
included the 3 new scenario tests that passed from the start (GREEN on
first run, never RED), so only 13 tests were genuinely RED and the prior
baseline was 63, not 66. Second, the "63 prior + 13 new = 79" framing
omitted those 3 scenario tests (16 new at that point). The reported
timings (0.94s vs 0.87s) were not reliable run-to-run; prior reporting
treated them as comparable and is marked inconsistent — the fresh actual
result below is authoritative and earlier timings are not reused as
evidence.

**Fresh authoritative validation (actual, post-fix):** the exact plan
command `uv run --offline --no-sync --project
/Users/kpiwko/.config/dotfiles --group test pytest
.../test_git_workflow_contracts.py .../test_opencode_workflow_scenarios.py
.../test_worker_budget_contracts.py -q` → **88 passed, 0 skipped**
(0.95s). Breakdown: 63 pre-existing tests (53 git-workflow/scenario
baseline + 10 worker-budget) + 14 contract tests (13 original Task 2 + 1
new reviewer deps/env test) + 11 scenario-file tests (8 parametrized
decision rows + irrelevant-row + 2 malformed-function mutation tests) =
88 collected, 88 passed. The previous single failing run during this fix
(1 failed, 87 passed) was the irrelevant-row dict bug — caught and fixed
in-run; it was the only intermediate failure and no prior test regressed.

**Review state:** the two findings above are closed by this focused fix;
per the new review keying, a focused re-review of exactly this revision's
changed scope (scenario tests + reviewer wording + this evidence) is
warranted when requested — unchanged content elsewhere needs no
re-review. Limits stand: static contract assertions + fixture decision
logic, not live agent behavior proof.

**T2-F3 — unclosed-finding reuse semantics (closed, one-line helper +
row fix):** `validation_reusable` no longer includes `and not
finding_open` in `_decide_review_and_reuse`; the `unclosed-finding` row
now expects `review_needed=True, validation_reusable=True` because an
open finding alone changes no check inputs (worktree/index/allowlisted/
dependency/environment/criteria). A relevant worktree fix still
invalidates validation, and changed criteria can still invalidate it when
the criteria affect test inputs (`criteria_changed` remains in
`check_inputs`). The stale Limits line referencing the removed
`_revision_unchanged` helper was corrected to `_decide_review_and_reuse`.
Pytest actual output after the fix: **88 passed** (count only; run-to-run
timings are not reported as comparable evidence). Per the new review
keying, this one-line helper/row closure on the already-reviewed scope
does not warrant a whole-Task-2 re-review.

---

## Task 3A — Opt-in publication expectation gate (Phase 3)

Status: **offline complete.** Implemented inside the existing
`sandbox-git` wrapper; no separate check-only command framework, no
agent/skill/publication-protocol changes, no Git operation on HOME, no
fetch/push/publication, no model calls. All validation below used the
disposable offline `init_repo` fixtures and local-path bare remotes.

### 1. Interface and supported guarded forms

Prefix-only options before the subcommand; any expectation option
requires ALL six exactly once, well-formed and non-conflicting:

- `--expect-root ABS` — canonical cwd must equal it BEFORE any Git call;
  the observed worktree root must also equal it (a non-repo project dir
  falling back to the HOME bare dotfiles repo is rejected, so a project
  cannot be pushed through dotfiles by mistake).
- `--expect-head FULL_OID`, `--expect-branch NAME`,
  `--expect-upstream REMOTE:refs/heads/NAME|none`,
  `--expect-destination REMOTE:refs/heads/NAME`,
  `--expect-push-url URL`.
- Optional `--check-only` (only with the complete set): local read-only
  JSON report of observed values and per-field matches; runs NO guards,
  never calls the `default_branch` network fallback, and claims no
  authorization ("authorization_claimed": false).

Guarded operations: `publish [REMOTE]` and restricted `push` — no args,
`REMOTE` only, or `REMOTE HEAD:refs/heads/NAME` (HEAD-only source; a
`refs/heads/SOURCE` form could push a different commit than
`--expect-head` and is rejected). Force/delete/tag/wildcard/multiple
refspecs/other subcommands/unknown options fail closed with zero Git
calls. Publish and the wrapper's own no-refspec push forms always push an
explicit `HEAD:refs/heads/<current>` refspec, so `remote.push`/`push.default`
never redirect them; for `push REMOTE` without a refspec the destination is
resolved from `remote.<REMOTE>.push` (exactly one normal refspec) or
`push.default` (simple/current/upstream only; upstream must be on the push
remote) — anything ambiguous is rejected, never guessed. Effective push
URL = exactly one result of local `git remote get-url --push --all`
(Git itself resolves pushurl/insteadOf); multiple effective URLs reject.
Expectations are never echoed as observed values; all observations are
re-read from the repository. Comparisons run before the existing
potentially networked guards AND again immediately before `execvp`, with
the planned argv recomputed from post-guard observations; drift fails
without repair. Existing protected-branch/upstream/exit-status behavior
and all legacy unguarded paths are unchanged. Passing the flags is not
approval; the legacy unguarded invocation remains possible.

### 2. Genuine RED history (bugs found by the new tests, then fixed)

1. **Wrapper defect:** `NameError: name 'validate_push_url' is not
   defined` — the helper had been lost during an intermediate edit; the
   parse-failure batch caught it before any green claim. Restored.
2. **Test-helper defect:** the recording git shim embedded
   `PosixPath('...')` instead of a string literal, so the shim crashed and
   the wrapper reported "cannot determine worktree root". Fixed by
   embedding `str(sentinel)`.
3. **Test-design error, not wrapper:** branch/destination mismatch cases
   originally used `publish`, which correctly trips the parse-time
   publish branch/destination conflict check; re-scoped to `push origin`
   so those mismatches surface at comparison time as intended.
4. **Test-expectation error against preserved legacy behavior:** the
   push.default=upstream execution test expected a differently-named
   upstream push to execute, but the existing `validate_push` upstream
   guard legitimately rejects it. The legacy guard was NOT weakened; the
   test was re-scoped to prove resolution via `--check-only` JSON
   (`destination: origin:refs/heads/base`) plus preservation of the
   legacy rejection (`upstream branch 'base' differs from 'feat/test'`,
   zero push calls).

### 3. Test coverage delivered (57 new tests; 24 legacy preserved)

Parse failures closed before any Git call (32 parametrized cases: partial
sets, check-only alone, unknown/duplicate/misplaced options, missing
value, nonpublication subcommands, force/delete/tag/bare-destination/
source-only/too-many/refspec-without-remote push forms, malformed values,
both conflict cases); wrong cwd → zero Git calls; wrong-root-inside-repo
(HOME-bare fallback rejection); each head/branch/upstream/destination/
push-url mismatch stops before guards and before any `remote show`/`push`;
upstream-absence match and mismatch; check-only JSON (all fields,
authorization_claimed false, zero push/network/mutation, HEAD unchanged,
remote branch absent) and mismatch JSON (exit 1); matching execution with
exact recorded push argv for publish (with/without upstream,
`--set-upstream` only when upstream absent), bare push, `push REMOTE`,
and `push REMOTE HEAD:refs/heads/NAME`, each with the real local push
verified and no force flags; existing protected-branch, protected
refspec-destination and cross-remote-upstream guards still reject on
guarded paths; state drift between the two comparisons rejects for both
publish and push paths with no push executed; nonzero wrapped exec
propagates; push.default=upstream resolution (check-only) with legacy
guard preserved; remote.origin.push single-refspec resolution;
push.default=matching rejected; multiple remote.origin.push refspecs
rejected; multiple effective push URLs rejected; legacy unguarded push
(short-name destination, refs/heads/SOURCE refspec) unchanged.

Drift shim note: the drift injection renames the current branch when it
first sees `rev-parse --is-inside-work-tree`, which occurs only inside
`ensure_repo` during the guard phase (between the gate's two comparisons);
`drift=True` must never be used in matching-execution tests.

### 4. Validation (actual, final)

```
uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles --group test \
  pytest tests/test_sandbox_git.py tests/test_git_workflow_contracts.py \
  tests/test_opencode_workflow_scenarios.py tests/test_worker_budget_contracts.py -q
→ 169 passed, 0 skipped (111.92s)
```

Breakdown: 24 legacy wrapper tests (byte-for-byte unchanged, still
passing) + 57 new Task 3A tests + 88 contract-file tests (Task 2/4A.1
baselines, unmodified). Baseline before this task: 112 passed.

### 5. Scope identity (file hashes only, `shasum -a 256`, 2026-11-03)

- `.local/bin/sandbox-git`:
  `fd6f4dc4a35c7d8a67a35a773bdc69e91884a2b87348de4260b5b263fea2c033`
- `.config/dotfiles/tests/test_sandbox_git.py`:
  `e28a0849e0e07b40097ee405b1136002e5df246bf6f79836c0f388608f3723a4`

### 6. Residual limits (explicit, not closed by this task)

- Residual TOCTOU window between the final comparison and `execvp`
  remains; this is not an atomic transaction.
- Passing expectation flags is NOT consent/approval; the legacy unguarded
  invocation remains possible, so universal bypass prevention is not
  claimed. The wrapper cannot prove review quality or intent.
- A local check-only match is not remote freshness evidence; postflight
  (actual exit plus separately authorized local/remote/hosting receipts)
  stays parent-owned — no fabricated wrapper receipt was added.
- insteadOf/pushurl resolution delegates to local `git remote get-url
  --push --all` (single effective URL required); no independent
  reimplementation of Git URL rewriting is claimed.
- Task 3 remains PARTIAL after 3A: scoped index/worktree/untracked
  snapshot, base freshness and review/validation-input gates, and later
  publication instructions remain separate unfinished parent work.

### 7. Focused security-closure review fixes (B1, B2, I1, I2, I3)

Status: **CLOSED (offline).** Five reviewer findings fixed inside the same
wrapper/test scope; no architecture expansion, no force authority, no Git
operation on HOME, no model calls. All validation below used disposable
`init_repo` fixtures and local-path bare remotes only.

- **B1 (High) — resolved destination unprotected for guarded push REMOTE
  without refspec: CLOSED.** `guard_resolved_destination` now runs in the
  guard phase for every guarded execution path (publish and all push
  forms, both before the existing guards and again immediately before
  exec), refusing when the ACTUAL resolved destination — explicit refspec
  or config-resolved via remote.<REMOTE>.push / push.default — is
  protected, with the default branch resolved for the ACTUAL push remote
  (`default_branch(git, remote)`, not hardcoded origin). Check-only still
  reports matches only and claims no guard passed, per plan. Tests:
  `remote.origin.push=HEAD:refs/heads/main` with all six expectations
  matching rejects before any push; explicit `HEAD:refs/heads/trunk`
  (remote's own default branch) rejects; remote `--force` style option
  injection rejected (I2 batch).
- **B2 (High) — push-widening effective config: CLOSED.**
  `check_push_widening_config` (local, no network) rejects in BOTH
  execution and check-only, and runs inside every `observe()` call so the
  final pre-exec check detects config drift between comparisons:
  `remote.<R>.mirror=true`, `push.followTags=true`, any non-empty
  `push.pushOption`/`remote.<R>.pushOption`, `push.recurseSubmodules`
  not in no/false/off/0/empty, `push.gpgSign` not in false/no/off/0/empty,
  and malformed booleans fail closed. No raw push argv rewriting; legacy
  unguarded behavior untouched. Explicit scope statement: this is a fixed
  profile of known widening settings, NOT a claim that every Git side
  effect is contained; server-side pre-receive hooks remain outside this
  contract. Parametrized tests cover each rejected setting for
  execution AND check-only (no actual push in any rejected-case log),
  plus false/no/false/false safe values still executing normally.
- **I1 — legacy argument regression: CLOSED.** The misplaced-option
  rejection now applies only when the invocation actually carries prefix
  wrapper options; unguarded legacy calls may pass `--expect-*` /
  `--check-only` as literal Git data and forward unchanged. Test asserts
  the exact forwarded argv via the failing-git sentinel (exit 99 by
  design, no real commit/push), token-for-token after the wrapper's
  --git-dir/--work-tree prefix. True unknown leading prefix options still
  fail closed (existing parse batch retained).
- **I2 — remote option injection: CLOSED.** `validate_remote_name`
  rejects remote names starting with `-` before any Git call, so
  `publish --force` / `publish --receive-pack=x` fail closed at parse
  time (tests updated to the actual messages).
- **I3 — credential output: CLOSED.** Raw URLs are compared unchanged,
  but every output path is redacted: mismatch messages
  (`compare_or_fail`) and check-only JSON (observed and expected)
  sanitize userinfo via stdlib `urllib.parse` (scheme and scp-like
  forms; user:pass replaced with `user:<redacted>`; percent-encoded
  tokens covered by full userinfo stripping; URLs without userinfo pass
  through unchanged). `git remote get-url` itself strips userinfo from
  its output, so observed URLs are additionally credential-free at the
  source. Tests assert the secret appears in neither stdout nor stderr
  on both mismatch and check-only paths, including a wrong expected URL
  carrying a different secret.

**Genuine RED found by the new cases and fixed (no fabricated red):**

1. `push.gpgSign false` was wrongly rejected — the boolean check was
   inverted (`if not as_bool(...)`); fixed to reject only non-false
   values, with `if-asked` handled as a widening rejection rather than a
   malformed-boolean crash.
2. `WideningConfigError` escaped as a Python traceback instead of a
   `fail()` message; `observe()` now converts it to a clean fail-closed
   error.
3. `redact_url` returned `<redacted-invalid-url>` for ordinary local
   paths (no userinfo); fixed to pass userinfo-free URLs through
   unchanged so local-path remotes still report and match.
4. Test-side corrections recorded honestly: safe-value widening tests
   initially lacked an upstream (git itself failed 128 — test setup, not
   wrapper); the I1 sentinel assertion initially parsed the failing-git
   space-joined log as NUL-joined; the URL test initially expected
   `user:<redacted>@` in observed output although `git remote get-url`
   already strips userinfo at the source.

**Validation (actual, final, exact plan command on all four files):**

```
uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles --group test \
  pytest tests/test_sandbox_git.py tests/test_git_workflow_contracts.py \
  tests/test_opencode_workflow_scenarios.py tests/test_worker_budget_contracts.py -q
→ 189 passed, 0 skipped (152.53s)
```

Breakdown: 169 prior (24 legacy wrapper + 57 Task 3A + 88 contract files)
+ 20 new security-closure tests (2 B1 destination-protection, 9 B2
rejected-settings parametrized ×2 paths in one test each, 4 B2 safe
values, 1 I1 literal passthrough, 2 I2 publish-option injection in the
parse batch, 1 I3 redaction, plus the 2 new misplaced-option publish
cases) = 189 collected, 189 passed. The 24 legacy wrapper tests remain
byte-for-byte unchanged and passing.

### 8. Scope identity after security closure (file hashes only, 2026-11-03)

- `.local/bin/sandbox-git`:
  `5dfb252b8a9adb0a35609aab4f3b818125537d38d4be9e8a14062ebef8edcdf6`
- `.config/dotfiles/tests/test_sandbox_git.py`:
  `733f9b615c12b5ec2778396455aa3a69a47ed329a9d8f1106637bd9bde6bc957`

### 9. Focused N1/N2 closure (second security review pass)

Status: **CLOSED (offline).** Two edge findings on B1/B2 fixed; I1/I2/I3
confirmed closed by the reviewer and unchanged in substance (one
non-blocking `redact_url` robustness fix included below). No HOME Git
operations, no model calls, no publication, no architecture expansion.

- **N1 (High) — network window after final comparison: CLOSED.**
  `guard_resolved_destination` previously ran AFTER the final
  observe/compare; because `default_branch` may use the network-capable
  `git remote show` fallback, that ordering opened a network window after
  the last identity observation. All network-capable guards now run
  BEFORE the final observation in both `publish()` and the guarded push
  dispatch: initial check → resolved-destination protection (network) →
  existing guards `validate_publish`/`validate_push` (network) → final
  observe+compare → exec. After the final comparison only the push
  executes; the final observed destination must still match the expected
  destination, so destination drift remains covered by the comparison
  itself. Local config reads inside the final `observe()` contain no
  network call. Order is proven by two call-order tests (publish and
  push origin, fixtures deliberately lacking `refs/remotes/origin/HEAD`
  so the `remote show` fallback must fire): the last `remote show` index
  is strictly before the last `rev-parse HEAD` identity observation, and
  the push index is strictly after it.
- **N2 (Medium) — valueless bool key semantics: CLOSED.** A bare
  valueless config key is git TRUE, an explicitly empty value (`key =`)
  is false/reset; `git config --get-regexp` renders both nearly
  identically (probe: bare `key\n`, empty `key \n`), so the distinction
  cannot be made from the regexp line alone. Each matched widening key
  is now resolved with a local `git config --bool --get <key>` read:
  bare → true (rejected for mirror/followTags/gpgSign/recurseSubmodules,
  and any pushOption presence with a value or bare TRUE is rejected),
  explicit empty → false (allowed, subject to the existing profile),
  malformed boolean (e.g. `mirror=maybe`) → fail-closed rejection.
  Explicit false/off/no/0 remain allowed. Parametrized tests write bare
  and `key =` fragments directly into the fixture repo's config file
  (never HOME config) for mirror/followTags/gpgSign/recurseSubmodules/
  pushOption, asserting rejection for bare keys and normal execution for
  explicitly empty keys, with zero push calls in rejected logs.
- **Non-blocking `redact_url` robustness: FIXED.** The previous
  netloc-reassembly could raise on invalid ports and lose IPv6 brackets,
  and the interim splice arithmetic corrupted output. UserInfo is now
  removed by splitting the raw authority on its LAST '@' (scheme-aware
  authority bounds), preserving host, port and IPv6 brackets with no
  port re-parsing; raw URLs are still compared unchanged.

**Correction to section 7 (I3):** the earlier claim that "`git remote
get-url` itself strips userinfo" was imprecise — the wrapper's own
`redact_url` performs the output redaction; `git remote get-url` output
observed in tests happened to be credential-free for the tested
credential URL form, which is not a general guarantee. The redaction
tests remain valid (secrets asserted absent from stdout/stderr on both
mismatch and check-only paths).

**Genuine RED found by the new N1/N2 cases and fixed:**

1. The regexp-line `partition(" ")` present/bare heuristic was inverted
   relative to git's actual rendering, silently treating explicitly
   empty values as bare TRUE; replaced with per-key `--bool --get`
   resolution.
2. Malformed booleans (`mirror=maybe`) fell through silently after the
   `--bool` rework (bool_of → None skipped the check) and surfaced later
   as an unrelated URL error; now fail closed at the widening check.
3. `redact_url` splice arithmetic corrupted URLs containing userinfo
   (duplicated host fragment); replaced with authority-bounded last-@
   removal.

**Validation (actual, final, exact plan command on all four files):**

```
uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles --group test \
  pytest tests/test_sandbox_git.py tests/test_git_workflow_contracts.py \
  tests/test_opencode_workflow_scenarios.py tests/test_worker_budget_contracts.py -q
→ 201 passed, 0 skipped (185.24s)
```

Breakdown: 189 prior + 12 new N1/N2 tests (2 call-order tests, 5 bare-key
rejection rows, 5 explicit-empty allowed rows) = 201 collected, 201
passed. The 24 legacy wrapper tests remain byte-for-byte unchanged and
passing.

### 10. Scope identity after N1/N2 closure (file hashes only, 2026-11-03)

- `.local/bin/sandbox-git`:
  `bf78eac55c7df6c8f2a9d0581b6b4c1bda388bb4b8bc12aaab6c8558fd2f7177`
- `.config/dotfiles/tests/test_sandbox_git.py`:
  `879c32f43f14250461f9706e180b7f62fd788fc679767a272b3dbde7874f2234`

### 11. N3 closure — case-sensitive remote subsection in widening lookups

Status: **CLOSED (offline).** `check_push_widening_config` previously
lowercased the ENTIRE emitted config key before the per-key
`--bool --get`/`--get` lookups; git remote SUBSECTION names are
case-sensitive, so a widening setting on a remote like `MyFork` would
have been probed under a wrong (lowercased) key and silently missed. The
exact emitted key is now preserved for every config query; a lowercase
form (`lowered`) is used only for suffix/label comparison. Fail-closed
"config lookup disappeared" remains for keys that vanish between the
regexp discovery and the per-key resolution (an explicitly empty value
resolves as false, not disappeared).

Also fixed in the same pass (found by the N3 tests, genuine RED): the
pushOption branch applied `--bool` to non-boolean values (e.g. `x`),
misreporting a present pushOption as a disappeared lookup; a non-empty
value is now itself the rejection and `--bool` is consulted only for the
bare/explicit-empty discrimination. `--get-regexp` lowercases the
variable NAME while preserving the subsection case — observed in the
test expectations (`remote.MyFork.pushoption`).

Tests: `test_guarded_case_sensitive_remote_subsection_widening_rejects`
(2 rows, `pushOption=x` and `mirror=true` on remote `MyFork`): guarded
execution AND check-only each reject with the actual unsafe
mirror/pushOption message (not malformed/lookup artifacts) and zero
push calls in the logs. Existing origin-scoped tests unchanged.

**Validation (actual, final, exact plan command on all four files):**

```
uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles --group test \
  pytest tests/test_sandbox_git.py tests/test_git_workflow_contracts.py \
  tests/test_opencode_workflow_scenarios.py tests/test_worker_budget_contracts.py -q
→ 203 passed, 0 skipped (228.00s)
```

### 12. Scope identity after N3 closure (file hashes only, 2026-11-03)

- `.local/bin/sandbox-git`:
  `435ba85165999d46ae9a1aa82e6ab9e1f51ef20baeb5d5033df5ba8165f44644`
- `.config/dotfiles/tests/test_sandbox_git.py`:
  `eedd5d6bff2de0b1d262386e099292cc8c30ee21a39032a396020fa4438cea02`


