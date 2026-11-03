# Dotfiles PR Trace Remediation Implementation Plan

> **For agentic workers:** The user has approved implementation; this supersedes the earlier blanket planning-only status, not the finite-experiment or publication gates. Execute only the orchestrator's bounded assigned unit. This particular revision is status-only; reported code changes were performed previously, not by this planner. The parent orchestrator owns sequencing/delegation; do not launch another execution hierarchy. Stable task IDs 0–5 are retained; execution order follows the four phases below.

## Execution checkpoint — 2026-11-03

Source: parent-supplied implementation/reviewer receipts, with historical evidence in `.config/dotfiles/docs/plans/2026-11-02-dotfiles-pr-trace-evidence.md` (Task 3A appended through section 12). This status-only revision performs no investigation or validation rerun. This ledger supersedes historical pending wording in task steps below without expanding their scope.

- [ ] **Task 0 not started:** no new preparation review-loop investigation beyond previously supplied trace evidence.
- [x] **Common offline scenarios delivered:** four fixed scenarios in `tests/fixtures/opencode_workflow/scenarios.json`, with 11 tests in `tests/test_opencode_workflow_scenarios.py`. These validate definitions/contracts, not runtime budget enforcement.
- [x] **Task 1 offline complete, prior review PASS:** exact `systematic-debugging` allow plus conditional workflow and cross-reference permission boundary; no shell/model/steps/subagent/publication expansion. Exact ID confirmed through running `GET /api/skill` and installed superpowers `8ca22db`. Prior review closure remains complete.
- [ ] **Task 1 live proof pending:** existing-session visibility is corroboration, not actual fresh-worker skill load.
- [x] **Task 4A.1 narrowed offline deliverable delivered:** inactive context-only fixture `worker_budget.ts`, mock harness with 10 tests in the now-created `tests/test_worker_budget_contracts.py`, and pinned 2.1.4 docs/README. Prototype guards agent string `worker` AND provider `agentgateway`/model `worker`; semantic cap 8,000 respects a lower existing limit. Context-hook agent-string shape is explicitly live-unverified. Fixture is inactive only: no config registration or runtime cap change.
- [x] **Task 4A.1 review closure:** new-scope code findings fixed by shrinking the prototype and removing invented `http.request` and lowering/retry/default logic. Closure confirmed code/test findings closed; remaining documentation caveats then corrected and focused tests passed. No further review needed for this closure absent relevant changes.
- [x] **Task 4A.1 focused offline validation:** 63 passed, 0 skipped (53 prior + 10 mock tests), historical parent receipt; mock results prove only their context-fixture boundary, not outgoing wire/runtime behavior.
- [x] **Task 2 offline complete:** three-tier instructions; scoped index/worktree/allowlisted-untracked snapshot; dependency/environment-sensitive validation reuse; review revision and finding closure. Task-specific validation **88 passed, 0 skipped across three files**, parent-reported, not rerun by planner. Manual review T2-F1/F2 closed; T2-F3 helper/row corrected (`unclosed finding`: review=True, reuse=True) and orchestrator read confirmed. Digests remain in worker result; no further review needed for this closure absent relevant changes. Static/fixture results are not live coordination proof.
- [x] **Task 3A offline complete:** six-expectation wrapper prefix and local-only `--check-only`; canonical root before Git, full HEAD/branch/upstream/actual destination/single effective push URL checked before guards and finally before exec. Added resolved-destination protected guard and fail-closed widening-config checks (mirror/followTags/pushOption/recurse/gpg), with canonical Git boolean semantics for false/empty/bare values and case-sensitive remote names. Raw URLs are compared, outputs redacted; 24 legacy tests remain unchanged. No universal bypass-prevention, authorization or atomicity claim.
- [x] **Latest four-file focused offline validation: 203 passed, 0 skipped**, parent-reported. Manual review **PASS**; B1/B2/I1/I2/I3/N1/N2/N3 closed on wrapper SHA-256 `435ba85165999d46ae9a1aa82e6ab9e1f51ef20baeb5d5033df5ba8165f44644` and tests SHA-256 `eedd5d6bff2de0b1d262386e099292cc8c30ee21a39032a396020fa4438cea02`. Qodo unavailable; no follow-up review for unchanged scope.
- [x] **Additional read-only runtime evidence:** `GET /api/agent` reports worker ID/name `worker`, model provider `agentgateway`/ID `worker`, steps 40. Current route has no `compatibility.maxTokensField` override and an empty raw body; live worker entry request settings/headers/body are empty. Official standard-compatible default `max_completion_tokens` is expected, **not wire-proven**. Documented `ctx.session.interrupt({sessionID, resume:false})` is supported API evidence, not proof of actual HTTP abort/deadline enforcement.
- [ ] **Task 4A remains partial:** context-only fixture still inactive; configured output limit remains 32,000. Actual context-hook identity shape, lowered outgoing request, HTTP abort, length continuation and maximum retry count remain unverified. Do not reinstate fabricated lowering/retry logic to close gaps.
- [ ] **Broad Task 3 remains partial:** snapshot/index/untracked, base-freshness/review-input gates and full publication protocol pending; postflight parent-owned. **Tasks 0, 4B and 5 not started.** No active hook, approved smoke or set per-run finite ceiling; no actual HOME Git operations, commits, push, PR or restart. No 80-minute smoke approved. Pricing work is deferred until a finite safe envelope is feasible; implementation approval is not live-call or production-cap approval.

