"""Isolated database-backed UI for Ivanti patch reports."""
from __future__ import annotations
from datetime import date, datetime
from typing import Any
import pandas as pd
import streamlit as st
from sqlalchemy import func, or_, select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceObservation, PatchDeviceState, PatchFinding

PAGE_SIZES = [25, 50, 100, 200, 500]
SORTS = {
    "Missing patches: high to low": "missing_desc",
    "Missing patches: low to high": "missing_asc",
    "Risk score: high to low": "risk_desc",
    "Consecutive days: high to low": "days_desc",
    "Device name: A to Z": "name_asc",
    "Device name: Z to A": "name_desc",
}

def initialize_patch_report_state() -> None:
    defaults = {
        "patch_ui_offset": 0, "patch_ui_page_size": 100,
        "patch_ui_search": "", "patch_ui_min_days": 1,
        "patch_ui_min_missing": 1,
        "patch_ui_sort": "Missing patches: high to low",
        "patch_ui_date": None,
    }
    for key, value in defaults.items(): st.session_state.setdefault(key, value)

def _date(value: Any) -> date:
    if isinstance(value, date): return value
    try: return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError): return date.today()

def _clauses(report_date: date, search: str, min_days: int, min_missing: int) -> list[Any]:
    values = [
        PatchDeviceObservation.scan_date == report_date,
        PatchDeviceObservation.missing_patch_count >= min_missing,
        PatchDeviceState.consecutive_days >= min_days,
    ]
    if search.strip():
        pattern = f"%{search.strip()}%"
        values.append(or_(
            PatchDeviceObservation.device_name.ilike(pattern),
            PatchDeviceObservation.discovery_id.ilike(pattern),
            PatchDeviceObservation.ip_address.ilike(pattern),
        ))
    return values

def _ordering(code: str) -> tuple[Any, ...]:
    if code == "missing_asc": return (PatchDeviceObservation.missing_patch_count.asc(), PatchDeviceObservation.device_name.asc())
    if code == "risk_desc": return (PatchDeviceObservation.risk_score.desc().nullslast(), PatchDeviceObservation.missing_patch_count.desc())
    if code == "days_desc": return (PatchDeviceState.consecutive_days.desc(), PatchDeviceObservation.missing_patch_count.desc())
    if code == "name_asc": return (PatchDeviceObservation.device_name.asc(),)
    if code == "name_desc": return (PatchDeviceObservation.device_name.desc(),)
    return (PatchDeviceObservation.missing_patch_count.desc(), PatchDeviceObservation.device_name.asc())

def _load(report_date: date, search: str, min_days: int, min_missing: int, sort_code: str, limit: int, offset: int) -> dict[str, Any]:
    filters = _clauses(report_date, search, min_days, min_missing)
    join = PatchDeviceState.discovery_id == PatchDeviceObservation.discovery_id
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(PatchDeviceObservation).join(PatchDeviceState, join).where(*filters)) or 0
        missing_total = db.scalar(select(func.coalesce(func.sum(PatchDeviceObservation.missing_patch_count), 0)).select_from(PatchDeviceObservation).join(PatchDeviceState, join).where(*filters)) or 0
        eligible = db.scalar(select(func.count()).select_from(PatchDeviceObservation).join(PatchDeviceState, join).where(*filters, PatchDeviceState.is_active.is_(True), PatchDeviceState.consecutive_days >= 14)) or 0
        pairs = db.execute(select(PatchDeviceObservation, PatchDeviceState).join(PatchDeviceState, join).where(*filters).order_by(*_ordering(sort_code)).offset(offset).limit(limit)).all()
        ids = [o.discovery_id for o, _ in pairs]
        grouped: dict[str, list[PatchFinding]] = {item: [] for item in ids}
        if ids:
            findings = db.scalars(select(PatchFinding).where(PatchFinding.scan_date == report_date, PatchFinding.discovery_id.in_(ids), PatchFinding.evidence_type == "CONFIRMED_MISSING").order_by(PatchFinding.discovery_id, PatchFinding.severity.asc().nullslast(), PatchFinding.patch_name.asc().nullslast())).all()
            for item in findings: grouped.setdefault(item.discovery_id, []).append(item)
        devices = []
        for observation, state in pairs:
            devices.append({
                "device_name": observation.device_name, "discovery_id": observation.discovery_id,
                "ip_address": observation.ip_address, "os_name": observation.os_name,
                "missing_patch_count": observation.missing_patch_count, "risk_score": observation.risk_score,
                "last_scanned_at": observation.last_scanned_at.isoformat() if observation.last_scanned_at else None,
                "consecutive_days": state.consecutive_days, "is_active": state.is_active,
                "ticket_status": state.ticket_status, "ticket_reference": state.ticket_reference,
                "ticket_eligible": bool(state.is_active and state.consecutive_days >= 14 and (state.missing_patch_count or 0) > 0),
                "telemetry": observation.telemetry or {},
                "findings": [{
                    "patch_name": f.patch_name, "patch_id": f.patch_id, "kb_number": f.kb_number,
                    "notification_id": f.notification_id, "vendor_name": f.vendor_name,
                    "patch_status": f.patch_status, "severity": f.severity,
                    "released_at": f.released_at.isoformat() if f.released_at else None,
                } for f in grouped.get(observation.discovery_id, [])],
            })
    return {"total": int(total), "missing_total": int(missing_total), "eligible": int(eligible), "devices": devices}

