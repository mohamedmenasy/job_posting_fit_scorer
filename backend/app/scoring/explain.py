"""Explanation rule table (spec §7.9). Fixed templates only — no generated prose."""

from collections.abc import Callable
from dataclasses import dataclass

from app.domain import (
    CandidateProfile,
    ComponentResult,
    Explanation,
    Penalty,
    SemanticJobEvaluation,
    tech_slug,
)
from app.scoring.blockers import evidence_line
from app.scoring.config import ScoringConfig
from app.scoring.skills import evidence_level

YEARS = {"y0_2": (0, "0–2"), "y3_4": (3, "3–4"), "y5_7": (5, "5–7"), "y8_10": (8, "8–10"), "y11_plus": (11, "11+")}


def label(value: str) -> str:
    text = value.replace("_", " ")
    return text[:1].upper() + text[1:]


# text, signal ids, driving confidence (None = not hedged), evidence target
Hit = tuple[str, list[str], float | None, str | None]


@dataclass
class Ctx:
    sem: SemanticJobEvaluation
    profile: CandidateProfile
    cfg: ScoringConfig
    comps: dict[str, ComponentResult]


@dataclass
class Rule:
    section: str
    component: str | None
    fn: Callable[[Ctx], list[Hit]]


def _kmp_weak(c: Ctx) -> bool:
    kmp = c.sem.skills.get("kmp")
    return kmp is None or evidence_level(kmp.evidence.score) != "strong"


def _strong_skills(c: Ctx) -> list[Hit]:
    labels = {s.id: s.label for s in c.profile.tracked_skills}
    hits = [(sid, sig) for sid, sig in c.sem.skills.items()
            if sig.requirement.value in ("required", "preferred") and evidence_level(sig.evidence.score) == "strong"]
    if not hits:
        return []
    return [(f"Strong resume evidence for {', '.join(labels.get(sid, sid) for sid, _ in hits)}",
             [f"skill_ev.{sid}" for sid, _ in hits],
             min(min(sig.requirement.confidence, sig.evidence.confidence) for _, sig in hits), None)]


def _preferred_domain(c: Ctx) -> list[Hit]:
    d = c.sem.domain
    preferred = c.profile.preferences.preferred_domains
    if not preferred or d.p(*preferred) < 0.6:
        return []
    top = max(preferred, key=d.p)
    return [(f"Preferred domain: {label(top)}", ["domain"], d.confidence, None)]


def _arrangement(c: Ctx, strength: bool) -> list[Hit]:
    comp = c.comps["work_arrangement"]
    if not comp.applicable or (comp.value < 0.9 if strength else comp.value > 0.5):
        return []
    wa = c.sem.work_arrangement
    text = (f"{label(wa.value)}, matches your preference" if strength
            else f"{label(wa.value)}; you prefer {c.profile.preferences.remote_preference}")
    return [(text, ["work_arrangement"], comp.confidence, "work_arrangement")]


def _kmp_concern(c: Ctx) -> list[Hit]:
    k = c.sem.kmp_requirement
    if k.value not in ("required", "preferred") or k.p(k.value) < 0.6 or not _kmp_weak(c):
        return []
    text = f"KMP listed as {k.value}"
    if kmp := c.sem.skills.get("kmp"):
        text += f"; {evidence_level(kmp.evidence.score)} resume evidence"
    return [(text, ["kmp_requirement"], k.confidence, "kmp_requirement")]


def _title_vs_scope(c: Ctx) -> list[Hit]:
    t, s = c.sem.title_level, c.sem.seniority
    if (t.value == s.value or "unclear" in (t.value, s.value) or t.p(t.value) < 0.6 or s.p(s.value) < 0.6):
        return []
    return [(f"Title reads {label(t.value)}; scope reads {label(s.value)}", ["title_level", "seniority"],
             min(t.confidence, s.confidence), "seniority")]


def _years(c: Ctx) -> list[Hit]:
    y = c.sem.min_years_required
    have = c.profile.preferences.years_experience
    if have is None or y.value not in YEARS or y.p(y.value) < 0.6 or YEARS[y.value][0] <= have:
        return []
    return [(f"Asks {YEARS[y.value][1]} years; profile says {have:g}", ["min_years_required"], y.confidence,
             "min_years_required")]


def _score_rule(signal: str, text: str) -> Callable[[Ctx], list[Hit]]:
    def fn(c: Ctx) -> list[Hit]:
        s = getattr(c.sem, signal)
        return [(text.format(score=f"{s.score:.1f}", domain=label(c.sem.domain.value)), [signal], s.confidence, None)] \
            if s.score >= 3.0 else []
    return fn


