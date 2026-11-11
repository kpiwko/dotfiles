"""Request limit checks."""

MAX_CONCURRENCY = 4


def allowed(active, requested=1):
    """Return whether ``requested`` more slots fit the limit."""
    if requested <= 0:
        return active <= MAX_CONCURRENCY
    return active + requested <= MAX_CONCURRENCY
