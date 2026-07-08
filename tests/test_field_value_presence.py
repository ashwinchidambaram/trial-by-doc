from tbdoc.scoring.scorers import is_extractive_gold, field_value_presence


def test_numeric_value_present_exact_and_formatted():
    md = "Total Due .......... $8,500.00 for services rendered"
    assert field_value_presence(md, ["nexus_tech_amount_paid=8500"]) == 1.0

def test_value_absent_scores_zero():
    md = "The quick brown fox jumps over the lazy dog."
    assert field_value_presence(md, ["nexus_tech_amount_paid=8500"]) == 0.0

def test_partial_multifield_recall():
    md = "Name: Jane Roe    Amount: 8500"
    # two gold fields; only the amount is present -> 0.5
    got = field_value_presence(md, ["amount=8500;name=John Doe"])
    assert abs(got - 0.5) < 1e-9

def test_string_value_garbled_matches_via_fuzzy_window():
    # 'Jane Rox' is NOT a literal substring of gold 'Jane Roe' (last char differs), so this
    # forces the ANLS sliding-window path (not exact substring); it sits at the END of the
    # markdown — the position the naive step-loop skipped.
    md = "Applicant: Jane Rox"
    assert field_value_presence(md, ["name=Jane Roe"], anls_threshold=0.8) == 1.0

def test_boolean_alias_present():
    md = "Checkbox for exemption: [X]"
    assert field_value_presence(md, ["exempt=true"]) == 1.0

def test_derived_answer_is_not_extractive():
    assert is_extractive_gold("How many line items are on the invoice?", ["count=7"]) is False

def test_surface_value_is_extractive():
    assert is_extractive_gold("What is the amount paid?", ["amount=8500"]) is True

def test_long_freetext_gold_not_extractive():
    long = "x" * 100
    assert is_extractive_gold("Summarize the letter", [f"summary={long}"]) is False
