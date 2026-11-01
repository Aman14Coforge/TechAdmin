"""Infrastructure Agent Streamlit page.

The public entry point intentionally matches StreamlitApp/app.py:

    render_infrastructure_agent_page(claims, access)

This page reads Infrastructure Agent incident state from the existing
TechAdmin PostgreSQL database. It does not call Identity Agent or Compliance
Agent code and does not alter either workflow.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from App.services.infrastructure.processor import process_infrastructure_sites
from App.services.infrastructure.scheduler import scheduler_status
from App.services.infrastructure.state_repository import (
    InfrastructureStateRepository,
)


def _detail_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    return {}


def _incident_frame(
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    rows = [
        {
            "Site": item.get("location_name"),
            "Status": item.get("current_status"),
            "Priority": item.get("priority"),
            "Score": item.get("site_score"),
            "Affected devices": item.get("affected_count"),
            "Ticket status": item.get("ticket_status"),
            "Ticket ID": item.get("ticket_id"),
            "Email status": item.get("email_status"),
            "Last detected": item.get("last_detected_at"),
            "Last ticketed": item.get("last_ticketed_at"),
            "Recovered": item.get("recovered_at"),
        }
        for item in records
    ]

    return pd.DataFrame(
        rows,
        columns=[
            "Site",
            "Status",
            "Priority",
            "Score",
            "Affected devices",
            "Ticket status",
            "Ticket ID",
            "Email status",
            "Last detected",
            "Last ticketed",
            "Recovered",
        ],
    )


def _render_scheduler_status(
    status: dict[str, Any],
) -> None:
    running = bool(status.get("running"))
    state = "Running" if running else "Stopped"
    next_run = status.get("next_run_time") or "Not scheduled"
    interval = status.get("interval_minutes") or 10

    st.caption(
        f"Scheduler: {state} · Poll interval: {interval} minutes · "
        f"Next run: {next_run}"
    )


def _render_manual_result() -> None:
    result = st.session_state.get(
        "infrastructure_last_manual_result"
    )

    if not isinstance(result, dict):
        return

    errors = result.get("errors")
    message = (
        f"Latest manual poll: {result.get('alerts', 0)} alerts, "
        f"{result.get('tickets_attempted', 0)} ticket attempts, "
        f"{result.get('tickets_created', 0)} successful ticket operations, "
        f"{result.get('emails_sent', 0)} emails sent, and "
        f"{result.get('skipped', 0)} existing incidents skipped."
    )

    if errors:
        st.warning(message)
        with st.expander("Manual poll errors"):
            for error in errors:
                st.write(f"- {error}")
    else:
        st.success(message)


def _render_incident_detail(
    item: dict[str, Any],
) -> None:
    detail = _detail_payload(
        item.get("detail_json")
    )

    overview_rows = [
        {
            "Field": "Site",
            "Value": item.get("location_name"),
        },
        {
            "Field": "Current status",
            "Value": item.get("current_status"),
        },
        {
            "Field": "Priority",
            "Value": item.get("priority"),
        },
        {
            "Field": "Site score",
            "Value": item.get("site_score"),
        },
        {
            "Field": "Site reason",
            "Value": item.get("site_reason"),
        },
        {
            "Field": "Affected devices",
            "Value": item.get("affected_count"),
        },
        {
            "Field": "Ticket status",
            "Value": item.get("ticket_status"),
        },
        {
            "Field": "Ticket ID",
            "Value": item.get("ticket_id"),
        },
        {
            "Field": "Ticket message",
            "Value": item.get("ticket_message"),
        },
        {
            "Field": "Email status",
            "Value": item.get("email_status"),
        },
        {
            "Field": "Email message",
            "Value": item.get("email_message"),
        },
        {
            "Field": "First detected",
            "Value": item.get("first_detected_at"),
        },
        {
            "Field": "Last detected",
            "Value": item.get("last_detected_at"),
        },
        {
            "Field": "Last ticketed",
            "Value": item.get("last_ticketed_at"),
        },
        {
            "Field": "Recovered",
            "Value": item.get("recovered_at"),
        },
    ]

    st.dataframe(
        pd.DataFrame(overview_rows),
        hide_index=True,
        width="stretch",
    )

    devices = detail.get("devices")
    if isinstance(devices, list) and devices:
        st.markdown("#### Affected devices")
        st.dataframe(
            pd.DataFrame(devices),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(
            "No affected-device detail was stored for this incident."
        )

    st.markdown("#### iEngage description")
    st.code(
        str(
            item.get("ticket_description")
            or "No ticket description is available."
        ),
        language=None,
        wrap_lines=True,
    )

    st.markdown("#### Copy into SolarWinds chat")
    st.code(
        str(
            item.get("solarwinds_prompt")
            or "No SolarWinds investigation prompt is available."
        ),
        language=None,
        wrap_lines=True,
    )


def render_infrastructure_agent_page(
    claims: dict[str, Any],
    access: dict[str, Any],
) -> None:
    """Render the Infrastructure Agent workspace.

    Args:
        claims: Authenticated Streamlit identity claims. Reserved for future
            per-user UI authorization and intentionally not modified.
        access: TechAdmin app_users authorization record. Reserved for future
            role-specific UI actions and intentionally not modified.
    """
    del claims, access

    repository = InfrastructureStateRepository()

    try:
        status = scheduler_status()
    except Exception as exc:
        status = {
            "running": False,
            "next_run_time": None,
            "interval_minutes": 10,
        }
        scheduler_error = (
            f"{type(exc).__name__}: {exc}"
        )
    else:
        scheduler_error = None

    with st.container(key="content"):
        heading, action = st.columns(
            [5, 1.4],
            vertical_alignment="center",
        )

        heading.markdown(
            '<div class="ta-greet">'
            '<h1>Infrastructure Agent</h1>'
            '<p>Monitor ITOM site health, automatic iEngage incidents, '
            'and GNOC notifications.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        if action.button(
            "Run poll now",
            icon=":material/refresh:",
            width="stretch",
            key="infrastructure_run_poll",
        ):
            with st.spinner(
                "Reading the latest ITOM site health and "
                "processing Infrastructure Agent automations..."
            ):
                try:
                    result = process_infrastructure_sites()
                    st.session_state[
                        "infrastructure_last_manual_result"
                    ] = result
                except Exception as exc:
                    st.session_state[
                        "infrastructure_last_manual_result"
                    ] = {
                        "alerts": 0,
                        "tickets_attempted": 0,
                        "tickets_created": 0,
                        "emails_sent": 0,
                        "skipped": 0,
                        "errors": [
                            f"{type(exc).__name__}: {exc}"
                        ],
                    }

            st.rerun()

        _render_scheduler_status(status)

        if scheduler_error:
            st.warning(
                "Infrastructure scheduler status could not be read: "
                f"{scheduler_error}"
            )

        _render_manual_result()

        try:
            records = repository.list_incidents()
        except Exception as exc:
            st.error(
                "Infrastructure incident data could not be loaded from "
                f"the TechAdmin database: {type(exc).__name__}: {exc}"
            )
            return

        active = [
            item
            for item in records
            if item.get("current_status") != "recovered"
        ]
        p1_count = sum(
            item.get("priority") == "P1"
            and item.get("current_status") != "recovered"
            for item in records
        )
        p2_count = sum(
            item.get("priority") == "P2"
            and item.get("current_status") != "recovered"
            for item in records
        )
        ticketed_count = sum(
            bool(item.get("ticket_id"))
            for item in active
        )

        metric_1, metric_2, metric_3, metric_4 = st.columns(4)
        metric_1.metric("Active sites", len(active))
        metric_2.metric("P1 critical", p1_count)
        metric_3.metric("P2 warning", p2_count)
        metric_4.metric(
            "Active with ticket ID",
            ticketed_count,
        )

        if not records:
            st.info(
                "No Infrastructure Agent incidents are recorded yet. "
                "Configure ITOM access and run a poll."
            )
            return

        search_column, filter_column = st.columns(
            [3, 1.4],
            vertical_alignment="bottom",
        )

        search = search_column.text_input(
            "Search site or ticket",
            placeholder="Site name or iEngage ticket ID",
            key="infrastructure_search",
        ).strip().casefold()

        show_recovered = filter_column.checkbox(
            "Include recovered sites",
            value=False,
            key="infrastructure_show_recovered",
        )

        filtered = [
            item
            for item in records
            if (
                show_recovered
                or item.get("current_status") != "recovered"
            )
            and (
                not search
                or search
                in str(
                    item.get("location_name") or ""
                ).casefold()
                or search
                in str(
                    item.get("ticket_id") or ""
                ).casefold()
            )
        ]

        frame = _incident_frame(filtered)
        st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=420,
        )

        st.download_button(
            "Download infrastructure incident summary",
            data=frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="infrastructure_site_incidents.csv",
            mime="text/csv",
            icon=":material/download:",
            key="infrastructure_download_csv",
        )

        st.markdown("### Incident details")

        if not filtered:
            st.info(
                "No incidents match the selected search and filters."
            )
            return

        for index, item in enumerate(filtered):
            label = (
                f"{item.get('priority') or 'N/A'} · "
                f"{item.get('location_name') or 'Unknown site'} · "
                f"{item.get('current_status') or 'unknown'} · "
                f"Ticket {item.get('ticket_id') or 'not available'}"
            )

            with st.expander(
                label,
                expanded=index == 0,
            ):
                _render_incident_detail(item)
