"""Exact comparisons between the numbers in a question and the thresholds written in clauses.

A small language model often gets "4 years against 5 or more years" wrong, both when it answers and when it
checks an answer. So code does the arithmetic and the model does the language. For every clause shown to the
model, this module finds conditions such as "more than RM 500", "5 or more years", "Grades 6 and above" or
"within 24 hours", compares them with the figures the employee gave, and returns plain sentences like
"- [POL-08 §2.3] condition 'more than rm 500': the employee's RM 400 does NOT meet it".

It only reports a comparison when the units agree, and it says nothing when the question has no figures.
"""

import re
from dataclasses import dataclass

WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30}
WORD_RE = "|".join(WORDS)
NUM = r"\d{1,3}(?:,\d{3})+|\d+"
UNIT = (r"years?|yrs?|months?|weeks?|working days?|business days?|calendar days?|days?|hours?|hrs?|characters?")
SUFFIX = (r"or more|or fewer|or less|or under|or below|or above|or over|and above|and over|and below|"
          r"or higher|or lower|or longer|or shorter")

UNIT_NAMES = {"year": "years", "yr": "years", "month": "months", "week": "weeks", "working day": "working_days",
              "business day": "working_days", "calendar day": "calendar_days", "day": "days", "hour": "hours",
              "hr": "hours", "character": "characters"}
DAY_UNITS = {"days", "working_days", "calendar_days"}

AMOUNT = re.compile(
    rf"(?P<cur>\b(?:rm|myr)\s*)?(?P<num>{NUM})(?:\.\d+)?(?:\s+(?P<suf1>{SUFFIX}))?"
    rf"(?:\s+(?:[a-z]+\s+)??(?P<unit>{UNIT})\b)?(?:\s+(?P<suf2>{SUFFIX}))?", re.I)

COMPARATORS = [  # (regex that must end right before the amount, operator)
    (r"(less than|fewer than|below|under|lower than)\s*$", "<"),
    (r"(more than|above|over|exceeding|exceeds|greater than)\s*$", ">"),
    (r"(up to|no more than|not more than|not exceeding|at most|maximum of|capped at|within|limited to)\s*$", "<="),
    (r"(at least|minimum of|no less than|not less than)\s*$", ">="),
    (r"(from)\s*$", "from"),
    (r"(to)\s*$", "to"),
]
SUFFIX_OPS = {"or more": ">=", "and above": ">=", "or above": ">=", "and over": ">=", "or over": ">=",
              "or higher": ">=", "or longer": ">=",
              "or fewer": "<=", "or less": "<=", "or under": "<=", "or below": "<=", "and below": "<=",
              "or lower": "<=", "or shorter": "<="}
TAG_UNIT = re.compile(r"\((rm|years?|months?|weeks?|days?|hours?)\)", re.I)

GRADE_RANGE = re.compile(r"grades?\s+(\d+)\s+to\s+(\d+)", re.I)
GRADE_UP = re.compile(r"grades?\s+(\d+)\s+and\s+(?:above|higher|over)", re.I)
GRADE_PAIR = re.compile(r"grades?\s+(\d+)\s+and\s+(\d+)", re.I)


@dataclass
class Condition:
    unit: str
    lo: float = None
    lo_inc: bool = True
    hi: float = None
    hi_inc: bool = True
    phrase: str = ""

    def holds(self, v):
        if self.lo is not None and (v < self.lo or (v == self.lo and not self.lo_inc)):
            return False
        if self.hi is not None and (v > self.hi or (v == self.hi and not self.hi_inc)):
            return False
        return True


@dataclass
class Quantity:
    value: float
    unit: str
    text: str


def norm_unit(raw):
    raw = raw.lower().strip()
    if raw in ("rm", "myr", "ringgit", "bucks", "dollars"):
        return "rm"
    raw = re.sub(r"s$", "", raw)
    return UNIT_NAMES.get(raw, raw)


def to_number(token):
    token = token.lower()
    return float(WORDS[token]) if token in WORDS else float(token.replace(",", ""))


def fmt(v):
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def label(value, unit):
    name = unit.replace("_", " ")
    return f"{fmt(value)} {name[:-1] if value == 1 and name.endswith('s') else name}"


# What the employee said
QTY = re.compile(
    rf"(?:\b(?P<cur>rm|myr)\s*(?P<n1>{NUM})(?:\.\d+)?"
    rf"|\b(?P<n2>{NUM}|{WORD_RE})(?:\.\d+)?\s*-?\s*(?:[a-z]+\s+)??(?P<unit>{UNIT}|ringgit|bucks|dollars)\b)", re.I)
GRADE_Q = re.compile(r"\bgrade\s*(\d+)\b", re.I)