def _summary(devices: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for device in devices:
        telemetry = device.get("telemetry") or {}
        rows.append({
            "Device": device.get("device_name"), "IP address": device.get("ip_address"),
            "Operating system": device.get("os_name"), "Missing patches": device.get("missing_patch_count"),
            "Detailed findings": len(device.get("findings") or []), "Risk score": device.get("risk_score"),
            "Consecutive days": device.get("consecutive_days"), "Critical": telemetry.get("security_critical"),
            "Important": telemetry.get("security_important"), "Exploited": telemetry.get("exploited_missing_patches"),
            "Ticket eligible": device.get("ticket_eligible"), "Ticket status": device.get("ticket_status"),
            "Last scanned": device.get("last_scanned_at"),
        })
    return pd.DataFrame(rows)

def _finding_frame(values: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Patch name": v.get("patch_name"), "KB number": v.get("kb_number"), "Patch ID": v.get("patch_id"),
        "Vendor": v.get("vendor_name"), "Severity": v.get("severity"), "Status": v.get("patch_status"),
        "Released": v.get("released_at"), "Notification ID": v.get("notification_id"),
    } for v in values])

def _page_csv(devices: list[dict[str, Any]]) -> bytes:
    rows = []
    for device in devices:
        base = {key: device.get(key) for key in ("device_name", "discovery_id", "ip_address", "os_name", "missing_patch_count", "risk_score", "consecutive_days", "ticket_eligible", "ticket_status")}
        findings = device.get("findings") or []
        if not findings: rows.append(base)
        for finding in findings: rows.append({**base, **finding})
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")

def _all_csv(report_date: date, search: str, min_days: int, min_missing: int, sort_code: str) -> bytes:
    filters = _clauses(report_date, search, min_days, min_missing)
    join = PatchDeviceState.discovery_id == PatchDeviceObservation.discovery_id
    with SessionLocal() as db:
        pairs = db.execute(select(PatchDeviceObservation, PatchDeviceState).join(PatchDeviceState, join).where(*filters).order_by(*_ordering(sort_code))).all()
        rows = [{
            "device_name": o.device_name, "discovery_id": o.discovery_id, "ip_address": o.ip_address,
            "os_name": o.os_name, "missing_patch_count": o.missing_patch_count, "risk_score": o.risk_score,
            "consecutive_days": s.consecutive_days, "first_seen_date": s.first_seen_date,
            "last_seen_date": s.last_seen_date, "is_active": s.is_active,
            "ticket_eligible": bool(s.is_active and s.consecutive_days >= 14 and (s.missing_patch_count or 0) > 0),
            "ticket_status": s.ticket_status, "ticket_reference": s.ticket_reference,
        } for o, s in pairs]
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")

