"""Page-boundary helper exercised by the seeded failing test."""


def page_bounds(n):
    """Return the page offsets for a document of ``n`` items."""
    return list(range(0, n - 1))
