"""
Purpose: Tests for App/intent/validator.py.
Scope: Deterministic (non-LLM) missing-field detection.
"""
from App.intent.validator import validate_fields
from App.schemas.extraction import ExtractedFields


def test_all_fields_present_is_valid():
    fields = ExtractedFields(username="aman.gupta", email="aman.gupta@company.com", employee_id="EMP12345")
    missing, is_valid = validate_fields("password_reset", fields)
    assert missing == []
    assert is_valid is True


def test_missing_username_only():
    fields = ExtractedFields(email="aman.gupta@company.com", employee_id="EMP12345")
    missing, is_valid = validate_fields("password_reset", fields)
    assert missing == ["username"]
    assert is_valid is False


def test_missing_email_only():
    fields = ExtractedFields(username="aman.gupta", employee_id="EMP12345")
    missing, is_valid = validate_fields("password_reset", fields)
    assert missing == ["email"]
    assert is_valid is False


def test_missing_employee_id_only():
    fields = ExtractedFields(username="aman.gupta", email="aman.gupta@company.com")
    missing, is_valid = validate_fields("password_reset", fields)
    assert missing == ["employee_id"]
    assert is_valid is False


def test_multiple_missing_fields():
    fields = ExtractedFields(username="aman.gupta")
    missing, is_valid = validate_fields("password_reset", fields)
    assert set(missing) == {"email", "employee_id"}
    assert is_valid is False


def test_all_fields_missing():
    fields = ExtractedFields()
    missing, is_valid = validate_fields("password_reset", fields)
    assert set(missing) == {"username", "email", "employee_id"}
    assert is_valid is False


def test_unrecognized_intent_has_no_mandatory_fields():
    fields = ExtractedFields()
    missing, is_valid = validate_fields("unknown", fields)
    assert missing == []
    assert is_valid is True


def test_malformed_email_is_treated_as_missing():
    fields = ExtractedFields(username="aman.gupta", email="not-an-email", employee_id="EMP12345")
    assert fields.email is None  # normalized to None by the schema
    missing, is_valid = validate_fields("password_reset", fields)
    assert missing == ["email"]
    assert is_valid is False
