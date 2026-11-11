# Triage and routing suite — design only (prepared, not executed)

Design record for the orchestrator triage policy added to
`~/.config/opencode/agents/orchestrator.md`: answer from supplied evidence, do a
few bounded reads when scope or routing is genuinely unclear, and route by
uncertainty and decision type rather than by step count or keywords.

**Status: design only.** `cases.json` is a data document with prompts, supplied
evidence, and hidden expectations. It is **not** an executable harness: there is
no runner, scorer, fixture builder, or test in this directory, nothing imports
it, and nothing here invokes a model, provider, network, or subprocess. The
offline definition checks elsewhere in this project do not read this suite.
Adding a runner or scorer is an explicitly separate, separately approved change.

## What this suite is for

Two definition arms over the same fixed case inputs:

- **baseline**: orchestrator definition at `3060ad7` (pre-change);
- **candidate**: orchestrator definition with the triage section.

The cases test *routing decisions*, not implementation quality. They are
deliberately small: each asks for one observable first move plus a short list of
forbidden detours. Case prompts and supplied evidence are self-contained and use
synthetic paths (`/synthetic/acme-cli`), so no case depends on the contents of
`$HOME` or on a real repository.

## Structure

```text
triage-routing-v1/
  README.md    # this design, scoring rules, protocol
  cases.json   # actor inputs (prompt + supplied_evidence) and hidden expectation
```

`cases.json` separates columns deliberately:

- `input.prompt` — the user message the orchestrator receives;
- `input.supplied_evidence` — facts the user provides in the same turn; treat as
  authoritative and sufficient for the cases that say so;
- `expectation` — hidden target, never shown to the actor;
- `observable` — the target expressed as event counts/identities, not prose.

The `case` / `pair` columns group controlled contrasts: two cases differ mainly
in the dimension the policy names (evidence sufficiency, step count, iteration
uncertainty, review value, premium opt-in).

## Cases

| case | pair | expected first move | forbidden detours |
| --- | --- | --- | --- |
| `direct-answer-supplied-evidence` | evidence | answer from the supplied frontmatter | any delegation, any read, skill attempt |
| `bounded-inspection-before-routing` | evidence | 1–3 named reads, then one `worker` assignment | `planner`, `architect`, unread delegation, >4 reads |
| `small-clear-change-worker` | sequence | one `worker` assignment | `planner`, `architect`, `reviewer`, multiple workers |
| `obvious-multistep-local-sequence-no-planner` | sequence | brief local ordered sequence, then `worker` | `planner`, `architect`, any skill, plan artifact demand |
| `uncertain-migration-planner` | planning | `planner` | direct `worker` implementation, `architect` |
| `durable-architecture-architect` | planning | `architect` | `planner` first, `worker`, unilateral decision |
| `concrete-failure-worker` | execution | `worker` with the failure evidence | `planner`, `architect`, `zweistein`, prior archaeology |
| `useful-independent-review-reviewer` | review | `reviewer` with the supplied packet | skipped review, `worker` redo, packet reconstruction |
| `trivial-change-no-review` | review | finish on the worker result | `reviewer`, second `worker`, `planner` |
| `explicit-premium-zweistein` | premium | `zweistein` | substituting `worker`/`architect`, declining |
| `no-unsolicited-premium` | premium | `worker` | `zweistein`, `planner`, `architect` |
| `ambiguous-requirement-minimal-clarification` | ambiguity | one minimal user question, no delegation | guessing a format, `planner`/`architect` invention, multiple questions |

The two "sequence" cases form the keyword-temptation contrast: the second names
"plan" and "brainstorm" for a two-file change, while the first does not. Both
expect no `planner` and no skill use, so an actor that keys on the word rather
than the work fails the contrast.

## Scoring from native events

A future run must score from recorded native events, per case:

- **delegations**: the actual subagent agent id and order from subagent tool
  events. A final message claiming "I asked the planner" is not evidence.
- **tool attempts**: every `read`/`grep`/other tool attempt with its target,
  including **denied** attempts. A denied attempt counts as an attempt, never as
  zero and never as a failure by itself.
- **skill attempts**: count of `skill` tool calls; the target is `0` in every
  case because `skill` is denied for this agent.
- **local sequence**: whether a brief ordered sequence is visible in the
  orchestrator's own user-visible narration before the first delegation. This is
  not private chain of thought; absent narration is simply not evidence.
- **final outcome**: recorded for reporting, but not used to infer routing. A
  worker's "done" does not prove the orchestrator delegated; a correct answer
  does not prove it answered from evidence.

If the required event stream for a case is missing, incomplete, or cannot
distinguish denied from absent, that case is **unscorable**. Do not fill gaps
from final prose, and do not score a case `pass` on outcome alone.

## Future live protocol (NOT AUTHORIZED, NOT RUN)

If a separate, finite live envelope is approved:

- Hold the model constant at `agentgateway/illusionist` (the snapshot model) in
  both arms; run each case for both arms with identical inputs.
- Keep the case list and prompts unchanged; no ad-hoc additions mid-run.
- Record raw per-attempt events before scoring, and report unscorable cases as
  unscorable.
- State plainly that a difference is attributable only to the definition change
  under these fixtures. No routing-efficacy, cost, or production claim follows
  without live measurement, and all-illusionist results say nothing about other
  models.

No paid or free run is part of this change, and no efficacy claim is made here.

## Non-goals

- No runner, scorer, judge, fixture generator, or test file.
- No change to other agent roles, permissions, or the shared eval framework.
- No claim that the triage prose, or these cases, improve production routing.
