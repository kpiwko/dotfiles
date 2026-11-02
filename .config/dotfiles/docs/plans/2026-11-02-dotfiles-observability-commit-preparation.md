# Dotfiles Observability Commit Preparation Implementation Plan

> **For agentic workers:** Execution handoff via `subagent-driven-development` or `executing-plans` is advisory; the parent orchestrator owns sequencing and delegation. This planning subtask authorizes only this plan-file write, not implementation, tests, or Git mutations.

**Goal:** Prepare tested, logically scoped LOCAL commits for the existing observability and devcluster changes without publishing or sweeping unrelated dirty files into them.

**Architecture:** Preserve the existing OpenCode → Collector → MLflow pipeline and secret-sourced AgentGateway routing. Package existing changes into three code/test commits and one final documentation commit; stage whole allowlisted files, not intertwined README hunks.

**Tech stack:** POSIX shell, JSON configuration, Kubernetes/Collector OTTL, Python >=3.12, pytest >=9,<10, existing uv tooling.

**Spec:** Parent assignment and bounded review update dated 2026-11-02. The Oct 26 investigation/remediation plan and evidence ledger are local-only historical context, deliberately omitted from these commits; this contract and the required READMEs must stand alone without them. Historical context grants no renewed runtime permissions.

## Global constraints and Git contract

- Repository: dotfiles, remote `origin = git@github.com:kpiwko/dotfiles.git`; execution root **`/Users/kpiwko`** for every shell/Git invocation. Test commands below use a subshell changing to `.config/dotfiles` only to select the existing project configuration.
- Every Git operation uses **`sandbox-git` from exactly `/Users/kpiwko`**; no raw Git, bare-repository inspection, new worktree, or branch rename.
- Parent-provided snapshot, not freshly verified by planner: branch `sol-orchestrator`, HEAD `24646ec`, upstream **`origin/sol-orchestartor`** (intentional preservation of existing spelling); upstream synchronized. Base/review target `origin/main` at `aaf353d`, ancestor of HEAD, 2 ahead / 0 behind, with preexisting commits `96bab69`, `24646ec`.
- Keep both existing commits unchanged; append local commits only. Prospective push destination is the EXISTING `origin/sol-orchestartor`, not a newly invented remote branch. Prospective PR base is `origin/main`.
- Scope separation: Task 0/final audit = analysis/read-only Git; Tasks 1–4 = explicit-path staging and new local commits only. No local branch synchronization, fetch, merge, rebase, amend, reset, rewrite, push, deletion, PR/MR creation, or merge authority. Any publication (including force push) requires a new explicit user gate; nothing here requests publication.
- Parent authorization covers tests and logical local commits, not deployment, service restart, real model calls, production DB writes/backfill, package upgrades, or cache patches. Do not run `devcluster up` or provisioning commands as validation.
- `.config/dotfiles/docs/adr/` does not exist on inspection; no accepted ADR was found there. Follow `.config/opencode/AGENTS.md`, current manifests, `pyproject.toml`, and Makefile conventions; introduce no architectural refactor or dependencies.
- Preserve unrelated state exactly. Never bulk-stage, clean, delete, overwrite, or stash dirty work to obtain an artificially clean tree. Respect an existing index: if already staged content belongs to another worker, coordinate before committing.

## Parent-reported execution checkpoint — before Task 4

- [x] Task 0 envelope/inventory review completed; branch `sol-orchestrator` preserved and exclusions retained.
- [x] Task 1 completed: `b88b44679c02fb7624b6d55e7a76fb983f141b12`, `fix(telemetry): route OpenCode traces to experiment 23`; exactly 3 allowlisted files; targeted **8 passed**.
- [x] Task 2 completed: `18027b9`, `fix(otel): preserve canonical span types for MLflow indexing`; exactly 4 allowlisted files; targeted **32 passed, 7 skipped**.
- [x] Task 3 completed: `e6bc238066b03d3e877f40def4d18bb50495bdd7`, `fix(devcluster): start stopped Lima before deployment`; exactly 2 allowlisted files; shell syntax **PASS**, targeted **17 passed**.
- [x] Targeted re-review **PASS**: all findings resolved, including verification of the network-create ownership label in the actual argument vector and its new regression.
- [x] Latest full suite recorded: **151 passed, 7 skipped, 65.06 s**; compatibility module **14 static passes, 7 behavioral skips**. Results and commits are parent-reported, not planner executions. No behavioral rerun this pass.
- [ ] Task 4 documentation commit remains pending, including this plan.
- [ ] Final aggregate audit and handoff remain pending. **Not pushed; no PR created.**

