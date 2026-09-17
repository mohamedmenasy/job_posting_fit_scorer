"""Semantic fixtures for the fake evaluator (spec §6.6, §13.1 cases).

Each fixture = a realistic sample posting + signal overrides on top of the android_staff_perfect baseline.
Evidence and requirement lines are located by case-insensitive substring of the posting's lines, so fixtures
stay valid when postings are edited; entries that match no line are dropped.
"""

import math
from typing import get_args

from app.domain import ENUMS, ChoiceSignal, NoulSignal, ScoreSignal


def _options(options) -> list[str]:
    return list(get_args(ENUMS[options])) if isinstance(options, str) else list(options)


def ch(value: str, p: float = 0.9, conf: float | None = None, options="RoleFamily") -> ChoiceSignal:
    """Choice with probability p on value and the remainder spread evenly over the other options."""
    opts = _options(options)
    rest = (1 - p) / (len(opts) - 1) if len(opts) > 1 else 0.0
    return ChoiceSignal(value=value, confidence=p if conf is None else conf,
                        probabilities={o: (p if o == value else rest) for o in opts})


def sc(score: float, levels: int, conf: float = 0.9, probabilities: dict[int, float] | None = None) -> ScoreSignal:
    """Score whose probability mass sits on the two levels around `score`, so the weighted mean equals it."""
    if probabilities is None:
        lo, hi = math.floor(score), math.ceil(score)
        probabilities = {i: 0.0 for i in range(levels)}
        probabilities[lo] += hi - score if hi != lo else 1.0
        if hi != lo:
            probabilities[hi] += score - lo
    else:
        probabilities = {i: probabilities.get(i, 0.0) for i in range(levels)}
        score = sum(k * v for k, v in probabilities.items())
    return ScoreSignal(score=score, levels=levels, normalized=score / (levels - 1), probabilities=probabilities,
                       confidence=conf)


def nl(p: float) -> NoulSignal:
    return NoulSignal(probability=p, derived_confidence=abs(2 * p - 1))


def _base() -> dict:
    return {
        "role_family": ch("android_native", 0.92),
        "android_relevance": sc(3.9, 5),
        "seniority": ch("staff", 0.85, options="Seniority"),
        "title_level": ch("staff", 0.9, options="Seniority"),
        "staff_ic_signal": nl(0.85),
        "management_intensity": sc(1.2, 5),
        "kmp_requirement": ch("preferred", 0.85, options="RequirementLevel"),
        "cross_platform_intensity": sc(0.3, 5),
        "domain": ch("fintech", 0.9, options="Domain"),
        "work_arrangement": ch("remote", 0.9, options="WorkArrangement"),
        "requires_relocation": nl(0.03),
        "security_clearance_required": nl(0.02),
        "us_citizenship_required": nl(0.02),
        "work_authorization_signal": ch("not_stated", 0.9, options="WorkAuthSignal"),
        "min_years_required": ch("y8_10", 0.8, options="YearsBucket"),
        "technical_fit": sc(3.7, 5),
        "seniority_fit": sc(3.6, 5),
        "domain_fit": sc(3.4, 5),
        "role_preference_fit": sc(2.8, 4),
        "location_match": ch("in_preferred_location", 0.9, options="LocationMatch"),
        # skill id -> (requirement level, resume evidence score 0-3); kmp requirement comes from kmp_requirement
        "skills": {"android": ("required", 3), "kotlin": ("required", 3), "jetpack_compose": ("required", 3),
                   "coroutines": ("required", 2.8), "architecture": ("required", 3), "testing": ("required", 2.7),
                   "system_design": ("preferred", 2.7), "ci_cd": ("mentioned", 2), "kmp": (None, 1),
                   "leadership": ("required", 3)},
        # technology slug -> centrality score 0-3
        "technologies": {"kotlin": 3, "jetpack_compose": 2.6, "java": 1.0, "flutter": 0, "react_native": 0, "kmp": 1.2,
                         "kotlin_multiplatform": 1.2, "swift": 0},
        # substring -> (line kind, skill id or none, resume evidence 0-3); first matching key wins per line
        "lines": {"Kotlin Multiplatform": ("preferred_qualification", "kmp", 1),
                  "years of Android": ("required_qualification", "android", 3),
                  "Compose": ("required_qualification", "jetpack_compose", 3),
                  "Kotlin": ("required_qualification", "kotlin", 3),
                  "architecture": ("core_responsibility", "architecture", 3),
                  "mentor": ("core_responsibility", "leadership", 3)},
        # evidence target -> substring
        "evidence": {"work_arrangement": "remote", "kmp_requirement": "Kotlin Multiplatform",
                     "min_years_required": "years", "seniority": "technical direction",
                     "management_intensity": "mentor"},
    }


