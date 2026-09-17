"""TypeSafe states (spec §6.2). Only fields listed here ever leave the machine."""

from app.domain import CandidateProfile, JobPosting


def build_job_state(job: JobPosting, lines: dict[str, str]) -> dict:
    optional = {"location": job.location, "salary": job.salary_text}
    return {"job": {"title": job.title, "company": job.company,
                    **{k: v for k, v in optional.items() if v}, "lines": lines}}


def build_fit_state(job: JobPosting, lines: dict[str, str], profile: CandidateProfile) -> dict:
    prefs = profile.preferences
    optional = {"preferred_roles": prefs.preferred_roles, "preferred_locations": prefs.preferred_locations}
    return {**build_job_state(job, lines),
            "candidate": {"resume": profile.resume_text, **{k: v for k, v in optional.items() if v}}}