**Goal:** Bound worker execution first, reduce unnecessary coordination second, and repair trustworthy trace interpretation third, with preventive Git predictability and minimal administration.

**Architecture:** Preserve the orchestrator/worker/reviewer split, `sandbox-git`, and OpenCode → Collector → MLflow pipeline. Ship four independently verifiable phases; worker improvements do not wait for telemetry fixes. Prefer one narrow worker budget hook and existing tests/contracts over new agents, receipt frameworks or dashboards.

**Tech Stack:** Existing OpenCode/plugin/provider integration; Markdown contracts; Python >=3.12, pytest >=9,<10; installed plugin test tooling only where verified.

**Spec:** User counterproposal dated 2026-11-02 supersedes this plan's earlier publication-attribution and rollout assumptions. Related historical context: `2026-11-02-dotfiles-observability-commit-preparation.md` and `2026-10-26-opencode-mlflow-evidence.md` in this directory; neither grants renewed execution authority.

## Constraints and scope

- Repository `kpiwko/dotfiles`; execution root `/Users/kpiwko`; known base remote `origin = git@github.com:kpiwko/dotfiles.git`, review base `main`. Current branch/HEAD are not assumed. Every future shell invocation explicitly sets `shell.workdir` to its assigned absolute root; HOME Git is delegated to worker using `sandbox-git` only.
- This revision authorizes **only this plan status edit**. Previously reported implementation is recorded, not newly performed here. No implementation/config/runtime changes, Git commands, experiments, commits or publication in this revision. Future implementation tasks need assignments and scoped permission.
- Local synchronization, branch setup/rewrite, commit, push, review creation/modification, deletion and merge are separate scopes. Fetch changes local refs; remote read is a distinct read/network scope. Unknown freshness is not permission to fetch. No history repair.
- Preserve dirty/index state and unrelated work. No HOME sweep, bare-repository inspection, cache patches, dependency acquisition, service restart, cluster changes, paid model switch, new agents or execution framework.
- Bounded prior inspection found no accepted ADR under `.config/dotfiles/docs/`; existing contracts apply. **ADR REQUIRED: NO** for this contract work; a later significant runtime/fork/security choice may need one.
- Worker skills remain deny-default and nested subagents denied. Only the exact discovered debugging skill may be newly allowed. No TDD/verification/code-quality bundle or publication authority expansion.
- No blanket prompt/tool/secret logging, private hidden chain-of-thought or blanket HOME hashes. Record scoped sanitized facts and synthetic canaries. Cost metrics `cost.usage` and `session.cost.total` stay intentionally disabled.

## Diagnosis and corrected accounting

Trace/GitHub observations below are supplied verified evidence, not new runtime measurements in this revision.

- Target experiment-23 trace `tr-8b397246fc07e86146e1838818e926d2`, Nov2 13:29:42–13:38:45 UTC, lasted 543.067 s and was interrupted. Worker LLM `apzIE+6vBCo=` took 500.853 s (~92%), emitted 32,000 completion tokens and finished `length`; afterward only `publish-change` and `sandbox-git status` completed. No push/PR/reviewer call occurred in this trace. Tool-count checkpoints cannot constrain the initial generation.
- **The user personally pushed the commits.** Manual publication explains the absence of agent publication in this trace; do not infer hidden agent publication or attribute final PR/history/branch transitions to agents. Do not investigate manual publication authorization.
- PR43, `https://github.com/kpiwko/dotfiles/pull/43`, `Updates`, merged Nov2 13:47:55Z, head `updates`, base `main`, contains FIVE commits: `0c2a3a6`, `44d71b4`, `c1ed717`, `227089e`, `7487a92` (zellij). Two preexisting changes were already in base through PR42, merged Oct23 from `sol-orchestartor`. This is resolved accounting context, not an agent transaction failure.
- Prior worker comparisons found equal trees for `96bab69/0255c2f`, `24646ec/030dfba`, `b88b446/0c2a3a6`, `18027b9/44d71b4`, `e6bc238/c1ed717`, `6f23ccb/227089e`. Content survived; changed hashes do not establish loss. No historical re-audit or repair is requested.
- Oct27 trace `tr-48d29b22f3962c491f1c64024574ca14` had 111 spans, a ~576 s worker ending maxsteps, and no reviewers. The actual preparation review-loop trace/count remains unresolved; neither sampled trace disproves the user's complaint.
- Delegation `I7CMyybBECQ=` and exported child input have collapsed spacing such as `Gitoperation: normal nonforce push currentbranch...`. Both share the export pipeline; model wording versus native serialization versus export corruption remains unresolved.
- Root span session `ses_e86fd393dffeqj63vFOR5p1DPW` differs from trace metadata child `ses_e638c1d83ffev7ezLGpV7GX1QD`; root-session filtering omits target. Child `4ZIYJyCVaUY=` nests correctly below `I7CMyybBECQ=`, and child tools/LLMs exist, so missing ingestion is not demonstrated.
- Root/trace OK coexists with abort errors and length termination. Metadata completion 759 does not represent visible LLM completions 32,000 and 1,254. Empty events, absent reasoning text and zero reasoning counts do not establish whether provider data existed.
- At diagnosis time worker allowed only init/publish after wildcard deny. Task 1 has since added exactly `systematic-debugging`; fresh-worker load remains unproved. Local directory counts never established plugin skill absence. Reviewer already treats implementation validations as evidence instead of rerunning tests.

