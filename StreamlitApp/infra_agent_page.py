"""Infrastructure Agent workspace: ITOM site scores, problem devices and iEngage tickets.

Data comes from the read-only ITOM database (SolarWinds and Intune):
    * query 2 (site_scores.sql) drives the location distribution and site lists
    * query 1 (site_alerts.sql) supplies the problem devices for a site
Set ITOM_USE_MOCK_DATA=true to run the page on sample data.
"""
from __future__ import annotations

import hashlib
import math
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from App.integration.itom.config import ItomConfig

try:
    from App.integration.itom.config import ItomConfigError
except ImportError:  # config.py from before the missing-settings fix
    class ItomConfigError(ValueError):
        missing: list[str] = []
        env_file = PROJECT_ROOT / ".env"
from App.services.infra.service import PRIORITY_BY_STATUS, SITE_STATUSES, InfrastructureService
from App.services.infra.ticket_service import InfrastructureTicketService

STATUS_COLORS = {
    "critical": "#E9939C",
    "warning": "#F4C77F",
    "healthy": "#76C9AE",
}
STATUS_ICONS = {
    "critical": ":material/error:",
    "warning": ":material/warning:",
    "healthy": ":material/check_circle:",
}
DEVICE_STATUS_ORDER = {"Down": 1, "Critical": 2, "Warning": 3, "NonCompliant": 4}
CACHE_SECONDS = ItomConfig.from_env().cache_seconds

INFRA_CSS = """
<style>
.st-key-card_infra_distribution, .st-key-card_infra_site { padding-bottom: 20px !important; }
.ta-infra-kicker { color:#1F5FD6; font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin:0 0 4px; }
.ta-infra-title { font-size:20px; font-weight:700; color:var(--ta-ink, #1B2433); margin:0; }
.ta-infra-sub { color:var(--ta-muted, #5B6B80); font-size:14px; margin:2px 0 0; }
.ta-infra-donut { display:flex; justify-content:center; padding:10px 0 4px; }
.ta-infra-donut svg { filter: drop-shadow(0 6px 14px rgba(15,31,51,.08)); }
.ta-infra-meta { color:var(--ta-muted, #5B6B80); font-size:12.5px; margin:-2px 0 10px; }
.ta-infra-tile { background:#fff; border:1px solid #E6E9EF; border-radius:12px; padding:14px 16px; }
.ta-infra-tile .lbl { color:#5B6B80; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
.ta-infra-tile .val { font-size:26px; font-weight:700; color:#1B2433; line-height:1.2; }
.ta-infra-tile .val.bad { color:#C2404F; }
.ta-infra-tile .val.warn { color:#B7791F; }
.ta-infra-pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; }
.ta-infra-pill.critical { background:#FBE3E6; color:#B4303F; }
.ta-infra-pill.warning { background:#FDF0D9; color:#97600F; }
.ta-infra-pill.healthy { background:#DDF3EA; color:#1F7A5A; }
[class*="st-key-infra_status_"] .stButton > button { justify-content:flex-start; height:40px; }
.st-key-infra_status_active_critical .stButton > button { border-color:#E9939C !important; background:#FDF1F2 !important; }
.st-key-infra_status_active_warning .stButton > button { border-color:#F4C77F !important; background:#FEF8EC !important; }
.st-key-infra_status_active_healthy .stButton > button { border-color:#76C9AE !important; background:#EEF8F4 !important; }
</style>
"""


# ---------------------------------------------------------------------------
# Data access (cached; the ITOM database is refreshed by its own sync runs)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _service() -> InfrastructureService:
    return InfrastructureService()


IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None, microsecond=0)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def _load_itom_data() -> dict[str, Any]:
    """Both queries in one cached load, so sites and devices always come from the same fetch."""
    service = _service()
    return {"sites": service.site_scores(), "alerts": service.site_alerts(), "fetched_at": _now_ist()}


