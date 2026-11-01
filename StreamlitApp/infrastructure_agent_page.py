"""Operator-friendly Infrastructure Agent page."""
from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from App.services.infrastructure.processor import process_infrastructure_sites
from App.services.infrastructure.scheduler import scheduler_status
from App.services.infrastructure.state_repository import InfrastructureStateRepository

STATUS_ORDER = {"Down": 1, "Critical": 2, "Warning": 3, "NonCompliant": 4, "Unknown": 5}


def _text(value: Any, fallback: str = "Not available") -> str:
    if value in (None, ""):
        return fallback
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        try:
            return value.astimezone().strftime("%d %b %Y, %H:%M %Z")
        except (ValueError, OSError):
            return value.isoformat()
    return str(value)


def _safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _detail(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return _safe(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return _safe(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _css() -> None:
    st.markdown(
        """
        <style>
          .infra-site-head{display:flex;align-items:center;gap:13px;margin:4px 0 15px}
          .infra-site-avatar{width:50px;height:50px;border-radius:14px;display:flex;align-items:center;
            justify-content:center;font-weight:800;background:#fee9e3;color:#d92d20;font-size:18px}
          .infra-kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:800;
            color:#197a4a;margin-bottom:3px}
          .infra-site-name{font-size:22px;font-weight:720;color:#101828}
          .infra-site-sub{font-size:13px;color:#667085;margin-top:3px}
          .infra-tile{border-radius:13px;padding:15px 16px;height:126px;box-sizing:border-box;
            display:flex;flex-direction:column;justify-content:center;border:1px solid #cce8d7;background:#ecf8f1}
          .infra-tile.warn{border-color:#f4d7a5;background:#fff7e8}
          .infra-tile.bad{border-color:#f6c0b7;background:#fff0ed}
          .infra-tile.info{border-color:#cadcf4;background:#eef5ff}
          .infra-tile .label{font-size:12px;color:#667085;margin-bottom:6px}
          .infra-tile .value{font-size:21px;color:#157347;font-weight:750;line-height:1.12}
          .infra-tile.warn .value{color:#b54708}.infra-tile.bad .value{color:#b42318}
          .infra-tile.info .value{color:#175cd3}
          .infra-tile .sub{font-size:12px;color:#667085;margin-top:7px;line-height:1.35}
          .infra-summary{border-left:4px solid #ef5b3f;background:#fff7f4;border-radius:4px 12px 12px 4px;
            padding:13px 15px;color:#344054;line-height:1.55;margin:12px 0 16px}
          .infra-result{border:1px solid #e4e7ec;border-radius:13px;background:#fff;padding:14px 16px;
            height:135px;box-sizing:border-box}
          .infra-result .title{font-size:12px;color:#667085;text-transform:uppercase;letter-spacing:.07em;font-weight:750}
          .infra-result .main{font-size:19px;color:#101828;font-weight:740;margin:7px 0}
          .infra-result .detail{font-size:12px;color:#667085;line-height:1.4}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _countdown(status: dict[str, Any]) -> None:
    next_run = status.get("next_run_time")
    if not status.get("running") or not next_run:
        st.caption("Automatic monitoring is stopped.")
        return
    components.html(
        f"""
        <div style="font-family:Segoe UI,Arial,sans-serif;color:#667085;font-size:14px">
          Automatic monitoring is active · Next check in
          <strong id="infra-count" style="color:#197a4a">calculating...</strong>
        </div>
        <script>
          const target=new Date({json.dumps(next_run)}).getTime();
          const node=document.getElementById('infra-count');
          function tick(){{const left=Math.max(0,target-Date.now());const seconds=Math.floor(left/1000);
          node.textContent=`${{Math.floor(seconds/60)}}m ${{String(seconds%60).padStart(2,'0')}}s`;}}
          tick();setInterval(tick,1000);
        </script>
        """,
        height=25,
    )


def _site_table(records: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Site": _text(item.get("location_name"), ""),
        "Priority": _text(item.get("priority"), ""),
        "Health": _text(item.get("current_status"), "").title(),
        "Score": float(item["site_score"]) if item.get("site_score") is not None else None,
        "Affected": int(item.get("affected_count") or 0),
        "Ticket": _text(item.get("ticket_id"), "Pending"),
        "Email": _text(item.get("email_status"), "Not sent").title(),
        "Last checked": _text(item.get("last_detected_at")),
    } for item in records])


def _device_table(devices: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame([{
        "Device": _text(device.get("device_name")),
        "Status": _text(device.get("device_status")),
        "Type": _text(device.get("ci_type")),
        "Monitoring source": _text(device.get("source_system")),
        "Location": _text(device.get("source_location")),
        "Last seen": _text(device.get("device_last_seen_ist")),
        "Unreachable for": _text(device.get("device_silent_for")),
    } for device in devices])
    if not frame.empty:
        frame["_rank"] = frame["Status"].map(STATUS_ORDER).fillna(99)
        frame = frame.sort_values(["_rank", "Device"]).drop(columns=["_rank"])
    return frame


def _history_table(records: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Check type": _text(item.get("trigger_type"), "").title(),
        "Result": "Interrupted" if item.get("status") == "failed" and "stopped or restarted" in str(
            item.get("error_summary") or "").lower() else _text(item.get("status"), "").replace("_", " ").title(),
        "Sites checked": int(item.get("alerts_found") or 0),
        "New tickets": int(item.get("tickets_created") or 0),
        "Existing sites": int(item.get("sites_skipped") or 0),
        "Recovered": int(item.get("sites_recovered") or 0),
        "Emails": int(item.get("emails_sent") or 0),
        "Issues": int(item.get("error_count") or 0),
        "Started": _text(item.get("started_at")),
        "Completed": _text(item.get("completed_at")),
        "Time taken": f"{float(item['duration_seconds']):.1f}s" if item.get("duration_seconds") is not None else "Not completed",
    } for item in records])


def _initials(location: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", location) if word]
    return (words[0][:2] if len(words) == 1 else words[0][0] + words[-1][0]).upper() if words else "SI"


def _tile(column: Any, label: str, value: str, sub: str, tone: str = "") -> None:
    with column:
        st.markdown(
            f'<div class="infra-tile {escape(tone)}"><div class="label">{escape(label)}</div>'
            f'<div class="value">{escape(value)}</div><div class="sub">{escape(sub)}</div></div>',
            unsafe_allow_html=True,
        )


def _selected_site(item: dict[str, Any]) -> None:
    detail = _detail(item.get("detail_json"))
    devices = detail.get("devices") if isinstance(detail.get("devices"), list) else []
    location = _text(item.get("location_name"), "Unknown site")
    priority = _text(item.get("priority"), "")
    status = _text(item.get("current_status"), "Unknown").title()
    reason = _text(item.get("site_reason"), "No issue reason was reported")
    total, healthy = int(detail.get("total_devices") or 0), int(detail.get("healthy") or 0)
    critical, degraded = int(detail.get("critical_devices") or 0), int(detail.get("degraded") or 0)
    affected = int(item.get("affected_count") or 0)
    ticket = _text(item.get("ticket_id"), "Pending")
    ticket_status = _text(item.get("ticket_status"), "Not attempted").title()
    email_status = _text(item.get("email_status"), "Not sent").title()

    st.markdown(
        f'<div class="infra-site-head"><div class="infra-site-avatar">{escape(_initials(location))}</div>'
        f'<div><div class="infra-kicker">Site health record</div><div class="infra-site-name">{escape(location)}</div>'
        f'<div class="infra-site-sub">Last checked {_text(item.get("last_detected_at"))}</div></div></div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4, gap="small")
    status_counts: dict[str, int] = {}
    for device in devices:
        device_status = _text(device.get("device_status"), "Unknown")
        status_counts[device_status] = status_counts.get(device_status, 0) + 1

    affected_breakdown = " · ".join(
        f"{count} {device_status}"
        for device_status, count in sorted(
            status_counts.items(),
            key=lambda entry: STATUS_ORDER.get(entry[0], 99),
        )
    ) or "No affected-device status was returned"

    _tile(
        c1,
        "Reported site health",
        f"{priority} · {status}",
        "Status reported by the latest ITOM snapshot",
        "bad" if priority == "P1" else "warn",
    )
    _tile(
        c2,
        "Reported site score",
        _text(item.get("site_score")),
        reason,
        "bad" if priority == "P1" else "warn",
    )
    _tile(
        c3,
        "Affected records",
        str(affected),
        affected_breakdown,
        "warn",
    )
    _tile(
        c4,
        "Automation",
        ticket_status,
        f"Ticket {ticket} · Email {email_status.lower()}",
        "info",
    )

    database_status = _text(item.get("current_status"), "Unknown").lower()
    mapping_text = (
        f"The latest ITOM snapshot reports {location} as {database_status}. "
        f"TechAdmin maps the reported {database_status} status to {priority}. "
        f"The site score ({_text(item.get('site_score'))}) and reason "
        f"({reason}) are displayed exactly from the ITOM site record. "
        f"The affected-device list contains {affected} records: {affected_breakdown}. "
        "TechAdmin has not calculated the site score or independently determined the site status."
    )
    st.markdown(
        f'<div class="infra-summary"><strong>Data explanation:</strong> '
        f'{escape(mapping_text)}</div>',
        unsafe_allow_html=True,
    )

    overview, device_tab, action_tab = st.tabs(["Overview", f"Affected devices ({len(devices)})", "Ticket and notification"])
    with overview:
        left, right = st.columns(2)
        with left:
            st.metric("Total monitored devices", total)
            st.metric("Healthy devices", healthy)
        with right:
            st.metric("Critical or down", critical)
            st.metric("Degraded", degraded)

    with device_tab:
        frame = _device_table(devices)
        if frame.empty:
            st.info("No affected-device details are available for this site.")
        else:
            f1, f2 = st.columns([1.2, 2.2])
            status_filter = f1.selectbox("Status", ["All"] + sorted(frame["Status"].unique().tolist()), key=f"dev_status_{location}")
            search = f2.text_input("Search device", placeholder="Enter device name", key=f"dev_search_{location}").strip().casefold()
            shown = frame
            if status_filter != "All": shown = shown[shown["Status"] == status_filter]
            if search: shown = shown[shown["Device"].str.casefold().str.contains(search, na=False)]
            st.dataframe(shown, hide_index=True, width="stretch", height=360)
            st.download_button("Download device list", frame.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{re.sub(r'[^A-Za-z0-9_-]+','_',location)}_devices.csv", mime="text/csv",
                icon=":material/download:", key=f"dev_download_{location}")

    with action_tab:
        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown(f'<div class="infra-result"><div class="title">iEngage ticket</div><div class="main">{escape(ticket)}</div>'
                f'<div class="detail">Status: {escape(ticket_status)}<br>Created: {escape(_text(item.get("last_ticketed_at")))}</div></div>', unsafe_allow_html=True)
        with right:
            st.markdown(f'<div class="infra-result"><div class="title">Email notification</div><div class="main">{escape(email_status)}</div>'
                f'<div class="detail">Last sent: {escape(_text(item.get("last_emailed_at")))}</div></div>', unsafe_allow_html=True)
        with st.expander("Investigation guide for SolarWinds"):
            st.caption("Copy this into SolarWinds chat when deeper investigation is required.")
            st.code(_text(item.get("solarwinds_prompt"), "No investigation guide is available."), language=None, wrap_lines=True)
        with st.expander("Details sent to iEngage"):
            st.code(_text(item.get("ticket_description"), "No ticket description is available."), language=None, wrap_lines=True)


def render_infrastructure_agent_page(claims: dict[str, Any], access: dict[str, Any]) -> None:
    del claims, access
    _css()
    repo = InfrastructureStateRepository()
    try: status = scheduler_status()
    except Exception: status = {"running": False, "next_run_time": None, "interval_minutes": 10}

    with st.container(key="content"):
        left, right = st.columns([5, 1.4], vertical_alignment="center")
        left.markdown('<div class="ta-greet"><h1>Infrastructure Agent</h1></div>', unsafe_allow_html=True)
        if right.button("Run poll now", icon=":material/refresh:", width="stretch", key="infrastructure_run_poll"):
            with st.spinner("Checking site health..."):
                try: result = process_infrastructure_sites(trigger_type="manual")
                except Exception as exc: result = {"alerts":0,"tickets_created":0,"emails_sent":0,"skipped":0,"errors":[f"{type(exc).__name__}: {exc}"]}
                st.session_state.infrastructure_last_manual_result = result
            st.rerun()
        _countdown(status)

        result = st.session_state.get("infrastructure_last_manual_result")
        if isinstance(result, dict):
            msg = f"Latest manual check: {result.get('alerts',0)} sites found, {result.get('tickets_created',0)} tickets created, {result.get('emails_sent',0)} emails sent, and {result.get('skipped',0)} existing sites unchanged."
            (st.warning if result.get("errors") else st.success)(msg)

        sites_tab, history_tab = st.tabs(["Site health", "Check history"])
        with sites_tab:
            try: records = repo.list_incidents()
            except Exception as exc:
                st.error(f"Site data could not be loaded: {type(exc).__name__}: {exc}"); return
            active = [x for x in records if x.get("current_status") != "recovered"]
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Sites needing attention",len(active)); m2.metric("Critical sites",sum(x.get("priority")=="P1" for x in active))
            m3.metric("Warning sites",sum(x.get("priority")=="P2" for x in active)); m4.metric("Sites with tickets",sum(bool(x.get("ticket_id")) for x in active))
            f1,f2,f3 = st.columns([2.5,1.2,1.2])
            search=f1.text_input("Search",placeholder="Site or ticket number",key="infra_search").strip().casefold()
            priority=f2.selectbox("Priority",["All","P1","P2"],key="infra_priority")
            recovered=f3.checkbox("Show recovered",False,key="infra_recovered")
            filtered=[x for x in records if (recovered or x.get("current_status")!="recovered") and (priority=="All" or x.get("priority")==priority) and (not search or search in str(x.get("location_name") or "").casefold() or search in str(x.get("ticket_id") or "").casefold())]
            st.caption("Select one row to view the site details below.")
            event=st.dataframe(_site_table(filtered),hide_index=True,width="stretch",height=365,key="infra_site_table",on_select="rerun",selection_mode="single-row")
            rows=list(event.selection.rows) if hasattr(event,"selection") else []
            selected=int(rows[0]) if rows else (0 if filtered else -1)
            if 0 <= selected < len(filtered): st.write(""); _selected_site(filtered[selected])
            else: st.info("No site matches the selected filters.")

        with history_tab:
            st.caption("Each automatic and manual site check is shown here.")
            limit=st.selectbox("History",[25,50,100,250],index=1,key="infra_history",format_func=lambda x:f"Latest {x} checks")
            try: history=repo.list_poll_runs(limit)
            except Exception as exc:
                st.error(f"Check history could not be loaded: {type(exc).__name__}: {exc}"); return
            if history:
                frame=_history_table(history); st.dataframe(frame,hide_index=True,width="stretch",height=430)
                st.download_button("Download check history",frame.to_csv(index=False).encode("utf-8-sig"),file_name="infrastructure_check_history.csv",mime="text/csv",icon=":material/download:")
            else: st.info("No check history is available yet.")
