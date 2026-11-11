# Review request

Reviewed revision: content-sha256:db2414f0b4b5e8d00e72aa9143c2d4baa7f549fda2157d3b9fb26bacd85a3c87
(fixture content snapshot of the supplied scope files; not a Git commit)

Scope: `src/labels.py` — one new module. Supplied source available for context
lookups: `src/text_utils.py` (unchanged dependency in the changed scope).
Diff: `diff.patch` (new-file diff for `src/labels.py`).

Acceptance criteria:

- `render_label(value)` returns an upper-case label for an operator-provided
  string.
- `render_label("")` returns a displayable string and does not raise.
- Internal whitespace is collapsed by the existing `normalize` helper.

Implementation result: added `src/labels.py`, reusing `normalize` from
`src/text_utils.py`.

Validation: the implementer reports the label rendering cases in the task
passing.

Known limitations: none reported.
