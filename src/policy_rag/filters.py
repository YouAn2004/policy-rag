"""Access and validity rules. These run BEFORE any search, so forbidden text is never scored or shown."""

from datetime import date


def is_allowed(chunk, role, as_of=None):
    """A clause is searchable only if its policy is current, already in force, and open to the role."""
    meta = chunk.meta
    as_of = as_of or date.today().isoformat()
    if meta.status != "current":
        return False
    if meta.effective_date > as_of:  # ISO dates compare correctly as strings
        return False
    return "all" in meta.audience or role in meta.audience
