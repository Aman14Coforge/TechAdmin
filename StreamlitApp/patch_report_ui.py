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

def render_patch_report(initial_result: dict[str, Any]) -> None:
    initialize_patch_report_state()
    initial_date = _date(initial_result.get("as_of"))
    if st.session_state.patch_ui_date is None: st.session_state.patch_ui_date = initial_date.isoformat()
    st.markdown("### Ivanti patch compliance report")
    st.caption("Filters, sorting, pagination, and exports read PostgreSQL only. No new Ivanti scan is triggered.")
    with st.form("patch_report_filters", clear_on_submit=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        search = c1.text_input("Search device, discovery ID, or IP address", value=st.session_state.patch_ui_search, placeholder="Example: LP-CIG-0X124306")
        min_days = c2.number_input("Minimum consecutive days", 1, 365, int(st.session_state.patch_ui_min_days))
        min_missing = c3.number_input("Minimum missing patches", 1, 100000, int(st.session_state.patch_ui_min_missing))
        c4, c5, c6 = st.columns([2, 1, 1])
        sort_label = c4.selectbox("Sort by", list(SORTS), index=list(SORTS).index(st.session_state.patch_ui_sort))
        page_size = c5.selectbox("Rows per page", PAGE_SIZES, index=PAGE_SIZES.index(st.session_state.patch_ui_page_size))
        report_date = c6.date_input("Report date", value=_date(st.session_state.patch_ui_date), max_value=date.today())
        applied = st.form_submit_button("Apply filters", type="primary", width="stretch")
    if applied:
        st.session_state.patch_ui_search = search.strip(); st.session_state.patch_ui_min_days = int(min_days)
        st.session_state.patch_ui_min_missing = int(min_missing); st.session_state.patch_ui_sort = sort_label
        st.session_state.patch_ui_page_size = int(page_size); st.session_state.patch_ui_date = report_date.isoformat()
        st.session_state.patch_ui_offset = 0; st.rerun()
    if st.button("Reset filters", key="patch_reset_filters"):
        st.session_state.patch_ui_search = ""; st.session_state.patch_ui_min_days = 1
        st.session_state.patch_ui_min_missing = 1; st.session_state.patch_ui_sort = "Missing patches: high to low"
        st.session_state.patch_ui_page_size = 100; st.session_state.patch_ui_date = initial_date.isoformat()
        st.session_state.patch_ui_offset = 0; st.rerun()
    offset, limit = int(st.session_state.patch_ui_offset), int(st.session_state.patch_ui_page_size)
    chosen_date = _date(st.session_state.patch_ui_date)
    result = _load(chosen_date, st.session_state.patch_ui_search, int(st.session_state.patch_ui_min_days), int(st.session_state.patch_ui_min_missing), SORTS[st.session_state.patch_ui_sort], limit, offset)
    total, devices = result["total"], result["devices"]
    pages = max(1, (total + limit - 1) // limit); page = min(pages, offset // limit + 1)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Matching devices", f"{total:,}"); m2.metric("Missing patch instances", f"{result['missing_total']:,}")
    m3.metric("14-day ticket eligible", f"{result['eligible']:,}"); m4.metric("Page", f"{page:,} of {pages:,}")
    if not devices: st.info("No patch-non-compliant devices match the selected filters."); return
    st.dataframe(_summary(devices), hide_index=True, width="stretch", height=560, column_config={
        "Missing patches": st.column_config.NumberColumn(format="%d"),
        "Risk score": st.column_config.NumberColumn(format="%.2f"),
        "Ticket eligible": st.column_config.CheckboxColumn(),
    })
    previous, status, next_page = st.columns([1, 2, 1])
    if previous.button("Previous page", key=f"patch_previous_{offset}", disabled=offset <= 0, width="stretch"):
        st.session_state.patch_ui_offset = max(0, offset - limit); st.rerun()
    status.markdown(f"<div style='text-align:center;padding:.55rem'>Showing <strong>{offset + 1:,}</strong> to <strong>{min(offset + len(devices), total):,}</strong> of <strong>{total:,}</strong></div>", unsafe_allow_html=True)
    if next_page.button("Next page", key=f"patch_next_{offset}", disabled=offset + len(devices) >= total, width="stretch"):
        st.session_state.patch_ui_offset = offset + limit; st.rerun()
    left, right = st.columns(2)
    left.download_button("Download current page with patch details", _page_csv(devices), f"patch_report_{chosen_date}_page_{page}.csv", "text/csv", width="stretch")
    right.download_button("Download all matching device summaries", _all_csv(chosen_date, st.session_state.patch_ui_search, int(st.session_state.patch_ui_min_days), int(st.session_state.patch_ui_min_missing), SORTS[st.session_state.patch_ui_sort]), f"patch_report_{chosen_date}_all_devices.csv", "text/csv", width="stretch")
    st.markdown("### Device patch details")
    for device in devices:
        findings = device.get("findings") or []
        with st.expander(f"{device.get('device_name') or 'Unknown'} · {int(device.get('missing_patch_count') or 0):,} missing · {len(findings):,} details"):
            a, b = st.columns(2)
            a.write(f"Discovery ID: `{device.get('discovery_id') or 'Unavailable'}`")
            a.write(f"IP address: `{device.get('ip_address') or 'Unavailable'}`")
            a.write(f"Operating system: {device.get('os_name') or 'Unavailable'}")
            b.write(f"Risk score: **{device.get('risk_score') if device.get('risk_score') is not None else 'Unavailable'}**")
            b.write(f"Consecutive days: **{device.get('consecutive_days') or 0}**")
            b.write(f"Ticket eligible: **{'Yes' if device.get('ticket_eligible') else 'No'}**")
            if device.get("telemetry"):
                with st.expander("Stored telemetry"): st.json(device["telemetry"])
            if findings: st.dataframe(_finding_frame(findings), hide_index=True, width="stretch")
            else: st.warning("No detailed Missing patch summaries were returned for this snapshot.")
