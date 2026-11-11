"""Retry delay schedule."""

DELAYS = (1, 2, 4, 8)


def retry_delay(attempt):
    """Return the delay in seconds for a zero-based attempt index."""
    if attempt < 0:
        raise ValueError("attempt must be non-negative")
    return DELAYS[min(attempt, len(DELAYS))]
