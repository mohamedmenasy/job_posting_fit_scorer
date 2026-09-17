import pytest

from app.ingest.csv_import import CsvError, parse_csv, rows_from_mapping, suggest_mapping

CSV = b"Company,Job Title,Job Description,City\nAcme,Android Engineer,\"Build apps.\nShip them.\",Berlin\n"


def test_parses_headers_rows_and_quoted_newlines():
    parsed = parse_csv(CSV)
    assert parsed.columns == ["Company", "Job Title", "Job Description", "City"]
    assert parsed.rows[0]["Job Description"] == "Build apps.\nShip them."
    assert parsed.delimiter == "," and parsed.encoding == "utf-8"


def test_bom_semicolons_and_tabs():
    assert parse_csv("﻿company;title\nAcme;Dev\n".encode()).delimiter == ";"
    assert parse_csv("﻿company;title\nAcme;Dev\n".encode()).columns == ["company", "title"]
    assert parse_csv(b"company\ttitle\nAcme\tDev\n").delimiter == "\t"
    assert parse_csv("company,title\nAcmé,Dev\n".encode("latin-1")).encoding == "latin-1"


def test_duplicate_and_blank_headers_are_disambiguated():
    assert parse_csv(b"company,company,\nA,B,C\n").columns == ["company", "company_2", "column_3"]


@pytest.mark.parametrize("data,message", [
    (b"", "empty"),
    (b"company,title\n", "no data rows"),
    (b"company,title\n" + b"a,b\n" * 501, "500"),
])
def test_rejects_bad_files(data, message):
    with pytest.raises(CsvError) as err:
        parse_csv(data)
    assert message in str(err.value).lower()


@pytest.mark.parametrize("column,field", [
    ("Company", "company"), ("Employer", "company"), ("Job Title", "title"), ("Role", "title"),
    ("Job Description", "description"), ("Details", "description"), ("City", "location"),
    ("Apply Link", "source_url"), ("Salary Range", "salary_text"), ("Req ID", "external_id"),
    ("Notes", None),
])
def test_mapping_synonyms(column, field):
    assert suggest_mapping([column]).get(column) == field


def test_mapping_never_assigns_one_field_twice():
    mapping = suggest_mapping(["company", "employer", "title"])
    assert list(mapping.values()).count("company") == 1


def test_rows_from_mapping_reports_missing_required_fields():
    mapping = {"Company": "company", "Job Title": "title", "Job Description": "description"}
    rows = [{"Company": "Acme", "Job Title": "Dev", "Job Description": "x" * 60},
            {"Company": "", "Job Title": "Dev", "Job Description": "x" * 60},
            {"Company": "Acme", "Job Title": "Dev", "Job Description": ""}]
    results = rows_from_mapping(rows, mapping)
    assert results[0].posting and results[0].posting.description.startswith("x")
    assert results[1].error and "company" in results[1].error
    assert results[2].posting and results[2].posting.description == ""


def test_rows_from_mapping_ignores_unmapped_columns_and_bad_urls():
    mapping = {"Company": "company", "Job Title": "title", "Link": "source_url", "Notes": None}
    rows = [{"Company": "Acme", "Job Title": "Dev", "Link": "not a url", "Notes": "ignored"}]
    [result] = rows_from_mapping(rows, mapping)
    assert result.posting is not None and result.posting.source_url is None
    assert result.warnings and "source_url" in result.warnings[0]
