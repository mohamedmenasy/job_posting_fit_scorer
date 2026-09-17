import pytest

from app.semantic.catalog import Q
from app.semantic.packer import PostingOrResumeTooLong, estimate_tokens, pack


def q(i, size=100):
    return Q(id=f"q{i}", state="job", body={"type": "noul", "instructions": "x" * size})


def test_packs_greedily_within_budget_preserving_order():
    state = {"job": {"lines": {"L000": "y" * 100}}}
    questions = [q(i) for i in range(50)]
    groups = pack(state, questions, budget=500)
    assert len(groups) > 1
    assert [x.id for g in groups for x in g] == [x.id for x in questions]
    assert all(estimate_tokens(state, g) <= 500 for g in groups)


def test_single_request_when_it_fits():
    assert len(pack({"a": 1}, [q(1), q(2)], budget=24000)) == 1


def test_oversized_state_fails():
    with pytest.raises(PostingOrResumeTooLong):
        pack({"resume": "z" * 10_000}, [q(1)], budget=1000)


def test_oversized_single_question_fails():
    with pytest.raises(PostingOrResumeTooLong):
        pack({"a": 1}, [q(1, size=10_000)], budget=1000)
