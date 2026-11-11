"""Pacing helpers for the scheduler."""

MAX_PERCENT = 100


def clamp_percent(value):
    """Clamp a percentage into the inclusive 0..100 range."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("value must be an int")
    return max(0, min(MAX_PERCENT, value))
