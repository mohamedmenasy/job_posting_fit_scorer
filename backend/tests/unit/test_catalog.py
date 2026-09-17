from app.semantic.catalog import EVALUATOR_VERSION, build_questions, catalog_hash, question_set_hash
from tests.conftest import make_profile

PINNED = {"1.0.0": "1621822ea6f9272fe10f4fcec67a62f328f80d7994d78cd047a14d1ac4ec2a53"}


def qs(**prefs):
    lines = {"L000": "Requirements:", "L001": "5+ years of Android development with Kotlin",
             "L002": "Experience with Kotlin Multiplatform is a plus"}
    return {q.id: q for q in build_questions(make_profile(**prefs), lines)}


def test_catalog_hash_pinned_to_evaluator_version():
    # Changing question wording, state format, segmentation, or parsing? Bump EVALUATOR_VERSION and add its hash.
    assert PINNED[EVALUATOR_VERSION] == catalog_hash()


def test_primitive_limits_and_unique_ids():
    built = build_questions(make_profile(required_technologies=["Kotlin"]),
                            {f"L{i:03d}": f"eligible requirement line {i}" for i in range(254)})
    assert len({q.id for q in built}) == len(built)
    for q in built:
        if q.kind == "score":
            assert 2 <= q.levels <= 10
        if q.kind == "choice":
            assert len(q.options) <= 255


def test_dynamic_questions():
    q = qs(required_technologies=["Jetpack Compose"], avoid_technologies=["Flutter"])
    assert "skill_req.kmp" not in q and "skill_req.kotlin" in q and "skill_ev.kmp" in q
    assert {"tech_centrality.jetpack_compose", "tech_centrality.flutter"} <= set(q)
    assert set(q["evidence.seniority"].options) == {"L000", "L001", "L002", "none"}
    assert "line_kind.L000" not in q and {"line_kind.L001", "line_skill.L002", "line_ev.L001"} <= set(q)
    assert q["line_skill.L001"].options[-1] == "none"
    assert q["line_kind.L001"].state == "job" and q["line_ev.L001"].state == "fit"
    assert q["line_kind.L001"].body["instructions"]["line"] == "`job.lines.L001`"


def test_static_questions_follow_spec():
    q = qs()
    assert q["role_family"].kind == "choice" and len(q["role_family"].options) == 10
    assert q["android_relevance"].levels == 5 and q["staff_ic_signal"].kind == "noul"
    assert q["title_level"].options == q["seniority"].options
    assert len(q["domain"].options) == 15 and q["min_years_required"].options[0] == "not_stated"
    assert all(v is None for k, v in q["domain"].body["criteria"].items()
               if k not in {"ai_ml", "enterprise", "media_streaming", "delivery_logistics", "government_defense", "other"})


def test_optional_fit_questions():
    assert "role_preference_fit" not in qs() and "location_match" not in qs()
    both = qs(preferred_roles=["Staff Android"], preferred_locations=["Remote US"])
    assert both["role_preference_fit"].levels == 4
    assert both["location_match"].options == ["in_preferred_location", "outside_preferred_locations", "unclear"]


def test_question_set_hash_changes_with_questions():
    a = build_questions(make_profile(), {"L000": "Build Android apps with Kotlin daily"})
    b = build_questions(make_profile(), {"L000": "Build iOS apps with Swift every day", "L001": "Mentor other engineers"})
    assert question_set_hash(a) != question_set_hash(b)
    assert question_set_hash(a) == question_set_hash(build_questions(make_profile(), {"L000": "Other text, same shape here"}))
