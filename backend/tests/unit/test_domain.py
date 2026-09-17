import pytest
from pydantic import ValidationError

from app.domain import (
    DEFAULT_TRACKED_SKILLS,
    BlockerFacts,
    CandidatePreferences,
    CandidateProfileIn,
    JobPostingIn,
    TrackedSkill,
    semantic_hash,
)


def profile(**prefs):
    return CandidateProfileIn(resume_text="Android engineer", preferences=CandidatePreferences(**prefs),
                              blocker_facts=BlockerFacts(), tracked_skills=DEFAULT_TRACKED_SKILLS)


def test_default_tracked_skills_match_spec():
    assert [s.id for s in DEFAULT_TRACKED_SKILLS][:4] == ["android", "kotlin", "java", "jetpack_compose"]
    assert len(DEFAULT_TRACKED_SKILLS) == 18


def test_technology_in_two_lists_rejected():
    with pytest.raises(ValidationError):
        profile(required_technologies=["Kotlin"], avoid_technologies=[" kotlin "])


def test_role_family_preferred_and_avoided_rejected():
    with pytest.raises(ValidationError):
        profile(preferred_role_families=["flutter"], avoided_role_families=["flutter"])


def test_skill_ids_must_be_unique_slugs():
    with pytest.raises(ValidationError):
        CandidateProfileIn(resume_text="x", preferences=CandidatePreferences(), blocker_facts=BlockerFacts(),
                           tracked_skills=[TrackedSkill(id="Bad Id", label="x")])
    with pytest.raises(ValidationError):
        CandidateProfileIn(resume_text="x", preferences=CandidatePreferences(), blocker_facts=BlockerFacts(),
                           tracked_skills=[TrackedSkill(id="a", label="x"), TrackedSkill(id="a", label="y")])


def test_empty_resume_rejected():
    with pytest.raises(ValidationError):
        CandidateProfileIn(resume_text="  ", preferences=CandidatePreferences(), blocker_facts=BlockerFacts(),
                           tracked_skills=[])


def test_semantic_hash_ignores_scoring_only_fields_and_blocker_facts():
    a = profile(remote_preference="remote")
    b = profile(remote_preference="onsite", management_preference="ic")
    b.blocker_facts.needs_visa_sponsorship = True
    assert semantic_hash(a) == semantic_hash(b)
    assert semantic_hash(a) != semantic_hash(profile(preferred_roles=["Staff Android"]))


def test_job_posting_validation():
    with pytest.raises(ValidationError):
        JobPostingIn(company="A", title="B", description="too short")
    with pytest.raises(ValidationError):
        JobPostingIn(company="A", title="B", description="x" * 60, source_url="ftp://x.com")
    j = JobPostingIn(company="  Acme ", title=" Eng ", description="x" * 60)
    assert (j.company, j.title) == ("Acme", "Eng")
