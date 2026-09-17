"""TypeSafe answers → SemanticJobEvaluation (spec §6.5). Strict: any deviation fails the evaluation."""

import math

from app.domain import (
    CandidateProfile,
    ChoiceSignal,
    Evidence,
    NoulSignal,
    RequestMeta,
    RequirementLine,
    ScoreSignal,
    SemanticJobEvaluation,
    SkillSignal,
)
from app.semantic.catalog import EVALUATOR_VERSION, EVIDENCE_TARGETS, Q, catalog_hash, technologies
from app.semantic.lines import eligible_ids


class MalformedTypeSafeResponse(Exception):
    pass


def _prob(x, where: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x) or not 0 <= x <= 1:
        raise MalformedTypeSafeResponse(f"{where}: invalid probability {x!r}")
    return float(x)


def _num(ans: dict, key: str, where: str) -> float:
    x = ans.get(key)
    if isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x):
        raise MalformedTypeSafeResponse(f"{where}: missing or invalid {key}")
    return float(x)


def choice_signal(ans: dict, options: list[str], where: str = "choice") -> ChoiceSignal:
    value = ans.get("choice")
    probs = ans.get("probabilities")
    if value not in options or not isinstance(probs, dict) or not set(probs) <= set(options):
        raise MalformedTypeSafeResponse(f"{where}: choice outside declared options")
    return ChoiceSignal(value=value, confidence=_prob(ans.get("confidence"), where),
                        probabilities={k: _prob(v, where) for k, v in probs.items()})


def score_signal(ans: dict, levels: int, where: str = "score") -> ScoreSignal:
    probs = ans.get("probabilities")
    if not isinstance(probs, dict):
        raise MalformedTypeSafeResponse(f"{where}: missing probabilities")
    try:
        probabilities = {int(k): _prob(v, where) for k, v in probs.items()}
    except ValueError as e:
        raise MalformedTypeSafeResponse(f"{where}: non-integer level key") from e
    if set(probabilities) != set(range(levels)):
        raise MalformedTypeSafeResponse(f"{where}: probabilities must cover levels 0..{levels - 1}")
    score = _num(ans, "score", where)
    if not 0 <= score <= levels - 1:
        raise MalformedTypeSafeResponse(f"{where}: score out of range")
    return ScoreSignal(score=score, levels=levels, normalized=score / (levels - 1), probabilities=probabilities,
                       confidence=_prob(ans.get("confidence"), where))


def noul_signal(ans: dict, where: str = "noul") -> NoulSignal:
    p = _prob(ans.get("noul"), where)
    return NoulSignal(probability=p, derived_confidence=abs(2 * p - 1))


def parse_answers(answers: dict[str, dict], questions: list[Q], profile: CandidateProfile, lines: dict[str, str], *,
                  model: str, requests: list[RequestMeta], question_set_hash: str) -> SemanticJobEvaluation:
    signals: dict[str, ChoiceSignal | ScoreSignal | NoulSignal] = {}
    for q in questions:
        ans = answers.get(q.id)
        if not isinstance(ans, dict) or ans.get("type") != q.kind:
            raise MalformedTypeSafeResponse(f"{q.id}: missing answer or wrong answer type")
        if q.kind == "choice":
            signals[q.id] = choice_signal(ans, q.options, q.id)
        elif q.kind == "score":
            signals[q.id] = score_signal(ans, q.levels, q.id)
        else:
            signals[q.id] = noul_signal(ans, q.id)

    def evidence(target: str) -> Evidence:
        sig = signals[f"evidence.{target}"]
        line_id = None if sig.value == "none" else sig.value
        return Evidence(line_id=line_id, text=lines.get(line_id) if line_id else None,
                        probability=sig.probabilities.get(sig.value, 0.0))

    skills = {s.id: SkillSignal(requirement=signals["kmp_requirement" if s.id == "kmp" else f"skill_req.{s.id}"],
                                evidence=signals[f"skill_ev.{s.id}"]) for s in profile.tracked_skills}
    static = {name: signals[name] for name in [
        "role_family", "android_relevance", "seniority", "title_level", "staff_ic_signal", "management_intensity",
        "kmp_requirement", "cross_platform_intensity", "domain", "work_arrangement", "requires_relocation",
        "security_clearance_required", "us_citizenship_required", "work_authorization_signal", "min_years_required",
        "technical_fit", "seniority_fit", "domain_fit"]}
    return SemanticJobEvaluation(
        **static,
        role_preference_fit=signals.get("role_preference_fit"),
        location_match=signals.get("location_match"),
        skills=skills,
        technologies={slug: signals[f"tech_centrality.{slug}"] for slug in technologies(profile.preferences)},
        lines=[RequirementLine(id=lid, text=lines[lid], kind=signals[f"line_kind.{lid}"],
                               skill=signals[f"line_skill.{lid}"], evidence=signals[f"line_ev.{lid}"])
               for lid in eligible_ids(lines)],
        all_lines=lines,
        evidence={target: evidence(target) for target in EVIDENCE_TARGETS},
        model=model, evaluator_version=EVALUATOR_VERSION, catalog_hash=catalog_hash(),
        question_set_hash=question_set_hash, requests=requests,
    )
