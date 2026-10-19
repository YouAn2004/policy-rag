"""Deterministic answer checks. No model involved, so they are cheap and always the same."""

import re

CLAUSE_CITE = re.compile(r"POL-(\d{2})\s*(?:v[\d.]+\s*)?§\s*(\d+\.\d+)")
TABLE_CITE = re.compile(r"POL-(\d{2})\s*Table:\s*([^\]\n,;]+)")
BRACKET_POL = re.compile(r"\[[^\]]*POL-[^\]]*\]")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s+", re.M)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30}
SILENT = re.compile(
    r"\bnot\s+(?:explicitly\s+)?(?:specified|mentioned|addressed|stated|covered)\b"
    r"|\b(?:does|do|did)\s+not\s+(?:specify|mention|address|contain|cover|say|state|include|define)\b"
    r"|\bno\b[^.\n]{0,40}\b(?:is|are)\s+(?:specified|mentioned|stated|provided)\b"
    r"|\bno\s+(?:information|details?|mention|rules?|clauses?|provisions?|guidance|polic(?:y|ies))\b"
    r"[^.\n]{0,60}\b(?:specif|provid|mention|found|address|cover|state|available)"
    r"|,\s*not\s+for\s+\w+ing\b",
    re.I)
WORD_NUMBER = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)


def extract_citations(text):
    """All cited labels in normalised form, in order, without duplicates."""
    found = []
    for m in CLAUSE_CITE.finditer(text):
        found.append((m.start(), f"POL-{m.group(1)} §{m.group(2)}"))
    for m in TABLE_CITE.finditer(text):
        found.append((m.start(), f"POL-{m.group(1)} Table: {m.group(2).strip()}"))
    out = []
    for _, key in sorted(found):
        if key not in out:
            out.append(key)
    return out


def says_silent(answer):
    """True when the answer says the policy is silent on the question, instead of giving a rule."""
    return bool(SILENT.search(answer))


def norm_number(s):
    s = s.replace(",", "").rstrip(".")
    if "." in s:
        ip, fp = s.split(".", 1)
        return (ip.lstrip("0") or "0") + "." + fp
    return s.lstrip("0") or "0"


def numbers_in(text):
    return {norm_number(n) for n in NUMBER.findall(text)}


def question_numbers(question):
    """Digits and spelled out numbers ('four years') in the employee's own words."""
    return numbers_in(question) | {str(NUMBER_WORDS[w.lower()]) for w in WORD_NUMBER.findall(question)}


def answer_numbers(answer):
    """Numbers the answer states. Citation labels and list markers do not count."""
    body = LIST_MARKER.sub("", BRACKET_POL.sub("", answer))
    return numbers_in(body)


def verify_structure(answer, available_keys, context_text, question):
    """Check citations and numbers. available_keys is a set of lower-cased allowed labels."""
    cited = extract_citations(answer)
    invalid = [c for c in cited if c.lower() not in available_keys]
    allowed_numbers = numbers_in(context_text) | question_numbers(question)
    unsupported = sorted(answer_numbers(answer) - allowed_numbers)
    return {
        "cited": cited,
        "invalid_citations": invalid,
        "uncited": not cited,
        "unsupported_numbers": unsupported,
    }


def problems(v):
    """Turn a verification result into short sentences for the retry prompt. Empty means clean."""
    out = []
    if v["uncited"]:
        out.append("The answer has no citations. Cite every statement with a label such as [POL-05 §3.2].")
    if v["invalid_citations"]:
        out.append("These citations are not in the clauses provided: " + ", ".join(v["invalid_citations"]) + ".")
    if v["unsupported_numbers"]:
        out.append("These numbers are not in the clauses: " + ", ".join(v["unsupported_numbers"]) + ". Use only figures written in the clauses.")
    return " ".join(out)
