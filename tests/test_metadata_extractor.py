"""
Purpose: Tests for App/intent/metadata_extractor.py.
Scope: The single-call LLM extraction path, using FakeLLMClient.
"""
import pytest

from App.intent.metadata_extractor import MetadataExtractionError, extract_raw


def test_extract_raw_all_fields_present(fake_llm):
    raw = extract_raw(
        fake_llm,
        "Reset password for aman.gupta. My email is aman.gupta@company.com and employee id is EMP12345.",
    )
    assert raw["intent"] == "password_reset"
    assert raw["username"] == "aman.gupta"
    assert raw["email"] == "aman.gupta@company.com"
    assert raw["employee_id"] == "EMP12345"


def test_extract_raw_username_only(fake_llm):
    raw = extract_raw(fake_llm, "Reset password for aman.gupta")
    assert raw["username"] == "aman.gupta"
    assert raw["email"] is None
    assert raw["employee_id"] is None


def test_extract_raw_email_only(fake_llm):
    raw = extract_raw(fake_llm, "Reset password, my email is priya.sharma@company.com")
    assert raw["email"] == "priya.sharma@company.com"
    assert raw["username"] is None
    assert raw["employee_id"] is None


def test_extract_raw_employee_id_only(fake_llm):
    raw = extract_raw(fake_llm, "Reset password, employee id EMP99887")
    assert raw["employee_id"] == "EMP99887"
    assert raw["username"] is None
    assert raw["email"] is None


def test_extract_raw_no_fields_present(fake_llm):
    raw = extract_raw(fake_llm, "Reset password.")
    assert raw["username"] is None
    assert raw["email"] is None
    assert raw["employee_id"] is None


def test_extract_raw_empty_query_raises(fake_llm):
    with pytest.raises(MetadataExtractionError):
        extract_raw(fake_llm, "")


def test_extract_raw_whitespace_query_raises(fake_llm):
    with pytest.raises(MetadataExtractionError):
        extract_raw(fake_llm, "   ")
