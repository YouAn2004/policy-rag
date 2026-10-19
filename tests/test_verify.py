

def test_spelled_out_number_in_question_counts_as_supported():
    from policy_rag.verify import verify_structure
    v = verify_structure("A 4-year service period gives 16 days [POL-02 §1.1].", {"pol-02 §1.1"},
                         "[POL-02 §1.1] 16 days for less than 5 years", "I joined four years ago. How many days?")
    assert v["unsupported_numbers"] == []
    v = verify_structure("You get 9 days [POL-02 §1.1].", {"pol-02 §1.1"},
                         "[POL-02 §1.1] 16 days", "I joined four years ago. How many days?")
    assert v["unsupported_numbers"] == ["9"]
