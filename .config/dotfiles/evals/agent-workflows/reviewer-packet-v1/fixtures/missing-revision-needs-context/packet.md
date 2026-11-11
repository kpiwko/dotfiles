# Review request

Reviewed revision: my uncommitted working tree on branch `main` — no commit
and no content hash exist yet.

Scope: `src/limits.py` — one new module.
Diff: `diff.patch` (new-file diff for `src/limits.py`).

Acceptance criteria:

- `allowed(active, requested=1)` is true only when the requested slots fit
  under `MAX_CONCURRENCY`.
- `MAX_CONCURRENCY` is `4`.
- A zero or negative `requested` value is treated as no additional load.

Implementation result: added `src/limits.py` with `MAX_CONCURRENCY` and
`allowed`.

Validation: the implementer reports the fit and overflow cases passing.

Known limitations: concurrency accounting is per process.
