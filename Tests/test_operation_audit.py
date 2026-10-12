from types import SimpleNamespace
import json
from unittest.mock import Mock

from App.db import operation_audit


def test_record_execution_stores_full_redacted_output(monkeypatch):
    response = {
        "success": True,
        "intent": "get_user_details",
        "message": "User details retrieved successfully.",
        "tool_result": {
            "success": True,
            "tool": "GET_USER_DETAILS",
            "message": "User details retrieved successfully.",
            "result": {
                "backend": "api",
                "user": {"displayName": "Amit Bhagat", "accountEnabled": True},
                "temporary_password": "NeverStoreThis!",
                "password_token": "transient-vault-handle",
            },
        },
    }
    session = Mock()
    session.query.return_value.filter.return_value.count.return_value = 0
    session_context = Mock()
    session_context.__enter__ = Mock(return_value=session)
    session_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(operation_audit, "SessionLocal", Mock(return_value=session_context))

    operation_audit.record_execution("ui_history_test", response)

    execution = session.add.call_args.args[0]
    stored = json.loads(execution.result_summary)
    stored_result = stored["tool_result"]["result"]
    assert stored_result["user"] == {"displayName": "Amit Bhagat", "accountEnabled": True}
    assert stored_result["temporary_password"] == "[redacted]"
    assert "password_token" not in stored_result
    assert "NeverStoreThis!" not in execution.result_summary
    assert "transient-vault-handle" not in execution.result_summary


def test_get_request_result_loads_latest_owned_execution(monkeypatch):
    user_id = "11111111-1111-4111-8111-111111111111"
    request = SimpleNamespace(
        request_id="22222222-2222-4222-8222-222222222222",
        original_request="Get user details for amit@example.com",
        target_reference="am*********@example.com",
        status="SUCCEEDED",
        requested_at="2026-10-09T10:00:00Z",
        completed_at="2026-10-09T10:00:01Z",
    )
    response = {
        "success": True,
        "message": "User details retrieved.",
        "tool_result": {"message": "User details retrieved.", "result": {"user": {"id": "user-1"}}},
    }
    execution = SimpleNamespace(
        result_summary=json.dumps(response),
        execution_status="SUCCEEDED",
        finished_at="2026-10-09T10:00:01Z",
        duration_ms=1000,
        error_message=None,
    )
    request_result = Mock()
    request_result.first.return_value = (request, "Get User Details")
    execution_result = Mock()
    execution_result.scalars.return_value.first.return_value = execution
    session = Mock()
    session.execute.side_effect = [request_result, execution_result]
    session_context = Mock()
    session_context.__enter__ = Mock(return_value=session)
    session_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(operation_audit, "SessionLocal", Mock(return_value=session_context))

    record = operation_audit.get_request_result(user_id, request.request_id)

    assert record["request"] == "Get user details for amit@example.com"
    assert record["operation"] == "Get User Details"
    assert record["has_execution"] is True
    assert record["response"] == response
    assert record["summary"] == "User details retrieved."
    request_statement = session.execute.call_args_list[0].args[0]
    assert request_statement is not None


def test_close_request_accepts_null_tool_result_payload(monkeypatch):
    row = SimpleNamespace(
        operation_id=None,
        target_type=None,
        target_reference=None,
        request_parameters=None,
        intent_confidence=None,
        target_object_id=None,
        status=None,
        completed_at=None,
    )
    session = Mock()
    session.get.return_value = row
    session_context = Mock()
    session_context.__enter__ = Mock(return_value=session)
    session_context.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(operation_audit, "SessionLocal", Mock(return_value=session_context))
    monkeypatch.setattr(operation_audit, "ensure_operation_id", Mock(return_value=None))
    monkeypatch.setattr(operation_audit, "record_execution", Mock())
    error_logger = Mock()
    monkeypatch.setattr(operation_audit.logger, "error", error_logger)

    operation_audit.close_request(
        "ui_40457b18",
        {
            "intent": "password_reset",
            "metadata": None,
            "tool_result": {"result": None},
            "confirmation_required": True,
        },
    )

    error_logger.assert_not_called()
    assert row.target_reference is None
    assert row.status == operation_audit.STATUS_AWAITING_APPROVAL