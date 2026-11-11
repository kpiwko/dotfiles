# Reviewer packet suite — prepared fixtures, offline checks

Focused companion suite for the packet-first, shell-free reviewer contract
introduced in commit `681b80c7` ("reviewer: make review packet-first and
shell-free"). It adds **offline definition checks** and **prepared behavioral
fixtures**.

**Status: prepared, not executed as a live evaluation.** No agent, model,
provider, network or subprocess is launched by anything here. The offline tests
prove that the definitions state the contract and that the fixtures are
internally consistent; they are not behavioral validation and not efficacy
evidence.

## Contents

```text
reviewer_packet_contract.py          # frontmatter/body parser + violation codes
fixtures/<case>/packet.md            # exact reviewer input (orchestrator inputs)
fixtures/<case>/diff.patch           # real unified diff where one is supplied
fixtures/<case>/scope/**             # fixed post-image source bytes
expectations/<case>.json             # hidden expectation, kept out of inputs
tests/test_reviewer_packet_contract.py
```

Expectations are deliberately stored outside `fixtures/`: a fixture directory
contains only what the agent would receive, and a test fails if any JSON file
appears under `fixtures/`.

## Cases

| case | actor | supplied packet | expected result |
| --- | --- | --- | --- |
| `clean-packet-pass` | reviewer | complete, clean new module | `PASS`, no findings |
| `seeded-bug-changes-required` | reviewer | complete, one seeded defect | `CHANGES_REQUIRED` at `src/backoff.py:10` |
| `missing-diff-needs-context` | reviewer | revision + scope, no diff | `NEEDS_CONTEXT` ("diff or diff artifact") |
| `missing-revision-needs-context` | reviewer | diff + scope, mutable working tree | `NEEDS_CONTEXT` ("immutable reviewed revision") |
| `single-lookup-defect` | reviewer | diff looks correct; defect needs one source read | `CHANGES_REQUIRED` at `src/labels.py:8` using `src/text_utils.py` (`max_lookups: 4`) |
| `beyond-budget-needs-context` | reviewer | diff + scope; legacy caller compatibility evidence absent | `NEEDS_CONTEXT`, never `PASS` |
| `orchestrator-missing-artifact` | orchestrator | worker result without diff/artifact/revision | request artifact from `@worker`; do not invoke reviewer |

Every case is `status: prepared_not_executed`. There are no saved runs and no
saved model output in this suite.

`beyond-budget-needs-context` is deliberately additive: the visible diff keeps
`DEFAULT_LIMIT` at `25` and clamps only when a caller passes a positive `total`,
so the diff alone justifies neither `PASS` nor a finding. The unresolved
legacy-caller compatibility question needs caller source or recorded validation
that the packet does not supply and the lookup allowance cannot reach.

## Revision identity

Each reviewer packet declares:

```text
Reviewed revision: content-sha256:<64 hex>
(fixture content snapshot of the supplied scope files; not a Git commit)
```

The identity is the SHA-256 of a canonical `{relative path: sha256}` manifest of
the fixture's `scope/` bytes (`reviewer_packet_contract.content_identity`). It is
a genuine, fixed content identity; it is **not** fabricated Git provenance. A
test recomputes it from real bytes, and a mutation test shows that changing one
byte changes the identity. Packets for mutable-worktree cases deliberately
contain no such identity.

## Offline checks

Run with the pinned interpreter from the project root (same interpreter as
`AGENT_DEFINITION_EVAL.md`):

```bash
/Users/kpiwko/devel/adlc/experiments/02-git-operations/git-pilot-v1/.venv/bin/python \
  -m unittest discover \
  -s /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -t /Users/kpiwko/.config/dotfiles/evals/agent-workflows/tests \
  -p 'test_reviewer_packet_contract.py'
```

What the definition checks assert (against `~/.config/opencode/agents/`; override
the directory with `OPENCODE_AGENTS_DIR`):

- reviewer frontmatter is `mode: subagent`, ≤ 12 steps, `edit`/`subagent` deny,
  and shell deny for the universal resource `"*"` with **no effective shell
  allow exception**: rules are resolved in order with the last match winning, so
  a wildcard action (`*`) or an action glob (`she*`) that matches `shell` and
  survives a later deny fails the check, while allows for unrelated actions do
  not;
- no Qodo surface anywhere in the reviewer definition;
- the required packet concepts are stated (immutable revision, exact scope,
  diff, acceptance criteria, implementation result, validation, known
  limitations);
- exactly the three verdicts `` `PASS` ``, `` `CHANGES_REQUIRED` ``,
  `` `NEEDS_CONTEXT` `` are offered, with no foreign verdict token;
- one pass, four-lookup allowance, no unsupported `PASS`, refusal of shell,
  network research and retrying a denied action;
- orchestrator: packet assembly, worker artifact request instead of reviewer
  reconstruction, no automatic review for every small change, immutable content
  review keying, and no second review of unchanged relevant content;
- `eval-snapshot/agents/{reviewer,orchestrator}.md` equal their sources modulo
  the single model-line rewrite.

Mutation tests deliberately break each of those properties and require the
validator to report the matching code, so the checks fail on regressions rather
than merely passing on today's prose. They do not compare whole-prose snapshots.

Fixture checks assert: expectation/fixture sets match; declared content
identities match real bytes; every diff declares the correct old/new hunk counts,
hunks are ordered and non-overlapping, and each hunk's new side reconstructs the
supplied post-image at its declared `+start` position (a new-file diff must
cover the whole post-image); each expected finding's `path:line` exists and
contains its token; lookup requirements point at supplied files within four
lookups; `PASS`/`CHANGES_REQUIRED`/`NEEDS_CONTEXT` findings and `missing` fields
are mutually consistent; expectations never leak into agent inputs. Removed
lines are not required to be globally absent, because repeated or moved content
is legitimate.

These checks do **not** prove an agent follows the contract. They cannot detect
a live reviewer that ignores the packet, invents findings, or exceeds its lookup
budget.

## Observation requirements for a future bounded run (NOT RUN)

No saved-result scorer is implemented here, and the existing end-state-only
runner cannot observe procedure. If a future bounded run is approved, telemetry
must let a consumer distinguish, per case:

- observed tool attempts, including **denied** attempts (a denied shell attempt
  is a data point, not a failure and not "no attempt");
- each `read`/`grep` lookup with its path, counted against the four-lookup
  allowance;
- subagent invocations for the orchestrator case, so a reviewer call is visible;
- missing or incomplete telemetry, which is **unscorable** — never zero attempts
  and never inferred from final prose.

A final report alone is insufficient evidence: prose claiming a lookup or a
verdict does not show what the agent attempted. Any small scorer added later must
keep these distinctions; otherwise prepare fixtures and record raw attempts only.

## Future live comparison protocol (NOT AUTHORIZED, NOT RUN)

If a separately approved, finite envelope exists, compare the **same model**
(`agentgateway/illusionist`, the snapshot model) and these exact fixtures across
two definition arms:

- baseline: the agent definitions at `681b80c7^` (the pre-change parent), staged
  as a snapshot;
- candidate: the current definitions.

Use the case inputs above unchanged, record the per-attempt telemetry described
above, and keep the run inside the approved envelope. All-illusionist results say
nothing about Sonnet, production routing or provider-side savings: the model is
held constant, so any difference can only be attributed to the definition
change under those fixtures, and no efficacy or cost claim follows without live
measurement.