def _age_text(since: Any) -> str:
    if not isinstance(since, datetime):
        return "—"
    minutes = max(int((_now_ist() - since).total_seconds() // 60), 0)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60}h {minutes % 60}m ago"


def _init() -> None:
    defaults = {
        "infra_status": None,
        "infra_site": None,
        "infra_selected": {},
        "infra_editor_version": 0,
        "infra_ticket_job": None,
        "infra_ticket_result": None,
        "infra_tickets": [],
        "infra_refresh_from": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _select_status(status: str) -> None:
    st.session_state.infra_status = None if st.session_state.infra_status == status else status
    st.session_state.infra_site = None


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _donut_svg(counts: dict[str, int], total: int, size: int = 210) -> str:
    stroke = 34
    radius = (size - stroke) / 2
    circumference = 2 * math.pi * radius
    centre = size / 2
    segments = []
    offset = 0.0
    for status in SITE_STATUSES:
        count = counts.get(status, 0)
        if not count or not total:
            continue
        length = circumference * count / total
        segments.append(
            f'<circle cx="{centre}" cy="{centre}" r="{radius}" fill="none" '
            f'stroke="{STATUS_COLORS[status]}" stroke-width="{stroke}" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {centre} {centre})">'
            f'<title>{escape(status)}: {count}</title></circle>'
        )
        offset += length
    if not segments:
        segments.append(
            f'<circle cx="{centre}" cy="{centre}" r="{radius}" fill="none" stroke="#E6E9EF" stroke-width="{stroke}"/>'
        )
    return (
        f'<div class="ta-infra-donut"><svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="{total} locations by combined score status">'
        f'<circle cx="{centre}" cy="{centre}" r="{radius - stroke / 2}" fill="#fff"/>'
        + "".join(segments)
        + f'<text x="{centre}" y="{centre + 2}" text-anchor="middle" font-size="30" font-weight="700" fill="#6B7686">{total}</text>'
        f'<text x="{centre}" y="{centre + 24}" text-anchor="middle" font-size="12" fill="#8A95A5">Locations</text>'
        "</svg></div>"
    )


def _tile(label: str, value: Any, tone: str = "") -> str:
    return (
        f'<div class="ta-infra-tile"><div class="lbl">{escape(label)}</div>'
        f'<div class="val {tone}">{escape(str(value))}</div></div>'
    )


def _fmt_time(value: Any) -> str:
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y, %H:%M")
    return str(value)


def _render_distribution(summary: dict[str, Any]) -> None:
    counts = summary["by_status"]
    total = summary["total_locations"]
    with st.container(key="card_infra_distribution", border=True):
        st.markdown(
            '<p class="ta-infra-kicker">Distribution</p>'
            '<p class="ta-infra-title">Combined score classification</p>'
            '<p class="ta-infra-sub">Location</p>',
            unsafe_allow_html=True,
        )
        chart, legend = st.columns([1.1, 1], vertical_alignment="center")
        chart.markdown(_donut_svg(counts, total), unsafe_allow_html=True)
        with legend:
            st.caption("Select a status to list its sites")
            for status in SITE_STATUSES:
                active = st.session_state.infra_status == status
                key = f"infra_status_active_{status}" if active else f"infra_status_{status}"
                with st.container(key=key):
                    if st.button(
                        f"{status.title()}  ·  {counts.get(status, 0)}",
                        key=f"infra_status_btn_{status}",
                        icon=STATUS_ICONS[status],
                        width="stretch",
                    ):
                        _select_status(status)
                        st.rerun()


def _render_tiles(summary: dict[str, Any], alerts: list[dict[str, Any]]) -> None:
    p1_sites = {row["location_name"] for row in alerts if row.get("priority") == "P1"}
    p2_sites = {row["location_name"] for row in alerts if row.get("priority") == "P2"}
    tiles = [
        ("Monitored devices", f"{summary['total_devices']:,}", ""),
        ("Down / critical devices", f"{summary['critical_devices']:,}", "bad"),
        ("Degraded devices", f"{summary['degraded_devices']:,}", "warn"),
        ("Problem devices in alert", f"{len(alerts):,}", "bad"),
        ("P1 sites with alerts", len(p1_sites), "bad"),
        ("P2 sites with alerts", len(p2_sites), "warn"),
    ]
    for start in range(0, len(tiles), 2):
        columns = st.columns(2)
        for column, (label, value, tone) in zip(columns, tiles[start:start + 2]):
            column.markdown(_tile(label, value, tone), unsafe_allow_html=True)
        st.write("")


def _render_site_list(sites: list[dict[str, Any]], alerts: list[dict[str, Any]], status: str) -> None:
    alert_counts: dict[str, int] = {}
    for row in alerts:
        alert_counts[row["location_name"]] = alert_counts.get(row["location_name"], 0) + 1

    st.markdown(
        f'### <span class="ta-infra-pill {escape(status)}">{escape(status)}</span> &nbsp;{len(sites)} site'
        f'{"s" if len(sites) != 1 else ""}',
        unsafe_allow_html=True,
    )
    if not sites:
        st.info(f"No locations are currently {status}.")
        return
    if status == "healthy":
        st.caption("Healthy sites have no P1/P2 alert, so there are no problem devices to ticket.")
    else:
        st.caption("Click a site to see its problem devices.")

    frame = pd.DataFrame(
        [
            {
                "Site": site["location_name"],
                "Priority": PRIORITY_BY_STATUS.get(status, "—"),
                "Score": site.get("site_score"),
                "Problem devices": alert_counts.get(site["location_name"], 0),
                "Total devices": site.get("total_devices"),
                "Down / critical": site.get("critical_devices"),
                "Degraded": site.get("degraded"),
                "Not assessed": site.get("not_assessed"),
                "Healthy %": site.get("healthy_pct"),
            }
            for site in sites
        ]
    )
    selection = st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"infra_sites_table_{status}",
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            "Healthy %": st.column_config.NumberColumn("Healthy %", format="%.1f%%"),
        },
    )
    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        chosen = frame.iloc[rows[0]]["Site"]
        if chosen != st.session_state.infra_site:
            st.session_state.infra_site = chosen
            st.session_state.infra_editor_version += 1
            st.rerun()


def _rows_key(devices: list[dict[str, Any]]) -> str:
    return hashlib.sha1("|".join(row["device_name"] for row in devices).encode("utf-8")).hexdigest()[:10]


def _device_frame(devices: list[dict[str, Any]], selected: set[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Select": row["device_name"] in selected,
                "Device": row["device_name"],
                "Status": row.get("device_status"),
                "Source": row.get("source_system"),
                "Type": row.get("ci_type"),
                "Source location": row.get("source_location"),
                "Last seen (IST)": _fmt_time(row.get("device_last_seen_ist")),
                "Silent for": row.get("device_silent_for") or "—",
            }
            for row in devices
        ]
    )