def quantities(question):
    out, seen = [], set()
    for m in QTY.finditer(question):
        if m.group("cur"):
            q = Quantity(to_number(m.group("n1")), "rm", f"RM {fmt(to_number(m.group('n1')))}")
        else:
            unit = norm_unit(m.group("unit"))
            value = to_number(m.group("n2"))
            q = Quantity(value, unit, "RM " + fmt(value) if unit == "rm" else label(value, unit))
        if (q.value, q.unit) not in seen:
            seen.add((q.value, q.unit))
            out.append(q)
    for m in GRADE_Q.finditer(question):
        q = Quantity(float(m.group(1)), "grade", f"Grade {m.group(1)}")
        if (q.value, q.unit) not in seen:
            seen.add((q.value, q.unit))
            out.append(q)
    return out


# What the clause says
def _amounts(line):
    default = None
    tag = TAG_UNIT.search(line)
    if tag:
        default = norm_unit(tag.group(1))
    found = []
    for m in AMOUNT.finditer(line):
        unit = "rm" if m.group("cur") else (norm_unit(m.group("unit")) if m.group("unit") else default)
        if unit is None:
            continue
        before = line[:m.start()]
        op = None
        cstart = m.start()
        for pattern, name in COMPARATORS:
            cm = re.search(pattern, before, re.I)
            if cm:
                op, cstart = name, cm.start()
                break
        suffix = (m.group("suf1") or m.group("suf2") or "").lower()
        if suffix:
            op = SUFFIX_OPS[suffix]
        found.append(dict(value=to_number(m.group("num")), unit=unit, op=op, start=cstart, end=m.end(), pos=m.start()))
    return found


def conditions(text):
    """Every recognisable numeric condition in a clause or table text."""
    out = []
    for line in text.lower().split("\n"):
        amounts = _amounts(line)
        i = 0
        while i < len(amounts):
            a = amounts[i]
            nxt = amounts[i + 1] if i + 1 < len(amounts) else None
            between = line[a["end"]:nxt["pos"]] if nxt else ""
            # a range written as "above 2,000 and up to 10,000", "from 5,000 to 50,000" or "5,000 to 50,000"
            if nxt and nxt["unit"] == a["unit"] and nxt["op"] in ("<=", "to") and (
                    a["op"] in (">", ">=", "from") or (a["op"] is None and nxt["op"] == "to")) \
                    and re.fullmatch(r"\s*(and|but|,)?\s*(up to|no more than|not more than|not exceeding|to)?\s*", between + " "):
                out.append(Condition(a["unit"], a["value"], a["op"] != ">", nxt["value"], True,
                                     line[a["start"]:nxt["end"]].strip()))
                i += 2
                continue
            phrase = line[a["start"]:a["end"]].strip()
            if a["op"] == "<":
                out.append(Condition(a["unit"], hi=a["value"], hi_inc=False, phrase=phrase))
            elif a["op"] == "<=":
                out.append(Condition(a["unit"], hi=a["value"], hi_inc=True, phrase=phrase))
            elif a["op"] == ">":
                out.append(Condition(a["unit"], lo=a["value"], lo_inc=False, phrase=phrase))
            elif a["op"] in (">=", "from"):
                out.append(Condition(a["unit"], lo=a["value"], lo_inc=True, phrase=phrase))
            i += 1
        for m in GRADE_RANGE.finditer(line):
            out.append(Condition("grade", float(m.group(1)), True, float(m.group(2)), True, m.group(0)))
        for m in GRADE_UP.finditer(line):
            out.append(Condition("grade", float(m.group(1)), True, None, True, m.group(0)))
        for m in GRADE_PAIR.finditer(line):
            if "to" not in m.group(0) and float(m.group(2)) == float(m.group(1)) + 1:
                out.append(Condition("grade", float(m.group(1)), True, float(m.group(2)), True, m.group(0)))
    return out


def convert(q, unit):
    """The question's figure expressed in the condition's unit, or None when they cannot be compared."""
    if q.unit == unit:
        return q.value, None
    if q.unit in DAY_UNITS and unit in DAY_UNITS and "days" in (q.unit, unit):
        return q.value, None
    if q.unit == "weeks" and unit in ("working_days", "days"):
        return q.value * 5, f"{fmt(q.value * 5)} working days"
    return None


def threshold_hints(question, clauses, limit=14):
    """clauses is an iterable of (label, text). Returns a block of sentences, or '' when nothing applies."""
    qs = quantities(question)
    if not qs:
        return ""
    lines = []
    for label, text in clauses:
        for cond in conditions(text):
            for q in qs:
                got = convert(q, cond.unit)
                if got is None:
                    continue
                value, note = got
                ok = cond.holds(value)
                what = q.text if note is None else f"{q.text} ({note})"
                lines.append(f"- [{label}] condition '{cond.phrase}': the employee's {what} "
                             f"{'MEETS' if ok else 'does NOT meet'} it")
    return "\n".join(lines[:limit])