RULES = [
    Rule("strength", "platform", lambda c: [("Primarily native Android", ["role_family"], c.sem.role_family.confidence, None)]
         if c.sem.role_family.value == "android_native" and c.sem.role_family.p("android_native") >= 0.6 else []),
    Rule("strength", "android", _score_rule("android_relevance", "Android is the main day-to-day work ({score}/4)")),
    Rule("strength", "technical", _strong_skills),
    Rule("strength", "technical", _score_rule("technical_fit", "Strong technical match ({score}/4)")),
    Rule("strength", "seniority", lambda c: [(f"Staff-level IC scope ({c.sem.staff_ic_signal.probability:.2f})",
                                              ["staff_ic_signal"], c.sem.staff_ic_signal.derived_confidence, None)]
         if c.sem.staff_ic_signal.probability >= 0.7
         and set(c.profile.preferences.preferred_levels) & {"staff", "principal", "architect"} else []),
    Rule("strength", "domain", _score_rule("domain_fit", "Background transfers to {domain} ({score}/4)")),
    Rule("strength", "domain", _preferred_domain),
    Rule("strength", "work_arrangement", lambda c: _arrangement(c, strength=True)),
    Rule("strength", None, lambda c: [("KMP is preferred, not required", ["kmp_requirement"], c.sem.kmp_requirement.confidence,
                                       "kmp_requirement")]
         if c.sem.kmp_requirement.value == "preferred" and c.sem.kmp_requirement.p("preferred") >= 0.6 and _kmp_weak(c) else []),
    Rule("strength", "technical", lambda c: [
        (f"Uses {t}", [f"tech_centrality.{tech_slug(t)}"], s.confidence, None)
        for t in c.profile.preferences.preferred_technologies
        if (s := c.sem.technologies.get(tech_slug(t))) and s.score >= 2.0]),
    Rule("concern", None, _kmp_concern),
    Rule("concern", None, _title_vs_scope),
    Rule("concern", None, lambda c: [("Work arrangement not stated", ["work_arrangement"], c.sem.work_arrangement.confidence,
                                      None)]
         if c.sem.work_arrangement.value == "unclear" and c.sem.work_arrangement.p("unclear") >= 0.6 else []),
    Rule("concern", None, lambda c: _arrangement(c, strength=False)),
    Rule("concern", None, _years),
    Rule("note", None, lambda c: [("Sponsorship: not stated", ["work_authorization_signal"], None, None)]
         if c.sem.work_authorization_signal.value == "not_stated" else []),
    Rule("note", None, lambda c: [("Security clearance: no explicit requirement detected", ["security_clearance_required"],
                                   None, None)]
         if c.sem.security_clearance_required.probability < 0.5 else []),
]


def explanations(sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig, *,
                 comps: list[ComponentResult], penalties: list[Penalty], blocker_concerns: list[Explanation],
                 stale_semantics: bool, uncertain: list[str]) -> list[Explanation]:
    ctx = Ctx(sem, profile, cfg, {c.name: c for c in comps})
    weights = cfg.weights.model_dump()
    bands = cfg.confidence_bands
    strengths: list[tuple[float, Explanation]] = []
    out: list[Explanation] = []
    uncertain_texts: list[tuple[str, str, float]] = []

    for rule in RULES:
        for text, signals, confidence, target in rule.fn(ctx):
            if rule.section in ("strength", "concern") and confidence is not None and confidence < bands.accept:
                if confidence < bands.review:
                    uncertain_texts.append((signals[0], f"{signals[0]}: confidence {confidence:.2f}", confidence))
                    continue
                text = f"Likely: {text}"
            ev = evidence_line(sem, target, cfg)
            item = Explanation(section=rule.section, text=text, signal_ids=signals, confidence=confidence,
                               evidence_line_id=ev.line_id if ev else None)
            if rule.section == "strength":
                strengths.append((weights[rule.component] if rule.component else -1.0, item))
            else:
                out.append(item)

    out += [Explanation(section="concern", text=f"{p.reason} (−{p.points:g})", signal_ids=p.signal_ids,
                        confidence=None, evidence_line_id=None) for p in penalties]
    out += blocker_concerns
    if stale_semantics:
        out.append(Explanation(section="concern", text="Profile changed since this evaluation — re-evaluate for accurate results",
                               signal_ids=[], confidence=None, evidence_line_id=None))
    for signal in uncertain:
        uncertain_texts.append((signal, f"{signal}: confidence {getattr(sem, signal).confidence:.2f}",
                                getattr(sem, signal).confidence))
    seen: set[str] = set()
    for signal, text, confidence in uncertain_texts:
        if text not in seen:
            seen.add(text)
            out.append(Explanation(section="uncertain", text=text, signal_ids=[signal], confidence=confidence,
                                   evidence_line_id=None))
    ordered = [item for _, item in sorted(strengths, key=lambda pair: -pair[0])]
    return ordered + out