def _render_site_devices(
    site: dict[str, Any],
    devices: list[dict[str, Any]],
    operator: str,
) -> None:
    location = site["location_name"]
    status = str(site.get("site_status") or "").casefold()
    first = devices[0] if devices else {}
    reason = first.get("site_reason") or "—"
    priority = first.get("priority") or PRIORITY_BY_STATUS.get(status, "—")

    with st.container(key="card_infra_site", border=True):
        title, close = st.columns([6, 1], vertical_alignment="center")
        title.markdown(
            f'<p class="ta-infra-kicker">Site details</p>'
            f'<p class="ta-infra-title">{escape(location)} &nbsp;'
            f'<span class="ta-infra-pill {escape(status)}">{escape(priority)} · {escape(status)}</span></p>'
            f'<p class="ta-infra-sub">Combined score {escape(str(site.get("site_score")))} · {escape(str(reason))}</p>',
            unsafe_allow_html=True,
        )
        if close.button("Close", key="infra_close_site", icon=":material/close:", width="stretch"):
            st.session_state.infra_site = None
            st.rerun()

        if not devices:
            st.info("The latest sync has no Down/Critical/Warning SolarWinds or NonCompliant/Unknown Intune devices for this site.")
            return

        by_status: dict[str, int] = {}
        for row in devices:
            by_status[row.get("device_status") or "Unknown"] = by_status.get(row.get("device_status") or "Unknown", 0) + 1
        metric_columns = st.columns(max(len(by_status), 1))
        for column, (name, count) in zip(
            metric_columns, sorted(by_status.items(), key=lambda item: DEVICE_STATUS_ORDER.get(item[0], 5))
        ):
            column.metric(name, count)

        filter_source, filter_status = st.columns(2)
        sources = sorted({row.get("source_system") or "—" for row in devices})
        statuses = sorted({row.get("device_status") or "—" for row in devices}, key=lambda s: DEVICE_STATUS_ORDER.get(s, 5))
        chosen_sources = filter_source.multiselect("Source system", sources, default=sources, key=f"infra_src_{location}")
        chosen_statuses = filter_status.multiselect("Device status", statuses, default=statuses, key=f"infra_sts_{location}")
        visible = [
            row for row in devices
            if (row.get("source_system") or "—") in chosen_sources and (row.get("device_status") or "—") in chosen_statuses
        ]
        if not visible:
            st.session_state.infra_selected[location] = []
            if not chosen_sources:
                st.info("Select at least one source system to see devices.")
            elif not chosen_statuses:
                st.info("Select at least one device status to see devices.")
            else:
                st.info("No devices match these filters.")
            return

        selected: set[str] = set(st.session_state.infra_selected.get(location, []))
        pick_all, clear, _spacer = st.columns([1.6, 1, 3])
        if pick_all.button("Select all shown devices", key="infra_select_all", icon=":material/done_all:", width="stretch"):
            st.session_state.infra_selected[location] = sorted(row["device_name"] for row in visible)
            st.session_state.infra_editor_version += 1
            st.rerun()
        if clear.button("Clear selection", key="infra_clear", icon=":material/deselect:", width="stretch"):
            st.session_state.infra_selected[location] = []
            st.session_state.infra_editor_version += 1
            st.rerun()

        frame = _device_frame(visible, selected)
        edited = st.data_editor(
            frame,
            hide_index=True,
            width="stretch",
            # A new key whenever the filtered rows change, so ticks never carry over to other rows.
            key=f"infra_devices_{location}_{st.session_state.infra_editor_version}_{_rows_key(visible)}",
            disabled=[column for column in frame.columns if column != "Select"],
            column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
        )
        # Only devices that are both ticked and visible under the current filters
        # count; selections hidden by a filter change are dropped.
        selected = set(edited.loc[edited["Select"], "Device"].tolist())
        st.session_state.infra_selected[location] = sorted(selected)
        st.caption(f"{len(selected)} of {len(visible)} shown device{'s' if len(visible) != 1 else ''} selected.")

        already = {
            name
            for ticket in st.session_state.infra_tickets
            if ticket.get("location_name") == location and ticket.get("success") and not ticket.get("dry_run")
            for name in ticket.get("device_names", [])
        }
        repeat = sorted(selected & already)
        if repeat:
            st.warning(
                f"{len(repeat)} selected device(s) were already included in a ticket this session: "
                + ", ".join(repeat[:10]) + (" …" if len(repeat) > 10 else "")
            )

        note = st.text_area(
            "Note for the ticket (optional)",
            key=f"infra_note_{location}",
            placeholder="Anything the support team should know",
            max_chars=250,
        )
        if st.button(
            f"Raise iEngage ticket for {len(selected)} device{'s' if len(selected) != 1 else ''}",
            key="infra_raise_ticket",
            type="primary",
            icon=":material/confirmation_number:",
            disabled=not selected,
        ):
            ordered = [row for row in visible if row["device_name"] in selected]
            st.session_state.infra_ticket_job = {
                "site": {**site, "site_reason": reason, "priority": priority},
                "devices": ordered,
                "note": note,
                "operator": operator,
            }
            st.session_state.infra_ticket_result = None
            st.rerun()


