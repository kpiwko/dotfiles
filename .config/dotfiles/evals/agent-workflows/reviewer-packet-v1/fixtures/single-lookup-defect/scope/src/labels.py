"""Label rendering."""

from text_utils import normalize


def render_label(value):
    """Render an operator-provided label for display."""
    return normalize(value).upper()
