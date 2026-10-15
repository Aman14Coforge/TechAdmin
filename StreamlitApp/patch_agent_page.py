"""Compliance Agent workspace using MCP for reports and ticket operations."""
from __future__ import annotations

from datetime import date
from html import escape
import re
from typing import Any, Callable

import pandas as pd
import streamlit as st
from loguru import logger

from App.integration.iengage.client import IEngageClient
from App.mcp_client.patch_mcp_client import PatchMCPClient
from App.services.patch.analytics_service import PatchAnalyticsService
from App.services.patch.security_history import (
    finish_security_query,
    start_security_query,
)
from App.services.patch.semantic import PatchSemanticInterpreter
from App.services.patch.security_query_service import SecurityPatchQueryService


SORTS = {
    "Missing patches: high to low": "missing_desc",
    "Risk score: high to low": "risk_desc",
    "Days open: high to low": "days_desc",
    "Device name: A to Z": "name_asc",
}


# =============================================================================
# State and common helpers
# =============================================================================


def _selected_device_names(
    frame: pd.DataFrame,
    indices: list[Any],
) -> list[str]:
    names: list[str] = []

    for index in indices:
        if not isinstance(index, int):
            continue
        if not 0 <= index < len(frame):
            continue

        name = str(
            frame.iloc[index].get("Device") or ""
        ).strip()

        if name and name not in names:
            names.append(name)

    return names


