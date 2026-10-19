"""Question rewriting. Maps casual wording to handbook vocabulary before retrieval."""

from . import prompts


def rewrite_query(llm, question):
    """Return a rewritten query, or the original question if the model gives nothing usable."""
    try:
        out = llm.complete(question, system=prompts.REWRITE_SYSTEM, purpose="rewrite")
    except Exception:
        return question
    line = (out or "").strip().splitlines()[0].strip().strip('"').strip() if (out or "").strip() else ""
    return line[:200] if line else question
