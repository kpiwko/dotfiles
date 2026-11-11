# Triage and routing suite — design only (prepared, not executed)

Design record for the orchestrator triage policy added to
`~/.config/opencode/agents/orchestrator.md`: answer from supplied evidence, do a
few bounded reads when scope or routing is genuinely unclear, and route by
uncertainty and decision type rather than by step count or keywords.

**Status: design only.** `cases.json` is a data document with prompts, supplied
evidence, fixture bytes, and hidden expectations. It is **not** an executable
harness: there is no runner, scorer, fixture builder, or test in this directory,
nothing imports it, and nothing here invokes a model, provider, network, or
subprocess. In particular the first-delegation stop in the scoring window below
is a *scoring design*: no stub, interceptor, or window enforcement exists today.
The offline definition checks elsewhere in this project do not read this suite.
Adding a runner, scorer, or stub is an explicitly separate, separately approved
change.

## Comparison arms: committed eval snapshots

The two arms are the evaluation snapshots of their own ref, not raw agent source
and not a model-architecture model:

- **baseline** — eval snapshot committed at `3060ad7`; its
  `eval-snapshot/manifest.json` records `snapshot_id` prefix `9516b5ba` and
  `model: agentgateway/illusionist`;
- **candidate** — eval snapshot committed at `9ef4bcb`; its manifest records
  `snapshot_id` prefix `2385bc57` and the same model.

Provenance, verified by reading each committed manifest rather than recalled:
both declare `model: agentgateway/illusionist` and the same six roles, and their
only differences are `snapshot_id` plus the two `orchestrator.md` hashes
(`source_sha256` and `files_sha256`). The manifests therefore record a
model-constant, orchestrator-only snapshot regeneration. Full ids and hashes
live in those manifest files; only prefixes are quoted here because the prefixes
are what is checkable without guessing bytes.

## What this suite is for

The cases test *routing decisions*, not implementation quality. They are
deliberately small: each asks for one observable first move, and each negative is
expressed as a machine-countable event or a precisely defined visible-text check.
Prompts and supplied evidence are self-contained and use synthetic paths
(`/synthetic/acme-cli`), so no case depends on the contents of `$HOME` or on a
real repository.

## Structure

```text
triage-routing-v1/
  README.md    # this design, scoring rules, protocol
  cases.json   # actor inputs (prompt, supplied evidence, fixtures) + hidden expectations
```

`cases.json` separates columns deliberately:

- `input.prompt` — the user message the orchestrator receives;
- `input.supplied_evidence` — facts the user provides in the same turn; treat as
  authoritative and sufficient for the cases that say so;
- `input.materialization.virtual_workspace` — synthetic path → file bytes that a
  future run writes to disk (see materialization contract);
- `expectation` — hidden target and rationale, never shown to the actor;
- `observable` — the target expressed as event counts, path lists, and
  explicitly named text assertions.

## Cases: 12 cases = 5 contrast pairs + 2 singleton probes

Pair names must match the `pairs` object in `cases.json` exactly. The table is
grouped by pair; the two singleton probes are listed last.

| case | pair | expected first move |
| --- | --- | --- |
| `direct-answer-supplied-evidence` | evidence-sufficiency | answer from the supplied frontmatter |
| `bounded-inspection-before-routing` | evidence-sufficiency | 1–3 named reads, then one `worker` assignment naming the resolved module |
| `small-clear-change-worker` | size-and-sequence | brief local sequence, then one `worker` assignment |
| `obvious-multistep-local-sequence-no-planner` | size-and-sequence | brief local sequence, then `worker` |
| `uncertain-migration-planner` | specialist-type | `planner` |
| `durable-architecture-architect` | specialist-type | `architect` |
| `useful-independent-review-reviewer` | review-value | `reviewer` with the supplied packet |
| `trivial-change-no-review` | review-value | finish on the worker result |
| `explicit-premium-zweistein` | premium-opt-in | `zweistein` |
| `no-unsolicited-premium` | premium-opt-in | `worker` |
| `concrete-failure-worker` | — (probe: execution) | `worker` with the failure evidence |
| `ambiguous-requirement-minimal-clarification` | — (probe: ambiguity) | one minimal clarification question |

So the suite holds **five contrast pairs** (10 cases): evidence sufficiency,
size-and-sequence, specialist type, review value, premium opt-in. The
`execution` and `ambiguity` entries are **single-case probes**, not contrasts;
there is no iteration-uncertainty pair and no claim that any dimension is
isolated beyond the named pair.

The two `size-and-sequence` cases are the keyword-temptation contrast: the second
names "plan" and "brainstorm" for a two-file change while the first does not.
Both expect no `planner` and no skill use, so an actor keying on the word rather
than the work fails the contrast.

## Scoring window: first decision → first delegation

All counts are window-scoped, from the actor's first action (first tool call,
subagent call, question call, or user-visible message):

