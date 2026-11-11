"""Request limit checks."""

MAX_CONCURRENCY = 4


def allowed(active, requested=1):
    """Return whether ``requested`` more slots fit the limit."""
    return active + requested <= MAX_CONCURRENCY
