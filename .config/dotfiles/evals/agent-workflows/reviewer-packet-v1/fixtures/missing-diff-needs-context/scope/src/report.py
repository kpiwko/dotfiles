"""Report summary helpers."""


def summarize(rows):
    """Return per-status counts for report rows."""
    counts = {}
    for row in rows:
        status = row.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts
