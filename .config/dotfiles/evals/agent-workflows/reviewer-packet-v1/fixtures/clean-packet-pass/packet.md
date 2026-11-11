# Review request

Reviewed revision: content-sha256:0906afb71efef14b6e0fef52babaa16aa15ffb8c606dd372a4187b58ff463e82
(fixture content snapshot of the supplied scope files; not a Git commit)

Scope: `src/pacing.py` — one new module, no other file changed.
Diff: `diff.patch` (new-file diff for `src/pacing.py`).

Acceptance criteria:

- `clamp_percent(value)` returns `value` unchanged when `0 <= value <= 100`.
- It returns `0` below that range and `100` above it.
- A non-`int` value, including `bool`, raises `TypeError`.

Implementation result: added `src/pacing.py` with `MAX_PERCENT` and
`clamp_percent`.

Validation: the implementer reports the three acceptance cases passing locally;
no failures were reported.

Known limitations: no separator or locale handling; out of scope for this
change.