_ANDROID_STAFF_POSTING = {
    "company": "Ledgerly", "title": "Staff Android Engineer", "location": "Remote (US)", "salary_text": "$230k–$270k",
    "description": """About Ledgerly
Ledgerly builds the mobile banking app used by 4 million small businesses.
What you'll do
- Set technical direction for Android across our three mobile product teams
- Own the architecture of our Android app, from modularization to offline sync
- Partner with iOS and backend leads on cross-platform API and release strategy
- Mentor senior engineers and raise the bar through design reviews
What we're looking for
- 8+ years of Android development, including large apps in production
- Deep expertise in Kotlin, coroutines, and Flow
- Production experience with Jetpack Compose
- Experience with Kotlin Multiplatform is a plus
Benefits
- This role is fully remote within the US
- Competitive salary, equity, and a home office stipend""",
}

FIXTURES: dict[str, dict] = {
    "android_staff_perfect": {"posting": _ANDROID_STAFF_POSTING},
    "flutter_heavy": {
        "posting": {"company": "Parcelio", "title": "Senior Mobile Engineer (Flutter)", "location": "Remote (EU)",
                    "description": """About Parcelio
Parcelio helps local couriers run same-day delivery.
Responsibilities
- Build and ship features in our Flutter app for iOS and Android
- Maintain our shared Dart codebase and design system widgets
- Occasionally write platform channels in Kotlin or Swift
Requirements
- 4+ years of mobile development, with 2+ years of Flutter and Dart
- Experience publishing apps to the App Store and Google Play
- Familiarity with native Android or iOS is a plus
We work remotely across European time zones."""},
        "role_family": ch("flutter", 0.85), "android_relevance": sc(1.0, 5), "cross_platform_intensity": sc(3.5, 5),
        "seniority": ch("senior", 0.85, options="Seniority"), "title_level": ch("senior", 0.9, options="Seniority"),
        "staff_ic_signal": nl(0.2), "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "domain": ch("delivery_logistics", 0.85, options="Domain"), "min_years_required": ch("y3_4", 0.8, options="YearsBucket"),
        "technical_fit": sc(1.6, 5), "seniority_fit": sc(2.4, 5), "domain_fit": sc(1.8, 5), "role_preference_fit": sc(0.8, 4),
        "skills": {"flutter": ("required", 0.2), "android": ("preferred", 3), "kotlin": ("mentioned", 3),
                   "swift": ("mentioned", 0), "ios": ("preferred", 0.5)},
        "technologies": {"flutter": 3, "kotlin": 0.8, "dart": 3},
        "lines": {"Flutter and Dart": ("required_qualification", "flutter", 0.2),
                  "App Store": ("required_qualification", "none", 2),
                  "Build and ship features": ("core_responsibility", "flutter", 0.5)},
        "evidence": {"work_arrangement": "remotely", "min_years_required": "4+ years", "seniority": "Build and ship"},
    },
    "engineering_manager": {
        "posting": {"company": "Streamly", "title": "Engineering Manager, Android", "location": "New York, NY (Hybrid)",
                    "description": """About the team
Streamly's Android team builds the playback experience for 20 million viewers.
What you'll do
- Manage a team of 8 Android engineers, including hiring and performance reviews
- Run quarterly planning with product and design partners
- Grow engineers' careers through regular 1:1s and coaching
- Stay close enough to the code to guide architecture decisions
What you bring
- 3+ years managing mobile engineering teams
- A background as an Android engineer with Kotlin
Hybrid: three days a week in our New York office."""},
        "role_family": ch("engineering_management", 0.85), "android_relevance": sc(2.0, 5),
        "seniority": ch("manager", 0.85, options="Seniority"), "title_level": ch("manager", 0.9, options="Seniority"),
        "staff_ic_signal": nl(0.1), "management_intensity": sc(3.6, 5),
        "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "domain": ch("media_streaming", 0.9, options="Domain"), "work_arrangement": ch("hybrid", 0.9, options="WorkArrangement"),
        "min_years_required": ch("y3_4", 0.7, options="YearsBucket"),
        "technical_fit": sc(2.6, 5), "seniority_fit": sc(1.8, 5), "domain_fit": sc(2.0, 5), "role_preference_fit": sc(1.0, 4),
        "skills": {"people_management": ("required", 1), "android": ("required", 3), "kotlin": ("required", 3),
                   "leadership": ("required", 3)},
        "lines": {"Manage a team": ("core_responsibility", "people_management", 1),
                  "managing mobile": ("required_qualification", "people_management", 1)},
        "evidence": {"work_arrangement": "Hybrid", "management_intensity": "Manage a team", "seniority": "Manage a team",
                     "min_years_required": "3+ years"},
    },
    "clearance_required": {
        "posting": {"company": "Aegis Mobile Systems", "title": "Senior Android Engineer", "location": "Arlington, VA",
                    "description": """About us
Aegis Mobile Systems builds secure field-communication apps for defense customers.
The role
- Develop secure Android applications in Kotlin for hardened devices
- Implement encrypted messaging and offline mapping features
Requirements
- 5+ years of Android development
- Active Secret clearance required; ability to obtain TS/SCI
- Work onsite at our Arlington, VA facility"""},
        "seniority": ch("senior", 0.85, options="Seniority"), "title_level": ch("senior", 0.9, options="Seniority"),
        "staff_ic_signal": nl(0.25), "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "domain": ch("government_defense", 0.9, options="Domain"), "work_arrangement": ch("onsite", 0.9, options="WorkArrangement"),
        "security_clearance_required": nl(0.95), "min_years_required": ch("y5_7", 0.85, options="YearsBucket"),
        "domain_fit": sc(1.5, 5), "role_preference_fit": sc(2.0, 4),
        "evidence": {"security_clearance_required": "clearance", "work_arrangement": "onsite",
                     "min_years_required": "5+ years", "seniority": "Develop secure"},
    },
    "gov_contractor_no_clearance": {
        "posting": {"company": "CivicStack", "title": "Android Engineer", "location": "Remote (US)",
                    "description": """About CivicStack
We build software used by federal agencies and state governments to deliver benefits online.
What you'll do
- Build accessible Android features for millions of benefit applicants
- Work with designers to meet WCAG accessibility standards
What you'll need
- 4+ years of Android development with Kotlin
- A passion for public service
This is a remote role open to candidates across the US."""},
        "seniority": ch("senior", 0.7, options="Seniority"), "title_level": ch("unclear", 0.8, options="Seniority"),
        "staff_ic_signal": nl(0.15), "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "domain": ch("government_defense", 0.85, options="Domain"), "security_clearance_required": nl(0.05),
        "min_years_required": ch("y3_4", 0.8, options="YearsBucket"), "role_preference_fit": sc(1.8, 4),
        "evidence": {"work_arrangement": "remote role", "min_years_required": "4+ years"},
    },
    "no_sponsorship_info": {
        "posting": {"company": "Shoplane", "title": "Senior Android Engineer", "location": "Remote (US)",
                    "description": """About Shoplane
Shoplane powers checkout for 30,000 online stores.
What you'll do
- Build our Android checkout SDK in Kotlin
- Improve app performance and startup time
- Mentor mid-level engineers on the team
What we're looking for
- 6+ years of Android development
- Strong Kotlin and Jetpack Compose skills
Remote within the United States."""},
        "seniority": ch("senior", 0.85, options="Seniority"), "title_level": ch("senior", 0.9, options="Seniority"),
        "domain": ch("ecommerce", 0.9, options="Domain"), "work_authorization_signal": ch("not_stated", 0.95, options="WorkAuthSignal"),
        "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "min_years_required": ch("y5_7", 0.85, options="YearsBucket"),
        "evidence": {"work_arrangement": "Remote within", "min_years_required": "6+ years"},
    },
    "explicit_no_sponsorship": {
        "posting": {"company": "Medilink", "title": "Staff Android Engineer", "location": "Boston, MA (Remote OK)",
                    "description": """About Medilink
Medilink connects patients with their care teams through secure messaging.
What you'll do
- Lead the technical direction of our Android patient app
- Design HIPAA-compliant offline storage and sync
Requirements
- 8+ years of Android development in Kotlin
- Experience with healthcare or other regulated industries is a plus
Work authorization
- Candidates must be authorized to work in the US without current or future visa sponsorship"""},
        "domain": ch("healthcare", 0.95, options="Domain"),
        "work_authorization_signal": ch("explicit_no_sponsorship", 0.93, options="WorkAuthSignal"),
        "work_arrangement": ch("multiple_options", 0.6, options="WorkArrangement"),
        "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "evidence": {"work_authorization_signal": "sponsorship", "min_years_required": "8+ years",
                     "seniority": "technical direction", "work_arrangement": None},
    },
    "staff_title_senior_scope": {
        "posting": {"company": "Tripwise", "title": "Staff Android Engineer", "location": "Remote (Canada or US)",
                    "description": """About Tripwise
Tripwise helps travelers plan and book multi-city trips.
What you'll do
- Build new booking screens in our Android app
- Fix bugs and improve test coverage within the booking squad
- Participate in code reviews for your team
Requirements
- 5+ years of Android development
- Experience with Kotlin and Jetpack Compose
Remote across Canada and the US."""},
        "seniority": ch("senior", 0.85, options="Seniority"), "title_level": ch("staff", 0.9, options="Seniority"),
        "staff_ic_signal": nl(0.3), "domain": ch("travel", 0.9, options="Domain"),
        "kmp_requirement": ch("not_mentioned", 0.9, options="RequirementLevel"),
        "min_years_required": ch("y5_7", 0.85, options="YearsBucket"), "seniority_fit": sc(2.2, 5),
        "evidence": {"seniority": "booking squad", "min_years_required": "5+ years", "work_arrangement": "Remote across"},
    },
}


def fixture(name: str | None) -> dict:
    """Baseline merged with a named fixture's overrides (nested maps are replaced, evidence merged)."""
    merged = _base()
    over = FIXTURES.get(name or "", FIXTURES["android_staff_perfect"])
    for key, value in over.items():
        if key == "evidence":
            merged["evidence"] = {k: v for k, v in {**merged["evidence"], **value}.items() if v}
        elif key == "skills":
            merged["skills"] = {**{k: v for k, v in merged["skills"].items() if k == "kmp"}, **value}
        elif key == "lines":
            merged["lines"] = value
        elif key == "technologies":
            merged["technologies"] = {**merged["technologies"], **value}
        elif key != "posting":
            merged[key] = value
    return merged
