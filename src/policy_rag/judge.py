"""Answerability check.

The model points at the clause that settles the question, or says none. Pointing is an easier task for a
small model than judging whether the clauses are "enough", and the label it names is checked against the
clauses actually shown, so an invented label counts as not found.
"""

import re
from dataclasses import dataclass

from . import prompts
from .llm import parse_json
from .verify import extract_citations

NONE_WORDS = {"", "none", "null", "n/a", "no clause", "no"}
LOOSE_LABEL = re.compile(r"(POL-\d{2})\D{0,12}?(\d+\.\d+)")


@dataclass
class Verdict:
    answerable: bool
    clause: str
    reason: str
    raw: str


def labels_in(clause):
    """Normalised labels named in the model's reply. Tolerates 'POL-04 3.2' and a missing section sign."""
    clause = re.sub(r"(?i)\bpol-", "POL-", clause)
    clause = re.sub(r"(?i)\btable:", "Table:", clause)
    found = extract_citations(clause)
    if found:
        return found
    m = LOOSE_LABEL.search(clause)
    return [f"{m.group(1)} §{m.group(2)}"] if m else []


def find_clause(llm, question, context, available, checks=""):
    """available maps lower case clause labels to chunks, as returned by PolicyAssistant.build_context."""
    raw = llm.complete(prompts.judge_user(question, context, checks), system=prompts.JUDGE_SYSTEM,
                       purpose="judge", json_mode=True)
    data = parse_json(raw)
    reason = str(data.get("reason", "")).strip()
    clause = data.get("clause", "")
    if isinstance(clause, list):
        clause = ", ".join(str(c) for c in clause)
    clause = str(clause or "").strip().strip("[]. ")

    if not data:
        return Verdict(False, "", "the judge reply could not be read", raw)
    if clause.lower() in NONE_WORDS:
        return Verdict(False, "", reason or "no clause settles the question", raw)
    for label in labels_in(clause):
        if label.lower() in available:
            return Verdict(True, label, reason, raw)
    return Verdict(False, clause, f"the judge named a clause that is not in the context: {clause}", raw)
