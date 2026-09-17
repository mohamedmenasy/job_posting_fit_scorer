"""Hard blockers, possible blockers, and blocker-related concerns (spec §7.4).

A blocker needs an explicit posting signal at/above threshold AND an explicitly set profile fact.
"""

from typing import Literal

from app.domain import CandidateProfile, Evidence, Explanation, HardBlocker, SemanticJobEvaluation, tech_slug
from app.scoring.config import ScoringConfig

Fact = Literal["blocks", "unset", "ok"]

IC_LADDER = {"junior": 0, "mid": 1, "senior": 2, "staff": 3, "principal": 4, "architect": 4}


def evidence_line(sem: SemanticJobEvaluation, target: str | None, cfg: ScoringConfig) -> Evidence | None:
    ev = sem.evidence.get(target) if target else None
    return ev if ev and ev.line_id and ev.probability >= cfg.evidence_min_probability else None


def classify(probs: list[float], thresholds: list[float], fact: Fact, possible: float) -> str | None:
    if fact == "ok" or not probs:
        return None
    if all(p >= t for p, t in zip(probs, thresholds)):
        return "fire" if fact == "blocks" else "unset"
    if fact == "blocks" and all(p >= possible for p in probs):
        return "possible"
    return None


def _fact(value: bool | None, blocking: bool) -> Fact:
    if value is None:
        return "unset"
    return "blocks" if value == blocking else "ok"


def evaluate_blockers(sem: SemanticJobEvaluation, profile: CandidateProfile,
                      cfg: ScoringConfig) -> tuple[list[HardBlocker], list[HardBlocker], list[Explanation]]:
    bc = cfg.blockers
    prefs, facts = profile.preferences, profile.blocker_facts
    T = bc.threshold
    relocate: Fact = "ok" if prefs.willing_to_relocate else "blocks"
    # (type, label, fact label, probabilities, thresholds, fact, reason, evidence target, signal ids)
    rules: list[tuple] = []
    if bc.security_clearance.enabled:
        rules.append(("security_clearance", "security clearance", "clearance eligibility",
                      [sem.security_clearance_required.probability], [T],
                      _fact(facts.can_meet_clearance_requirement, False),
                      "Explicit security clearance requirement you cannot meet", "security_clearance_required",
                      ["security_clearance_required"]))
    if bc.us_citizenship.enabled:
        rules.append(("us_citizenship", "US citizenship", "US citizenship eligibility",
                      [sem.us_citizenship_required.probability], [T],
                      _fact(facts.can_meet_us_citizenship_requirement, False),
                      "Explicit US citizenship requirement you cannot meet", "us_citizenship_required",
                      ["us_citizenship_required"]))
    if bc.no_sponsorship.enabled:
        rules.append(("no_sponsorship", "no-sponsorship", "visa sponsorship need",
                      [sem.work_authorization_signal.p("explicit_no_sponsorship")], [T],
                      _fact(facts.needs_visa_sponsorship, True),
                      "Posting explicitly offers no visa sponsorship and you need it", "work_authorization_signal",
                      ["work_authorization_signal"]))
    if bc.relocation.enabled:
        rules.append(("relocation", "relocation", "relocation preference", [sem.requires_relocation.probability], [T],
                      relocate, "Posting explicitly requires relocation and you are not willing to relocate",
                      "requires_relocation", ["requires_relocation"]))
    if bc.onsite_location.enabled and sem.location_match is not None and prefs.preferred_locations:
        rules.append(("onsite_location", "onsite location", "relocation preference",
                      [sem.work_arrangement.p("onsite", "hybrid"), sem.location_match.p("outside_preferred_locations")],
                      [T, T], relocate, "In-office role outside your preferred locations and you are not willing to relocate",
                      "work_arrangement", ["work_arrangement", "location_match"]))
    tm = bc.technology_mismatch
    if tm.enabled:
        for tech in prefs.avoid_technologies:
            if s := sem.technologies.get(tech_slug(tech)):
                rules.append(("technology_mismatch", f"{tech}-centered", "", [s.probabilities.get(s.levels - 1, 0.0)],
                              [tm.avoid_core_probability], "blocks", f"{tech} is the core technology and you avoid it",
                              None, [f"tech_centrality.{tech_slug(tech)}"]))
        for tech in prefs.required_technologies:
            if s := sem.technologies.get(tech_slug(tech)):
                rules.append(("technology_mismatch", f"{tech}-absent", "", [s.probabilities.get(0, 0.0)],
                              [tm.required_absent_probability], "blocks", f"Required technology {tech} does not appear",
                              None, [f"tech_centrality.{tech_slug(tech)}"]))
    sf = bc.seniority_far_below
    preferred_ic = [IC_LADDER[level] for level in prefs.preferred_levels if level in IC_LADDER]
    if sf.enabled and preferred_ic:
        below = [level for level, idx in IC_LADDER.items() if idx <= min(preferred_ic) - sf.min_steps_below]
        if below:
            rules.append(("seniority_far_below", "far-below-level", "", [sem.seniority.p(*below)], [T], "blocks",
                          "Role is at least two levels below your preferred levels", "seniority", ["seniority"]))

    hard: list[HardBlocker] = []
    possible: list[HardBlocker] = []
    concerns: list[Explanation] = []
    for type_, label, fact_label, probs, thresholds, fact, reason, target, signals in rules:
        outcome = classify(probs, thresholds, fact, bc.possible_threshold)
        if outcome is None:
            continue
        ev = evidence_line(sem, target, cfg)
        confidence = min(probs)
        blocker = HardBlocker(type=type_, reason=reason, confidence=confidence, evidence=ev.text if ev else None)
        if outcome == "fire":
            hard.append(blocker)
            continue
        if outcome == "possible":
            possible.append(blocker)
            text = f"Possible {label} requirement ({confidence:.2f}) — verify"
        else:
            text = f"Explicit {label} requirement — set your {fact_label} in Profile to evaluate"
        concerns.append(Explanation(section="concern", text=text, signal_ids=signals, confidence=confidence,
                                    evidence_line_id=ev.line_id if ev else None))

    wa = sem.work_authorization_signal
    wa_text = {"explicit_specific_work_authorization_requirement": "Specific work authorization requirement — see posting",
               "ambiguous": "Work authorization wording is ambiguous — see posting"}.get(wa.value)
    if wa_text:
        ev = evidence_line(sem, "work_authorization_signal", cfg)
        concerns.append(Explanation(section="concern", text=wa_text, signal_ids=["work_authorization_signal"],
                                    confidence=wa.confidence, evidence_line_id=ev.line_id if ev else None))
    return hard, possible, concerns
