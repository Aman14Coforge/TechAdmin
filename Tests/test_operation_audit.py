from types import SimpleNamespace
from unittest.mock import Mock

from App.db import operation_audit


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