# Agent-definition evaluation — operator guide

Focused, offline operator guide for the neutral two-arm **agent-definition**
evaluation in this project. Earlier worker-budget policy/observer/SSE research is
preserved historical material, not a prerequisite and not an acceptance gate for
this workflow — see the README's preserved-research section and
[`runner-compatibility.md`](runner-compatibility.md).

**Status: prepared tooling only. No candidate definition has been selected, no
live evaluation has been approved or run, and nothing here is efficacy
evidence.** Synthetic fixtures in the tests validate the tool; they are not
experiment results.

## What is measured

Four fixed cases from `cases/worker-budget-v1/`: `small-edit`,
`failing-test-debug`, `reviewer-unchanged-handoff`, `publication-dry-run`.

- Scoring is deterministic final state only, through
  `agent_workflow_checks.judge_scenario` over the collected case record. Each
  case is `pass`, `fail` or `unscorable`.
- `unscorable` means malformed/unusable metadata; `fail` means a validly observed
  wrong end state. The boolean judge is true only for `pass`.
- Procedure coverage is `not_measured`. Delegations, reviews, reuse, retries,
  attempts and length stops are null and can never be inferred from events or
  prose in this milestone.
- No model judge, no rubric, no efficacy or ranking claim.

**Trust boundary of outcome scoring — this is not a sandbox.** To compare an end
state, `agent_workflow_checks` imports and executes the case's fixture Python
modules **in-process**, because the deterministic checks call those helpers
directly. The fixture bytes are the trusted local seeds under
`cases/worker-budget-v1/` (plus any overlay bytes a collected record substitutes
for them), so a broken, hostile or looping fixture runs with the scorer's own
privileges: it can read or write local files, consume CPU indefinitely, or
terminate the interpreter. Contained per-call errors become `fail`/`unscorable`,
and `KeyboardInterrupt` is deliberately not swallowed so operator cancellation
still propagates — but nothing else limits a fixture. Treat the dataset and saved
records as trusted local artifacts and never point scoring at an untrusted case
directory. No model, provider or network call is made and no subprocess is
launched, yet this is **not** a pure non-executing parser and **not** runtime
isolation or a hostile-artifact boundary.

Project root (`P`) for every command below:
`/Users/kpiwko/.config/dotfiles/evals/agent-workflows`. Pinned interpreter:

```text
/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python
```

The pinned harness checkout (1.57.1 /
`b041d5a6db0b1181d51d95190faf8f2c0808c38d`) and its SDK are supplied externally
(override with `AGENT_WORKFLOWS_HARNESS`). Nothing here installs or updates them,
and no credentials are required or stored. The checked-in snapshot config
references credentials only as `{env:…}` names.

## Prepare two source-defined arms (offline)

Both sources are explicit six-role agent directories
(`orchestrator.md`, `worker.md`, `reviewer.md`, `architect.md`, `planner.md`,
`zweistein.md`). There is no implicit product candidate; identical source
directories are refused.

```bash
/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  /Users/kpiwko/.config/dotfiles/evals/agent-workflows/agent_definition_eval.py prepare \
  --baseline-source /absolute/path/to/baseline-agents \
  --candidate-source /absolute/path/to/candidate-agents \
  --out /Users/kpiwko/.config/dotfiles/evals/agent-workflows/runs/<new-experiment-dir>
```

`runs/` is git-ignored. `prepare` validates and hashes the whole input set before
writing, refuses a nonempty `--out`, and never invokes a model, network endpoint
or subprocess. It prints the experiment path, arm snapshot ids and dataset hash;
the same inputs produce byte-identical files.

The generated arm configs embed **absolute paths** to the prepared experiment
directory (dataset, per-arm snapshot staging sources and `runner.plugin_dirs`).
A prepared experiment is therefore **not relocatable**: moving or copying `<out>`
makes `compare` fail closed with a linkage error rather than silently reading the
old location. Prepare once at the final location you intend to run and compare
from; do not prepare in one place and expect to run or compare it from another.

Output layout:

```text
<out>/experiment.json                          # schema_version 1; no timestamp, no absolute path
<out>/dataset/<case-id>/...                    # prepared four-case copy (no bootstrap/)
<out>/baseline/eval.agent-definition.yaml      # generated neutral config, explicit absolute paths
<out>/baseline/snapshot/manifest.json
<out>/baseline/snapshot/opencode.jsonc
<out>/baseline/snapshot/agents/*.md
<out>/candidate/eval.agent-definition.yaml
<out>/candidate/snapshot/...
```

