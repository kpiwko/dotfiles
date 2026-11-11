# Review request

Reviewed revision: content-sha256:e18e35d887d1728d3aab31cfe8dd5658371d90dfe4e6778e0a28e09e07198e0d
(fixture content snapshot of the supplied scope files; not a Git commit)

Scope: `src/report.py` — only changed file.
Diff: not supplied. Read the working tree or the recent commit to see what
changed.

Acceptance criteria:

- `summarize(rows)` returns a mapping of status to row count.
- Rows without a `status` key count under `unknown`.
- An empty row list returns an empty mapping.

Implementation result: reworked `summarize` in `src/report.py`.

Validation: the implementer reports the summary cases passing locally.

Known limitations: none reported.
