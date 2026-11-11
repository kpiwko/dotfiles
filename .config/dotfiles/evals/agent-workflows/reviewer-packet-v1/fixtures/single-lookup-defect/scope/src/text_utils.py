"""Text normalization helpers."""


def normalize(value):
    """Normalize a value for display; empty input normalizes to ``None``."""
    if not value:
        return None
    return " ".join(value.split())
