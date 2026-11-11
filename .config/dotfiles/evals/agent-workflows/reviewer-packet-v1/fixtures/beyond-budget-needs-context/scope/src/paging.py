"""Page-boundary helper exercised by the legacy export path."""

DEFAULT_LIMIT = 50


def page_bounds(offset, limit=None, total=0):
    """Return (start, end) page bounds clamped to ``total``."""
    if limit is None:
        limit = DEFAULT_LIMIT
    start = max(0, offset)
    end = min(start + limit, total)
    return start, end