def _dismiss_ticket_dialog() -> None:
    st.session_state.infra_ticket_job = None
    st.session_state.infra_ticket_result = None


def _infra_dialog(title: str):
    """st.dialog that clears the pending ticket when closed with X (Streamlit >= 1.48)."""
    try:
        return st.dialog(title, width="large", on_dismiss=_dismiss_ticket_dialog)
    except TypeError:
        return st.dialog(title, width="large")


@_infra_dialog("Raise infrastructure ticket")
def _ticket_dialog() -> None:
    job = st.session_state.infra_ticket_job
    result = st.session_state.infra_ticket_result
    if result is not None:
        if result.get("dry_run"):
            st.warning("Dry run only: iEngage is in dry-run mode, so no ticket was created.")
        elif result.get("success") and result.get("ticket_id"):
            st.success(f"Ticket {result['ticket_id']} created for {result['location_name']}.")
        elif result.get("success"):
            st.success(result.get("message") or "iEngage accepted the ticket request.")
        else:
            st.error(result.get("message") or "Ticket creation failed.")
            if result.get("sent"):
                st.warning(
                    "The request reached iEngage, so a ticket may still have been created. "
                    "Check iEngage for this site before raising again, to avoid a duplicate."
                )
        for item in result.get("attachment") or []:
            upload = item.get("upload")
            if not upload or result.get("dry_run"):
                continue
            if upload.get("uploaded"):
                st.success(f"Attached {item.get('file_name')} to the ticket.", icon=":material/attach_file:")
            else:
                st.warning(f"{item.get('file_name')} was not attached: {upload.get('message')}", icon=":material/attach_file:")
        if not result.get("dry_run") and (result.get("response_data") or not result.get("success")):
            with st.expander("iEngage response (for troubleshooting)", expanded=not result.get("success")):
                st.caption(f"HTTP status: {result.get('status_code') or '—'}")
                st.json(result.get("response_data") or {}, expanded=True)
                if result.get("attachment"):
                    for a in result["attachment"]:
                        st.caption(f"Attachment {a.get('file_name')} as form field '{a.get('field')}'")
                        if a.get("upload"):
                            st.json(a["upload"], expanded=False)
        st.caption(f"{len(result.get('device_names', []))} device(s): " + ", ".join(result.get("device_names", [])))
        if st.button("Close", type="primary", width="stretch", key="infra_ticket_close"):
            st.session_state.infra_ticket_job = None
            st.session_state.infra_ticket_result = None
            st.rerun()
        return
    if not job:
        st.info("No ticket is pending.")
        return

    try:
        tickets = InfrastructureTicketService()
        ticket_input = tickets.build_input(job["site"], job["devices"], requested_by=job["operator"], note=job["note"])
        description = tickets.preview_description(ticket_input)
    except Exception as exc:
        logger.exception("Could not prepare the infrastructure ticket.")
        st.error(f"The ticket could not be prepared: {type(exc).__name__}: {exc}")
        return

    st.markdown(
        f"**Site:** {escape(job['site']['location_name'])} &nbsp;·&nbsp; "
        f"**Priority:** {escape(str(job['site'].get('priority') or '—'))} &nbsp;·&nbsp; "
        f"**Devices:** {len(job['devices'])}"
    )
    st.dataframe(
        pd.DataFrame(
            [{"Device": d["device_name"], "Status": d.get("device_status"), "Source": d.get("source_system")} for d in job["devices"]]
        ),
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(job["devices"]), 260),
    )
    st.markdown("**iEngage description**")
    st.code(description, language=None, wrap_lines=True)
    location_for = getattr(tickets.integration, "location_for", None)
    if location_for:
        location_id, mapped = location_for(ticket_input)
        if mapped:
            st.caption(f"iEngage Office/Building Location: ID {location_id} (mapped for this site).")
        else:
            st.caption(
                f"iEngage Office/Building Location: default ID {location_id or '—'}. This site has no entry in "
                "INFRA_IENGAGE_SITE_LOCATION_IDS, so iEngage will show the default location."
            )
    preview_attachment = getattr(tickets, "preview_attachment", None)
    attachment = preview_attachment(ticket_input) if preview_attachment else None
    attached = attachment is not None
    if attachment is None:
        try:
            from App.integration.iengage.infra_ticket_service import build_device_file
            attachment = build_device_file(ticket_input)
        except ImportError:
            attachment = None
    if attachment is not None:
        info, download = st.columns([3, 1.2], vertical_alignment="center")
        label = "Attachment" if attached else "Excel (attach it in iEngage by hand)"
        info.markdown(
            f"**{label}:** `{escape(attachment.file_name)}` · {len(ticket_input.devices)} device rows · "
            f"{max(len(attachment.content) // 1024, 1)} KB"
        )
        download.download_button(
            "Download Excel", data=attachment.content, file_name=attachment.file_name,
            mime=attachment.content_type, icon=":material/download:", width="stretch", key="infra_csv_download",
        )
    if tickets.integration.config.dry_run:
        st.caption("iEngage is in dry-run mode (IENGAGE_DRY_RUN=true). Nothing will be sent.")

    approve, cancel = st.columns(2)
    if approve.button("Approve and raise", type="primary", width="stretch", key="infra_ticket_approve"):
        with st.spinner("Creating the ticket in iEngage..."):
            try:
                result = tickets.raise_ticket(ticket_input)
            except Exception as exc:
                logger.exception("Infrastructure ticket failed.")
                result = {
                    "success": False,
                    "status": "FAILED",
                    "ticket_id": None,
                    "message": f"{type(exc).__name__}: {exc}",
                    "location_name": ticket_input.location_name,
                    "device_names": [d.device_name for d in ticket_input.devices],
                    "dry_run": False,
                }
        st.session_state.infra_ticket_result = result
        st.session_state.infra_tickets.append(result)
        if result.get("success") and not result.get("dry_run"):
            st.session_state.infra_selected[ticket_input.location_name] = []
            st.session_state.infra_editor_version += 1
        st.rerun()
    if cancel.button("Cancel", width="stretch", key="infra_ticket_cancel"):
        st.session_state.infra_ticket_job = None
        st.rerun()