def _init() -> None:
    defaults: dict[str, Any] = {
        "security_selected": [],
        "security_selected_by_page": {},
        "security_details": None,
        "security_report": None,
        "security_job": None,
        "security_ticket_job": None,
        "security_ticket_results": None,
        "security_page": 1,
        "security_search": "",
        "security_sort": next(iter(SORTS)),
        "security_size": 25,
        "security_date": date.today().isoformat(),
        "security_conversation": [],
        "security_browse_devices": False,
        "security_patch_search_results": None,
        "security_device_list": None,
        "security_report_audit_id": None,
        "security_redirect_pending": False,
        "security_redirect_query": None,
        "security_redirect_audit_id": None,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _reset() -> None:
    for key in (
        "security_details",
        "security_report",
        "security_job",
        "security_ticket_job",
        "security_ticket_results",
        "security_patch_search_results",
        "security_device_list",
        "security_report_audit_id",
        "security_redirect_query",
        "security_redirect_audit_id",
    ):
        st.session_state[key] = None

    st.session_state.security_selected = []
    st.session_state.security_selected_by_page = {}
    st.session_state.security_conversation = []
    st.session_state.security_redirect_pending = False
    st.session_state.security_browse_devices = False


def _clear_report_context() -> None:
    """Remove report output that no longer belongs to the active view."""
    st.session_state.security_report = None
    st.session_state.security_job = None
    st.session_state.security_details = None
    st.session_state.security_patch_search_results = None
    st.session_state.security_report_audit_id = None


def _unwrap(response: dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict) and "success" in response:
        tool = response
    elif isinstance(response, dict):
        tool = response.get("result")
    else:
        tool = None

    if not isinstance(tool, dict):
        message = (
            response.get("message")
            if isinstance(response, dict)
            else "Invalid MCP response"
        )
        raise RuntimeError(message)

    result = tool.get("result")
    ticket_payload = isinstance(result, dict) and "tickets" in result

    if not tool.get("success") and not ticket_payload:
        raise RuntimeError(
            tool.get("error")
            or tool.get("message")
            or "MCP tool failed"
        )

    if not isinstance(result, dict):
        raise RuntimeError("MCP tool returned no structured result")

    return result


def _working(text: str) -> None:
    st.markdown(
        '<div class="ta-asst-head">'
        '<div class="ta-icon-tile">'
        '<span class="material-symbols-rounded">security</span>'
        '</div>'
        '<div>'
        '<div class="who">Compliance Agent</div>'
        '<div class="ta-working">'
        '<i></i><i></i><i></i>'
        f'<span>{escape(text)}</span>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _audit_start(
    query: str,
    operator: str,
    action: str,
    target: str | None = None,
) -> str | None:
    access = st.session_state.get("app_user_access") or {}

    return start_security_query(
        requester_id=access.get("user_id") or operator,
        requester_name=access.get("display_name") or operator,
        query_text=query,
        action=action,
        target=target,
        request_metadata={
            "snapshot": st.session_state.get("security_date")
        },
    )


def _audit_finish(
    query_id: str | None,
    *,
    status: str,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    finish_security_query(
        query_id,
        status=status,
        response_summary=summary,
        error_message=error,
    )


def _reported_ticket_id(
    result: dict[str, Any],
) -> str | None:
    ticket_id = result.get("ticket_id")

    if ticket_id:
        return str(ticket_id)

    message = result.get("message") or ""

    return IEngageClient._extract_ticket_id_from_message(
        {"message": message}
    )


def _latest_snapshot() -> date:
    try:
        return (
            SecurityPatchQueryService().latest_snapshot_date()
            or date.today()
        )
    except Exception:
        logger.exception("LATEST_PATCH_SNAPSHOT_LOOKUP_FAILED")
        return date.today()


def _queue_report(
    kind: str,
    devices: list[str],
    snapshot: date,
    query_id: str | None,
) -> None:
    st.session_state.security_details = None
    st.session_state.security_patch_search_results = None
    st.session_state.security_report = None
    st.session_state.security_date = snapshot.isoformat()

    st.session_state.security_job = {
        "type": kind,
        "devices": list(devices),
        "date": snapshot.isoformat(),
        "audit_id": query_id,
        "queued_for_scope": (
            "selected_devices"
            if kind == "selected"
            else "single_device"
            if kind == "device"
            else "all_non_compliant_devices"
        ),
    }


def _queue_device_list(
    snapshot: date,
    status: str,
    query_id: str | None,
    search: str = "",
) -> None:
    _clear_report_context()

    st.session_state.security_selected_by_page = {}
    st.session_state.security_selected = []
    st.session_state.security_date = snapshot.isoformat()

    st.session_state.security_device_list = {
        "date": snapshot.isoformat(),
        "status": status,
        "page": 1,
        "audit_id": query_id,
        "search": search,
    }


# =============================================================================
# Quick action dialogs
# =============================================================================


@st.dialog("Show devices")
def _device_list_dialog(operator: str) -> None:
    latest = _latest_snapshot()

    st.caption(
        "Choose a stored Ivanti snapshot and the device state to review."
    )

    with st.form("security_list_devices_form", border=False):
        snapshot = st.date_input(
            "Snapshot date",
            value=latest,
            max_value=date.today(),
        )
        status = st.selectbox(
            "Devices to show",
            ["Non-compliant", "Resolved", "All devices"],
        )
        submitted = st.form_submit_button(
            "Show devices",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    scope = {
        "Non-compliant": "non_compliant",
        "Resolved": "resolved",
        "All devices": "all",
    }[status]

    query = (
        f"Show {scope.replace('_', ' ')} endpoints "
        f"for {snapshot.isoformat()}"
    )
    query_id = _audit_start(
        query,
        operator,
        "device_list",
        scope,
    )

    st.session_state.security_conversation.append(
        {"role": "user", "content": query}
    )
    _queue_device_list(snapshot, scope, query_id)
    st.rerun()


@st.dialog("Search by device")
def _device_search_dialog(operator: str) -> None:
    st.caption(
        "Search the stored patch-compliance evidence by endpoint hostname."
    )

    with st.form("security_device_search_form", border=False):
        device = st.text_input(
            "Device name",
            placeholder="Enter all or part of an endpoint name",
        )
        snapshot = st.date_input(
            "Snapshot date",
            value=_latest_snapshot(),
            max_value=date.today(),
        )
        status = st.selectbox(
            "Include",
            [
                "Non-compliant in snapshot",
                "Resolved by this date",
                "All devices in snapshot",
            ],
        )
        submitted = st.form_submit_button(
            "Search devices",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    term = device.strip()
    if not term:
        st.error("Enter a device name or part of a name.")
        return

    query = f"Search devices matching {term} on {snapshot.isoformat()}"
    query_id = _audit_start(
        query,
        operator,
        "device_search",
        term,
    )

    st.session_state.security_conversation.append(
        {"role": "user", "content": query}
    )

    scope = {
        "Non-compliant in snapshot": "non_compliant",
        "Resolved by this date": "resolved",
        "All devices in snapshot": "all",
    }[status]

    _queue_device_list(
        snapshot,
        scope,
        query_id,
        search=term,
    )
    st.rerun()


@st.dialog("Device AI report")
def _device_report_dialog(operator: str) -> None:
    st.caption(
        "Generate a comprehensive device report from persisted Ivanti evidence."
    )

    with st.form("security_device_report_form", border=False):
        device = st.text_input(
            "Device name",
            placeholder="Enter an endpoint hostname",
        )
        snapshot = st.date_input(
            "Report date",
            value=_latest_snapshot(),
            max_value=date.today(),
        )
        submitted = st.form_submit_button(
            "Generate device AI report",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    name = device.strip()
    if not name:
        st.error("Enter a device name.")
        return

    query = (
        f"Generate a patch report for device {name} "
        f"on {snapshot.isoformat()}"
    )
    query_id = _audit_start(
        query,
        operator,
        "device_report",
        name,
    )

    st.session_state.security_conversation.append(
        {"role": "user", "content": query}
    )
    _queue_report("device", [name], snapshot, query_id)
    st.rerun()


@st.dialog("Fleet AI report")
def _fleet_ai_report_dialog(operator: str) -> None:
    latest = _latest_snapshot()

    st.caption(
        "Generate fleet-wide intelligence for all endpoints with confirmed "
        "missing patches in the selected snapshot."
    )

    with st.form("security_fleet_ai_report_form", border=False):
        snapshot = st.date_input(
            "Report snapshot",
            value=latest,
            max_value=date.today(),
            key="security_fleet_ai_report_date",
        )

        st.markdown(
            """
            The report includes:

            - Non-compliant endpoint and missing-patch totals
            - Highest-priority devices
            - Most commonly missing patches
            - Severity and operating-system distribution
            - Stored exposure trend
            - Ticket eligibility and resolved-history context
            - Ollama findings and recommended actions
            """
        )

        submitted = st.form_submit_button(
            "Generate fleet AI report",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    query = (
        "Generate a fleet-wide AI patch-compliance "
        f"report for {snapshot.isoformat()}"
    )
    query_id = _audit_start(
        query,
        operator,
        "fleet_report",
        snapshot.isoformat(),
    )

    st.session_state.security_conversation.append(
        {"role": "user", "content": query}
    )
    _queue_report("fleet", [], snapshot, query_id)
    st.rerun()


@st.dialog("Search patch or KB")
def _patch_search_dialog(operator: str) -> None:
    st.caption(
        "Find every endpoint with stored evidence for a patch name, KB, or Q identifier."
    )

    with st.form("security_patch_search_form", border=False):
        patch = st.text_input(
            "Patch name or KB number",
            placeholder="For example, KB5002912",
        )
        snapshot = st.date_input(
            "Search snapshot date",
            value=_latest_snapshot(),
            max_value=date.today(),
        )
        submitted = st.form_submit_button(
            "Find affected devices",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    value = patch.strip()
    if not value:
        st.error("Enter a patch name or KB number.")
        return

    query = f"Find devices missing {value} on {snapshot.isoformat()}"
    query_id = _audit_start(
        query,
        operator,
        "patch_search",
        value,
    )

    try:
        result = SecurityPatchQueryService().list_devices(
            report_date=snapshot,
            patch_query=value,
            page=1,
            page_size=25,
        )

        st.session_state.security_patch_search_results = {
            "patch": value,
            "date": snapshot.isoformat(),
            "page": 1,
            **result,
        }
        st.session_state.security_details = None
        st.session_state.security_report = None
        st.session_state.security_date = snapshot.isoformat()

        _audit_finish(
            query_id,
            status="completed",
            summary={
                "matches": result["total"],
                "snapshot": snapshot.isoformat(),
            },
        )

        st.session_state.security_conversation.extend(
            [
                {"role": "user", "content": query},
                {
                    "role": "assistant",
                    "content": (
                        f"Found {result['total']} device(s) matching {value} "
                        f"in the {snapshot.isoformat()} snapshot."
                    ),
                },
            ]
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _audit_finish(query_id, status="failed", error=error)
        st.error(f"Patch search failed: {error}")
        return

    st.rerun()


@st.dialog("Raise a remediation ticket")
def _raise_ticket_dialog(operator: str) -> None:
    with st.form("security_ticket_request_form", border=False):
        device = st.text_input(
            "Device name",
            placeholder="Enter the affected endpoint",
        )
        st.caption(
            "A human-approval step will appear before the remediation request is sent to iEngage."
        )
        submitted = st.form_submit_button(
            "Continue to approval",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    name = device.strip()
    if not name:
        st.error("Enter the affected device name.")
        return

    query = f"Raise a remediation ticket for {name}"
    query_id = _audit_start(
        query,
        operator,
        "patch_ticket",
        name,
    )

    st.session_state.security_conversation.append(
        {"role": "user", "content": query}
    )
    st.session_state.security_details = None
    st.session_state.security_report = None
    st.session_state.security_patch_search_results = None
    st.session_state.security_ticket_job = {
        "devices": [name],
        "reason": "Patch remediation requested from Compliance Agent.",
        "operator": operator,
        "audit_id": query_id,
    }
    st.session_state.security_ticket_results = None
    st.rerun()


# =============================================================================
# Identity-style quick action cards
# =============================================================================

def _render_security_quick_actions(
    operator: str,
) -> None:
    """Render Identity-style Security Agent quick-action cards."""

    st.markdown(
        """
        <div class="ta-hello">
            <h3>Quick actions</h3>
            <p>
                Pick a task, or describe what you need
                in the box below.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    actions: tuple[
        tuple[
            str,
            str,
            str,
            Callable[[str], None],
        ],
        ...,
    ] = (
        (
            "show_devices",
            "Show devices",
            ":material/devices:",
            _device_list_dialog,
        ),
        (
            "search_device",
            "Search by device",
            ":material/search:",
            _device_search_dialog,
        ),
        (
            "search_patch",
            "Search patch or KB",
            ":material/system_update:",
            _patch_search_dialog,
        ),
        (
            "device_report",
            "Device AI report",
            ":material/monitor_heart:",
            _device_report_dialog,
        ),
        (
            "fleet_report",
            "Fleet AI report",
            ":material/analytics:",
            _fleet_ai_report_dialog,
        ),
        (
            "raise_ticket",
            "Raise a ticket",
            ":material/confirmation_number:",
            _raise_ticket_dialog,
        ),
    )

    for row_start in range(
        0,
        len(actions),
        3,
    ):
        row_actions = actions[
            row_start:row_start + 3
        ]

        columns = st.columns(
            3,
            gap="medium",
        )

        for column, action in zip(
            columns,
            row_actions,
        ):
            (
                action_key,
                title,
                icon,
                dialog,
            ) = action

            with column:
                with st.container(
                    key=(
                        "qa_security_"
                        f"{action_key}"
                    )
                ):
                    if st.button(
                        title,
                        key=(
                            "security_quick_"
                            f"{action_key}"
                        ),
                        icon=icon,
                        width="stretch",
                    ):
                        dialog(operator)
# =============================================================================
# Report generation and rendering
# =============================================================================


def _run_job() -> None:
    job = st.session_state.security_job

    if not isinstance(job, dict):
        return

    report_date = date.fromisoformat(job["date"])
    report_type = str(job.get("type") or "fleet")
    devices = list(job.get("devices") or [])

    if report_type == "device":
        text = f"Analyzing stored patch evidence for {devices[0]}…"
    elif report_type == "selected":
        text = (
            f"Analyzing patch exposure across {len(devices)} selected endpoints…"
        )
    else:
        text = (
            "Analyzing the complete non-compliant fleet for "
            f"{report_date.isoformat()}…"
        )

    _working(text)

    try:
        client = PatchMCPClient()

        if report_type == "device":
            result = _unwrap(
                client.device_report(devices[0], report_date)
            )
        elif report_type == "selected":
            result = _unwrap(
                client.selected_report(devices, report_date)
            )
        else:
            result = _unwrap(client.fleet_report(report_date))

        result["_report_context"] = {
            "snapshot": report_date.isoformat(),
            "scope": job.get("queued_for_scope"),
            "devices": devices,
            "generated_via": "mcp",
        }
        st.session_state.security_report = result

        ai = result.get("ai") or {}
        analysis = ai.get("analysis") or {}
        summary = analysis.get("executive_summary")

        st.session_state.security_conversation.append(
            {
                "role": "assistant",
                "content": summary
                or (
                    "The evidence report is ready. The AI interpretation was "
                    "not available; open the report for deterministic analytics "
                    "and diagnostic details."
                ),
            }
        )

        _audit_finish(
            job.get("audit_id"),
            status="completed",
            summary={
                "report_type": result.get("report_type"),
                "snapshot": report_date.isoformat(),
                "evidence_summary": (
                    result.get("evidence", {}).get("summary", {})
                ),
                "ai_available": ai.get("available"),
                "ai_error": ai.get("error"),
                "generated_via": "mcp",
            },
        )

        if job.get("audit_id"):
            st.session_state.security_report_audit_id = job["audit_id"]

    except Exception as mcp_error:
        logger.exception(
            "PATCH_AI_REPORT_MCP_FAILED | scope={} | devices={} | date={}",
            report_type,
            devices,
            report_date.isoformat(),
        )

        try:
            analytics = PatchAnalyticsService()

            if report_type == "device":
                result = analytics.device_report(
                    devices[0],
                    report_date=report_date,
                )
            elif report_type == "selected":
                result = analytics.fleet_report(
                    report_date=report_date,
                    device_names=devices,
                )
            else:
                result = analytics.fleet_report(
                    report_date=report_date,
                )

            result["_report_context"] = {
                "snapshot": report_date.isoformat(),
                "scope": job.get("queued_for_scope"),
                "devices": devices,
                "generated_via": "local_fallback",
            }
            result["mcp_warning"] = (
                "The MCP report operation was unavailable. The report was "
                "generated through the local analytics service. "
                f"MCP error: {type(mcp_error).__name__}: {mcp_error}"
            )
            st.session_state.security_report = result

            ai = result.get("ai") or {}
            analysis = ai.get("analysis") or {}
            summary = analysis.get("executive_summary")

            st.session_state.security_conversation.append(
                {
                    "role": "assistant",
                    "content": summary
                    or "The evidence report is ready using local analytics.",
                }
            )

            _audit_finish(
                job.get("audit_id"),
                status="completed",
                summary={
                    "report_type": result.get("report_type"),
                    "snapshot": report_date.isoformat(),
                    "evidence_summary": (
                        result.get("evidence", {}).get("summary", {})
                    ),
                    "ai_available": ai.get("available"),
                    "ai_error": ai.get("error"),
                    "mcp_fallback": True,
                },
            )

            if job.get("audit_id"):
                st.session_state.security_report_audit_id = job["audit_id"]

        except Exception as fallback_error:
            logger.exception(
                "PATCH_AI_REPORT_FALLBACK_FAILED | scope={} | date={}",
                report_type,
                report_date.isoformat(),
            )

            error = (
                f"MCP report failed ({type(mcp_error).__name__}: {mcp_error}); "
                "local report generation also failed "
                f"({type(fallback_error).__name__}: {fallback_error})."
            )
            st.session_state.security_report = {
                "error": error,
                "_report_context": {
                    "snapshot": report_date.isoformat(),
                    "scope": job.get("queued_for_scope"),
                    "devices": devices,
                },
            }
            st.session_state.security_conversation.append(
                {"role": "assistant", "content": error}
            )
            _audit_finish(
                job.get("audit_id"),
                status="failed",
                error=error,
            )

    st.session_state.security_job = None
    st.rerun()


def _current_report_snapshot() -> str | None:
    device_list = st.session_state.get("security_device_list")

    if isinstance(device_list, dict):
        value = str(device_list.get("date") or "")
        return value or None

    value = str(st.session_state.get("security_date") or "")
    return value or None


def _render_analysis_list(title: str, values: Any) -> None:
    if not values:
        return

    if isinstance(values, dict):
        values = [values]
    elif not isinstance(values, list):
        values = [values]

    st.markdown(f"**{title}**")

    for value in values:
        if isinstance(value, dict):
            with st.container(border=True):
                for field, detail in value.items():
                    st.markdown(
                        f"**{str(field).replace('_', ' ').title()}**"
                    )
                    if isinstance(detail, list):
                        for entry in detail:
                            st.write("• " + str(entry))
                    else:
                        st.write(detail)
        else:
            st.write("• " + str(value))


def _render_report(report: dict[str, Any]) -> None:
    if report.get("error"):
        st.error(report["error"])
        return

    context = (
        report.get("_report_context")
        if isinstance(report.get("_report_context"), dict)
        else {}
    )
    evidence = (
        report.get("evidence")
        if isinstance(report.get("evidence"), dict)
        else {}
    )
    report_snapshot = str(
        context.get("snapshot") or evidence.get("snapshot") or ""
    )
    current_snapshot = _current_report_snapshot()

    if (
        report_snapshot
        and current_snapshot
        and report_snapshot != current_snapshot
    ):
        st.warning(
            "This report was generated for "
            f"{report_snapshot}, while the current device view uses "
            f"{current_snapshot}. Generate a new report for the active snapshot."
        )

        if st.button(
            "Remove old report",
            key="remove_stale_security_report",
        ):
            st.session_state.security_report = None
            st.session_state.security_report_audit_id = None
            st.rerun()
        return

    generation_path = context.get("generated_via")
    st.caption(
        "Security report · "
        f"{str(report.get('report_type') or 'patch').replace('_', ' ')} · "
        f"{report_snapshot or 'stored evidence'}"
        + (f" · {generation_path}" if generation_path else "")
    )

    if report.get("mcp_warning"):
        st.warning(report["mcp_warning"])

    summary = evidence.get("summary") or {}
    ai = report.get("ai") or {}
    analysis = ai.get("analysis") or {}

    if analysis.get("executive_summary"):
        st.markdown(
            '<div class="ta-note" style="margin:12px 0 16px">'
            '<strong>Executive summary</strong><br>'
            f'{escape(str(analysis["executive_summary"]))}'
            '</div>',
            unsafe_allow_html=True,
        )

    device_scope = report.get("report_type") == "device"
    metric_specs = [
        (
            "Snapshots" if device_scope else "Non-compliant devices",
            summary.get("snapshots", summary.get("devices", "—")),
        ),
        (
            "Missing instances",
            summary.get(
                "total_missing_instances",
                summary.get("current_missing", "—"),
            ),
        ),
        ("Ticket eligible", summary.get("ticket_eligible", "—")),
        ("High-risk devices", summary.get("high_risk_devices", "—")),
        (
            "Persistent ≥14 days",
            summary.get("persistent_14_day_devices", "—"),
        ),
        ("Resolved historical", summary.get("resolved_devices", "—")),
    ]
    visible = [
        (label, value)
        for label, value in metric_specs
        if value != "—"
    ]

    if visible:
        columns = st.columns(len(visible))
        for column, (label, value) in zip(columns, visible):
            column.metric(label, value)

    unavailable = evidence.get("unavailable_devices") or []
    if unavailable:
        st.warning(
            "No evidence at this snapshot for: "
            + ", ".join(unavailable)
        )

    errors = evidence.get("data_errors") or []
    if errors:
        st.warning(
            f"Evidence retrieval failed for {len(errors)} device(s)."
        )
        st.dataframe(errors, hide_index=True, width="stretch")

    labels = (
        ["Overview", "Patch exposure", "AI analysis"]
        if device_scope
        else [
            "Overview",
            "Priority devices",
            "Patch exposure",
            "AI analysis",
        ]
    )
    tabs = st.tabs(labels)
    overview = tabs[0]

    if device_scope:
        priority = None
        exposure, analysis_tab = tabs[1:]
    else:
        priority, exposure, analysis_tab = tabs[1:]

    with overview:
        trend = pd.DataFrame(evidence.get("trend") or [])

        if not trend.empty:
            date_key = (
                "date"
                if "date" in trend.columns
                else "Date"
                if "Date" in trend.columns
                else None
            )
            missing_key = next(
                (
                    key
                    for key in (
                        "missing_instances",
                        "missing_patches",
                        "Missing patches",
                    )
                    if key in trend.columns
                ),
                None,
            )

            if date_key and missing_key:
                chart = trend.set_index(date_key)[[missing_key]].rename(
                    columns={missing_key: "Missing patch instances"}
                )
                st.markdown(
                    "**Fleet exposure across stored scans**"
                    if not device_scope
                    else "**Device compliance trend**"
                )
                st.line_chart(chart, height=260)

            if (
                not device_scope
                and date_key
                and "devices" in trend.columns
            ):
                st.markdown("**Affected endpoint trend**")
                st.line_chart(
                    trend.set_index(date_key)[["devices"]],
                    height=220,
                )

        severity = (
            evidence.get("severity")
            or evidence.get("latest_severity_counts")
            or {}
        )
        if severity:
            st.markdown("**Ivanti severity values**")
            severity_frame = pd.DataFrame(
                {
                    "Severity": severity.keys(),
                    "Missing-patch instances": severity.values(),
                }
            ).set_index("Severity")
            st.bar_chart(severity_frame, height=240)

        operating_systems = evidence.get("operating_systems") or []
        os_frame = pd.DataFrame(operating_systems)
        if (
            not os_frame.empty
            and {"operating_system", "devices"}.issubset(
                os_frame.columns
            )
        ):
            st.markdown("**Affected endpoints by operating system**")
            st.bar_chart(
                os_frame.set_index("operating_system")[["devices"]],
                height=240,
            )

    if priority is not None:
        with priority:
            priority_frame = pd.DataFrame(
                evidence.get("priority_devices") or []
            )
            if priority_frame.empty:
                st.info("Priority ranking is not available for this result.")
            else:
                st.dataframe(
                    priority_frame,
                    hide_index=True,
                    width="stretch",
                )

    with exposure:
        rows = (
            evidence.get("top_missing_patches")
            or evidence.get("persistent_patch_ids")
            or evidence.get("persistent_patches")
            or []
        )

        if rows and isinstance(rows[0], (list, tuple)):
            rows = [
                {"Patch": row[0], "Snapshots affected": row[1]}
                for row in rows
            ]

        exposure_frame = pd.DataFrame(rows)
        if exposure_frame.empty:
            st.info(
                "No patch exposure details were available for this snapshot."
            )
        else:
            st.dataframe(
                exposure_frame,
                hide_index=True,
                width="stretch",
            )

        age_counts = (
            evidence.get("release_age")
            or evidence.get("latest_release_age_counts")
            or {}
        )
        if age_counts:
            st.markdown("**Release-age distribution**")
            age_frame = pd.DataFrame(
                list(age_counts.items()),
                columns=["Age", "Count"],
            ).set_index("Age")
            st.bar_chart(age_frame, height=230)

        if device_scope:
            st.markdown("**Change since the previous snapshot**")
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Newly missing",
                summary.get("new_since_previous_snapshot", "—"),
            )
            c2.metric(
                "Cleared",
                summary.get("cleared_since_previous_snapshot", "—"),
            )
            c3.metric(
                "Persistent",
                summary.get("persistent_across_all_snapshots", "—"),
            )

            for label, key in (
                ("New patch IDs", "new_patch_ids_since_previous"),
                ("Cleared patch IDs", "cleared_patch_ids_since_previous"),
                ("Persistent patch IDs", "persistent_patch_ids"),
            ):
                values = evidence.get(key) or []
                if values:
                    st.markdown(
                        f"**{label}:** "
                        + ", ".join(map(str, values[:30]))
                    )

            for snapshot in evidence.get("history", []):
                with st.expander(
                    f"{snapshot.get('scan_date')} · "
                    f"{snapshot.get('missing_patch_count', 0)} missing updates"
                ):
                    patches = pd.DataFrame(
                        snapshot.get("patches") or []
                    )
                    if patches.empty:
                        st.info(
                            "No detailed patch rows were stored for this snapshot."
                        )
                    else:
                        st.dataframe(
                            patches,
                            hide_index=True,
                            width="stretch",
                        )

    with analysis_tab:
        if not ai.get("available"):
            st.warning(
                "Report -  "
                "Analytics from stored Ivanti evidence are shown."
            )

            diagnostic = str(ai.get("error") or "").strip()
            if diagnostic:
                with st.expander(
                    "AI diagnostic details",
                    expanded=False,
                ):
                    st.write(f"Model: {ai.get('model') or 'Unknown'}")
                    st.write(f"Host: {ai.get('host') or 'Unknown'}")
                    st.code(
                        diagnostic,
                        language=None,
                        wrap_lines=True,
                    )

        st.markdown("### Executive summary")
        st.write(
            analysis.get("executive_summary")
            or "No analysis summary was returned."
        )

        for title, key in (
            ("Compliance assessment", "compliance"),
            ("Risk assessment", "risk"),
            ("Fleet risk", "fleet_risk"),
            ("Risk concentration", "risk_concentration"),
            ("Ticket recommendation", "ticket_recommendation"),
        ):
            value = analysis.get(key)
            if not value:
                continue

            st.markdown(f"**{title}**")
            if isinstance(value, dict):
                for field, detail in value.items():
                    st.write(
                        f"{field.replace('_', ' ').title()}: {detail}"
                    )
            else:
                st.write(value)

        for title, key in (
            ("Key findings", "key_findings"),
            ("Change since previous snapshot", "change_since_previous_snapshot"),
            ("Trend insights", "trend_insights"),
            ("Persistent exposure", "persistent_exposure"),
            ("Release-age insights", "release_age_insights"),
            ("Priority devices", "priority_devices"),
            ("Top patch exposures", "top_patch_exposures"),
            ("Cross-fleet patterns", "cross_fleet_patterns"),
            ("Operator checks", "operator_checks"),
            ("Hypotheses requiring verification", "hypotheses"),
            ("Recommended actions", "recommended_actions"),
            ("Data limitations", "data_limitations"),
        ):
            _render_analysis_list(title, analysis.get(key))


# =============================================================================
# Ticket approval and results
# =============================================================================


@st.dialog("Patch ticket approval", width="large")
def _ticket_dialog() -> None:
    job = st.session_state.security_ticket_job
    results = st.session_state.security_ticket_results

    if results is not None:
        created = sum(
            bool(
                item.get("success")
                and _reported_ticket_id(item)
                and not item.get("dry_run")
            )
            for item in results
        )
        accepted = sum(
            bool(
                item.get("success")
                and not _reported_ticket_id(item)
                and not item.get("dry_run")
            )
            for item in results
        )
        previews = sum(bool(item.get("dry_run")) for item in results)
        failed = sum(not bool(item.get("success")) for item in results)

        if created and not failed and not accepted and not previews:
            st.success(
                f"{created} remediation ticket"
                f"{'s' if created != 1 else ''} created successfully."
            )
        elif failed:
            st.warning(
                f"{created} ticket{'s' if created != 1 else ''} created; "
                f"{failed} request{'s' if failed != 1 else ''} failed."
            )
        elif previews:
            st.warning(
                "The request ran in preview mode and was not submitted to iEngage."
            )
        elif accepted:
            st.success(
                "iEngage accepted the remediation request. "
                "The returned confirmation is shown below."
            )

        _audit_finish(
            job.get("audit_id") if job else None,
            status="completed" if failed == 0 else "partial",
            summary={
                "created_with_id": created,
                "accepted_without_id": accepted,
                "dry_run": previews,
                "failed": failed,
                "devices": [
                    {
                        "device": item.get("device_name"),
                        "status": item.get("status"),
                        "ticket_id": _reported_ticket_id(item),
                    }
                    for item in results
                ],
            },
        )

        for result in results:
            with st.container(border=True):
                st.markdown(
                    f"**{escape(str(result.get('device_name') or 'Device'))}**"
                )

                ticket_id = _reported_ticket_id(result)

                if result.get("dry_run"):
                    st.warning(
                        "Preview completed. No live iEngage ticket was created."
                    )
                elif result.get("success") and ticket_id:
                    st.success("Ticket created successfully.")
                    st.markdown(f"**Ticket ID:** {escape(ticket_id)}")
                    st.caption(
                        str(result.get("message") or "iEngage confirmed creation.")
                    )
                elif result.get("success"):
                    st.success(
                        str(
                            result.get("message")
                            or "The ticket operation completed successfully."
                        )
                    )
                else:
                    st.error(
                        str(result.get("message") or "Ticket creation failed.")
                    )
                    if result.get("ticket_id"):
                        st.caption(
                            f"Returned reference: {result['ticket_id']}"
                        )

        if st.button("Close", type="primary", width="stretch"):
            st.session_state.security_ticket_job = None
            st.session_state.security_ticket_results = None
            st.rerun()
        return

    if not job:
        st.info("No ticket operation is pending.")
        return

    st.warning(
        f"Create remediation tickets for {len(job['devices'])} selected device(s)?"
    )
    st.write(", ".join(job["devices"]))

    left, right = st.columns(2)

    if left.button(
        "Approve and create",
        type="primary",
        width="stretch",
        key="security_ticket_approve",
    ):
        with st.spinner("Creating tickets in iEngage through MCP..."):
            try:
                payload = _unwrap(
                    PatchMCPClient().raise_tickets(
                        job["devices"],
                        reason=job["reason"],
                        requested_by=job["operator"],
                    )
                )
                results = payload.get("tickets") or []
                if not results:
                    raise RuntimeError(
                        "MCP completed without returning per-device ticket results."
                    )
            except Exception as exc:
                logger.exception("PATCH_TICKET_DIALOG_OPERATION_FAILED")
                results = [
                    {
                        "success": False,
                        "status": "FAILED",
                        "ticket_id": None,
                        "device_name": device,
                        "dry_run": False,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                    for device in job["devices"]
                ]

        st.session_state.security_ticket_results = results
        st.rerun()

    if right.button(
        "Cancel",
        width="stretch",
        key="security_ticket_cancel",
    ):
        _audit_finish(
            job.get("audit_id"),
            status="cancelled",
            summary={"cancelled": True},
        )
        st.session_state.security_ticket_job = None
        st.session_state.security_ticket_results = None
        st.rerun()


# =============================================================================
# Natural-language query processing
# =============================================================================


def _submit_security_query(query: str, operator: str) -> None:
    text = str(query or "").strip()
    if not text:
        return

    st.session_state.security_conversation.append(
        {"role": "user", "content": text}
    )

    selected_device = (
        st.session_state.security_selected[0]
        if len(st.session_state.security_selected) == 1
        else None
    )
    metadata = PatchSemanticInterpreter().interpret(
        text,
        selected_device=selected_device,
    )
    action = metadata.get("action")

    explicit_date = re.search(
        r"\b(20\d{2}-\d{2}-\d{2})\b",
        text,
    )
    snapshot = (
        explicit_date.group(1)
        if explicit_date
        else _latest_snapshot().isoformat()
    )

    try:
        snapshot_date = date.fromisoformat(snapshot)
    except ValueError:
        st.session_state.security_conversation.append(
            {
                "role": "assistant",
                "content": (
                    f"Invalid snapshot date: {snapshot}. Use YYYY-MM-DD."
                ),
            }
        )
        return

    st.session_state.security_date = snapshot
    target = (
        metadata.get("device_name")
        or metadata.get("patch_query")
        or ("Fleet" if action == "patch_report" else None)
    )

    st.session_state.security_details = None
    st.session_state.security_report = None
    st.session_state.security_patch_search_results = None

    query_id = _audit_start(
        text,
        operator,
        action or "unknown",
        target,
    )

    if action == "device_report" and metadata.get("device_name"):
        _queue_report(
            "device",
            [metadata["device_name"]],
            snapshot_date,
            query_id,
        )
        return

    if action == "device_list":
        lowered = text.casefold()
        status = metadata.get("device_status") or (
            "resolved"
            if "resolved" in lowered
            else "all"
            if any(
                phrase in lowered
                for phrase in (
                    "all devices",
                    "all endpoints",
                    "all status",
                )
            )
            else "non_compliant"
        )
        st.session_state.security_conversation.append(
            {
                "role": "assistant",
                "content": (
                    f"Showing {status.replace('_', ' ')} devices "
                    f"from the {snapshot} snapshot."
                ),
            }
        )
        _queue_device_list(
            snapshot_date,
            status,
            query_id,
        )
        return

    if action == "patch_report":
        selected = list(st.session_state.security_selected)
        lowered = text.casefold()
        selected_scope = bool(
            selected
            and any(
                term in lowered
                for term in (
                    "selected",
                    "these devices",
                    "chosen devices",
                )
            )
        )

        if selected_scope and len(selected) == 1:
            report_kind = "device"
        elif selected_scope:
            report_kind = "selected"
        else:
            report_kind = "fleet"

        _queue_report(
            report_kind,
            selected if selected_scope else [],
            snapshot_date,
            query_id,
        )
        return

    if action == "patch_search" and metadata.get("patch_query"):
        patch_query = str(metadata["patch_query"])

        try:
            result = SecurityPatchQueryService().list_devices(
                report_date=snapshot_date,
                patch_query=patch_query,
                page=1,
                page_size=25,
            )
            st.session_state.security_patch_search_results = {
                "patch": patch_query,
                "date": snapshot,
                "page": 1,
                **result,
            }
            st.session_state.security_conversation.append(
                {
                    "role": "assistant",
                    "content": (
                        f"Found {result['total']} device(s) with confirmed "
                        f"missing matches for {patch_query}. Results use "
                        f"the {snapshot} snapshot."
                    ),
                }
            )
            _audit_finish(
                query_id,
                status="completed",
                summary={
                    "matches": result["total"],
                    "snapshot": snapshot,
                    "patch": patch_query,
                },
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            st.session_state.security_conversation.append(
                {
                    "role": "assistant",
                    "content": f"Patch search failed: {error}",
                }
            )
            _audit_finish(query_id, status="failed", error=error)
        return

    if action in {"patch_ticket", "eligible_ticket_batch"}:
        names = (
            [metadata["device_name"]]
            if metadata.get("device_name")
            else list(st.session_state.security_selected)
        )

        if not names:
            answer = (
                "Enter a device name or select one or more endpoints "
                "before requesting ticket approval."
            )
            st.session_state.security_conversation.append(
                {"role": "assistant", "content": answer}
            )
            _audit_finish(
                query_id,
                status="needs_input",
                summary={"response": answer},
            )
            return

        st.session_state.security_ticket_job = {
            "devices": names,
            "reason": metadata.get("reason") or text,
            "operator": operator,
            "audit_id": query_id,
        }
        st.session_state.security_ticket_results = None
        return

    if action == "redirect_identity":
        st.session_state.security_redirect_query = text
        st.session_state.security_redirect_audit_id = query_id
        st.session_state.security_redirect_pending = True
        return

    if action == "unsupported_security":
        answer = (
            metadata.get("explanation")
            or "That Compliance Agent operation is not available yet."
        )
    elif action == "patch_scan":
        answer = (
            "Starting a live Ivanti scan from chat is not enabled. "
            "Use the administrator scan control or wait for the scheduled scan."
        )
    else:
        answer = (
            metadata.get("clarification_question")
            or (
                "Try a device hostname, KB number, non-compliant device list, "
                "device AI report, or fleet AI report."
            )
        )

    st.session_state.security_conversation.append(
        {"role": "assistant", "content": answer}
    )
    _audit_finish(
        query_id,
        status="completed",
        summary={"response": answer},
    )


@st.dialog("Open Identity Agent?")
def _identity_redirect_dialog() -> None:
    query = st.session_state.get("security_redirect_query", "")

    st.write(
        "This looks like an identity-management request. "
        "Continue in Identity Agent?"
    )
    if query:
        st.caption(query)

    left, right = st.columns(2)

    if left.button(
        "Open Identity Agent",
        type="primary",
        width="stretch",
        key="security_to_identity_confirm",
    ):
        st.session_state.page = "assistant"
        st.session_state.queued_query = query
        st.session_state.identity_security_redirect_bypass = True
        _audit_finish(
            st.session_state.get("security_redirect_audit_id"),
            status="redirected",
            summary={"destination": "Identity Agent"},
        )
        st.session_state.security_redirect_pending = False
        st.rerun()

    if right.button(
        "Stay here",
        width="stretch",
        key="security_to_identity_cancel",
    ):
        _audit_finish(
            st.session_state.get("security_redirect_audit_id"),
            status="cancelled",
            summary={"redirect_cancelled": True},
        )
        st.session_state.security_redirect_pending = False
        st.session_state.security_redirect_query = None
        st.rerun()


# =============================================================================
# Search and device table renderers
# =============================================================================


def _render_patch_search_page(operator: str) -> None:
    current = st.session_state.security_patch_search_results
    if not current:
        return

    page = int(current.get("page", 1))
    snapshot = date.fromisoformat(current["date"])
    result = SecurityPatchQueryService().list_devices(
        report_date=snapshot,
        patch_query=current["patch"],
        page=page,
        page_size=25,
    )

    st.markdown(
        f"### Devices missing {escape(str(current['patch']))}"
    )
    st.caption(
        f"{result['total']:,} matching endpoints · "
        f"snapshot {snapshot.isoformat()}"
    )

    frame = pd.DataFrame(
        [
            {
                "Device": row["device_name"],
                "IP address": row["ip_address"],
                "Operating system": row["os_name"],
                "Missing patches": row["missing_patch_count"],
                "Days open": row["consecutive_days"],
                "Risk score": row["risk_score"],
            }
            for row in result["rows"]
        ]
    )

    if frame.empty:
        st.info("No matching endpoint has stored evidence for this snapshot.")
        return

    normalized_patch = re.sub(
        r"[^A-Za-z0-9]",
        "_",
        str(current["patch"]),
    )
    table_key = (
        f"security_kb_{normalized_patch}_{snapshot.isoformat()}_{page}"
    )
    event = st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=360,
        on_select="rerun",
        selection_mode="multi-row",
        key=table_key,
    )
    indices = (
        list(event.selection.rows)
        if event and hasattr(event, "selection")
        else []
    )
    selected = _selected_device_names(frame, indices)
    st.session_state.security_selected = selected

    previous, summary, next_page = st.columns([1, 3, 1])

    if previous.button(
        "Previous",
        disabled=page <= 1,
        key=f"kb_prev_{page}",
    ):
        st.session_state.security_patch_search_results = {
            **current,
            "page": page - 1,
        }
        st.rerun()

    summary.markdown(
        f"<div class='ta-page-copy'>Page {result['page']} of "
        f"{result['pages']} · {len(selected)} selected</div>",
        unsafe_allow_html=True,
    )

    if next_page.button(
        "Next",
        disabled=page >= result["pages"],
        key=f"kb_next_{page}",
    ):
        st.session_state.security_patch_search_results = {
            **current,
            "page": page + 1,
        }
        st.rerun()

    if selected:
        view_col, report_col, ticket_col = st.columns(3)

        if view_col.button(
            "View selected patches",
            key=f"kb_view_{page}",
            width="stretch",
        ):
            try:
                st.session_state.security_details = [
                    SecurityPatchQueryService().device_details(name)
                    for name in selected
                ]
                st.session_state.security_patch_search_results = None
                st.rerun()
            except Exception as exc:
                st.error(
                    "Could not load selected patches: "
                    f"{type(exc).__name__}: {exc}"
                )

        if report_col.button(
            "Selected AI report",
            key=f"kb_report_{page}",
            width="stretch",
        ):
            query = (
                f"Generate AI report for endpoints missing "
                f"{current['patch']}: {', '.join(selected)}"
            )
            query_id = _audit_start(
                query,
                operator,
                "selected_report",
                ", ".join(selected[:5]),
            )
            st.session_state.security_conversation.append(
                {"role": "user", "content": query}
            )
            _queue_report(
                "device" if len(selected) == 1 else "selected",
                selected,
                snapshot,
                query_id,
            )
            st.rerun()

        if ticket_col.button(
            "Raise selected tickets",
            key=f"kb_ticket_{page}",
            width="stretch",
        ):
            query_id = _audit_start(
                f"Raise remediation tickets for {', '.join(selected)}",
                operator,
                "patch_ticket",
                ", ".join(selected[:5]),
            )
            st.session_state.security_ticket_job = {
                "devices": selected,
                "reason": f"Missing patch {current['patch']} remediation.",
                "operator": operator,
                "audit_id": query_id,
            }
            st.session_state.security_ticket_results = None
            st.rerun()


def _render_device_list(operator: str) -> None:
    job = st.session_state.security_device_list
    if not job:
        return

    snapshot = date.fromisoformat(job["date"])
    scope = job["status"]

    try:
        result = SecurityPatchQueryService().list_devices(
            report_date=snapshot,
            page=int(job["page"]),
            page_size=25,
            include_resolved=scope == "all",
            device_status=scope,
            search=job.get("search", ""),
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        st.error(f"Could not load endpoints: {error}")
        _audit_finish(job.get("audit_id"), status="failed", error=error)
        return

    if not job.get("audited"):
        _audit_finish(
            job.get("audit_id"),
            status="completed",
            summary={
                "devices": result["total"],
                "snapshot": snapshot.isoformat(),
                "status": scope,
            },
        )
        job["audited"] = True

    title = {
        "non_compliant": "Non-compliant devices",
        "resolved": "Resolved devices",
        "all": "Devices in this snapshot",
    }.get(scope, "Devices")

    st.markdown(f"### {title}")
    st.caption(
        f"{result['total']:,} endpoint(s) · snapshot {snapshot.isoformat()}"
        + (
            f" · matching {job['search']}"
            if job.get("search")
            else ""
        )
    )

    rows: list[dict[str, Any]] = []
    for item in result["rows"]:
        ticket = item.get("ticket_reference")
        rows.append(
            {
                "Device": item["device_name"],
                "IP address": item.get("ip_address"),
                "Operating system": item.get("os_name"),
                "Missing patches": item.get("missing_patch_count"),
                "Risk score": item.get("risk_score"),
                "Days affected": item.get("consecutive_days"),
                "Status": (
                    "Resolved"
                    if item.get("active") is False
                    else "Non-compliant"
                ),
                "Ticket": "✓" if ticket else "—",
                "Ticket ID": ticket or "—",
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        st.info("No endpoints match this view and date.")
        return

    selection_key = (
        f"security_list_{scope}_{snapshot.isoformat()}_"
        f"{job.get('search', '')}_{result['page']}"
    )
    event = st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=390,
        on_select="rerun",
        selection_mode="multi-row",
        key=selection_key,
    )
    indices = (
        list(event.selection.rows)
        if event and hasattr(event, "selection")
        else []
    )
    st.session_state.security_selected_by_page[result["page"]] = (
        _selected_device_names(frame, indices)
    )
    selected = list(
        dict.fromkeys(
            name
            for names in st.session_state.security_selected_by_page.values()
            for name in names
        )
    )
    st.session_state.security_selected = selected

    previous, summary, next_page = st.columns([1, 3, 1])

    if previous.button(
        "Previous",
        disabled=result["page"] <= 1,
        key=f"device_list_prev_{scope}_{result['page']}",
    ):
        job["page"] = result["page"] - 1
        st.rerun()

    summary.markdown(
        f"<div class='ta-page-copy'>Page {result['page']} of "
        f"{result['pages']} · {len(selected)} selected</div>",
        unsafe_allow_html=True,
    )

    if next_page.button(
        "Next",
        disabled=result["page"] >= result["pages"],
        key=f"device_list_next_{scope}_{result['page']}",
    ):
        job["page"] = result["page"] + 1
        st.rerun()

    action_columns = st.columns(4)

    if action_columns[0].button(
        "View selected patches",
        disabled=not selected,
        key=f"list_view_{scope}_{result['page']}",
        width="stretch",
    ):
        try:
            st.session_state.security_details = [
                SecurityPatchQueryService().device_details(name)
                for name in selected
            ]
            st.rerun()
        except Exception as exc:
            st.error(
                f"Unable to load selected patch evidence: "
                f"{type(exc).__name__}: {exc}"
            )

    if action_columns[1].button(
        "Selected AI report",
        disabled=not selected,
        key=f"list_report_{scope}_{result['page']}",
        width="stretch",
    ):
        query = f"AI report for selected endpoints: {', '.join(selected)}"
        query_id = _audit_start(
            query,
            operator,
            "selected_report",
            ", ".join(selected[:5]),
        )
        st.session_state.security_conversation.append(
            {"role": "user", "content": query}
        )
        _queue_report(
            "device" if len(selected) == 1 else "selected",
            selected,
            snapshot,
            query_id,
        )
        st.rerun()

    if action_columns[2].button(
        "Fleet AI report",
        disabled=scope == "resolved",
        key=f"list_fleet_report_{scope}_{result['page']}",
        width="stretch",
    ):
        query = f"Fleet AI report for {snapshot.isoformat()}"
        query_id = _audit_start(
            query,
            operator,
            "fleet_report",
            snapshot.isoformat(),
        )
        st.session_state.security_conversation.append(
            {"role": "user", "content": query}
        )
        _queue_report("fleet", [], snapshot, query_id)
        st.rerun()

    if action_columns[3].button(
        "Raise selected tickets",
        disabled=not selected,
        key=f"list_ticket_{scope}_{result['page']}",
        width="stretch",
    ):
        query = f"Raise remediation tickets for {', '.join(selected)}"
        query_id = _audit_start(
            query,
            operator,
            "patch_ticket",
            ", ".join(selected[:5]),
        )
        st.session_state.security_ticket_job = {
            "devices": selected,
            "reason": "Patch remediation requested from Compliance Agent.",
            "operator": operator,
            "audit_id": query_id,
        }
        st.session_state.security_ticket_results = None
        st.rerun()


# =============================================================================
# Public page renderer
# =============================================================================


def render_patch_agent_page(
    claims: dict[str, Any],
    access: dict[str, Any],
) -> None:
    """Render the Compliance Agent workspace."""
    _init()

    operator = (
        access.get("user_principal_name")
        or claims.get("preferred_username")
        or claims.get("name")
        or "operator"
    )

    redirected_query = st.session_state.pop(
        "patch_query_prefill",
        None,
    )
    if redirected_query:
        _submit_security_query(
            redirected_query,
            operator,
        )

    if st.session_state.get("security_redirect_pending"):
        _identity_redirect_dialog()

    with st.container(key="content"):
        with st.container(key="greet_row"):
            heading, action = st.columns(
                [5, 1.4],
                vertical_alignment="center",
            )

            with heading:
                subtitle = (
                    "Review endpoint compliance, investigate missing patches, "
                    "generate intelligence reports, and manage remediation."
                    if not st.session_state.security_conversation
                    else "Review the latest Compliance Agent request and its operational evidence."
                )
                st.markdown(
                    '<div class="ta-greet">'
                    '<h1>Compliance Agent</h1>'
                    f'<p>{escape(subtitle)}</p>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            with action:
                with st.container(key="new_conversation"):
                    if st.button(
                        "New conversation",
                        icon=":material/add_comment:",
                        width="stretch",
                        key="security_new_conversation",
                    ):
                        _reset()
                        st.rerun()

        show_landing = not any(
            (
                st.session_state.security_conversation,
                st.session_state.security_job,
                st.session_state.security_device_list,
                st.session_state.security_patch_search_results,
                st.session_state.security_details,
                st.session_state.security_report,
            )
        )

        if show_landing:
            _render_security_quick_actions(operator)

        for turn in st.session_state.security_conversation:
            role = turn.get("role")
            content = str(turn.get("content") or "")

            if role == "user":
                st.markdown(
                    '<div class="ta-user-row">'
                    '<div class="ta-user-bubble">'
                    '<div class="meta">You</div>'
                    f'<div class="txt">{escape(content)}</div>'
                    '</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="ta-asst-head">'
                    '<div class="ta-icon-tile">'
                    '<span class="material-symbols-rounded">security</span>'
                    '</div>'
                    '<div>'
                    '<div class="who">Compliance Agent</div>'
                    f'<div class="msg">{escape(content)}</div>'
                    '</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

        if st.session_state.security_patch_search_results:
            _render_patch_search_page(operator)

        if st.session_state.security_device_list:
            _render_device_list(operator)

        if st.session_state.security_details:
            st.markdown("### Selected-device missing patches")

            for details in st.session_state.security_details:
                device_name = str(
                    details.get("device_name") or "Unknown device"
                )

                with st.expander(device_name, expanded=True):
                    history = details.get("history") or []
                    if not history:
                        st.info(
                            "No stored patch observations were returned for this device."
                        )
                        continue

                    for snapshot in history:
                        snapshot_date = snapshot.get("scan_date") or "Unknown date"
                        missing_count = int(
                            snapshot.get("missing_patch_count") or 0
                        )
                        st.markdown(
                            f"**{snapshot_date} · {missing_count} missing patches**"
                        )

                        metrics = st.columns(3)
                        metrics[0].metric("Missing patches", missing_count)
                        metrics[1].metric(
                            "Risk score",
                            snapshot.get("risk_score")
                            if snapshot.get("risk_score") is not None
                            else "Unavailable",
                        )
                        metrics[2].metric(
                            "Operating system",
                            snapshot.get("os_name") or "Unavailable",
                        )

                        patches = pd.DataFrame(snapshot.get("patches") or [])
                        if patches.empty:
                            st.info(
                                "The observation exists, but no detailed patch rows "
                                "were stored for this snapshot."
                            )
                        else:
                            st.dataframe(
                                patches,
                                hide_index=True,
                                width="stretch",
                            )

        if st.session_state.security_job:
            _run_job()

        if st.session_state.security_report:
            _render_report(st.session_state.security_report)

    query = st.chat_input(
        "Ask about an endpoint, KB, scan snapshot, or remediation…",
        key="security_chat_input",
    )

    if query:
        _submit_security_query(query, operator)
        st.rerun()

    if st.session_state.get("security_ticket_job"):
        _ticket_dialog()
