"""TypeSafe question catalog (spec §6.3). Questions are plain SDK-compatible dicts.

Bump EVALUATOR_VERSION whenever question wording, state format, segmentation, or parsing changes;
tests/unit/test_catalog.py pins catalog_hash() per version.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, get_args
from uuid import UUID

from app.domain import (
    CandidatePreferences,
    CandidateProfile,
    Domain,
    RoleFamily,
    Seniority,
    TrackedSkill,
    canonical_json,
    sha256,
    tech_slug,
)
from app.semantic.lines import SEGMENTATION_VERSION, eligible_ids

EVALUATOR_VERSION = "1.0.0"

LINES = "`job.lines`"
RESUME = "`candidate.resume`"


@dataclass(frozen=True)
class Q:
    id: str
    state: Literal["job", "fit"]
    body: dict

    @property
    def kind(self) -> str:
        return self.body["type"]

    @property
    def options(self) -> list[str]:
        return list(self.body["criteria"])

    @property
    def levels(self) -> int:
        return len(self.body["criteria"])


def _choice(question: dict, criteria: dict) -> dict:
    return {"type": "choice", "instructions": question, "criteria": criteria}


def _score(question: dict, levels: list[str]) -> dict:
    return {"type": "score", "instructions": question, "criteria": levels}


def _noul(question: dict, true: dict, false: dict) -> dict:
    return {"type": "noul", "instructions": question, "criteria": {"true": true, "false": false}}


REQUIREMENT_CRITERIA = {
    "required": {"what": "Asked of candidates as a must-have qualification or a core responsibility"},
    "preferred": {"what": "Listed as a nice-to-have, bonus, or plus"},
    "mentioned": {"what": "Appears, for example in the tech stack or roadmap, without being asked of candidates"},
    "not_mentioned": {"what": "Does not appear in the posting"},
}

SENIORITY_CRITERIA = {
    "junior": "Early-career; works on well-defined tasks with close guidance",
    "mid": "Delivers features independently within one team",
    "senior": "Owns complex features or systems end to end, makes team-level technical decisions, mentors others",
    "staff": "Leads technical direction across multiple teams or a whole product area",
    "principal": "Sets technical strategy and architecture across an organization",
    "architect": "A dedicated architecture role that defines system designs, with little feature delivery",
    "manager": "Manages a team of engineers as the main responsibility",
    "senior_manager": "Manages managers or several teams",
    "director_plus": "Director or executive leading an engineering organization",
    "unclear": "The posting does not describe enough scope to judge",
}
assert list(SENIORITY_CRITERIA) == list(get_args(Seniority))

EVIDENCE_TARGETS = {
    "security_clearance_required": "Which line of the posting states a security clearance requirement?",
    "us_citizenship_required": "Which line of the posting states a US citizenship requirement?",
    "work_authorization_signal": "Which line of the posting says something about visa sponsorship or work authorization?",
    "work_arrangement": "Which line of the posting states whether the role is remote, hybrid, or onsite?",
    "requires_relocation": "Which line of the posting states a relocation requirement?",
    "kmp_requirement": "Which line of the posting mentions Kotlin Multiplatform?",
    "min_years_required": "Which line of the posting states the required years of experience?",
    "seniority": "Which line of the posting best shows the scope or seniority the role expects?",
    "management_intensity": "Which line of the posting best shows people-management or leadership responsibilities?",
}


def _static_job_questions() -> list[Q]:
    role_family = {
        "android_native": {"what": "Building native Android apps with the Android SDK, Kotlin, or Java is the main work",
                           "not_for": "Roles that split native work across Android and iOS"},
        "mobile_general": {"what": "Native mobile work spanning both Android and iOS",
                           "not_for": "Roles centered on one cross-platform framework"},
        "ios": {"what": "Native iOS development with Swift or Objective-C is the main work"},
        "kotlin_multiplatform": {"what": "Kotlin Multiplatform shared code is the center of the role"},
        "flutter": {"what": "Flutter is the primary application platform"},
        "react_native": {"what": "React Native is the primary application platform"},
        "backend": {"what": "Server-side services, APIs, or data systems are the main work"},
        "fullstack": {"what": "Both web frontend and backend development"},
        "engineering_management": {"what": "Managing engineers or teams is the main job",
                                   "not_for": "Tech lead roles that stay mostly hands-on"},
        "other": {"what": "None of the above fits"},
    }
    assert list(role_family) == list(get_args(RoleFamily))
    domain_descriptions = {
        "ai_ml": "AI or machine-learning products or platforms",
        "enterprise": "Business or enterprise software",
        "media_streaming": "Media, streaming, or entertainment",
        "delivery_logistics": "Delivery, mobility, or logistics",
        "government_defense": "Government or defense",
        "other": "None of the above",
    }
    return [Q(id, "job", body) for id, body in [
        ("role_family", _choice(
            {"question": "What is the primary engineering role family of this job?", "inspect": LINES,
             "focus": "Judge by day-to-day responsibilities and required qualifications, not by the title alone."},
            role_family)),
        ("android_relevance", _score(
            {"question": "How central is native Android engineering to this job?", "inspect": LINES},
            ["No Android work appears in the responsibilities or requirements",
             "Android appears only as optional, a nice-to-have, or occasional collaboration with Android engineers",
             "Some hands-on Android work, but most of the role is about something else",
             "Substantial hands-on Android work shared with another major focus, such as iOS or backend",
             "Native Android engineering is the main day-to-day work"])),
        ("seniority", _choice(
            {"question": "What level of seniority does this job target?", "inspect": LINES,
             "focus": "Judge by the scope, ownership, and influence described, not by the title."},
            SENIORITY_CRITERIA)),
        ("title_level", _choice(
            {"question": "What seniority level does the job title alone indicate?", "inspect": "`job.title`",
             "focus": "Use only the words in the title."},
            {**SENIORITY_CRITERIA, "unclear": "The title does not indicate a level"})),
        ("staff_ic_signal", _noul(
            {"question": "Is this primarily a senior technical individual-contributor role involving architecture, "
                         "cross-team technical leadership, platform ownership, technical strategy, or broad "
                         "engineering influence?", "inspect": LINES},
            {"what": "Hands-on or near-hands-on technical leadership whose influence reaches beyond a single team or feature"},
            {"what": "Feature-level individual-contributor work, or a role whose main job is managing people",
             "examples": ["Build new screens for our checkout flow", "Manage a team of 8 engineers"]})),
        ("management_intensity", _score(
            {"question": "How much people or organizational management does this job involve?", "inspect": LINES},
            ["Individual contributor with no leadership responsibilities",
             "Mentoring or informal technical guidance only",
             "Tech lead: guides a team's technical work and planning without managing people",
             "Significant people or project leadership, such as hiring, performance input, or leading a team's delivery",
             "Primarily people or organizational management: direct reports, performance reviews, org planning"])),
        ("kmp_requirement", _choice(
            {"question": "How does the posting treat Kotlin Multiplatform (KMP)?", "inspect": LINES},
            REQUIREMENT_CRITERIA)),
        ("cross_platform_intensity", _score(
            {"question": "How much of this role involves cross-platform app frameworks instead of native development?",
             "inspect": LINES,
             "focus": "Count Flutter, React Native, .NET MAUI/Xamarin, Ionic/Cordova and similar frameworks. "
                      "Kotlin Multiplatform does not count here; it is judged separately."},
            ["No cross-platform framework work (native-only or not an app role)",
             "Mostly native, with minor or optional cross-platform framework exposure",
             "A meaningful mix of native and cross-platform framework work",
             "Mostly cross-platform framework work with some native work",
             "The whole role revolves around a cross-platform framework"])),
        ("domain", _choice(
            {"question": "Which industry domain does this company or product operate in?",
             "inspect": ["`job.company`", LINES]},
            {d: domain_descriptions.get(d) for d in get_args(Domain)})),
        ("work_arrangement", _choice(
            {"question": "What work arrangement does the posting offer for this role?",
             "inspect": ["`job.location`", LINES]},
            {"remote": {"what": "Fully remote; may still limit eligible countries or time zones"},
             "hybrid": {"what": "A mix of remote work and required in-office days"},
             "onsite": {"what": "Work from the office every day"},
             "multiple_options": {"what": "The candidate may choose among remote, hybrid, or onsite"},
             "unclear": {"what": "The posting does not state the arrangement",
                         "not_for": "Guessing from the presence of an office address"}})),
        ("requires_relocation", _noul(
            {"question": "Does the posting explicitly require the hire to relocate?", "inspect": LINES},
            {"what": "Relocation is stated as required for this role",
             "examples": ["Relocation to Seattle is required", "Must relocate within 60 days of starting"]},
            {"what": "No stated relocation requirement",
             "not_for": ["An office location alone", "Relocation assistance offered but not required"]})),
        ("security_clearance_required", _noul(
            {"question": "Does the posting explicitly require the candidate to already have, obtain, or be eligible "
                         "for a US government security clearance?", "inspect": LINES},
            {"what": "An explicit security clearance requirement for this role",
             "examples": ["Active Secret clearance required", "Must be able to obtain and maintain a TS/SCI clearance",
                          "Candidates must be eligible for a DoD security clearance"]},
            {"what": "No explicit security clearance requirement",
             "not_for": ["The employer works with government or defense customers but states no clearance requirement",
                         "Standard background checks or drug screening"],
             "examples": ["We build software used by federal agencies"]})),
        ("us_citizenship_required", _noul(
            {"question": "Does the posting explicitly require US citizenship?", "inspect": LINES},
            {"what": "US citizenship is explicitly required",
             "examples": ["Must be a US citizen", "US citizenship is required for this position"]},
            {"what": "US citizenship is not explicitly required",
             "not_for": ["Authorization to work in the US that does not mention citizenship",
                         "A clearance requirement that does not mention citizenship",
                         "The employer's industry or customers"]})),
        ("work_authorization_signal", _choice(
            {"question": "What does the posting explicitly say about visa sponsorship or work authorization?",
             "inspect": LINES,
             "focus": "Use only statements in the posting. Never infer policy from the company, industry, location, "
                      "security context, or nationality."},
            {"explicit_sponsorship_available": {"what": "States that visa sponsorship is available",
                                                "examples": ["Visa sponsorship available",
                                                             "We sponsor H-1B visas for this role"]},
             "explicit_no_sponsorship": {"what": "States that sponsorship is not available",
                                         "examples": ["We do not sponsor visas",
                                                      "Must be authorized to work in the US without current or future sponsorship"]},
             "explicit_specific_work_authorization_requirement": {
                 "what": "Requires a specific citizenship, residency, or work authorization without addressing sponsorship",
                 "examples": ["Must be a US citizen or permanent resident", "Must have the right to work in the UK"]},
             "not_stated": {"what": "Says nothing about sponsorship, visas, citizenship, or work authorization",
                            "not_for": "Inferring policy from anything other than explicit statements"},
             "ambiguous": {"what": "Mentions sponsorship or work authorization, but what applies to this role is unclear or contradictory",
                           "examples": ["Sponsorship may be considered for exceptional candidates"]}})),
        ("min_years_required", _choice(
            {"question": "What minimum years of professional experience does the posting ask for?", "inspect": LINES,
             "focus": "Use the number stated for overall or core experience. If a range is given, use its lower bound."},
            {"not_stated": "No years of experience are stated", "y0_2": "0 to 2 years", "y3_4": "3 to 4 years",
             "y5_7": "5 to 7 years", "y8_10": "8 to 10 years", "y11_plus": "11 or more years"})),
    ]]


def _skill_text(skill: TrackedSkill) -> str:
    return f"{skill.label}: {skill.description}" if skill.description else skill.label


def technologies(prefs: CandidatePreferences) -> dict[str, str]:
    out: dict[str, str] = {}
    for text in prefs.required_technologies + prefs.preferred_technologies + prefs.avoid_technologies:
        out.setdefault(tech_slug(text), text)
    return out


def build_questions(profile: CandidateProfile, lines: dict[str, str]) -> list[Q]:
    skills = profile.tracked_skills
    prefs = profile.preferences
    eligible = eligible_ids(lines)
    job = _static_job_questions()
    job += [Q(f"skill_req.{s.id}", "job", _choice(
        {"question": "How does the posting treat this skill?", "skill": _skill_text(s), "inspect": LINES},
        REQUIREMENT_CRITERIA)) for s in skills if s.id != "kmp"]
    job += [Q(f"tech_centrality.{slug}", "job", _score(
        {"question": "How central is this technology to the work in this job?", "technology": text, "inspect": LINES},
        ["Does not appear in the posting", "Mentioned in passing, as optional, or as a nice-to-have",
         "A significant part of the work, alongside other main technologies", "The core technology of the role"]))
        for slug, text in technologies(prefs).items()]
    line_options = {**{lid: None for lid in lines}, "none": "No line of the posting states this"}
    job += [Q(f"evidence.{target}", "job", _choice({"question": question, "inspect": LINES}, line_options))
            for target, question in EVIDENCE_TARGETS.items()]
    job += [Q(f"line_kind.{lid}", "job", _choice(
        {"question": "What kind of statement is this line of the job posting?", "line": f"`job.lines.{lid}`"},
        {"required_qualification": {"what": "A skill, experience, or credential candidates must have",
                                    "examples": ["5+ years of Android development", "Strong Kotlin skills"]},
         "preferred_qualification": {"what": "A skill or experience listed as a plus or nice-to-have",
                                     "examples": ["Experience with Kotlin Multiplatform is a plus"]},
         "core_responsibility": {"what": "Work the hire will do", "examples": ["Own the architecture of our Android app"]},
         "other": {"what": "Company information, benefits, hiring process, legal text, or headings"}}))
        for lid in eligible]
    skill_options = {**{s.id: _skill_text(s) for s in skills},
                     "none": "None of the listed skills, or the line asks for no skill"}
    job += [Q(f"line_skill.{lid}", "job", _choice(
        {"question": "Which listed skill does this line of the job posting mainly ask for?", "line": f"`job.lines.{lid}`"},
        skill_options)) for lid in eligible]

    fit = [
        Q("technical_fit", "fit", _score(
            {"question": "How well does the candidate's experience match the most important technical requirements of this job?",
             "compare": [RESUME, LINES],
             "focus": "Weigh the core required skills and responsibilities. Do not count keyword overlap."},
            ["The candidate lacks most of the core technical requirements",
             "Weak overlap: only a few core requirements are evidenced",
             "Moderate overlap: about half of the core requirements are evidenced",
             "Strong match: most core requirements are clearly evidenced",
             "Exceptional overlap: nearly all of the most important requirements are evidenced in depth"])),
        Q("seniority_fit", "fit", _score(
            {"question": "How well does the scope the candidate has demonstrated match the scope this job expects?",
             "compare": [RESUME, LINES],
             "focus": "Compare ownership, influence, and leadership scope, not job titles or years alone."},
            ["Clearly the wrong level: far above or far below the candidate's demonstrated scope",
             "A substantial mismatch in scope", "Plausible but imperfect: some gap in scope",
             "A strong level match", "An excellent match for the candidate's demonstrated scope"])),
        Q("domain_fit", "fit", _score(
            {"question": "How well does the candidate's background transfer to this company's domain?",
             "compare": [RESUME, "`job.company`", LINES]},
            ["Little relevant domain or background overlap", "Limited overlap",
             "Transferable experience from related domains",
             "Strong relevant experience in this or a closely related domain",
             "Exceptional domain relevance: deep experience in this domain"])),
    ]
    if prefs.preferred_roles:
        fit.append(Q("role_preference_fit", "fit", _score(
            {"question": "How closely does this job match the kinds of roles the candidate wants?",
             "compare": ["`candidate.preferred_roles`", "`job.title`", LINES]},
            ["Not one of the wanted roles or anything close to them",
             "Adjacent to a wanted role, such as the same platform with a different focus",
             "A close variant of a wanted role", "Matches one of the wanted roles"])))
    if prefs.preferred_locations:
        fit.append(Q("location_match", "fit", _choice(
            {"question": "Is this job located in, or open to candidates from, one of the candidate's preferred locations?",
             "compare": ["`candidate.preferred_locations`", "`job.location`", LINES]},
            {"in_preferred_location": {"what": "Based in, or open to candidates in, one of the preferred locations"},
             "outside_preferred_locations": {"what": "Based in, or restricted to, places outside all preferred locations"},
             "unclear": {"what": "The posting does not give enough location information"}})))
    fit += [Q(f"skill_ev.{s.id}", "fit", _score(
        {"question": "How strongly does the resume show this skill?", "skill": _skill_text(s), "inspect": RESUME},
        ["No evidence of this skill in the resume", "Weak or indirect evidence, such as a keyword without context",
         "Partial evidence: related work or limited use",
         "Strong evidence: substantial hands-on use in roles or projects"])) for s in skills]
    fit += [Q(f"line_ev.{lid}", "fit", _score(
        {"question": "How strongly does the resume show what this line of the job posting asks for?",
         "compare": [RESUME, f"`job.lines.{lid}`"]},
        ["No evidence in the resume", "Weak or indirect evidence", "Partial evidence: related but not the same",
         "Clear, direct evidence"])) for lid in eligible]
    return job + fit


def catalog_hash() -> str:
    sentinel = CandidateProfile(
        id=UUID(int=0), created_at=datetime(2000, 1, 1, tzinfo=UTC), semantic_hash="", resume_text="<resume>",
        preferences=CandidatePreferences(required_technologies=["<technology>"], preferred_roles=["<role>"],
                                         preferred_locations=["<location>"]),
        tracked_skills=[TrackedSkill(id="skill", label="<label>", description="<description>")])
    questions = build_questions(sentinel, {"L000": "<line text for catalog hash>"})
    return sha256(canonical_json({"segmentation": SEGMENTATION_VERSION, "questions": [[q.id, q.state, q.body] for q in questions]}))


def question_set_hash(questions: list[Q]) -> str:
    return sha256(canonical_json([[q.id, q.state, q.body] for q in questions]))