def _render_ticket_log() -> None:
    tickets = st.session_state.infra_tickets
    if not tickets:
        return
    with st.expander(f"Tickets raised this session ({len(tickets)})"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Site": t.get("location_name"),
                        "Status": t.get("status"),
                        "Ticket ID": t.get("ticket_id") or "—",
                        "Devices": len(t.get("device_names", [])),
                        "Message": t.get("message"),
                    }
                    for t in reversed(tickets)
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def _sync_time(alerts: list[dict[str, Any]]) -> Any:
    return alerts[0].get("sync_completed_ist") if alerts else None


def _render_missing_settings(exc: ItomConfigError) -> None:
    st.error("The Infrastructure Agent is not connected to the ITOM database yet: " + ", ".join(exc.missing) + " is not set.")
    st.markdown(f"Add these lines to **`{exc.env_file}`**, then stop and restart Streamlit:")
    st.code(
        "ITOM_DB_HOST=172.18.51.38\n"
        "ITOM_DB_PORT=5432\n"
        "ITOM_DB_NAME=itom_db\n"
        "ITOM_DB_USER=itom_ro\n"
        "ITOM_DB_PASSWORD=<itom_ro password>",
        language="bash",
    )
    st.caption(
        "ITOM_DB_PASSWORD is separate from DB_PASSWORD, which TechAdmin uses for its own database. "
        "To look at the page without the database, set ITOM_USE_MOCK_DATA=true instead."
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_infra_agent_page(claims: dict[str, Any], access: dict[str, Any]) -> None:
    _init()
    st.markdown(INFRA_CSS, unsafe_allow_html=True)
    operator = access.get("user_principal_name") or claims.get("preferred_username") or claims.get("name") or "operator"

    with st.container(key="content"):
        head, action = st.columns([5, 1.4], vertical_alignment="center")
        head.markdown(
            '<div class="ta-greet"><h1>Infrastructure Agent</h1>'
            "<p>Site health from SolarWinds and Intune, with P1/P2 problem devices and iEngage ticketing.</p></div>",
            unsafe_allow_html=True,
        )
        if action.button("Refresh data", icon=":material/refresh:", width="stretch", key="infra_refresh",
                         help="Fetch the latest data from ITOM now. ITOM syncs about every 10 minutes."):
            st.session_state.infra_refresh_from = st.session_state.get("infra_last_sync") or "unknown"
            _load_itom_data.clear()
            st.rerun()

        try:
            with st.spinner("Loading site scores from ITOM..."):
                data = _load_itom_data()
                sites, alerts = data["sites"], data["alerts"]
        except ItomConfigError as exc:
            _render_missing_settings(exc)
            return
        except Exception as exc:
            logger.exception("Could not load ITOM data.")
            st.error(
                "Could not load data from the ITOM database. Check ITOM_DB_HOST, ITOM_DB_USER and "
                f"ITOM_DB_PASSWORD, and that this server can reach it. ({type(exc).__name__}: {exc})"
            )
            return

        service = _service()
        if service.uses_mock_data:
            st.info("Showing sample data (ITOM_USE_MOCK_DATA=true). Set it to false to read the live ITOM database.")
        sync_time = _sync_time(alerts)
        st.session_state.infra_last_sync = sync_time
        previous_sync = st.session_state.infra_refresh_from
        if previous_sync is not None:
            st.session_state.infra_refresh_from = None
            if previous_sync != "unknown" and previous_sync == sync_time:
                st.toast("Refreshed. No newer ITOM sync yet.", icon=":material/info:")
            else:
                st.toast("Refreshed with the latest ITOM sync.", icon=":material/check_circle:")
        action.markdown(
            f'<p class="ta-infra-meta" style="margin:4px 0 0;text-align:center">'
            f'Last sync {escape(_fmt_time(sync_time))} IST ({escape(_age_text(sync_time))})<br>'
            f'Fetched {escape(_age_text(data["fetched_at"]))}</p>',
            unsafe_allow_html=True,
        )

        summary = service.summarize(sites)
        left, right = st.columns([1.35, 1], gap="medium")
        with left:
            _render_distribution(summary)
        with right:
            _render_tiles(summary, alerts)

        status = st.session_state.infra_status
        if status:
            status_sites = service.sites_with_status(sites, status)
            _render_site_list(status_sites, alerts, status)

            location = st.session_state.infra_site
            site = next((s for s in status_sites if s["location_name"] == location), None)
            if site is not None:
                _render_site_devices(site, service.devices_for_site(alerts, location), operator)

        _render_ticket_log()

    if st.session_state.infra_ticket_job:
        _ticket_dialog()