- **end**: the first subagent delegation. That child is a **stub** — it is not
  executed and no follow-on calls are counted. When the actor delegates nothing,
  the window ends at its final direct answer or clarification.
- **later workflow is out of scope**: `max_subagent_calls_in_window` is a
  window-scoped target, never a total-call budget, so a legitimate review,
  validation, or follow-on workflow after the first delegation cannot false-fail
  a case.
- **not implemented**: nothing in this repository enforces the window or stubs a
  child today; this section specifies what a future scorer would do.

## Routing evidence versus visible text assertions

Each `scoring_fields` entry in `cases.json` is tagged `kind`:

- **`event`** (routing evidence): subagent delegations with agent id and order,
  tool attempts with normalized targets (denied attempts count as attempts),
  skill attempts, and question calls.
- **`text`** (visible text assertions, judged manually from the recorded
  user-visible output; private reasoning is never evidence):
  - `local_sequence` — `"required"` in the two straightforward-implementation
    cases, `"ignored"` elsewhere. Required means the actor's own user-visible
    message before the first delegation shows an ordered sequence of at least two
    steps (or a step plus its validation); a numbered or arrow-separated list
    counts. `"ignored"` means genuinely not scored — not a hidden failure.
  - `clarification_text` — used only when no question tool call was recorded.
  - `premium_mention` — literal mention or offer of a premium path in visible
    text.
  - `answer_content` and `delegation_content` — literal content checks (the
    supplied rule; the required execution root and resolved path).

Subjective detours that cannot be observed (for example "refusing because the
task has two steps", or "inventing a migration order") are not scored and have
been removed rather than guessed at.

**Missing observations are unscorable.** If the required event stream or the
user-visible text channel is absent or cannot distinguish denied from absent,
that case is **unscorable** — never zero-count, never `pass` on outcome alone.
Distinguish the two absences: if the observable is missing *because the actor did
something else* (delegated instead of asking, edited instead of answering), that
is a **fail**; if the recording lacks the channel entirely, it is
**unscorable**.

## Clarification case (probe: ambiguity)

`ambiguous-requirement-minimal-clarification` allows **0 reads and 0
delegations** in the window. Its observable is exactly one user question:
`required_user_questions: 1`, `max_user_questions: 1`. Assessment: count
`question` tool calls in the window; if the harness records none, require exactly
one user-visible message containing a single clarification request that asks for
the target property and the compatibility constraint, and no second question. A
guessed-format implementation or a delegation with zero questions is a fail.
Hidden reasoning is never evidence.

## Materialization contract (future runs)

- **actor input**: `input.prompt` verbatim, then `input.supplied_evidence`
  verbatim as the user-supplied evidence block. `expectation`, `observable`,
  `pairs`, `singleton_probes`, and `arms.provenance` are hidden and must never
  appear in the prompt, the workspace, or any tool-visible file.
- **workspace**: each case gets a fresh isolated directory outside `$HOME`. Keys
  of `virtual_workspace` are synthetic absolute paths whose prefix is rewritten
  to that directory (`"/synthetic/<rest>"` → `"<workspace>/<rest>"`) before the
  prompt is shown; observed read targets and delegation paths are normalized back
  to the synthetic form before scoring.
- **which files exist**: only the paths listed in `virtual_workspace`. Two cases
  carry fixtures — `bounded-inspection-before-routing` (six files across two
  candidate checkouts, so its reads genuinely resolve the live root and the
  option-assembly module) and `useful-independent-review-reviewer` (one diff
  artifact). Every other case gets an empty workspace root, needs no reads, and
  its `max_context_reads` is a ceiling; read *success* is not scored anywhere.
- **review packet identity**: the review case supplies the diff bytes and their
  `sha256` content identity, so the packet references real supplied bytes rather
  than an invented Git commit, branch, or checkout. Because the window stops at
  the first delegation, child execution is unnecessary.
- **repo independence**: no case reads `$HOME`, a real repository, or the
  network. Supplied evidence and fixture bytes are the only metadata; no case
  asserts facts about unlisted locations.

## Future live protocol (NOT AUTHORIZED, NOT RUN)

If a separate, finite live envelope is approved:

- Hold the model constant at `agentgateway/illusionist` in both arms and run each
  case for both arms with identical inputs, using the snapshot commit prefixes
  above.
- Stop at the first delegation with a stub child, or record the full window and
  truncate scoring at it; keep the case list and prompts unchanged.
- Record raw per-attempt events before scoring, and report unscorable cases as
  unscorable.
- State plainly that a difference is attributable only to the definition change
  under these fixtures. No routing-efficacy, cost, or production claim follows
  without live measurement, and all-illusionist results say nothing about other
  models.

No paid or free run is part of this change, and no efficacy claim is made here.

## Non-goals

- No runner, scorer, judge, fixture generator, stub, or interceptor.
- No change to other agent roles, permissions, or the shared eval framework.
- No claim that the triage prose, or these cases, improve production routing.
