"""Unit tests for the Phase 7 eligibility rule engine.

No FastAPI, no Groq. Criteria are taken from the sample Income Certificate
regulation wording, not invented limits.
"""

from ai_modules.eligibility_nudge.documents import (
    document_covers_requirement,
    missing_required_documents,
)
from ai_modules.eligibility_nudge.errors import InvalidAnswersError
from ai_modules.eligibility_nudge.evaluator import (
    RESULT_ELIGIBLE,
    RESULT_MANUAL_REVIEW,
    RESULT_POTENTIALLY_INELIGIBLE,
    coerce_answer,
    evaluate_rules,
    validate_answers,
)
from ai_modules.eligibility_nudge.questionnaire import EligibilityQuestion
from ai_modules.eligibility_nudge.rules import extract_programme, questionnaire_for_programme
import pytest

SAMPLE_CRITERIA = (
    "An applicant is eligible for an income certificate under this example "
    "scheme if the total annual household income is below 2,50,000 rupees, "
    "the applicant has been a resident of the district for at least one year, "
    "and the applicant is not already holding a valid income certificate "
    "issued in the same financial year."
)
SAMPLE_DOCUMENTS = (
    "The applicant must submit proof of identity, proof of residence, and "
    "proof of income."
)

PASSING = {
    "annual_household_income": 180_000,
    "resident_of_district_at_least_one_year": True,
    "holds_income_certificate_this_year": False,
}


def sample_programme():
    return extract_programme(
        eligibility_criteria=SAMPLE_CRITERIA,
        required_documents=SAMPLE_DOCUMENTS,
        scheme_name="Example Income Certificate Scheme",
        regulation_id=1,
    )


def test_questionnaire_contains_only_supported_sample_criteria():
    programme = sample_programme()
    fields = {question.field_name for question in programme.questions}
    assert fields == {
        "annual_household_income",
        "resident_of_district_at_least_one_year",
        "holds_income_certificate_this_year",
    }
    assert programme.unsupported == ()
    assert "Proof of identity" in programme.required_document_types
    assert "Proof of residence" in programme.required_document_types
    assert "Proof of income" in programme.required_document_types


def test_unparseable_criteria_are_manual_review():
    programme = extract_programme(
        eligibility_criteria="Applicants must be residents of the district.",
        required_documents=None,
        scheme_name="Ambiguous Scheme",
    )
    assert programme.rules == ()
    assert programme.unsupported
    result = evaluate_rules(programme, {})
    assert result.result == RESULT_MANUAL_REVIEW
    assert result.warning_issued is True


def test_passing_criteria_are_eligible():
    programme = sample_programme()
    questionnaire = questionnaire_for_programme(
        programme, regulation_id=1, scheme_name="Example"
    )
    answers = validate_answers(questionnaire, PASSING)
    result = evaluate_rules(programme, answers, missing_documents=[])
    assert result.result == RESULT_ELIGIBLE
    assert result.warning_issued is False
    assert result.failed_criteria == []


def test_failing_income_is_potentially_ineligible():
    programme = sample_programme()
    answers = dict(PASSING)
    answers["annual_household_income"] = 300_000
    result = evaluate_rules(programme, answers)
    assert result.result == RESULT_POTENTIALLY_INELIGIBLE
    assert result.warning_issued is True
    assert any("2,50,000" in item or "250,000" in item for item in result.failed_criteria)


def test_multiple_failures_are_reported():
    programme = sample_programme()
    answers = {
        "annual_household_income": 400_000,
        "resident_of_district_at_least_one_year": False,
        "holds_income_certificate_this_year": True,
    }
    result = evaluate_rules(programme, answers)
    assert result.result == RESULT_POTENTIALLY_INELIGIBLE
    assert len(result.failed_criteria) == 3


def test_same_input_same_result():
    programme = sample_programme()
    first = evaluate_rules(programme, PASSING)
    second = evaluate_rules(programme, PASSING)
    assert first.result == second.result
    assert first.failed_criteria == second.failed_criteria
    assert first.explanation == second.explanation


def test_answer_validation_rejects_bad_payloads():
    programme = sample_programme()
    questionnaire = questionnaire_for_programme(
        programme, regulation_id=1, scheme_name="Example"
    )
    with pytest.raises(InvalidAnswersError):
        validate_answers(questionnaire, {"annual_household_income": 1000})
    with pytest.raises(InvalidAnswersError):
        validate_answers(questionnaire, {**PASSING, "favourite_colour": "blue"})
    with pytest.raises(InvalidAnswersError):
        validate_answers(questionnaire, {**PASSING, "annual_household_income": "twelve"})
    with pytest.raises(InvalidAnswersError):
        validate_answers(
            questionnaire,
            {**PASSING, "resident_of_district_at_least_one_year": "maybe"},
        )


def test_invalid_choice_is_rejected():
    question = EligibilityQuestion(
        question_id="category",
        field_name="category",
        question_text="Category",
        answer_type="choice",
        options=("A", "B"),
    )
    with pytest.raises(InvalidAnswersError):
        coerce_answer(question, "C")
    assert coerce_answer(question, "A") == "A"


def test_malformed_date_is_rejected():
    question = EligibilityQuestion(
        question_id="issued_on",
        field_name="issued_on",
        question_text="Date",
        answer_type="date",
    )
    with pytest.raises(InvalidAnswersError):
        coerce_answer(question, "31-02-2026")


def test_required_documents_matching():
    required = ["Proof of identity", "Proof of residence", "Proof of income"]
    assert document_covers_requirement("Identity Proof", "Proof of identity")
    assert document_covers_requirement("Residence Proof", "Proof of residence")
    assert document_covers_requirement("Income Proof", "Proof of income")
    assert not document_covers_requirement("Income Certificate", "Proof of income")
    missing = missing_required_documents(required, ["Identity Proof"])
    assert "Proof of residence" in missing
    assert "Proof of income" in missing
    assert "Proof of identity" not in missing


def test_missing_documents_warn_but_do_not_flip_eligible_result():
    programme = sample_programme()
    result = evaluate_rules(
        programme, PASSING, missing_documents=["Proof of income"]
    )
    assert result.result == RESULT_ELIGIBLE
    assert result.warning_issued is True
    assert result.missing_documents == ["Proof of income"]
