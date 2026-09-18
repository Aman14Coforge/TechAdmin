"""
Test Intent Classifier
Author: Team
Purpose: Test intent classification functionality

TODO: Implement tests
- Test valid intent classification
- Test invalid input handling
- Test confidence scoring
- Test edge cases
"""

import pytest

from App.intent.unified_extractor import UnifiedIntentMetadataExtractor


def test_intent_classification_password_reset():
    """TODO: Test password reset intent detection"""
    pass


def test_intent_classification_invalid_input():
    """TODO: Test handling of invalid input"""
    pass


def test_intent_confidence_score():
    """TODO: Test confidence score calculation"""
    pass


def test_explicit_email_overrides_model_metadata():
    """The requested email must be used instead of incorrect model output."""

    result = UnifiedIntentMetadataExtractor._prepare_result(
        raw_result={
            "intent": "get_user_details",
            "confidence": 0.2,
            "explanation": "User lookup",
            "metadata": {
                "email": "aman.14.gupta@coforge.com",
                "username": "aman.14.gupta",
            },
        },
        user_input="get user detail amit.bhagat@coforge.com",
    )

    assert result["metadata"]["email"] == "amit.bhagat@coforge.com"
    assert result["metadata"]["username"] == "amit.bhagat"
