from __future__ import annotations

import pytest

from App.intent.analyzer import IntentAnalyzer
from App.schemas.models import WorkflowState
from App.workflows.graph import build_graph
from tests.fakes import FakeLLM


def invoke_with_fake(
    llm_data: dict,
    query: str,
) -> WorkflowState:
    fake_llm = FakeLLM(
        llm_data,
    )

    graph = build_graph(
        IntentAnalyzer(
            fake_llm,
        )
    )

    raw_result = graph.invoke(
        WorkflowState(
            user_query=query,
        )
    )

    return WorkflowState.model_validate(
        raw_result,
    )


def test_username_is_derived_from_email() -> None:
    state = invoke_with_fake(
        {
            "intent": "password_reset",
            "username": None,
            "email": (
                "Shreesanyog.Rath@Coforge.com"
            ),
            "employee_id": "EMP10001",
            "confidence": 0.99,
        },
        (
            "Reset password using email "
            "Shreesanyog.Rath@Coforge.com "
            "and employee ID EMP10001"
        ),
    )

    assert state.fields.username == (
        "Shreesanyog.Rath"
    )

    assert state.fields.username_source == (
        "derived_from_email"
    )

    assert state.validation is not None
    assert state.validation.is_valid is True

    assert "username" in (
        state.validation.derived_fields
    )

    assert state.tool_called is not None
    assert state.tool_called.value == (
        "reset_password_tool"
    )


def test_missing_employee_id_requests_it() -> None:
    state = invoke_with_fake(
        {
            "intent": "password_reset",
            "username": None,
            "email": (
                "Shreesanyog.Rath@Coforge.com"
            ),
            "employee_id": None,
            "confidence": 0.99,
        },
        (
            "Reset password using email "
            "Shreesanyog.Rath@Coforge.com"
        ),
    )

    assert state.fields.username == (
        "Shreesanyog.Rath"
    )

    assert state.validation is not None
    assert state.validation.is_valid is False

    assert state.validation.missing_fields == [
        "employee_id",
    ]

    assert state.selected_agent == (
        "identity_agent"
    )

    assert state.clarification_required is True

    assert state.clarification_question == (
        "Please provide the employee ID."
    )

    assert state.tool_called is None
    assert state.tool_result is None


@pytest.mark.parametrize(
    "intent, expected_tool, group_name",
    [
        (
            "password_reset",
            "reset_password_tool",
            None,
        ),
        (
            "account_unlock",
            "unlock_account_tool",
            None,
        ),
        (
            "grant_access",
            "grant_revoke_access_tool",
            "VPN-Users",
        ),
        (
            "revoke_access",
            "grant_revoke_access_tool",
            "VPN-Users",
        ),
        (
            "failed_login_investigation",
            "investigate_failed_login_tool",
            None,
        ),
    ],
)
def test_correct_tool_is_called(
    intent: str,
    expected_tool: str,
    group_name: str | None,
) -> None:
    query = (
        f"{intent} using email "
        f"user.name@example.com and "
        f"employee ID EMP10001"
    )

    llm_data = {
        "intent": intent,
        "username": None,
        "email": "user.name@example.com",
        "employee_id": "EMP10001",
        "group_name": group_name,
        "confidence": 0.99,
    }

    if group_name:
        query = (
            f"{query} for group "
            f"{group_name}"
        )

    state = invoke_with_fake(
        llm_data,
        query,
    )

    assert state.validation is not None
    assert state.validation.is_valid is True

    assert state.fields.username == (
        "user.name"
    )

    assert state.fields.username_source == (
        "derived_from_email"
    )

    assert state.selected_agent == (
        "identity_agent"
    )

    assert state.tool_called is not None
    assert state.tool_called.value == (
        expected_tool
    )

    assert state.tool_result is not None
    assert (
        state.tool_result.status.value
        == "not_implemented"
    )


def test_hallucinated_email_is_rejected() -> None:
    state = invoke_with_fake(
        {
            "intent": "password_reset",
            "username": None,
            "email": "invented@example.com",
            "employee_id": "EMP10001",
            "confidence": 0.90,
        },
        (
            "Reset my password for "
            "employee ID EMP10001"
        ),
    )

    assert state.fields.email is None
    assert state.fields.username is None

    assert state.validation is not None
    assert state.validation.is_valid is False

    assert "email" in (
        state.validation.rejected_fields
    )

    assert "username" in (
        state.validation.missing_fields
    )

    assert "email" in (
        state.validation.missing_fields
    )

    assert state.tool_called is None