The Task 0–3 instructions below remain the executed contract, not requests to repeat completed work. Their completion results are recorded above; Task 4 and final audit checkboxes remain open until the parent completes them.

## Review focus

1. Missing experiment header must not silently acquire a Collector fallback; Task 2 retains the no-default regression.
2. Existing canonical span types (including empty/non-string values) must win; unsupported/missing/non-string/JSON-quoted kinds stay unmapped; Task 2 checks the synthetic fixture and guarded rules.
3. Stopped/running/missing/start-failed Lima instances must preserve safe operation ordering; Task 3 checks four stubbed lifecycle regressions.
4. Source configuration and offline tests do not prove current runtime routing, wire propagation, persistence, or root-output repair; Task 4 labels causal limits and historical findings.
5. Historical evidence can expose credentials, prompts, private endpoints, or local paths; omit both Oct 26 documents entirely and preserve them untouched. Task 4 reviews only required documentation for safe, self-contained claims; final audit checks exact commit contents.

## Task 0 — Confirm the local commit envelope

**Git permission:** Read-only analysis; **no Git changes**. **Files:** only the allowlists below and exclusion inventory.

- [ ] Using read-only `sandbox-git` inspection, confirm branch, HEAD, base ancestry, upstream spelling, current index, and bounded tracked/untracked inventory. Record any drift; do not repair it with synchronization/rewrite. Pause only if it changes ownership/scope or makes the commit contract unsafe.
- [ ] Review diffs against the parent inventory; whole-file staging below is allowed only if each file contains exclusively its named workstream. Unexpected edits require an explicit reviewed partition, not automatic inclusion.
- [ ] Preserve/exclude `.config/opencode/cli.json` (preexisting verbosity), `.config/zellij/config.kdl` (link plugin), ignored `.env` secrets, backups/state/service.json/notifier/tui.json files, skills, `__pycache__`, `.config/dotfiles/.superpowers/sdd`, `.config/dotfiles/docs/plans/2026-10-16-devel-directory-reorganization.md`, and raw audit/trace artifacts outside the approved config paths.
- [ ] Omit `.config/dotfiles/docs/plans/2026-10-26-opencode-mlflow-evidence.md` and `.config/dotfiles/docs/plans/2026-10-26-opencode-mlflow-investigation-remediation.md` entirely: parent decision is to preserve this large, unreviewed historical content uncommitted, without redaction work in this pass.
- [ ] Also exclude `.config/dotfiles/docs/plans/2026-10-22-git-workflow-mlflow-evaluation.md` (B3/Harbor PR42 history; separate workstream unless independently shown relevant), `.config/dotfiles/docs/plans/2026-10-14-mlflow-traces-compat-flag.md` (tool unchanged; unrelated by default), and `.config/dotfiles/uv.lock`. Current `pyproject.toml` declares only pytest in the test group; generation by uv alone is NOT a dependency change or evidence of tracked-lock policy. Preserve the lockfile uncommitted unless a separate policy/requirement is established; no need to block these commits on that investigation.

**Acceptance:** A bounded approved-file inventory and untouched unrelated work; no branch or index mutation in this task.

## Task 1 — Local commit: fixed experiment routing

**Suggested subject:** `fix(telemetry): route OpenCode traces to experiment 23`

**Exact file allowlist (HOME-relative):**
- `.config/opencode/opencode.jsonc`
- `.config/k8s/env.example`
- `.config/dotfiles/tests/test_ai_infrastructure_manifests.py`

**Interface/behavior:** Plugin `options.otlpHeaders = "x-mlflow-experiment-id=23"`; provisioning template `MLFLOW_EXPERIMENT_ID=23`. AgentGateway remains `$MLFLOW_EXPERIMENT_ID`/`agentgateway-secrets` sourced, not hardcoded in its manifest. Existing provider credentials/settings remain unchanged. No runtime activation.

- [ ] Review these existing changes and `test_telemetry_routes_to_fixed_experiment_23`; ensure the test checks plugin header, template, gateway expansion and secret boundary.
- [ ] Run from execution root: `(cd .config/dotfiles && uv run --group test pytest tests/test_ai_infrastructure_manifests.py)` using existing tooling; expected all pass. Rendering uses existing kubectl/kustomize/devcluster-kubectl in build-only mode, not cluster apply. If tooling/dependencies require acquisition, report the prerequisite rather than install implicitly.
- [ ] With **explicit-path staging + local commit permission only**, stage exactly the allowlist after diff/secret review and create one new commit. Verify its file list and patch contain routing only. Do not stage either README here.

