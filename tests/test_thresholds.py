"""The comparator is plain code, so these tests use the real handbook clauses and the questions that fooled the model."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from policy_rag import config  # noqa: E402
from policy_rag.parsing import parse_folder  # noqa: E402
from policy_rag.thresholds import conditions, quantities, threshold_hints  # noqa: E402


@pytest.fixture(scope="module")
def clause():
    chunks = [c for _, cs in parse_folder(config.HANDBOOK_DIR) for c in cs if c.meta.status == "current"]
    texts = {c.cite_key: c.text for c in chunks}
    return lambda label: (label, texts[label])


def verdicts(question, clause, *labels):
    """{(label, condition phrase): True/False} for the given clauses."""
    out = {}
    for line in threshold_hints(question, [clause(l) for l in labels], limit=99).split("\n"):
        if not line:
            continue
        m = re.match(r"- \[(.+?)\] condition '(.+?)': .* (MEETS|does NOT meet) it", line)
        out[(m.group(1), m.group(2))] = m.group(3) == "MEETS"
    return out


@pytest.mark.parametrize("question, expected", [
    ("A supplier gave me a gift worth RM 350. What should I do?", [(350, "rm")]),
    ("a vendor sent me a hamper worth about 400 bucks", [(400, "rm")]),
    ("I joined four years ago", [(4, "years")]),
    ("I have been here 3 years", [(3, "years")]),
    ("she is a 4-year employee", [(4, "years")]),
    ("how much notice for taking just one day off", [(1, "days")]),
    ("notice for two weeks of leave", [(2, "weeks")]),
    ("a 9 hour flight", [(9, "hours")]),
    ("I have 8 unused days", [(8, "days")]),
    ("my claim is RM 9,000", [(9000, "rm")]),
    ("a Grade 7 employee", [(7, "grade")]),
    ("can i wfh everyday?", []),
    ("Can I take a sabbatical?", []),
])
def test_quantities_read_from_questions(question, expected):
    assert [(q.value, q.unit) for q in quantities(question)] == [(float(v), u) for v, u in expected]


def test_the_gift_bands_that_fooled_the_model(clause):
    for question in ("A supplier gave me a gift worth RM 350.", "a vendor sent me a hamper worth about 400 bucks"):
        v = verdicts(question, clause, "POL-08 §2.1", "POL-08 §2.2", "POL-08 §2.3", "POL-08 Table: Gift thresholds")
        assert v[("POL-08 §2.1", "up to rm 200")] is False
        assert v[("POL-08 §2.2", "more than rm 200")] is True
        assert v[("POL-08 §2.3", "more than rm 500")] is False
        assert v[("POL-08 Table: Gift thresholds", "above 200 and up to 500")] is True
    v = verdicts("Can I keep a RM 600 gift?", clause, "POL-08 §2.2", "POL-08 §2.3")
    assert v[("POL-08 §2.3", "more than rm 500")] is True


def test_years_of_service_tiers(clause):
    for question, tier_one in (("I joined four years ago", True), ("I have been here 3 years", True), ("after 6 years of service", False)):
        v = verdicts(question, clause, "POL-02 §1.1", "POL-02 §1.2")
        assert v[("POL-02 §1.1", "less than 5 years")] is tier_one
        assert v[("POL-02 §1.2", "5 or more years")] is (not tier_one)


def test_leave_notice_bands(clause):
    one = verdicts("notice for just one day off next week", clause, "POL-02 §2.1", "POL-02 §2.2")
    assert one[("POL-02 §2.1", "3 working days or fewer")] is True
    assert one[("POL-02 §2.2", "more than 5 consecutive working days")] is False
    weeks = verdicts("How much notice do I need to give for two weeks of leave?", clause, "POL-02 §2.1", "POL-02 §2.2")
    assert weeks[("POL-02 §2.1", "3 working days or fewer")] is False
    assert weeks[("POL-02 §2.2", "more than 5 consecutive working days")] is True
    assert "2 weeks (10 working days)" in threshold_hints("two weeks of leave", [clause("POL-02 §2.2")])


def test_money_ranges_including_tables(clause):
    v = verdicts("My expense claim is RM 9,000", clause, "POL-04 §2.1", "POL-04 §2.2", "POL-04 §2.3", "POL-04 Table: Approval matrix")
    assert v[("POL-04 §2.2", "above rm 2,000 and up to rm 10,000")] is True
    assert v[("POL-04 §2.1", "up to rm 2,000")] is False and v[("POL-04 §2.3", "above rm 10,000")] is False
    assert v[("POL-04 Table: Approval matrix", "above 2,000 and up to 10,000")] is True
    p = verdicts("a RM 20,000 purchase", clause, "POL-12 §1.1", "POL-12 §1.2", "POL-12 §1.3", "POL-12 Table: Purchasing thresholds")
    assert p[("POL-12 §1.2", "from rm 5,000 to rm 50,000")] is True
    assert p[("POL-12 Table: Purchasing thresholds", "5,000 to 50,000")] is True
    assert p[("POL-12 §1.1", "below rm 5,000")] is False and p[("POL-12 §1.3", "above rm 50,000")] is False
    assert verdicts("a RM 60,000 purchase", clause, "POL-12 §1.3")[("POL-12 §1.3", "above rm 50,000")] is True


def test_flight_length_and_deadlines(clause):
    v = verdicts("I am flying 7 hours to Sydney", clause, "POL-05 §2.1", "POL-05 §2.2")
    assert v[("POL-05 §2.1", "under 6 hours")] is False and v[("POL-05 §2.2", "6 hours or more")] is True
    late = verdicts("My laptop was stolen 3 hours ago", clause, "POL-06 §2.4")
    assert late[("POL-06 §2.4", "within 2 hours")] is False
    assert verdicts("found it 1 hour ago", clause, "POL-06 §2.4")[("POL-06 §2.4", "within 2 hours")] is True


def test_grade_bands(clause):
    v = verdicts("What is the notice period for a Grade 7 employee?", clause, "POL-11 §3.3")
    assert v[("POL-11 §3.3", "grades 1 to 5")] is False and v[("POL-11 §3.3", "grades 6 and above")] is True
    b = verdicts("target bonus for a Grade 5 employee", clause, "POL-10 §2.1")
    assert b[("POL-10 §2.1", "grades 4 to 6")] is True
    assert b[("POL-10 §2.1", "grades 1 to 3")] is False and b[("POL-10 §2.1", "grades 7 and 8")] is False


def test_nothing_is_said_without_matching_units_or_figures(clause):
    assert threshold_hints("can i wfh everyday?", [clause("POL-03 §2.2")]) == ""
    assert threshold_hints("a gift worth RM 350", [clause("POL-02 §2.1")]) == ""  # money against days
    assert threshold_hints("can i work from bali for a month", [clause("POL-03 §3.1")]) == ""  # months against working days
    assert threshold_hints("a 3 working days trip", [clause("POL-04 §1.2")]) == ""  # working against calendar days


def test_limit_and_empty_clauses(clause):
    many = [clause(f"POL-08 §2.{i}") for i in (1, 2, 3)] * 5
    assert len(threshold_hints("a gift worth RM 350", many, limit=4).split("\n")) == 4
    assert conditions("Employees must wear smart casual clothes.") == []
