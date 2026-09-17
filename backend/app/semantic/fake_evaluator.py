"""Fixture-backed evaluator for tests, the seed script, and EVALUATOR=fake dev mode (spec §6.6)."""

from app.domain import CandidateProfile, Evidence, JobPosting, RequirementLine, SemanticJobEvaluation, SkillSignal
from app.semantic.catalog import EVALUATOR_VERSION, EVIDENCE_TARGETS, build_questions, catalog_hash, question_set_hash, technologies
from app.semantic.fake_fixtures import FIXTURES, ch, fixture, sc
from app.semantic.lines import eligible_ids, segment


class FakeJobSemanticEvaluator:
    model = "fake"

    async def evaluate(self, profile: CandidateProfile, job: JobPosting) -> SemanticJobEvaluation:
        name = (job.external_id or "").removeprefix("fixture:") if (job.external_id or "").startswith("fixture:") else None
        if name is None:  # a pasted fixture posting (e.g. from the UI) selects that fixture
            pasted = " ".join(job.description.split())
            name = next((n for n, fx in FIXTURES.items() if " ".join(fx["posting"]["description"].split()) == pasted), None)
        fx = fixture(name)
        lines = segment(job.description)
        prefs = profile.preferences
        skill_ids = [s.id for s in profile.tracked_skills]

        skills = {}
        for sid in skill_ids:
            requirement, evidence = fx["skills"].get(sid, ("not_mentioned", 0))
            req = fx["kmp_requirement"] if sid == "kmp" else ch(requirement or "not_mentioned", 0.9, options="RequirementLevel")
            skills[sid] = SkillSignal(requirement=req, evidence=sc(evidence, 4))

        def match(needle: str, ids) -> str | None:
            return next((lid for lid in ids if needle.lower() in lines[lid].lower()), None)

        requirement_lines = []
        for lid in eligible_ids(lines):
            kind, skill, evidence = next((v for k, v in fx["lines"].items() if k.lower() in lines[lid].lower()),
                                         ("other", "none", 0))
            skill = skill if skill in skill_ids else "none"
            requirement_lines.append(RequirementLine(
                id=lid, text=lines[lid], kind=ch(kind, 0.9, options="LineKind"),
                skill=ch(skill, 0.9, options=skill_ids + ["none"]), evidence=sc(evidence, 4)))

        evidence = {}
        for target in EVIDENCE_TARGETS:
            lid = match(fx["evidence"][target], lines) if target in fx["evidence"] else None
            evidence[target] = Evidence(line_id=lid, text=lines.get(lid) if lid else None, probability=0.9)

        signals = {k: v for k, v in fx.items() if k not in {"skills", "technologies", "lines", "evidence"}}
        signals["role_preference_fit"] = signals["role_preference_fit"] if prefs.preferred_roles else None
        signals["location_match"] = signals["location_match"] if prefs.preferred_locations else None
        return SemanticJobEvaluation(
            **signals,
            skills=skills,
            # ponytail: technologies absent from a fixture get a middling, low-confidence centrality
            technologies={slug: sc(fx["technologies"][slug], 4) if slug in fx["technologies"] else sc(1.5, 4, conf=0.6)
                          for slug in technologies(prefs)},
            lines=requirement_lines, all_lines=lines, evidence=evidence,
            model=self.model, evaluator_version=EVALUATOR_VERSION, catalog_hash=catalog_hash(),
            question_set_hash=question_set_hash(build_questions(profile, lines)), requests=[],
        )
