"""Revision handoff decision: review need vs validation reuse (seeded, incomplete)."""


def decide(prior, current):
    """Return {"review_needed": bool, "validation_reusable": bool}."""
    changed = prior != current
    return {"review_needed": changed, "validation_reusable": not changed}
