# Review request

Reviewed revision: content-sha256:b6e33018d716b63c8c3890fb27dc84aca439d245645f222e8c8c5e65d03a3bd2
(fixture content snapshot of the supplied scope files; not a Git commit)

Scope: `src/paging.py` — the only supplied changed file.
Diff: `diff.patch` (single hunk against `src/paging.py`).

Acceptance criteria:

- `page_bounds` clamps the returned end offset to `total` for new callers.
- No behaviour change for existing legacy export callers, including their
  default page size.

Implementation result: raised `DEFAULT_LIMIT` from `25` to `50` and clamped the
end offset with `min(start + limit, total)`.

Validation: the implementer reports the new-caller cases passing. No legacy
export caller source, legacy test, or recorded legacy validation result was
supplied.

Known limitations: legacy export callers are outside the supplied scope; their
module is not part of the reviewed revision material.
