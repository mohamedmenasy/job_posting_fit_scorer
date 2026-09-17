"""JD line segmentation (spec §6.1)."""

import re

SEGMENTATION_VERSION = "1"
MAX_LINES = 254
_BULLET = re.compile(r"^(?:[-*•–]|\d+[.)])\s*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def segment(description: str) -> dict[str, str]:
    items: list[str] = []
    for line in description.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _BULLET.sub("", " ".join(line.split()))
        if not line:
            continue
        items.extend(_SENTENCE.split(line) if len(line) > 300 else [line])
    # ponytail: O(n²) merge loop; fine for the ≤ few-hundred-line postings this sees
    while len(items) > MAX_LINES:
        i = min(range(len(items) - 1), key=lambda k: len(items[k]) + len(items[k + 1]))
        items[i:i + 2] = [f"{items[i]} {items[i + 1]}"]
    return {f"L{i:03d}": text for i, text in enumerate(items)}


def eligible_ids(lines: dict[str, str]) -> list[str]:
    return [k for k, v in lines.items() if len(v) >= 20 and not v.endswith(":")]
