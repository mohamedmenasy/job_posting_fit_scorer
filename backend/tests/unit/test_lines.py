from app.semantic.lines import eligible_ids, segment


def test_bullets_whitespace_and_empty_lines():
    lines = segment("About the role:\r\n\r\n-   Build   Android apps with Kotlin\n• Lead architecture reviews\n"
                    "1. Mentor engineers daily\n2) Ship\n  -  \n")
    assert lines == {"L000": "About the role:", "L001": "Build Android apps with Kotlin",
                     "L002": "Lead architecture reviews", "L003": "Mentor engineers daily", "L004": "Ship"}


def test_long_line_split_on_sentences():
    long = ("We build payments. " * 20).strip()
    lines = segment(long)
    assert len(lines) == 20 and lines["L000"] == "We build payments."


def test_cap_merges_shortest_adjacent_pair():
    text = "\n".join(f"line number {i}" if i != 5 else "x" for i in range(300))
    lines = segment(text)
    assert len(lines) == 254
    assert list(lines) == [f"L{i:03d}" for i in range(254)]
    assert "line number 299" in lines["L253"]


def test_eligibility():
    lines = {"L000": "Requirements:", "L001": "Short one", "L002": "5+ years building Android apps"}
    assert eligible_ids(lines) == ["L002"]
