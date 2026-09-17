import pytest

from app.semantic.catalog import build_questions
from app.semantic.parser import MalformedTypeSafeResponse, parse_answers
from tests.conftest import fake_answers, make_profile

LINES = {"L000": "Requirements:", "L001": "5+ years of Android development with Kotlin",
         "L002": "Active Secret clearance required for this role"}


def parse(profile, answers=None, questions=None):
    questions = questions or build_questions(profile, LINES)
    answers = answers if answers is not None else fake_answers(questions)
    return parse_answers(answers, questions, profile, LINES, model="m", requests=[], question_set_hash="h")


def test_parses_complete_answer_set():
    ev = parse(make_profile(required_technologies=["Kotlin"]))
    assert ev.role_family.value == "android_native"
    assert ev.android_relevance.levels == 5 and ev.android_relevance.normalized == 0
    assert ev.staff_ic_signal.derived_confidence == pytest.approx(0.8)
    assert len(ev.skills) == 18
    assert ev.skills["kmp"].requirement == ev.kmp_requirement
    assert set(ev.technologies) == {"kotlin"}
    assert [line.id for line in ev.lines] == ["L001", "L002"] and ev.all_lines == LINES
    assert ev.role_preference_fit is None and ev.location_match is None
    assert set(ev.evidence) == {"security_clearance_required", "us_citizenship_required", "work_authorization_signal",
                                "work_arrangement", "requires_relocation", "kmp_requirement", "min_years_required",
                                "seniority", "management_intensity"}
    assert ev.evaluator_version == "1.0.0" and ev.catalog_hash and ev.question_set_hash == "h"


def test_optional_fit_signals_parsed_when_asked():
    ev = parse(make_profile(preferred_roles=["Staff Android"], preferred_locations=["Remote"]))
    assert ev.role_preference_fit.levels == 4 and ev.location_match.value == "in_preferred_location"


def test_evidence_resolves_line_text_and_none():
    profile = make_profile()
    questions = build_questions(profile, LINES)
    answers = fake_answers(questions)
    answers["evidence.security_clearance_required"] = {"type": "choice", "choice": "L002", "confidence": 0.9,
                                                       "probabilities": {"L002": 0.9, "none": 0.1}}
    answers["evidence.seniority"] = {"type": "choice", "choice": "none", "probabilities": {"none": 1.0}, "confidence": 1}
    ev = parse(profile, answers, questions)
    assert ev.evidence["security_clearance_required"].text == LINES["L002"]
    assert ev.evidence["security_clearance_required"].probability == 0.9
    assert ev.evidence["seniority"].line_id is None and ev.evidence["seniority"].text is None


def test_score_normalized_and_int_keys():
    profile = make_profile()
    questions = build_questions(profile, LINES)
    answers = fake_answers(questions)
    answers["technical_fit"] = {"type": "score", "score": 3.0, "confidence": 0.8,
                                "probabilities": {0: 0, "1": 0, "2": 0.1, "3": 0.8, "4": 0.1}}
    ev = parse(profile, answers, questions)
    assert ev.technical_fit.normalized == 0.75 and ev.technical_fit.probabilities[3] == 0.8


@pytest.mark.parametrize("mutate", [
    lambda a: a.pop("role_family"),
    lambda a: a.__setitem__("role_family", {"type": "score", "score": 1, "probabilities": {}, "confidence": 1}),
    lambda a: a["role_family"].__setitem__("choice", "astronaut"),
    lambda a: a["role_family"]["probabilities"].__setitem__("astronaut", 0.1),
    lambda a: a.__setitem__("technical_fit", {"type": "score", "score": 1, "confidence": 1, "probabilities": {"0": 1}}),
    lambda a: a.__setitem__("staff_ic_signal", {"type": "noul", "noul": 1.5}),
    lambda a: a["technical_fit"].pop("confidence"),
])
def test_rejects_malformed(mutate):
    profile = make_profile()
    questions = build_questions(profile, LINES)
    answers = fake_answers(questions)
    mutate(answers)
    with pytest.raises(MalformedTypeSafeResponse):
        parse(profile, answers, questions)
