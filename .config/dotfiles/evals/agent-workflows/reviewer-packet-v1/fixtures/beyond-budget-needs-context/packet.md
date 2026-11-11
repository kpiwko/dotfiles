# Review request

Reviewed revision: content-sha256:f07979531fb5b24f8acf813fe4610a74d11e1dd36b78fe279da052d59359eb7a
(fixture content snapshot of the supplied scope files; not a Git commit)

Scope: `src/paging.py` — the only supplied changed file.
Diff: `diff.patch` (single hunk against `src/paging.py`).

Acceptance criteria:

- `page_bounds` clamps the returned end offset to `total` when a caller passes
  a positive `total`.
- The default page size stays `25`, so legacy export callers that omit `limit`
  keep their current page size.
- No behaviour change for existing legacy export callers.

Implementation result: left `DEFAULT_LIMIT` at `25` and added a clamp guarded
by `total > 0`; the unguarded `end = start + limit` path is unchanged.

Validation: the implementer reports the new-caller cases passing. No legacy
export caller source, legacy test, or recorded legacy validation result was
supplied.

Known limitations: legacy export callers are outside the supplied scope; their
module is not part of the reviewed revision material, so whether any legacy
caller passes a positive `total` cannot be checked here.