- `experiment.json` records per arm the snapshot id, relative manifest/config
  paths, generated config hash and normalized non-arm hash; plus dataset case ids
  and content hash and pinned harness/runtime/model/argv/judge metadata.
- The dataset content hash covers case metadata (`input.yaml`,
  `annotations.yaml`) and seed bytes and excludes `bootstrap/`, `__pycache__`,
  `*.pyc` and `.git`. Because the pinned runner enumerates every subdirectory as
  a case, the prepared copy is what limits the run to exactly four cases; the
  trusted dataset is never modified or used as the run dataset.
- Both generated configs must share the same normalized non-arm hash; only the
  snapshot source root and dataset path differ.

### Snapshots and manifests

Snapshots are model-only rewrites: exactly one frontmatter `model:` line per role
becomes `agentgateway/illusionist`, and every other byte — tool/shell/skill/
subagent permission order included — is preserved. `manifest.json`
(`schema_version: 1`) contains the model, ordered roles, per-role source hashes
and generated file hashes; `snapshot_id` is the canonical SHA-256 of that
identity, with no timestamp, absolute source path, credential or machine Git
state. `verify_snapshot` detects tampering and stale manifest/content mismatch.

The checked-in `eval-snapshot/` is the reference snapshot, generated by
`eval-snapshot/build_snapshot.py` from the current native role agents with
`--source`/`--dest`. `prepare` never silently regenerates it.

### Generated config and honest limits

The checked-in `eval.agent-definition.yaml` is the neutral template: no budget
policy, arm bootstrap, observer/SSE staging or external `~/.config/opencode`
source-root allowance. The pinned runner argv is a literal constant
(`/usr/bin/env -u PWD opencode run --standalone --agent orchestrator --model
agentgateway/illusionist --format json {args}`); `--auto`, `--pure` and templated
model selection are deliberately absent. `runner.permission_mode` is ignored by
the CLI runner, so ordered permissions come only from the staged config/agents.

The all-illusionist stack is a **configuration property, not runtime isolation or
enforcement**: OpenCode merges the user's global config underneath a project
config, extra provider aliases may exist in the effective catalog, and
provider-private routing behind the gateway is not observable. No global-plugin,
global-config or budget-enforcement guarantee is claimed, and no
`execution.max_budget_usd` is configured here — a finite cost/time envelope is a
separate run-approval gate. Where any config does declare
`execution.max_budget_usd`, treat it as **advisory/substitution only**, never as
enforced spend control.

## Future run: provenance to save (NOT AUTHORIZED / NOT RUN)

A live run is a separately approved, finite envelope. This guide provides no
live launch command and nothing below was executed. When such a run is approved,
the pinned harness CLI runner uses the **generated** arm config from the prepared
experiment, and the run directory must keep that identity:

```text
<run>/harness/run_result.json                        # per-case exit status and elapsed
<run>/harness/cases/<case>/...                       # per-case harness artifacts (diagnostic)
<run>/collected/cases/<case>/...                     # collected case record (needed for an outcome)
<run>/provenance/run.json                            # saved linkage metadata
<run>/provenance/manifest.json                       # byte copy of that arm's prepared manifest
<run>/provenance/eval.agent-definition.yaml          # byte copy of that arm's generated config
```

Save provenance from the prepared experiment, unedited: copy
`<out>/<arm>/snapshot/manifest.json` to `provenance/manifest.json`, copy
`<out>/<arm>/eval.agent-definition.yaml` to
`provenance/eval.agent-definition.yaml`, and write `provenance/run.json` with
`schema_version: 1`, `arm`, `snapshot_id`, `config_sha256`, `nonarm_sha256`,
`dataset_content_sha256`, `case_ids` and `model`, taken from `experiment.json`.
`compare` verifies the saved bytes against the prepared arm; never edit them to
fit a result. Historical runs that lack these files stay diagnostic and never
gain retroactive provenance — do not manufacture provenance for old runs.

## Compare saved runs (offline)

