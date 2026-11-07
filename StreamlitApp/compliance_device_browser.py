"""Dialog-driven classified endpoint browser for Compliance Agent.

The browser is displayed only after the Show devices dialog or a natural-language
query requests a classified device list.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from App.services.patch.compliance_query_service import ComplianceQueryService

CATEGORY_OPTIONS = {
    "Active non-compliant": "active",
    "Persistent in all 14 successful snapshots": "persistent_14",
    "Stale reporting": "stale",
    "Last scan date unavailable": "unknown",
    "Resolved": "resolved",
    "All classified records": "all",
}
CATEGORY_LABELS = {value: label for label, value in CATEGORY_OPTIONS.items()}
CATEGORY_HELP = {
    "active": "Ivanti reports missing patches and lastScannedDate is inside the configured freshness window.",
    "persistent_14": "The same discoveryId has missing patches in all latest 14 successful daily TechAdmin snapshots and is currently fresh.",
    "stale": "Ivanti still returns missing patches, but the last patch-assessment timestamp is older than the freshness window.",
    "unknown": "Ivanti returned missing patches without a usable lastScannedDate.",
    "resolved": "The endpoint is no longer reported as vulnerable by the existing TechAdmin state workflow.",
    "all": "Every derived category in the selected stored snapshot.",
}


def initialize_classified_compliance_state() -> None:
    defaults = {
        "classified_compliance_request": None,
        "classified_compliance_search": "",
        "classified_compliance_min_missing": 1,
        "classified_compliance_page": 1,
        "classified_compliance_page_size": 100,
        "classified_selected_by_page": {},
        "classified_export": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_classified_compliance_state() -> None:
    """Clear the classified view when New conversation is clicked."""
    initialize_classified_compliance_state()
    st.session_state.classified_compliance_request = None
    st.session_state.classified_compliance_search = ""
    st.session_state.classified_compliance_min_missing = 1
    st.session_state.classified_compliance_page = 1
    st.session_state.classified_compliance_page_size = 100
    st.session_state.classified_selected_by_page = {}
    st.session_state.classified_export = None


def open_classified_compliance_view(
    *,
    snapshot: date,
    category: str,
    search: str = "",
) -> None:
    """Open a classified view from chat or dialog using one shared state path."""
    initialize_classified_compliance_state()
    normalized = category if category in CATEGORY_LABELS else "active"
    st.session_state.classified_compliance_request = {
        "date": snapshot.isoformat(),
        "category": normalized,
        "category_label": CATEGORY_LABELS[normalized],
    }
    st.session_state.classified_compliance_search = search.strip()
    st.session_state.classified_compliance_min_missing = 1
    st.session_state.classified_compliance_page = 1
    st.session_state.classified_selected_by_page = {}
    st.session_state.classified_export = None


def category_from_query(query: str, semantic_status: str | None = None) -> str:
    """Map existing and new natural-language device-list requests."""
    text = str(query or "").casefold()
    status = str(semantic_status or "").casefold()
    if "persistent" in text or "14/14" in text or "14 day" in text or "14-day" in text:
        return "persistent_14"
    if "stale" in text or "old scan" in text or "not reporting" in text:
        return "stale"
    if "unknown" in text or "scan date unavailable" in text or "no scan date" in text:
        return "unknown"
    if "resolved" in text or status == "resolved":
        return "resolved"
    if status == "all" or "all classified" in text or "all status" in text:
        return "all"
    return "active"


@st.dialog("Show devices", width="large")
def show_classified_devices_dialog() -> None:
    initialize_classified_compliance_state()
    latest = ComplianceQueryService().latest_snapshot_date() or date.today()
    st.caption("Choose a stored Ivanti snapshot and endpoint category. No new scan is started.")
    with st.form("classified_devices_dialog_form", border=False):
        snapshot = st.date_input("Report date", value=latest, max_value=date.today())
        label = st.selectbox("Endpoints", list(CATEGORY_OPTIONS))
        st.info(CATEGORY_HELP[CATEGORY_OPTIONS[label]])
        submit = st.form_submit_button("Show devices", type="primary", width="stretch")
    if submit:
        open_classified_compliance_view(
            snapshot=snapshot,
            category=CATEGORY_OPTIONS[label],
        )
        st.rerun()


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Device": row["device_name"],
                "Discovery ID": row.get("discovery_id") or "",
                "IP address": row.get("ip_address") or "Not available",
                "Operating system": row.get("os_name") or "Not available",
                "Category": row.get("compliance_category", "").replace("_", " ").title(),
                "Why included": row.get("inclusion_reason") or "Not available",
                "Missing patches": int(row.get("missing_patch_count") or 0),
                "Critical security": int(row.get("critical") or 0),
                "Important security": int(row.get("important") or 0),
                "Exploited": int(row.get("exploited") or 0),
                "Ivanti risk score": row.get("risk_score"),
                "Last patch assessment": row.get("last_scanned_at") or "Not available",
                "14-day evidence": f"{int(row.get('observed_14') or 0)}/{int(row.get('required_14') or 14)}",
                "Ticket status": (row.get("ticket_status") or "Not created").replace("_", " ").title(),
                "Ticket ID": row.get("ticket_reference") or "",
            }
            for row in rows
        ]
    )


def _selected(frame: pd.DataFrame, indices: list[Any]) -> list[str]:
    names: list[str] = []
    for index in indices:
        if isinstance(index, int) and 0 <= index < len(frame):
            name = str(frame.iloc[index].get("Device") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _all_selected() -> list[str]:
    return list(
        dict.fromkeys(
            name
            for values in st.session_state.classified_selected_by_page.values()
            for name in values
        )
    )


def render_requested_compliance_devices() -> None:
    initialize_classified_compliance_state()
    request = st.session_state.get("classified_compliance_request")
    if not isinstance(request, dict):
        return

    service = ComplianceQueryService()
    snapshot = date.fromisoformat(request["date"])
    category = request.get("category", "active")
    category_label = CATEGORY_LABELS.get(category, "Active non-compliant")
    summary = service.summary(snapshot)

    header, close = st.columns([5, 1], vertical_alignment="center")
    header.markdown(f"### {category_label}")
    if close.button("Close view", icon=":material/close:", width="stretch"):
        reset_classified_compliance_state()
        st.rerun()

    st.info(CATEGORY_HELP[category])
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active", summary["active"])
    c2.metric("Persistent 14/14", summary["persistent_14"])
    c3.metric("Stale", summary["stale"])
    c4.metric("Unknown", summary["unknown"])
    c5.metric("Resolved", summary["resolved"])

    with st.form("classified_filters", border=True):
        a, b, c = st.columns([2.4, 1, 1])
        search = a.text_input(
            "Search device, discovery ID, or IP",
            value=st.session_state.classified_compliance_search,
        )
        minimum = b.number_input(
            "Minimum missing patches",
            1,
            100000,
            int(st.session_state.classified_compliance_min_missing),
        )
        size = c.selectbox(
            "Rows per page",
            [25, 50, 100, 200, 500],
            index=[25, 50, 100, 200, 500].index(
                int(st.session_state.classified_compliance_page_size)
            ),
        )
        apply_filters = st.form_submit_button("Apply filters", type="primary", width="stretch")
    if apply_filters:
        st.session_state.classified_compliance_search = search.strip()
        st.session_state.classified_compliance_min_missing = int(minimum)
        st.session_state.classified_compliance_page_size = int(size)
        st.session_state.classified_compliance_page = 1
        st.session_state.classified_selected_by_page = {}
        st.session_state.classified_export = None
        st.rerun()

    result = service.list_devices(
        report_date=snapshot,
        category=category,
        search=st.session_state.classified_compliance_search,
        min_missing=int(st.session_state.classified_compliance_min_missing),
        page=int(st.session_state.classified_compliance_page),
        page_size=int(st.session_state.classified_compliance_page_size),
    )
    frame = _frame(result["rows"])
    if frame.empty:
        st.info("No endpoints match this view.")
        return

    event = st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=470,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"classified_{snapshot}_{category}_{result['page']}",
        column_config={
            "Discovery ID": None,
            "Ivanti risk score": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    indices = list(event.selection.rows) if hasattr(event, "selection") else []
    st.session_state.classified_selected_by_page[result["page"]] = _selected(frame, indices)
    selected = _all_selected()

    previous, page_copy, next_page = st.columns([1, 3, 1])
    if previous.button("Previous", disabled=result["page"] <= 1, width="stretch"):
        st.session_state.classified_compliance_page = result["page"] - 1
        st.rerun()
    page_copy.markdown(
        f"<div class='ta-page-copy'>Page {result['page']} of {result['pages']} · {len(selected)} selected</div>",
        unsafe_allow_html=True,
    )
    if next_page.button("Next", disabled=result["page"] >= result["pages"], width="stretch"):
        st.session_state.classified_compliance_page = result["page"] + 1
        st.rerun()

    if selected:
        report_button, ticket_button = st.columns(2)
        if report_button.button("AI report for selected", type="primary", width="stretch"):
            st.session_state.security_job = {
                "type": "device" if len(selected) == 1 else "selected",
                "devices": selected,
                "date": snapshot.isoformat(),
                "audit_id": None,
            }
            st.session_state.security_report = None
            st.rerun()
        if ticket_button.button("Raise tickets for selected", width="stretch"):
            access = st.session_state.get("app_user_access") or {}
            st.session_state.security_ticket_job = {
                "devices": selected,
                "reason": f"Patch remediation requested for {category_label} endpoints from snapshot {snapshot.isoformat()}.",
                "operator": access.get("user_principal_name") or access.get("display_name") or "operator",
                "audit_id": None,
            }
            st.session_state.security_ticket_results = None
            st.rerun()

    st.download_button(
        "Download current filtered page",
        frame.to_csv(index=False).encode("utf-8-sig"),
        f"compliance_{category}_{snapshot}_page_{result['page']}.csv",
        "text/csv",
        width="stretch",
    )

    signature = (
        snapshot.isoformat(),
        category,
        st.session_state.classified_compliance_search,
        int(st.session_state.classified_compliance_min_missing),
    )
    export = st.session_state.get("classified_export")
    if not isinstance(export, dict) or export.get("signature") != signature:
        if st.button(
            f"Prepare all {result['total']:,} matching devices for download",
            width="stretch",
        ):
            with st.spinner("Collecting all matching devices..."):
                all_frame = _frame(
                    service.all_devices(
                        report_date=snapshot,
                        category=category,
                        search=st.session_state.classified_compliance_search,
                        min_missing=int(st.session_state.classified_compliance_min_missing),
                    )
                )
                st.session_state.classified_export = {
                    "signature": signature,
                    "count": len(all_frame),
                    "data": all_frame.to_csv(index=False).encode("utf-8-sig"),
                }
            st.rerun()
    else:
        st.download_button(
            f"Download all {export['count']:,} matching devices",
            export["data"],
            f"compliance_{category}_{snapshot}_all.csv",
            "text/csv",
            type="primary",
            width="stretch",
        )
