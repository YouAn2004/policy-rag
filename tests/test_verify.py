

def test_spelled_out_number_in_question_counts_as_supported():
    from policy_rag.verify import verify_structure
    v = verify_structure("A 4-year service period gives 16 days [POL-02 §1.1].", {"pol-02 §1.1"},
                         "[POL-02 §1.1] 16 days for less than 5 years", "I joined four years ago. How many days?")
    assert v["unsupported_numbers"] == []
    v = verify_structure("You get 9 days [POL-02 §1.1].", {"pol-02 §1.1"},
                         "[POL-02 §1.1] 16 days", "I joined four years ago. How many days?")
    assert v["unsupported_numbers"] == ["9"]


import pytest  # noqa: E402

from policy_rag.verify import says_silent  # noqa: E402


@pytest.mark.parametrize("text", [
    "The policy does not specify different office hours during Ramadan [POL-03 §1.1].",
    "No office hours during Ramadan are specified in the provided policies [POL-03 §1.1].",
    "No, the clauses do not specify how soon HR must start investigating a complaint [POL-14 §3.2].",
    "No [POL-14 §3.2] provides the timeline for investigations, not for starting them.",
    "There is no information about this in the clauses provided.",
])
def test_answers_that_say_the_policy_is_silent_are_detected(text):
    assert says_silent(text)


@pytest.mark.parametrize("text", [
    "You get 16 days of annual leave [POL-02 §1.1].",
    "Sabbatical leave is not provided by the company [POL-02 §5.1].",
    "The company does not provide a home office allowance [POL-03 §4.2].",
    "No, alcohol is not reimbursable [POL-04 §3.1].",
    "Cryptocurrency payments are excluded from reimbursement [POL-04 §2.4].",
])
def test_answers_that_state_a_rule_are_not_treated_as_silent(text):
    assert not says_silent(text)