def _inject_patch_styles() -> None:
    st.markdown("""
    <style>
    .patch-heading{font-size:1.7rem;font-weight:650;letter-spacing:-.04em;color:var(--ta-ink,#1B2433);margin:.1rem 0 .25rem}
    .patch-subtitle{color:var(--ta-muted,#667085);font-size:.85rem;margin-bottom:1.15rem}
    .patch-eyebrow{color:var(--ta-orange-2,#E14C30);font-size:.68rem;font-weight:750;letter-spacing:.14em;text-transform:uppercase;margin-bottom:.25rem}
    .patch-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:.85rem 0 1.15rem}
    .patch-metric{background:#fff;border:1px solid var(--ta-line,#E6E9EF);border-radius:14px;padding:15px 17px;box-shadow:0 1px 2px rgba(16,24,40,.03)}
    .patch-metric .label{color:var(--ta-muted,#667085);font-size:.72rem;font-weight:600}
    .patch-metric .value{color:var(--ta-ink,#1B2433);font-size:1.55rem;font-weight:650;letter-spacing:-.035em;margin-top:4px}
    .patch-card{background:#fff;border:1px solid var(--ta-line,#E6E9EF);border-radius:14px;padding:16px 18px;margin:.75rem 0;box-shadow:0 1px 2px rgba(16,24,40,.03)}
    .patch-section-title{font-size:1rem;font-weight:650;color:var(--ta-ink,#1B2433);margin:0 0 .15rem}
    .patch-section-copy{font-size:.76rem;color:var(--ta-muted,#667085);margin:0 0 .85rem}
    .patch-pager{border:1px solid var(--ta-line,#E6E9EF);border-radius:12px;background:#fff;color:var(--ta-muted,#667085);font-size:.78rem;text-align:center;padding:.62rem .4rem}
    .patch-export-label{color:var(--ta-ink,#1B2433);font-weight:650;font-size:.9rem;margin:.3rem 0 .4rem}
    @media(max-width:760px){.patch-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.patch-metric{padding:12px}}
    </style>
    """, unsafe_allow_html=True)

