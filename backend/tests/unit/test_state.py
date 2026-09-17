import json

from app.semantic.state import build_fit_state, build_job_state
from tests.conftest import make_job, make_profile


def test_states_never_contain_blocker_facts_notes_or_scoring_only_preferences():
    profile = make_profile(
        work_authorization_notes="SECRET-AUTH-NOTE", preferred_levels=["staff"], preferred_role_families=["flutter"],
        avoided_role_families=["ios"], preferred_domains=["fintech"], remote_preference="remote",
        willing_to_relocate=True, management_preference="ic", years_experience=11.5,
        preferred_roles=["Staff Android"], preferred_locations=["Remote US"],
        blocker_facts={"needs_visa_sponsorship": True, "can_meet_us_citizenship_requirement": False,
                       "can_meet_clearance_requirement": False})
    job = make_job()
    lines = {"L000": "Build Android apps with Kotlin daily"}
    blob = json.dumps([build_job_state(job, lines), build_fit_state(job, lines, profile)])
    for forbidden in ["SECRET-AUTH-NOTE", "needs_visa", "citizenship_requirement", "clearance_requirement",
                      "preferred_levels", "role_families", "preferred_domains", "remote_preference",
                      "relocate", "management_preference", "years_experience", "11.5", "fintech", "blocker"]:
        assert forbidden not in blob
    fit = build_fit_state(job, lines, profile)
    assert set(fit["candidate"]) == {"resume", "preferred_roles", "preferred_locations"}
    assert fit["job"] == build_job_state(job, lines)["job"]


def test_empty_fields_omitted():
    job = make_job(location=None, salary_text=None)
    state = build_job_state(job, {"L000": "x"})
    assert set(state["job"]) == {"title", "company", "lines"}
    assert set(build_fit_state(job, {}, make_profile())["candidate"]) == {"resume"}
