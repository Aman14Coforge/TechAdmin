"""
Purpose: Tests for App/intent/classifier.py.
Scope: Intent resolution against the existing Configs/intent_mapping.yaml.
"""
from App.intent.classifier import classify_intent


def test_known_intent_is_returned_as_is():
    assert classify_intent({"intent": "password_reset"}) == "password_reset"


def test_unrecognized_intent_degrades_to_unknown():
    assert classify_intent({"intent": "make_coffee"}) == "unknown"


def test_missing_intent_key_degrades_to_unknown():
    assert classify_intent({}) == "unknown"


def test_non_dict_input_degrades_to_unknown():
    assert classify_intent(None) == "unknown"


def test_non_string_intent_value_degrades_to_unknown():
    assert classify_intent({"intent": 123}) == "unknown"