**Conclusion:** Runtime bounding is the first remedy to test, not a proven fix yet. Coordination improvements are preventive pending bounded review-loop evidence. Git transaction checks are preventive only. Telemetry work must separate raw execution facts from derived task outcomes.

## Documented capabilities, not installed confirmation

The user supplied current Context7 findings for `/anomalyco/opencode/v2.1.2`:

- [Plugin context hook](https://github.com/anomalyco/opencode/blob/v2.1.2/services/www/src/docs/content/build/plugins/index.mdx): `ctx.session.hook('context')` may mutate `event.options.maxTokens`; `agent: string`, sessionID/model are readonly context. Semantic options affect outgoing requests, not persisted messages. Raw HTTP body overlays apply **after** protocol lowering and may override semantic settings; hook registration order matters; title/generate are separate paths.
- Same documentation describes retry input `{sessionID, agent: string, model, error: {type, message, status?}, attempt}` and decision `{retry:false}` or `{retry:true, delay:number}`. [Effect documentation](https://github.com/anomalyco/opencode/blob/v2.1.2/services/www/src/docs/content/build/plugins/effect.mdx) numbers initial request attempt 1, first retry 2; the hook overrides a proposed retry decision.
- [Provider settings](https://github.com/anomalyco/opencode/blob/v2.1.2/services/www/src/docs/content/providers.mdx): `headerTimeout` and `chunkTimeout` in milliseconds/false; `timeout` is whole-request, with no default. These are provider-wide, not model-specific. Documented defaults are 5-minute HTTP header/chunk and 30-minute WebSocket chunk. Chunk timeout is **not** a wall deadline.

**Installed reconciliation:** OpenCode is 2.1.4; the OTel 2.0.1 runtime dist confirms context-hook usage, not semantic cap behavior. Worker `agentgateway/worker` uses standard `openai-compatible`, **not** `/responses`; `limit.output` remains 32,000. Prior blanket Responses requirements are corrected: worker's actual standard-provider lowering is the required path; architect/spade Responses are optional nonworker-isolation coverage, not a worker prerequisite. Pinned documentation plus current read-only route evidence predict `max_completion_tokens` without a compatibility override; the compatibility path can use `max_tokens`. Neither is outgoing-wire proof. Legacy `@opencode-ai/plugin` 1.15.13 cannot decide v2 API compatibility.

Task 4A's pinned-document/context-fixture portion is delivered; its real lowered-request and retry/abort boundary gaps remain. A compiled binary or absent Bun does not prove verification impossible. Context-hook agent shape, executable lowering/overlay behavior and actual retry/abort semantics remain unverified; task/session interrupt shape is documented, not abort-tested. “Three timeout retries” is unconfirmed; distinguish attempts from retries. No invented timeout flags, replacement watchdog/fork architecture or provider-wide timeout changes to hide these gaps.

## Common validation and small baseline

**Owner:** worker; orchestrator approves smoke envelope and retains concise results. Use one evidence artifact, `.config/dotfiles/docs/plans/2026-11-02-dotfiles-pr-trace-evidence.md`; sections by phase/task, no universal receipt service.

Use the SAME fixed scenario definitions before/after each affected phase:

1. Small simple edit with a known offline assertion.
2. Reproducible failing-test debugging with a known injected cause and passing target.
3. Relevant reviewer finding fixed once, then unchanged-revision handoff with no duplicate review; change a dependency/environment input to prove validation invalidation.
4. Publication dry-run: expected state succeeds, wrong root/head/destination or unauthorized operation stops; **no push**.

Keep offline deterministic fixtures separate from model smoke. The four definitions in `.config/dotfiles/tests/fixtures/opencode_workflow/scenarios.json` and 11 tests in `tests/test_opencode_workflow_scenarios.py` are already delivered; reuse rather than recreate them. Existing focused contracts are in `tests/test_git_workflow_contracts.py` and wrapper tests in `tests/test_sandbox_git.py`; `tests/test_worker_budget_contracts.py` is now created for the inactive context fixture's mock evidence, not outgoing lowering proof. Python scenario/phrase checks do not prove hook behavior or model adherence; mapped executable hook/lowering tests and later separately approved smoke provide distinct evidence.

**Future initial smoke authorization request:** keep the worker alias/model fixed; approve the fixed scenarios and at most one baseline and one 8,000 arm per scenario (eight scenario runs). Enumerate and approve any auxiliary reviewer calls separately within the same aggregate ceiling; do not switch implementation models. No replacement/continuation after a budget stop. Before starting, specify numeric aggregate token/monetary ceiling, per-run and whole-envelope wall deadlines, maximum actual HTTP attempts derived from installed policy, and a safe supported cancellation mechanism. No call is authorized until these numbers/mechanisms are approved. Read-only discovery supplies feasibility; bounded baseline results inform candidate numeric production deadlines. Additional 4,000/12,000 arms require a second explicit finite envelope, not automatic escalation. Include any reviewer/model calls in the approved aggregate ceiling. If safe bounded cancellation is unavailable, stop at offline capability evidence rather than starting unbounded calls.

Record success/completed acceptance, successful/failed tool calls, first **useful** tool latency, actual request attempts, finish reasons, input/output/available cache counters, total elapsed and total tokens per **completed task**, including failed attempts/rework. Report stopped/incomplete tasks separately so survivorship cannot hide cost. A smaller cap does not win if retries, continuations, rework or completion losses erase savings. Do not change tasks/model between arms.

Offline validation from `/Users/kpiwko`: `uv run --offline --no-sync --project /Users/kpiwko/.config/dotfiles --group test pytest /Users/kpiwko/.config/dotfiles/tests/test_git_workflow_contracts.py /Users/kpiwko/.config/dotfiles/tests/test_opencode_workflow_scenarios.py /Users/kpiwko/.config/dotfiles/tests/test_worker_budget_contracts.py /Users/kpiwko/.config/dotfiles/tests/test_sandbox_git.py`. Latest parent-reported result: **203 passed, 0 skipped**. This planner did not rerun it. Use existing installed dependencies only. For future code changes observe a failing regression then passing focused checks; record skips separately. No model call is an offline test.

## Review focus

1. Pre-tool latency, length-as-normal-finish, retry hooks and continuation are different paths: Task 4 tests each.
2. Worker-only hooks must not affect other agents/title/generate/provider clients: Task 4 tests exact agent matching and outgoing lowered body.
3. Snapshot identity includes relevant working tree, index and allowed untracked files: Task 2 tests changes to each plus dependency/environment invalidation.
4. Git instructions alone are not hard enforcement, and stale refs are not current remote truth: Task 3 adds deterministic supported checks and freshness tests.
5. Root grouping, partial counts and derived outcomes must not fabricate source facts: Task 5 tests synthetic nested/interrupted/length/steps/unknown cases.

## Phase 1 — Diagnose and bound the experiment surface

Ships independently: bounded evidence, installed capability map, fixed baseline definitions and the narrow debugging permission. No telemetry repair required.

### Task 0 — Bounded preparation review evidence

**Owner:** worker for native reads; planner may summarize supplied results. **Files:** evidence artifact and existing preparation plan. **Git scope:** none, analysis only.

- [ ] Read the two supplied root/child sessions and at most four explicitly linked sessions, capped at six bounded reads before checkpoint. Locate preparation/review evidence by explicit references or bounded experiment-23 search over timestamps learned there; no HOME/session sweep.
- [ ] Record actual reviewer invocations, relevant immutable content identity where available, triggers, findings/closure and validated inputs. Separate work performed, validated and reviewed. If unavailable, record checked IDs/ranges and retain “unresolved.” Do not investigate manual publication/authorization or reproduce resolved PR accounting.

**Acceptance:** Quantified preparation review loop or reproducible bounded evidence gap; spacing-origin gap remains visible until Task 5. **Rollback:** Diagnostic notes only; correct/remove unsupported claims without touching runtime/history.

### Task 4A — Installed controls and offline capability tests (Task 4, discovery portion)

**Status: PARTIAL, not complete.** **Owner:** worker. **Read:** existing evidence, `.config/opencode/opencode.jsonc`, `agents/worker.md`, named installed entry points and official version-pinned source/docs only. **Git scope:** none. Read-only HTTP and bounded offline tests/source fixtures are permitted in a new assignment; no dependency acquisition/install, cache patch, active plugin registration, model call or production cap.

- [x] Record installed versions/provider and a partial four-control matrix in evidence. Four scenario definitions and 11 fixture tests delivered. Native cap/abort behavior remains unverified; fixture tests do not prove it. `tests/test_worker_budget_contracts.py` **has now been created** for the 10-test inactive context-fixture mock harness.

**4A.1 narrowed offline deliverable complete; broader worker-path proof partial.** The earlier wider proof steps below retain their unresolved boundaries rather than falsely crediting mock context tests with lowering/runtime proof. Do not redo closed source/context-fixture review.

- [x] Deliver pinned official 2.1.4 docs/README; versioned references include `https://github.com/anomalyco/opencode/tree/v2.1.4` and `https://github.com/anomalyco/opencode/blob/v2.1.4/services/www/src/docs/content/build/plugins/index.mdx`, `https://github.com/anomalyco/opencode/blob/v2.1.4/services/www/src/docs/content/build/plugins/effect.mdx`, `https://github.com/anomalyco/opencode/blob/v2.1.4/services/www/src/docs/content/providers.mdx`. Context-only prototype review closed; source-expected cap field is not wire evidence.
- [ ] Complete executable boundary mapping for actual context-hook agent shape, semantic `maxTokens` consumption through standard-compatible lowering, later overlay behavior and supported runtime registration/order. Read-only API ID/model observations and source/documentation are recorded; do not claim all boundaries executed or use the legacy SDK as a substitute.
- [x] Create `tests/test_worker_budget_contracts.py` and inactive context-only `worker_budget.ts` with a 10-test mock harness. Remove invented `http.request`, lowering, retry and default implementations during review closure. No fabricated lowering implementation to assert the desired result; no Bun installation or cache patch.
- [x] Test semantic 8,000 cap, lower-limit preservation and exact agent/provider/model isolation at the mock context boundary. No persisted-message mutation or active registration. Tests do **not** prove final lowered outgoing request, real hook identity shape or runtime enforcement.
- [ ] Verify actual HTTP abort, retry count/numbering and length-versus-retry/continuation boundaries. Documented `ctx.session.interrupt({sessionID, resume:false})` is known; distinguish API shape from actual cancellation and from a whole-task deadline scheduler. Retain the four-control matrix and do not invent a watchdog/fork to conceal gaps.
- [x] Run focused offline tests and record review closure/evidence for the delivered context-only fixture. Historical 63-pass receipt, subsequent 88-pass Task 2 receipt, latest four-file **203 passed / 0 skipped** receipt are parent-reported; none imply wire proof or live activation.

**Acceptance of 4A.1:** Narrowed context-fixture/docs deliverable is complete and reviewed; actual worker lowering/abort boundaries remain explicit gaps in partial Task 4A. No live-server behavior claim from mocks. No smoke may bypass the still-unset finite ceiling/safe-cancel gate. **Rollback:** No live changes; preserve evidence and existing Task 1 edits. Any task-owned offline fixture removal requires explicit scope. No production numeric budget adoption.

### Task 1 — Exact debugging skill allow

**Owner:** worker. **Files:** `.config/opencode/agents/worker.md` permission block/Workflow; `tests/test_git_workflow_contracts.py`; evidence. **Git scope:** edits/offline tests only.

- [x] Confirm exact ID `systematic-debugging` via running `GET /api/skill` and installed superpowers `8ca22db`; no skill install/copy. Existing-session visibility corroborated, not a fresh-worker load.
- [x] Add ordered permission regressions for wildcard deny, exact debugging allow, existing init/publish allows, unrelated skills/subagents denied, reorder/widening mutations and exact allowed skill set. Task 1 historical combined validation **53 passed**, including 11 scenario tests and six skill-boundary tests; see evidence for red/green details.
- [x] Add only the exact allow, conditional concrete-failure workflow and cross-reference boundary: references do not expand permissions; denied/unexposed steps return a blocker. Shell/model/steps/publication rules unchanged. Single reviewer pass **PASS**, closure complete; no second review requested.
- [ ] Under the later approved smoke envelope, prove a fresh worker can discover/load intended skills while an unrelated workflow remains denied. Debugging scenario verifies behavior; static tests are not enough.

**Phase 1 exit:** Bounded gaps documented, installed controls mapped, offline tests pass, and exact permission change independently reviewable; live discovery/load proof may await Phase 2's approved envelope. **Rollback:** Restore only Task 1's specific allow/workflow edit if fresh-session discovery or isolation fails; do not roll back unrelated user configuration. No restart/publication implied.

## Phase 2 — Stabilize execution, then coordination

### Task 4B — Worker-only budget canary (Task 4, experiment portion)

**Owner:** worker; orchestrator owns authorization/numeric choices. **Files:** confirmed Task 4A local integration, `tests/test_worker_budget_contracts.py`, scenario fixtures, evidence; `opencode.jsonc` only if verified registration needs it and separately approved. **Git scope:** edits/offline tests only; smoke requires the explicit common envelope.

- [ ] Implement the minimal worker-only outgoing semantic cap arm **8,000**; keep **4,000** and **12,000** as subsequent experimental arms on the SAME tasks, not adopted production settings. Test final request body after the worker's actual standard `openai-compatible` lowering and raw-body overlays; the final field is determined by Task 4A.1, not assumed. Responses is optional nonworker coverage. Cap changes must not rewrite persisted messages or leak to other agents/providers.
- [ ] Implement only installed-supported cancellation/deadline controls selected in Task 4A and approved for the canary. Keep four budgets distinct. Numeric deadlines must be chosen after the bounded baseline, not invented now. If native whole-task/progress cancellation is unsupported, report that gap and do not claim an instruction enforces it.
- [ ] Test deadline/aggregate-budget expiry returns a safe partial stop: completed edits/evidence, blocked operation, next action and uncertainty. It must not automatically retry, continue generation, resume a child or replace the worker. Preserve normal bounded transient-error retries **within remaining authorized budgets**. Retry hook handles proposed error/timeout retries only; separately test `finish_reason=length` and model/tool continuation, which may not invoke it.
- [ ] With explicit envelope approval, run baseline then 8,000 on the fixed scenarios; count actual network attempts, tool success and completed-task cost/elapsed including rework. Stop at the first budget breach without recursive retry. Request a separate envelope for 4,000/12,000 only if useful; no paid model switch.
- [ ] Present per-scenario before/after results and proposed production values or “no demonstrated benefit.” Adopt only after explicit decision; reducing output length alone is not acceptance.

**Acceptance:** Worker isolation and final outgoing cap proven; safe no-replacement stop demonstrated; completion rate/total completed-task cost and latency support the choice, or no rollout. **Rollback:** Disable/remove only the confirmed worker budget registration/options and restore the prior worker behavior; preserve diagnostic receipts. Any restart/activation uses a separate approved gate.

### Task 2 — Three-tier coordination, not universal receipts

**Owner:** worker edits; orchestrator uses results; reviewer stays read-only. **Files:** `.config/opencode/agents/{worker,orchestrator,reviewer}.md`, `tests/test_git_workflow_contracts.py`, scenario fixtures/evidence. **Git scope:** edits/offline tests only.

**Status: offline complete, 88 passed / 0 skipped across three files, parent-reported.** Manual review T2-F1/F2 closed; T2-F3 helper/row corrected (`unclosed finding`: review=True, reuse=True) and orchestrator read confirmed. Digests retained in worker result. No additional review for this unchanged closure; runtime behavior remains unproved.

- [x] Implement/test three receipt tiers distinguishing performed/validated/reviewed work: lightweight small-change validation with review only when warranted; substantive exact snapshot/findings/validation/environment; publication full Task 3 envelope. No universal receipt engine.
- [x] Implement scoped index/worktree/allowlisted-untracked identity and dependency/environment-sensitive validation reuse; HEAD/branch alone insufficient; exclude unrelated HOME/secrets.
- [x] Implement immutable relevant-scope review identity and finding closure; unchanged content does not trigger duplicate review, reviewer stays read-only and does not rerun implementer tests.
- [x] Implement bounded worker entry/exit/checkpoint instructions and conditional concrete-failure debugging without new permission/model/steps authority.
- [x] Run focused offline static/fixture checks: **88 passed, 0 skipped**; this is not live coordination proof.
- [ ] Separately approved fixed smoke for actual duplicate-review/validation-reuse behavior remains pending; no live calls authorized by offline completion.

**Phase 2 exit:** An approved budget is beneficial or explicitly not adopted; tiered handoffs prevent the unchanged-snapshot duplicate in the fixed scenario and invalidate changed inputs. Telemetry repairs are not required. **Rollback:** Restore only phase-owned hook/contract edits if isolation, completion or coordination regresses; retain baseline/results and existing safety rules.

## Phase 3 — Preventive Git predictability

### Task 3 — Deterministic preflight / authorized execute / postflight

**Status: PARTIAL — Task 3A offline complete; broader snapshot/freshness/review gates and full publication protocol pending.** **Owner:** worker; orchestrator supplies separate operation scopes. **Files:** `.local/bin/sandbox-git` supported gates (`validate_publish`, `validate_push`, `publish`, `run_git` as applicable), `.config/dotfiles/tests/test_sandbox_git.py`, `.config/opencode/skills/publish-change/SKILL.md`, `agents/orchestrator.md`, contract tests. **Git scope:** source edits and offline synthetic checks only; any live Git inspection requires a separate read-only worker assignment. No fetch, commit or publication.

- [ ] Complete broader envelope beyond 3A: relevant index/worktree/allowlisted-untracked snapshot, base remote/ref/OID/freshness, review target, ordered base-relative commits/paths and validation/review identity. 3A implements root/HEAD/branch/upstream/destination/push-URL expectations only. Small-change handoffs need not carry the full envelope.
- [ ] Complete executable synthetic coverage for changed index/worktree/new allowlisted file, stale/unknown base freshness and review/validation input gates. A last-known ref stays labelled last-known without an authorized remote read; remote read does not synchronize refs, and fetch requires separate synchronization authority. Existing default-branch fallback remains potentially networked.
- [x] Deliver the 3A opt-in mechanical comparison/recheck boundary below; not the broader envelope or universal authorization enforcement.
- [ ] Extend skill/delegation text to require full publication envelope and partial receipt on interruption. Postflight must distinguish local commit, remote ref update and hosting review receipt; no PR inferred from status/tool success. No automatic cherry-pick/rebase/rename/amend/force/repair. Normal push and review creation remain separate authorization gates.
- [x] Complete 3A focused offline wrapper tests and unchanged legacy tests; no actual publication. Full fixed-scenario publication protocol remains pending with the broader gates. Keep PR43/equal-tree pairs as resolved context, not an authorization investigation.

#### Task 3A — Opt-in publication expectation gate (offline COMPLETE)

**Architect decision: ADR REQUIRED: NO. Owner:** worker. **Execution root:** `/Users/kpiwko`, explicit `shell.workdir` every call. **Files:** `.local/bin/sandbox-git` and `.config/dotfiles/tests/test_sandbox_git.py`; existing synthetic helpers reused. Original source references supplied by architect: `git_base:30–49`, `default_branch:89–107`, `validate_publish:210–226`, `publish:229–236`, `validate_push:239–261`, dispatch `406–412`; symbols may have shifted. **Delivered scope:** implementation and offline mocked tests only; no actual HOME Git operations, publication, fetch, model calls, instruction/publication-protocol changes or independent preflight/postflight framework. Target dotfiles base remains origin/main; no push destination is authorized by this task.

**Input interface:** wrapper-prefix expectation options before `publish REMOTE` or the supported limited `push` form:

- `--expect-root ABS`
- `--expect-head FULL_OID`
- `--expect-branch NAME`
- `--expect-upstream REMOTE:refs/heads/NAME|none`
- `--expect-destination REMOTE:refs/heads/NAME`
- `--expect-push-url URL`
- Optional `--check-only` with the complete expectation set.

Any expectation option requires **all six** exactly once with valid, nonconflicting values. Unknown/malformed/partial/conflicting options fail closed. Guarded operations are publication only: no sync/start-branch or arbitrary Git flags. Support `publish REMOTE` and a narrow `push REMOTE` form with either no refspec or one explicit normal branch refspec `refs/heads/SOURCE:refs/heads/DESTINATION`; reject force/delete/tag/wildcard/multiple/unsupported guarded forms. Resolve the actual destination using existing publication/tracking behavior; never merely echo the expected value. Legacy unguarded calls remain compatible.

- [x] Deliver synthetic parser/comparison tests and canonical cwd/assigned-root comparison **before any Git invocation**; verify actual worktree root, full HEAD, branch, upstream including absence, resolved destination and exactly one effective push URL. Raw effective URLs are compared; output is redacted. Ambiguous/multiple URLs reject.
- [x] Enforce comparisons **before** existing potentially networked guards and **again immediately before** existing `execvp` publication. State drift fails without repair. Preserve protected/upstream guards, existing argv/exec behavior and nonzero results; add resolved-destination protected guard. Residual final-check-to-exec TOCTOU remains acknowledged, not an atomic transaction.
- [x] Deliver local-only `--check-only` observations/comparisons without mutation/network calls or `default_branch` network fallback. Output is not consent, remote freshness evidence or proof all execution guards passed. Existing execution fallback remains unchanged and requires separately authorized network scope if reached.
- [x] Cover wrong-root zero-Git, all expectation mismatches/absence, invalid/unsupported forms, check-only isolation, expected argv/guards, between-check drift and exec/nonzero propagation. Additional fail-closed widening checks cover mirror/followTags/pushOption/recurse/gpg configuration, canonical Git false/empty/bare boolean semantics and case-sensitive remote names. **24 legacy tests unchanged.** Mocks prevent real publication.
- [x] Final four-file focused offline suite **203 passed, 0 skipped**, parent-reported; see common command above and evidence through section 12. Manual review **PASS**, B1/B2/I1/I2/I3/N1/N2/N3 closed on exact wrapper SHA-256 `435ba85165999d46ae9a1aa82e6ab9e1f51ef20baeb5d5033df5ba8165f44644` and tests SHA-256 `eedd5d6bff2de0b1d262386e099292cc8c30ee21a39032a396020fa4438cea02`. Qodo unavailable; no follow-up review for unchanged scope.

**Acceptance (offline complete):** Deterministic opt-in checks reject mismatches before side effects, recheck before exec and preserve legacy/guard/exit behavior in synthetic tests. Passing flags is **not consent**; legacy unguarded invocation remains possible, so no universal bypass-prevention claim. Wrapper cannot prove review quality or intent. Postflight stays parent-owned: actual exit plus separately authorized local/remote/hosting receipts, not a fabricated wrapper receipt. **Rollback:** Restore only Task 3A additions if supported legacy behavior regresses; retain existing safety guards.

**Task 3 remains partial after 3A:** scoped snapshot/index/untracked, base freshness and review/validation-input gates plus full publication instructions remain separate unfinished work. Do not claim the full earlier envelope implemented by these six expectations. No history repair or authorization investigation is added.

**Phase 3 acceptance:** Deterministic supported checks reject mismatches with no side effect, dry-run expected path passes, and unknown freshness stays explicit. This is preventive engineering, not a proven incident failure. **Rollback:** Restore only new wrapper/contract gates if they reject valid supported workflows; retain existing protected/destructive-operation safeguards. No actual push or history mutation for acceptance.

## Phase 4 — Trace reliability at the first proven bad boundary

### Task 5 — Native/export attribution and source-specific fixes

**Owner:** worker diagnoses; planner scopes any external-source implementation; architect only for a significant unresolved ownership decision. **Files:** evidence, `.config/opencode/README.md` measured limitations; inspect installed native/plugin source mapped by Task 4A and `.local/bin/mlflow-traces:build_time_filter` only as the existing metadata consumer. **Git scope:** none for diagnosis; external implementation and activation require their own scoped plan/approval.

- [ ] Under a separately approved finite canary envelope, compare nonsecret text with spaces/newlines/punctuation and commit-shaped IDs at native persisted delegation args, native child input and exported telemetry. Record byte lengths/digests and escaped relevant excerpt; missing stages remain unknown. Fix the **first proven bad boundary**, not downstream display fabrication. Preserve unresolved malformed-spacing evidence until attribution succeeds.
- [ ] Map exact installed version/path/symbol ownership for session grouping, child association, output, usage, outcomes and exposed summaries. Root session grouping stays distinct from child associations; keep nested parallel tool/LLM spans intact. Root-session filtering should find the trace without inventing child/root identity in the downloader.
- [ ] Define executable synthetic source fixtures: normal completion, interrupted request, `length`, step exhaustion, parallel children, duplicated rollup identity, partial tokens and unavailable summaries. Retain raw span status/finish reasons; compute a separately labelled task outcome so OK does not erase interruption, nor every length stop imply failed task completion.
- [ ] Separate root/direct usage from descendant totals; sum unique LLM invocation identities once, never parent summary plus descendants. Follow provider cache/reasoning counter semantics to prevent double count. Distinguish unknown/partial from measured zero; visible 32,000 and 1,254 completions retain actual span identities rather than being conflated with metadata 759. Reasoning availability is `available`, `not_exposed`, `not_captured` or `unknown`; only permitted provider-exposed persisted summaries may populate text.
- [ ] For a proven defect, produce the smallest source-specific implementation/fix plan with actual repository/root/base/files/tests and release/activation rollback; upstream fixed release versus owned fork remains a separate decision. No npm-cache patch, Collector I/O invention, private reasoning capture, cost-policy change or retroactive backfill. Update README only to measured behavior/limitations, not planned functionality.

**Phase 4 acceptance:** First divergent boundary identified or an explicit inaccessible-stage blocker; owned source fixes pass synthetic regressions and approved end-to-end canary before claims of improvement. **Rollback:** Revert only approved source-version/registration changes via the planned activation mechanism; restore prior runtime version if needed, keep raw evidence, never rewrite historical facts.

## Minimal measurement, decisions and self-review

Keep per-scenario raw rows initially; no dashboard. Track five primary measures: (1) P50/P95 first useful tool latency **only once sample counts justify percentile claims**, otherwise individual observations; (2) length-terminated generation counts/rate; (3) reviews per UNIQUE immutable relevant-scope revision; (4) reused versus invalidated validations with reasons; (5) derived task outcome versus raw root status. Also retain actual attempts/retries and total task duration/tokens/completion. Report sample counts, incomplete tasks and uncertainty.

Required future decisions: safe finite-envelope feasibility, then explicit smoke token/time/attempt and applicable cost ceiling; prices need not be investigated before feasibility. No 80-minute smoke or other experiment is authorized now. Production deadlines/cap await approved baseline/arms. Task 3A's expectation interface and offline implementation are complete (ADR NO); broader snapshot/freshness/review-input gates and later upstream/fork ownership remain future work. Read-only agent identity/route evidence and documented `ctx.session.interrupt({sessionID, resume:false})` are recorded above; actual HTTP abort, length continuation, maximum retry count and hook/runtime integration remain unverified. Manual publication authorization is **not** an open issue.

Optional later work only: capability-gated workdir boundary enforcement that is worker- AND assignment-root-aware across projects; never hardcode HOME for all agents/projects or mutate commands to conceal wrong-root intent. No additional skill permissions, agents, generalized receipt framework or dashboard is required.

Self-review: This status-only revision records completed Task 2 and Task 3A offline implementation/review, latest 203-pass receipt, and created budget tests without crediting them with wire/live proof. Stable IDs and remaining gates preserved; broad Task 3 and Task 4A remain partial, Task 0/4B/5 not started. Prior reported code changes are not described as planning-only; this planner changed only the plan and ran no tests, shell/Git commands, config/runtime edits, experiments or publication. Next recommended bounded unit is Task 4A's remaining source-backed offline lowering/abort feasibility boundary, with no activation/model calls; return a precise inaccessible-boundary blocker rather than fabricate runtime proof or begin a broad architecture change.