**Acceptance:** One local routing commit with regression coverage; no claim that running emitters have adopted experiment 23.

## Task 2 — Local commit: guarded MLflow span-type compatibility

**Suggested subject:** `fix(otel): preserve canonical span types for MLflow indexing`

**Exact file allowlist:**
- `.config/k8s/base/otel-collector.yaml`
- `.config/dotfiles/tests/test_otel_collector_manifests.py`
- `.config/dotfiles/tests/test_mlflow_span_type_compatibility.py`
- `.config/dotfiles/tests/fixtures/opencode_telemetry/span_type_cases.json`

**Interface/behavior:** Collector `transform.trace_statements` copies `openinference.span.kind` into absent `mlflow.spanType` for exactly TOOL, CHAIN, LLM, RETRIEVER, EMBEDDING, AGENT, RERANKER, UNKNOWN, GUARDRAIL, EVALUATOR. Preserve canonical values, I/O/token/cost attributes and metadata-based routing; never synthesize UNKNOWN for other inputs. Keep Collector 0.123.0 and MLflow 3.17.0 assumptions explicit.

- [ ] Review `OPENINFERENCE_SPAN_KIND_ALLOWLIST`, `test_otel_collector_maps_openinference_span_types_without_overwrite`, `test_otel_collector_experiment_header_has_no_fallback_default`, and all synthetic guard/negative cases. Keep the routing-no-default test in this commit: it shares the test file and protects compatibility without fragile hunk staging.
- [ ] Run `(cd .config/dotfiles && uv run --group test pytest tests/test_otel_collector_manifests.py tests/test_mlflow_span_type_compatibility.py)` with `OTEL_SPAN_TYPE_BEHAVIORAL` unset. Parent reports the compatibility module now has **14 static passes (including 11 cleanup unit regressions), 7 behavioral skips**; manifest tests are additional. Check the cleanup regressions alongside mapping consistency. A skip is not behavioral proof.
- [ ] Review the updated harness contract statically: per-run UUID resource names/ownership labels, `tempfile.mkdtemp` scratch allocation, no deletion of an existing directory, and Podman `--pull=never`. Cleanup must be restricted to resources owned by that run. **No behavioral rerun this pass.** A future opt-in run needs separate parent runtime confirmation, existing pinned images/local Podman, no host ports, production traffic or broad cleanup; default offline execution is sufficient for this local-preparation contract.
- [ ] With **explicit-path staging + local commit permission only**, review the entire new test/fixture for synthetic-only content, stage exactly this allowlist, and create/inspect one commit. No evidence ledger or raw runtime exports belong in it.

**Acceptance:** One local compatibility commit containing manifest, static regression and synthetic opt-in harness, with no fallback routing or dependency changes; observed versus skipped checks recorded separately.

## Task 3 — Local commit: safe Lima autostart

**Suggested subject:** `fix(devcluster): start stopped Lima before deployment`

**Exact file allowlist:**
- `.local/bin/devcluster`
- `.config/dotfiles/tests/test_devcluster.py`

**Interface/behavior:** `ensure_cluster_running()` precedes kubeconfig/namespace/secret/manifest work in `cmd_up()`. Running instances are not restarted; stopped instances start before dependent operations; missing instances instruct `devcluster create`; start failure exits before dependent operations. Preserve migration/secret/runtime ordering.

- [ ] Review `test_up_starts_stopped_vm_before_dependent_operations`, `test_up_with_running_vm_does_not_restart_it`, `test_up_without_instance_directs_to_create`, and `test_up_start_failure_blocks_dependent_operations`, including the stub command log ordering and failure assertions.
- [ ] Run `sh -n .local/bin/devcluster` and `(cd .config/dotfiles && uv run --group test pytest tests/test_devcluster.py)`; expect syntax success and all stubbed lifecycle tests pass, without touching a real Lima instance.
- [ ] With **explicit-path staging + local commit permission only**, stage exactly these two files and create/inspect one commit; defer lifecycle README text to Task 4.

**Acceptance:** One local lifecycle commit, four edge cases covered, no real deployment/restart.

## Task 4 — Local commit: consolidated operator/process documentation

**Suggested subject:** `docs(observability): document routing compatibility and deferred fixes`

**Required exact file allowlist:**
- `.config/k8s/README.md`
- `.config/opencode/README.md`
- `.config/dotfiles/docs/plans/2026-11-02-dotfiles-observability-commit-preparation.md` (this contract)

**Resolved omission:** Both Oct 26 documents are excluded entirely; there are no conditional additions and no historical-ledger redaction task in this pass. Preserve them uncommitted.

