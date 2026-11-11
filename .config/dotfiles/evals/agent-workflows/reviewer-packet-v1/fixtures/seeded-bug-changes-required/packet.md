# Review request

Reviewed revision: content-sha256:5ef1d0c7ec33b23f5483b54a64368cc55a86787a43bdf6d66dfcae73aa4afb6f
(fixture content snapshot of the supplied scope files; not a Git commit)

Scope: `src/backoff.py` — one new module, no other file changed.
Diff: `diff.patch` (new-file diff for `src/backoff.py`).

Acceptance criteria:

- `retry_delay(attempt)` returns `1`, `2`, `4`, `8` for attempts `0..3`.
- Attempts beyond the configured schedule reuse the last delay, `8` seconds.
- A negative attempt raises `ValueError`.

Implementation result: added `src/backoff.py` with `DELAYS` and `retry_delay`.

Validation: the implementer reports the four in-schedule attempts passing
locally; out-of-schedule attempts were not exercised.

Known limitations: no jitter is applied; out of scope for this change.