def render_patch_report(initial_result: dict[str, Any]) -> None:
    initialize_patch_report_state()
    _inject_patch_styles()
    initial_date = _date(initial_result.get("as_of"))
    if st.session_state.patch_ui_date is None: st.session_state.patch_ui_date = initial_date.isoformat()
    st.markdown('<div class="patch-eyebrow">Ivanti · Fleet health</div><div class="patch-heading">Patch compliance</div><div class="patch-subtitle">Monitor missing updates, prioritize exposed devices, and export remediation details. This report reads the latest stored scan and does not trigger a new Ivanti scan.</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="patch-section-title">Filter report</div><div class="patch-section-copy">Narrow the device list by identifier, exposure duration, and scan snapshot.</div>', unsafe_allow_html=True)
        with st.form("patch_report_filters", clear_on_submit=False):
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("Search device, discovery ID, or IP address", value=st.session_state.patch_ui_search, placeholder="Example: LP-CIG-0X124306")
            min_days = c2.number_input("Minimum consecutive days", 1, 365, int(st.session_state.patch_ui_min_days))
            min_missing = c3.number_input("Minimum missing patches", 1, 100000, int(st.session_state.patch_ui_min_missing))
            c4, c5, c6 = st.columns([2, 1, 1])
            sort_label = c4.selectbox("Sort by", list(SORTS), index=list(SORTS).index(st.session_state.patch_ui_sort))
            page_size = c5.selectbox("Rows per page", PAGE_SIZES, index=PAGE_SIZES.index(st.session_state.patch_ui_page_size))
            report_date = c6.date_input("Report date", value=_date(st.session_state.patch_ui_date), max_value=date.today())
            apply_col, reset_col, _ = st.columns([1, 1, 4])
            applied = apply_col.form_submit_button("Apply filters", type="primary", width="stretch")
            reset_requested = reset_col.form_submit_button("Reset", width="stretch")
    if applied:
        st.session_state.patch_ui_search = search.strip(); st.session_state.patch_ui_min_days = int(min_days)
        st.session_state.patch_ui_min_missing = int(min_missing); st.session_state.patch_ui_sort = sort_label
        st.session_state.patch_ui_page_size = int(page_size); st.session_state.patch_ui_date = report_date.isoformat()
        st.session_state.patch_ui_offset = 0; st.rerun()
    if reset_requested:
        st.session_state.patch_ui_search = ""; st.session_state.patch_ui_min_days = 1
        st.session_state.patch_ui_min_missing = 1; st.session_state.patch_ui_sort = "Missing patches: high to low"
        st.session_state.patch_ui_page_size = 100; st.session_state.patch_ui_date = initial_date.isoformat()
        st.session_state.patch_ui_offset = 0; st.rerun()
    offset, limit = int(st.session_state.patch_ui_offset), int(st.session_state.patch_ui_page_size)
    chosen_date = _date(st.session_state.patch_ui_date)
    result = _load(chosen_date, st.session_state.patch_ui_search, int(st.session_state.patch_ui_min_days), int(st.session_state.patch_ui_min_missing), SORTS[st.session_state.patch_ui_sort], limit, offset)
    total, devices = result["total"], result["devices"]
    pages = max(1, (total + limit - 1) // limit); page = min(pages, offset // limit + 1)
    st.markdown(
        '<div class="patch-metrics">'
        f'<div class="patch-metric"><div class="label">Matching devices</div><div class="value">{total:,}</div></div>'
        f'<div class="patch-metric"><div class="label">Missing patch instances</div><div class="value">{result["missing_total"]:,}</div></div>'
        f'<div class="patch-metric"><div class="label">14-day ticket eligible</div><div class="value">{result["eligible"]:,}</div></div>'
        f'<div class="patch-metric"><div class="label">Current page</div><div class="value">{page:,} <span style="font-size:.85rem;color:var(--ta-muted)">/ {pages:,}</span></div></div>'
        '</div>', unsafe_allow_html=True,
    )
    if not devices:
        with st.container(border=True):
            st.info("No patch-non-compliant devices match the selected filters.")
        return
    with st.container(border=True):
        st.markdown('<div class="patch-section-title">Devices requiring attention</div><div class="patch-section-copy">Select a device below for its confirmed missing-patch findings and scan telemetry.</div>', unsafe_allow_html=True)
        st.dataframe(_summary(devices), hide_index=True, width="stretch", height=480, column_config={
            "Missing patches": st.column_config.NumberColumn(format="%d"),
            "Risk score": st.column_config.NumberColumn(format="%.2f"),
            "Ticket eligible": st.column_config.CheckboxColumn(),
        })
    previous, status, next_page = st.columns([1, 2, 1])
    if previous.button("Previous page", key=f"patch_previous_{offset}", disabled=offset <= 0, width="stretch"):
        st.session_state.patch_ui_offset = max(0, offset - limit); st.rerun()
    status.markdown(f'<div class="patch-pager">Showing <strong>{offset + 1:,}–{min(offset + len(devices), total):,}</strong> of <strong>{total:,}</strong> devices</div>', unsafe_allow_html=True)
    if next_page.button("Next page", key=f"patch_next_{offset}", disabled=offset + len(devices) >= total, width="stretch"):
        st.session_state.patch_ui_offset = offset + limit; st.rerun()
    st.markdown('<div class="patch-export-label">Export report</div>', unsafe_allow_html=True)
    left, right = st.columns(2)
    left.download_button("Download page + patch findings", _page_csv(devices), f"patch_report_{chosen_date}_page_{page}.csv", "text/csv", width="stretch", icon=":material/download:")
    right.download_button("Download all matching devices", _all_csv(chosen_date, st.session_state.patch_ui_search, int(st.session_state.patch_ui_min_days), int(st.session_state.patch_ui_min_missing), SORTS[st.session_state.patch_ui_sort]), f"patch_report_{chosen_date}_all_devices.csv", "text/csv", width="stretch", icon=":material/download:")
    st.markdown('<div class="patch-export-label" style="margin-top:1.2rem">Device findings</div>', unsafe_allow_html=True)
    for device in devices:
        findings = device.get("findings") or []
        with st.expander(f"{device.get('device_name') or 'Unknown'} · {int(device.get('missing_patch_count') or 0):,} missing · {len(findings):,} details"):
            a, b = st.columns(2)
            a.markdown(f"**Discovery ID**  \n{device.get('discovery_id') or 'Unavailable'}")
            a.markdown(f"**IP address**  \n{device.get('ip_address') or 'Unavailable'}")
            a.markdown(f"**Operating system**  \n{device.get('os_name') or 'Unavailable'}")
            b.markdown(f"**Risk score**  \n{device.get('risk_score') if device.get('risk_score') is not None else 'Unavailable'}")
            b.markdown(f"**Consecutive days**  \n{device.get('consecutive_days') or 0}")
            b.markdown(f"**Ticket eligible**  \n{'Yes' if device.get('ticket_eligible') else 'No'}")
            if device.get("telemetry"):
                with st.expander("Stored telemetry"): st.json(device["telemetry"])
            if findings: st.dataframe(_finding_frame(findings), hide_index=True, width="stretch")
            else: st.warning("No detailed Missing patch summaries were returned for this snapshot.")