- [ ] Review both READMEs as whole files. Make them self-contained: cover experiment 23 template versus effective secret/service configuration, guarded span types/removal criterion, and safe `devcluster up` lifecycle. Fix the k8s README's ambiguous “Ingestion behavior was verified against pinned Collector” wording: Collector export checks do not themselves prove MLflow SQL ingestion. State the compatibility behavior and test boundaries without depending on an external evidence claim.
- [ ] Keep root-output work explicitly deferred to upstream fixed release/owned fork; no npm-cache patch, new Collector I/O mapping, invented version, or claim of a local fix. Treat dated v2.0.1/upstream-main observations as dated observations, not a fresh latest-version check. User is following upstream tracking; creating issues is not authorized. Do not assert the specific Effect overwrite mechanism was proven: final outbound wire capture was not performed.
- [ ] Remove committed-link dependencies on the omitted Oct 26 documents. If retaining their names for orientation, use plain text explicitly marked **local-only historical notes, not included in these commits**, not repository links or required supporting evidence. Apply this rule to the required READMEs, this contract and new test documentation; validate the commit tree, not just files available in the dirty worktree. No dangling links or expansion into Oct 22 Harbor history.
- [ ] Run `(cd .config/dotfiles && uv run --group test pytest tests/test_ai_infrastructure_manifests.py tests/test_otel_collector_manifests.py)` for existing documentation/manifest assertions; manually verify self-contained, truthful causal/dated claims and links in the candidate commit tree.
- [ ] With **explicit-path staging + local commit permission only**, stage exactly the three required files after the review-closure gate below passes. Inspect staged content for secrets, whitespace and file ownership, then create/inspect the final docs commit. Whole README staging deliberately avoids intermingled-hunk fragility.

**Acceptance:** One local docs commit explaining all three code commits and deferred work, including this Nov 2 contract, without historical-ledger content, dangling evidence links or a stale hypothesis promoted to fact.

## Final verification and handoff

**Git permission:** Read-only analysis; no publication or history changes.

- [x] **Pre-commit review-closure gate: PASS, parent-reported targeted re-review complete; all findings resolved.** The final closure includes the network-create ownership label in the actual argument vector and a new regression asserting it. No behavioral rerun this pass.
- [x] Record the latest parent-reported full-suite result after review fixes: **151 passed, 7 skipped, 65.06 s**, with behavioral opt-in unset. The compatibility module reports **14 static passes + 7 behavioral skips**, including 11 cleanup unit regressions. These are parent/worker reports, not planner executions.
- [ ] During the still-pending final audit, determine whether required content changed after that test snapshot; if so, rerun relevant offline checks and `(cd .config/dotfiles && uv run --group test pytest)` as appropriate. Record commands, counts, duration and skip reasons without enabling behavioral runtime.
- [ ] Inspect each new commit's exact paths/patch and the aggregate diff against `origin/main`; verify the two preexisting commits remain unchanged. Review inherited branch content too: new clean commits do not certify old commits for publication.
- [ ] Verify only allowlisted changes were committed, the index has no newly stranded staged content, excluded work remains intact/uncommitted, branch/upstream are unchanged, and remote tracking refs were not advanced by publication. A dirty worktree is expected and acceptable.
- [ ] Return local commit IDs/subjects/file groups, test outcomes (including skips), omissions, residual dirty-work ownership, and any content-review blockers. State **not pushed; no PR created** and repeat prospective destination/base. Stop at this boundary.

## Decisions and self-review

No branch-typo clarification or new architecture decision is needed for LOCAL commits. Generated lockfile and unrelated historical plans remain excluded. Parent has resolved both Oct 26 documents to **OMIT entirely and preserve uncommitted**; no further historical review/redaction is requested. Root-output delivery ownership and proof of the specific propagation mechanism remain deferred technical decisions, not blockers to bounded local preparation. **The targeted re-review gate is PASS, all findings resolved (parent-reported). Tasks 0–3 are complete; Task 4 documentation commit and final audit remain pending.** Other blockers are unsafe required content, conflicting index ownership, unexpected relevant edits, or failing required tests.

Self-review: all named workstreams have concrete file allowlists, behavior and validation; shared test-file and README ownership are assigned once; UUID/label-owned cleanup, fresh scratch allocation, no existing-directory deletion and no-pull behavior replace the old harness description; latest parent test counts, completed review PASS and Task 0–3 commit results are explicit; Task 4 and final audit remain pending; both historical documents are omitted and required docs are self-contained; no behavioral rerun is requested. This bounded update changed only this Nov 2 plan; no implementation, tests, network actions, or Git operations were performed by this planner.
