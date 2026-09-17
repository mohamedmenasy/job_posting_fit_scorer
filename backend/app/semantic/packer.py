"""Token-budget request packing (spec §6.4)."""

import math

from app.domain import canonical_json
from app.semantic.catalog import Q


class PostingOrResumeTooLong(Exception):
    pass


def estimate_tokens(state: dict, questions: list[Q]) -> int:
    return math.ceil(len(canonical_json({"state": state, "questions": {q.id: q.body for q in questions}})) / 3.5)


def pack(state: dict, questions: list[Q], budget: int) -> list[list[Q]]:
    if estimate_tokens(state, []) > budget:
        raise PostingOrResumeTooLong(f"state alone exceeds the {budget}-token request budget")
    groups: list[list[Q]] = [[]]
    for q in questions:
        # ponytail: re-serializes the growing group per question (O(n²) chars); fine for ~200 questions
        if estimate_tokens(state, groups[-1] + [q]) <= budget:
            groups[-1].append(q)
        elif groups[-1] and estimate_tokens(state, [q]) <= budget:
            groups.append([q])
        else:
            raise PostingOrResumeTooLong(f"question {q.id} does not fit the {budget}-token request budget")
    return [g for g in groups if g]
