"""
Purpose: Tests for App/core/response_parser.py.
Scope: All required robustness cases — pure JSON, fenced JSON, JSON
       surrounded by reasoning/prose, formatting noise, and malformed
       input that must raise rather than guess.
"""
import pytest

from App.core.response_parser import ResponseParsingError, extract_json_object


def test_pure_json_response():
    raw = '{"intent": "password_reset", "username": "aman.gupta", "email": null, "employee_id": null}'
    result = extract_json_object(raw)
    assert result["intent"] == "password_reset"
    assert result["username"] == "aman.gupta"


def test_json_in_markdown_fence_with_json_tag():
    raw = '```json\n{"intent": "password_reset", "username": "aman.gupta"}\n```'
    result = extract_json_object(raw)
    assert result == {"intent": "password_reset", "username": "aman.gupta"}


def test_json_in_plain_markdown_fence():
    raw = '```\n{"intent": "unknown"}\n```'
    result = extract_json_object(raw)
    assert result == {"intent": "unknown"}


def test_json_surrounded_by_reasoning_text_before_and_after():
    """The exact scenario the task describes — reasoning before AND
    after the JSON object, no markdown fence at all."""
    raw = (
        "Let me analyze this request carefully.\n\n"
        "The requested operation is a password reset.\n\n"
        "{\n"
        '  "intent": "password_reset",\n'
        '  "username": "aman.gupta",\n'
        '  "email": "aman.gupta@company.com",\n'
        '  "employee_id": "EMP12345"\n'
        "}\n\n"
        "This contains all required information."
    )
    result = extract_json_object(raw)
    assert result == {
        "intent": "password_reset",
        "username": "aman.gupta",
        "email": "aman.gupta@company.com",
        "employee_id": "EMP12345",
    }


def test_json_with_reasoning_before_only():
    raw = 'The username is aman.gupta.\n\n{"intent": "password_reset", "username": "aman.gupta"}'
    result = extract_json_object(raw)
    assert result == {"intent": "password_reset", "username": "aman.gupta"}


def test_json_with_minor_formatting_noise():
    raw = '   \n\n  {"intent": "password_reset", "username": "aman.gupta"}   \n  '
    result = extract_json_object(raw)
    assert result == {"intent": "password_reset", "username": "aman.gupta"}


def test_json_with_string_value_containing_braces_is_not_confused():
    """A brace inside a quoted string value must not break the balanced
    scan used to locate the real JSON object."""
    raw = 'Some text {not real json} then the real one: {"intent": "password_reset", "username": "user{123}"}'
    result = extract_json_object(raw)
    assert result["intent"] == "password_reset"
    assert result["username"] == "user{123}"


def test_prefers_candidate_with_intent_key_over_incidental_braces():
    raw = 'Note: config was {"unrelated": true} but the result is {"intent": "unknown"}'
    result = extract_json_object(raw)
    assert result == {"intent": "unknown"}


def test_malformed_json_raises_response_parsing_error():
    raw = "I cannot help with that request, sorry."
    with pytest.raises(ResponseParsingError):
        extract_json_object(raw)


def test_empty_string_raises_response_parsing_error():
    with pytest.raises(ResponseParsingError):
        extract_json_object("")


def test_whitespace_only_raises_response_parsing_error():
    with pytest.raises(ResponseParsingError):
        extract_json_object("   \n\t  ")


def test_none_input_raises_response_parsing_error():
    with pytest.raises(ResponseParsingError):
        extract_json_object(None)  # type: ignore[arg-type]


def test_unbalanced_braces_raise_response_parsing_error():
    raw = '{"intent": "password_reset", "username": "aman.gupta"'  # missing closing brace
    with pytest.raises(ResponseParsingError):
        extract_json_object(raw)


def test_json_array_alone_is_not_treated_as_the_result():
    """The expected shape is always an object, not a bare array — an
    array-only response should not be silently accepted as valid."""
    raw = '["password_reset", "aman.gupta"]'
    with pytest.raises(ResponseParsingError):
        extract_json_object(raw)
