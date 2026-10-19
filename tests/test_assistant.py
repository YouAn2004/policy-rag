"""Pipeline tests with a scripted fake model. They check control flow and safety, not model quality."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from policy_rag import config  # noqa: E402
from policy_rag.assistant import PolicyAssistant, contact_for  # noqa: E402
from policy_rag.evaluate import run_mode  # noqa: E402
from policy_rag.evaluate_e2e import fact_check  # noqa: E402
from policy_rag.index import PolicyIndex  # noqa: E402
from policy_rag.judge import find_clause, labels_in  # noqa: E402
from policy_rag.llm import parse_json  # noqa: E402
from policy_rag.parsing import parse_folder  # noqa: E402
from policy_rag.retrieve import Retriever  # noqa: E402
from policy_rag.verify import extract_citations, verify_structure  # noqa: E402
from test_retrieval import FakeEmbedder, FakeReranker  # noqa: E402


class ScriptedLLM:
    """Returns canned replies per purpose. A list means one reply per call, in order."""

    def __init__(self, **replies):
        self.replies = {k: (list(v) if isinstance(v, list) else [v]) for k, v in replies.items()}
        self.calls = []

    def complete(self, prompt, system=None, purpose="", json_mode=False):
        self.calls.append((purpose, prompt))
        queue = self.replies[purpose]
        return queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.fixture(scope="module")
def retriever():
    chunks = [c for _, cs in parse_folder(config.HANDBOOK_DIR) for c in cs]
    return Retriever(PolicyIndex.build(chunks, FakeEmbedder(), "fake"), FakeEmbedder(), FakeReranker())


def bot(retriever, llm, rewrite=False):
    return PolicyAssistant(retriever, llm, "dense", rewrite)


OK_JUDGE = '{"clause": "POL-02 §1.1", "reason": "clause found"}'
HOME_JUDGE = '{"clause": "POL-03 §4.2", "reason": "allowance clause"}'
OK_SUPPORT = '{"supported": true, "problems": []}'


def test_parse_json_variants():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('Sure! {"answerable": false} done') == {"answerable": False}
    assert parse_json("nonsense") == {}


def test_extract_citations_formats():
    t = "Yes [POL-05 §3.2][POL-04 §4.1]. Also [POL-02 v3.1 §1.4, POL-08 §2.2] and [POL-04 Table: Approval matrix]."
    assert extract_citations(t) == ["POL-05 §3.2", "POL-04 §4.1", "POL-02 §1.4", "POL-08 §2.2", "POL-04 Table: Approval matrix"]


def test_numeric_check_catches_invented_number():
    ctx = "[POL-04 §2.2] Claims above RM 2,000 and up to RM 10,000 are approved by the department head."
    good = verify_structure("The department head approves RM 5,000 claims [POL-04 §2.2].", {"pol-04 §2.2"}, ctx, "claim of RM 5,000")
    bad = verify_structure("The limit is RM 7,500 [POL-04 §2.2].", {"pol-04 §2.2"}, ctx, "claim of RM 5,000")
    assert good["unsupported_numbers"] == [] and bad["unsupported_numbers"] == ["7500"]
    steps = verify_structure("1. Tell your manager [POL-04 §2.2]\n2. Submit within 30 days [POL-04 §2.2]", {"pol-04 §2.2"}, ctx + " 30 days", "q")
    assert steps["unsupported_numbers"] == []  # list markers are not figures


def test_refusal_skips_generation_and_names_contact(retriever):
    llm = ScriptedLLM(judge='{"clause": "none", "reason": "no clause"}')
    r = bot(retriever, llm).ask("Can I bring my dog to the office?", "employee")
    assert r.status == "refused" and "@meridianworks.example" in r.text
    assert [c[0] for c in llm.calls] == ["judge"]  # no answer call was made


def test_good_answer_is_answered_with_resolved_citations(retriever):
    llm = ScriptedLLM(judge=OK_JUDGE, support=OK_SUPPORT,
                      answer="You get 16 days of annual leave per year [POL-02 §1.1].")
    r = bot(retriever, llm).ask("How many days of annual leave do I get with 3 years of service?", "employee")
    assert r.status == "answered"
    assert r.citations and r.citations[0]["label"] == "POL-02 §1.1" and r.citations[0]["version"] == "3.1"


def test_uncited_answer_is_retried_once_then_flagged(retriever):
    llm = ScriptedLLM(judge=OK_JUDGE, support=OK_SUPPORT, answer=["You get 16 days.", "You still get 16 days."])
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee")
    assert [c[0] for c in llm.calls].count("answer") == 2
    assert r.status == "flagged" and r.verification["uncited"]


def test_retry_fixes_invalid_citation(retriever):
    llm = ScriptedLLM(judge=OK_JUDGE, support=OK_SUPPORT,
                      answer=["16 days [POL-99 §1.1].", "16 days [POL-02 §1.1]."])
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee")
    assert r.status == "answered"
    retry_prompt = [p for purpose, p in llm.calls if purpose == "answer"][1]
    assert "not in the clauses provided" in retry_prompt


def test_unsupported_claim_from_support_judge_flags_answer(retriever):
    llm = ScriptedLLM(judge=OK_JUDGE, answer="You get 16 days [POL-02 §1.1].",
                      support='{"supported": false, "problems": ["invented"]}')
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee")
    assert r.status == "flagged"


def test_restricted_text_never_reaches_the_prompt_for_employee(retriever):
    llm = ScriptedLLM(judge='{"clause": "none", "reason": "no clause"}')
    bot(retriever, llm).ask("What bonus percentage does a Grade 5 employee get?", "employee")
    prompt = llm.calls[0][1].lower()
    # Public policies may mention a restricted policy by number (POL-14 points to POL-11).
    # What must never appear is restricted clause content or a restricted section header.
    assert "== pol-10" not in prompt and "== pol-11" not in prompt and "== pol-09" not in prompt
    assert "target bonus" not in prompt and "calibration" not in prompt and "notice after confirmation" not in prompt


def test_context_has_dates_for_precedence_and_no_superseded(retriever):
    llm = ScriptedLLM(judge='{"clause": "none", "reason": "no clause"}')
    bot(retriever, llm).ask("meal allowance on a domestic business trip", "employee")
    prompt = llm.calls[0][1]
    assert "effective 2026-03-01" in prompt or "effective 2025-07-01" in prompt
    assert "leave policy, version 3.0" not in prompt


def test_rewrite_adds_second_query_and_still_filters(retriever):
    llm = ScriptedLLM(rewrite="alcohol reimbursement client entertainment", judge='{"clause": "none", "reason": "no clause"}')
    r = bot(retriever, llm, rewrite=True).ask("can i expense a beer with the client", "employee")
    assert r.rewritten == "alcohol reimbursement client entertainment"
    assert all("POL-10" not in c for c in r.retrieved)


def test_rewrite_failure_falls_back_to_original(retriever):
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("model down")

    from policy_rag.rewrite import rewrite_query
    assert rewrite_query(Boom(), "my question") == "my question"


def test_run_mode_with_rewriter(retriever):
    q = [dict(id="x", type="t", role="employee", question="beer with client", answerable=True,
              expected=["POL-04#3.2"], forbidden=[], forbidden_docs=[])]
    rows = run_mode(retriever, q, "dense_rewrite", rewriter=lambda text: "alcohol is not reimbursable under any circumstances")
    assert rows[0]["rewrite"].startswith("alcohol") and rows[0]["rank"] is not None


def test_contact_mapping():
    assert contact_for("Human Resources and Finance").startswith("Human Resources")
    assert "finance@" in contact_for("Finance")
    assert "security@" in contact_for("IT Security")
    assert "hr@" in contact_for("")


def test_fact_check_logic():
    q = dict(must_contain=["16"], must_not_contain=["14 days"])
    assert fact_check(q, "You get 16 days.") is True
    assert fact_check(q, "You get 16 days, not 14 days.") is False
    assert fact_check({}, "anything") is None
    assert fact_check(dict(must_contain_any=[["refus", "return"]]), "It must be returned.") is True


def test_support_failure_triggers_one_regeneration_with_feedback(retriever):
    llm = ScriptedLLM(judge=HOME_JUDGE,
                      answer=["No allowance [POL-03 §4.2].", "Yes, RM 500 once [POL-03 §4.2]."],
                      support=['{"supported": false, "problems": ["says no allowance but clause provides one"]}', OK_SUPPORT])
    r = bot(retriever, llm).ask("Is there an allowance for a home office?", "employee")
    answers = [p for purpose, p in llm.calls if purpose == "answer"]
    assert len(answers) == 2 and "says no allowance but clause provides one" in answers[1]
    assert r.status == "answered" and "RM 500" in r.text


def test_judge_only_stops_before_generation(retriever):
    llm = ScriptedLLM(judge=OK_JUDGE)
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee", judge_only=True)
    assert r.status == "answered" and [c[0] for c in llm.calls] == ["judge"]


def test_refusal_records_total_time(retriever):
    r = bot(retriever, ScriptedLLM(judge='{"clause": "none", "reason": "no clause"}')).ask("dog in the office?", "employee")
    assert "total" in r.timings and r.timings["total"] >= 0


# The judge points at a clause
AVAILABLE = {"pol-04 §3.2": object(), "pol-12 table: purchasing thresholds": object()}


def judge_with(reply):
    return find_clause(ScriptedLLM(judge=reply), "q", "ctx", AVAILABLE)


def test_judge_accepts_a_clause_that_is_in_the_context():
    v = judge_with('{"clause": "POL-04 §3.2", "reason": "alcohol is not reimbursable"}')
    assert v.answerable and v.clause == "POL-04 §3.2"


def test_judge_none_means_not_answerable():
    for reply in ('{"clause": "none", "reason": "different topic"}', '{"clause": "None"}', '{"clause": ""}'):
        v = judge_with(reply)
        assert not v.answerable and v.reason


def test_judge_clause_that_is_not_in_the_context_is_refused():
    v = judge_with('{"clause": "POL-99 §9.9", "reason": "made up"}')
    assert not v.answerable and "not in the context" in v.reason


def test_judge_unreadable_reply_is_refused():
    v = judge_with("I think the answer is yes")
    assert not v.answerable and "could not be read" in v.reason


def test_judge_tolerates_label_formatting():
    for clause in ("[POL-04 §3.2]", "POL-04 3.2", "POL-04 §3.2.", "pol-04 § 3.2"):
        assert labels_in(clause.strip("[].")) == ["POL-04 §3.2"] or labels_in(clause) == ["POL-04 §3.2"], clause
    assert judge_with('{"clause": "POL-04 3.2"}').answerable
    assert judge_with('{"clause": ["POL-04 §3.2", "POL-05 §1.1"]}').answerable  # one valid label is enough
    assert judge_with('{"clause": "POL-12 Table: Purchasing thresholds"}').answerable


def test_a_made_up_clause_leads_to_a_refusal_in_the_pipeline(retriever):
    llm = ScriptedLLM(judge='{"clause": "POL-99 §9.9", "reason": "made up"}')
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee")
    assert r.status == "refused" and [c[0] for c in llm.calls] == ["judge"]


# The answer step can abstain
@pytest.mark.parametrize("reply", ["NOT_IN_POLICY", "not_in_policy.", "  Not in policy", "NOT_IN_POLICY\nThe clauses do not say."])
def test_answer_step_can_abstain_and_that_is_a_refusal(retriever, reply):
    llm = ScriptedLLM(judge=OK_JUDGE, answer=reply)
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee")
    assert r.status == "refused" and "@meridianworks.example" in r.text
    assert [c[0] for c in llm.calls] == ["judge", "answer"]  # no support check, no retry
    assert "do not contain a rule" in r.refusal_reason and "total" in r.timings


def test_ordinary_answers_are_not_mistaken_for_abstaining(retriever):
    llm = ScriptedLLM(judge=OK_JUDGE, support=OK_SUPPORT, answer="You get 16 days [POL-02 §1.1].")
    assert bot(retriever, llm).ask("How many days of annual leave do I get?", "employee").status == "answered"
    from policy_rag.assistant import ABSTAIN
    assert not ABSTAIN.match("No, this is not in the policy for managers [POL-02 §1.1].")


# Exact threshold comparisons reach the model
class FirstLabelLLM:
    """The judge names the first clause label it can see, and the answer cites that same label."""

    def __init__(self):
        self.calls, self.label = [], None

    def complete(self, prompt, system=None, purpose="", json_mode=False):
        self.calls.append((purpose, prompt))
        if purpose == "judge":
            m = re.search(r"\[(POL-\d\d §[\d.]+)\]", prompt)
            self.label = m.group(1) if m else None
            return json.dumps({"clause": self.label or "none", "reason": "x"})
        if purpose == "answer":
            return f"You should declare it [{self.label}]."
        return OK_SUPPORT

    def prompts(self, purpose):
        return [p for pu, p in self.calls if pu == purpose]


GIFT = "A supplier gave me a gift worth RM 350. What should I do?"


def test_hints_reach_judge_answer_and_support_prompts(retriever):
    llm = FirstLabelLLM()
    r = bot(retriever, llm).ask(GIFT, "employee")
    assert r.checks and "RM 350" in r.checks
    for purpose in ("judge", "answer", "support"):
        prompt = llm.prompts(purpose)[0]
        assert "Checked facts" in prompt and "RM 350" in prompt, purpose


def test_no_figures_means_no_checked_facts(retriever):
    llm = FirstLabelLLM()
    r = bot(retriever, llm).ask("Can I report harassment anonymously?", "employee")
    assert r.checks == ""
    assert all("Checked facts" not in p for _, p in llm.calls)


def test_hints_can_be_switched_off(retriever, monkeypatch):
    monkeypatch.setattr(config, "THRESHOLD_HINTS", False)
    llm = FirstLabelLLM()
    r = bot(retriever, llm).ask(GIFT, "employee")
    assert r.checks == "" and all("Checked facts" not in p for _, p in llm.calls)


def test_prompts_without_checks_are_unchanged():
    from policy_rag import prompts
    assert "Checked facts" not in prompts.answer_user("q", "ctx")
    assert "Checked facts" not in prompts.judge_user("q", "ctx")
    assert "Checked facts" in prompts.support_user("a", "ctx", "q", "- [POL-01 §1.1] x")


@pytest.mark.parametrize("reply", [
    "The policy does not specify different office hours during Ramadan [POL-02 §1.1].",
    "No office hours during Ramadan are specified in the provided policies [POL-02 §1.1].",
])
def test_an_answer_that_says_the_policy_is_silent_becomes_a_refusal(retriever, reply):
    llm = ScriptedLLM(judge=OK_JUDGE, answer=reply)
    r = bot(retriever, llm).ask("How many days of annual leave do I get?", "employee")
    assert r.status == "refused" and "@meridianworks.example" in r.text
    assert [c[0] for c in llm.calls] == ["judge", "answer"]


def test_progress_callback_reports_the_stages_in_order(retriever):
    seen = []
    llm = ScriptedLLM(judge=OK_JUDGE, support=OK_SUPPORT, answer="You get 16 days [POL-02 §1.1].")
    r = bot(retriever, llm, rewrite=False).ask("How many days of annual leave do I get?", "employee", progress=seen.append)
    assert r.status == "answered"
    assert seen == ["search", "judge", "answer", "verify"]


def test_progress_callback_stops_at_judge_for_a_refusal(retriever):
    seen = []
    llm = ScriptedLLM(judge='{"clause": "none", "reason": "nothing"}')
    bot(retriever, llm).ask("Can I bring my dog to the office?", "employee", progress=seen.append)
    assert seen == ["search", "judge"]
