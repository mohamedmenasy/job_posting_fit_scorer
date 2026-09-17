import pytest
from pydantic import ValidationError

from app.scoring.config import ScoringConfig


def test_defaults_match_spec():
    c = ScoringConfig()
    assert c.weights.technical == 30 and c.weights.management == 5
    assert c.arrangement_matrix["remote"]["onsite"] == 0.0
    assert c.penalties.missing_required_skill.cap == 20
    assert c.blockers.threshold == 0.8 and c.blockers.possible_threshold == 0.5
    assert c.status_thresholds.strong_match == 85
    assert c.evidence_min_probability == 0.5


@pytest.mark.parametrize("patch", [
    {"weights": {"technical": -1}},
    {"weights": {"technical": 0, "android": 0, "seniority": 0, "domain": 0}},
    {"blockers": {"threshold": 0.5, "possible_threshold": 0.6}},
    {"status_thresholds": {"strong_match": 70, "good_match": 70, "review": 55}},
    {"confidence_bands": {"accept": 0.5, "review": 0.6}},
    {"arrangement_matrix": {"remote": {"remote": 1.5}}},
    {"evidence_min_probability": 1.2},
])
def test_invalid_configs_rejected(patch):
    data = ScoringConfig().model_dump()
    for k, v in patch.items():
        if k == "arrangement_matrix":
            data[k]["remote"].update(v["remote"])
        elif isinstance(v, dict):
            data[k].update(v)
        else:
            data[k] = v
    with pytest.raises(ValidationError):
        ScoringConfig.model_validate(data)