```bash
/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  /Users/kpiwko/.config/dotfiles/evals/agent-workflows/agent_definition_eval.py compare \
  --experiment /absolute/path/to/experiment.json \
  --baseline-run /absolute/path/to/baseline-run \
  --candidate-run /absolute/path/to/candidate-run \
  --out /Users/kpiwko/.config/dotfiles/evals/agent-workflows/runs/<new-comparison-dir>
```

`compare` reads only saved artifacts, refuses a nonempty `--out`, and never
launches a model, agent or subprocess. It writes deterministic `comparison.json`
and readable `comparison.md`.

Eligibility state (anything other than `verified_comparable` suppresses paired
deltas and any efficacy interpretation):

- `verified_comparable` — saved provenance matches the prepared arm snapshot,
  config, dataset and case ids.
- `unverified` — required provenance is missing or mismatched, or the run records
  no harness model identity; outcomes may still be diagnostic.
- `incomparable` — controlled inputs differ between arms.
- `same_content_smoke_only` — both arms produced identical generated snapshot
  bytes, even if pre-rewrite sources (and snapshot ids) differed.

The `harness/run_result.json` `model` is the **harness-recorded/configured model
identity, not runtime attestation** of which model actually served a request; the
tool can only check what the harness saved. An absent record makes that arm
`unverified`; a recorded value that differs from the pinned model makes the pair
`incomparable`. A saved `provenance/run.json` `model` is a self-assertion and
never outweighs the harness record. No runtime model-enforcement or
identity-attestation guarantee is claimed anywhere in this workflow.

Per case the report includes `outcome` (`pass|fail|unscorable`), `execution`
(`completed|failed|unknown`), reasons, elapsed seconds and any measured
`token_usage`/`cost_usd`/`num_turns`, with availability and source. `completed`
requires exit code 0 **and** a passing end state, so a passing edit from a
failed or timed-out process is not completed. Exit status is a signed integer
process status, not a measurement: any nonzero value — including the pinned
harness's negative timeout/spawn status — is `failed`, a missing or malformed
status is `unknown`, and only `0` with a passing end state is `completed`.
Missing or invalid numbers stay unknown (zero only when explicitly recorded);
whole-run totals are never used as per-case values.

The pinned runner reports `token_usage` as `{"input": N, "output": N}`. The
report normalizes that shape to one labelled total, `input + output`, derived
**only** when both components are nonnegative safe integer counts; an absent,
partial, bool, negative, non-integer or out-of-range component leaves the total
unknown, and no component is ever reported as a total. A scalar reported
`token_usage` is retained as a labelled scalar total for compatibility and is
never split into invented completion tokens. Aggregates and paired deltas
combine only the same normalized unit, so a mapping total and a reported scalar
are both measurable but are not paired with each other; two agreeing sources
with the same normalized total are not treated as conflicting, while different
values stay `conflicting`. Aggregate coverage and paired deltas cover only
comparable completed pairs where both values are measured. The report makes no
efficacy or ranking claim.

## Tests (offline, explicit project root)

Run with the pinned interpreter and the project as the subprocess cwd; the suite
sets its own explicit child cwds and asserts preparation launches no
process/model:

```bash
/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  -m unittest discover \
  -s /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -t /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -p 'test_agent_definition_eval.py'

/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  -m unittest discover \
  -s /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -t /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -p 'test_worker_budget_*.py'
```

Current receipt (fresh, produced offline at project root P): 81 neutral tests and
119 worker-budget regression tests pass, including the real pinned
config/workspace/collector/judge integration. Do not treat those counts as a
frozen acceptance threshold; counts change as tests are added. The criterion is a
green run with **no skipped pinned-SDK/harness integration** — a skip there is a
blocker to claiming that integration acceptance. The legacy worker-budget suite
must run at the project root above; running it from `$HOME` hits cwd-relative
staging failures.

## Not claimed / deferred

- No live evaluation, candidate efficacy, production adoption or publication
  attempt is made or implied.
- No runtime model enforcement or attestation is claimed: the all-illusionist
  stack and the recorded harness model identity are configuration properties
  checked against saved bytes, not proof of runtime behaviour or of which model
  served a request.
- No MLflow logging, transport/provider receipt work or SSE decoding is required
  for this workflow.
- The earlier budget/policy/observer research, stress pair configs and their
  receipts remain preserved history; their uncommitted modules are not
  prerequisites for `prepare`, `compare` or the neutral tests.
