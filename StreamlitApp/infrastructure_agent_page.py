"""Polished Infrastructure Agent operator workspace."""
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
from App.services.infrastructure.models import InfrastructureDevice, InfrastructureSiteAlert
from App.services.infrastructure.processor import process_infrastructure_sites
from App.services.infrastructure.prompt_builder import build_ticket_description
from App.services.infrastructure.scheduler import scheduler_status
from App.services.infrastructure.state_repository import InfrastructureStateRepository

def _text(value: Any, fallback: str = "Not available") -> str:
    if value in (None, ""):
        return fallback
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone().strftime("%d %b %Y, %H:%M %Z")
    return str(value)

def _detail(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) if value else {}
    except Exception:
        return {}

def _alert(item: dict[str, Any]) -> InfrastructureSiteAlert:
    detail = _detail(item.get("detail_json"))
    devices = []
    for value in detail.get("devices") or []:
        if str(value.get("source_system") or "").upper() != "SOLARWINDS":
            continue
        devices.append(
            InfrastructureDevice(
                "SOLARWINDS",
                _text(value.get("device_name"), ""),
                value.get("ci_type"),
                _text(value.get("device_status"), ""),
                value.get("source_location"),
                None,
                None,
                value.get("device_silent_for"),
            )
        )
    return InfrastructureSiteAlert(
        str(item.get("sync_run_id") or ""),
        _text(item.get("location_name"), ""),
        detail.get("match_level"),
        _text(item.get("current_status"), "").lower(),
        float(item["site_score"]) if item.get("site_score") is not None else None,
        item.get("site_reason"),
        _text(item.get("priority"), ""),
        None, None, None,
        int(detail.get("total_devices") or 0),
        int(detail.get("healthy") or 0),
        int(detail.get("critical_devices") or 0),
        int(detail.get("degraded") or 0),
        int(detail.get("not_assessed") or 0),
        float(detail["healthy_pct"]) if detail.get("healthy_pct") is not None else None,
        devices,
    )

def _css() -> None:
    st.markdown("""
    <style>
      .infra-record{display:flex;align-items:center;gap:13px;margin:6px 0 17px}
      .infra-avatar{width:50px;height:50px;border-radius:14px;background:#fee9e3;color:#d92d20;
        display:flex;align-items:center;justify-content:center;font-weight:800;font-size:17px}
      .infra-kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#197a4a;font-weight:800}
      .infra-name{font-size:22px;font-weight:720;color:#101828;margin-top:2px}
      .infra-tile{height:128px;border-radius:13px;padding:16px;box-sizing:border-box;border:1px solid #cce8d7;background:#ecf8f1}
      .infra-tile.red{background:#fff0ed;border-color:#f6c0b7}.infra-tile.amber{background:#fff7e8;border-color:#f4d7a5}
      .infra-tile.blue{background:#eef5ff;border-color:#cadcf4}.infra-tile small{color:#667085}
      .infra-tile strong{display:block;font-size:20px;margin:8px 0;color:#157347}.infra-tile.red strong{color:#b42318}
      .infra-tile.amber strong{color:#b54708}.infra-tile.blue strong{color:#175cd3}
      .infra-explain{border-left:4px solid #ef5b3f;background:#fff7f4;padding:14px 16px;border-radius:4px 12px 12px 4px;
        color:#344054;line-height:1.55;margin:12px 0 16px}
    </style>""", unsafe_allow_html=True)

def _countdown(status: dict[str, Any]) -> None:
    next_run = status.get("next_run_time")
    if not status.get("running") or not next_run:
        st.caption("Automatic monitoring is stopped.")
        return
    st.iframe(f"""<div style='font:14px Segoe UI;color:#667085'>Automatic monitoring active · Next check in <b id='count' style='color:#197a4a'></b></div>
    <script>const t=new Date({json.dumps(next_run)}).getTime(),e=document.getElementById('count');let q=false;
    function x(){{let r=t-Date.now(),s=Math.max(0,Math.floor(r/1000));e.textContent=`${{Math.floor(s/60)}}m ${{String(s%60).padStart(2,'0')}}s`;
    if(r<=0&&!q){{q=true;e.textContent='refreshing...';setTimeout(()=>window.parent.location.reload(),12000)}}}}x();setInterval(x,1000);</script>""", height=25)

def _tile(column: Any, label: str, value: str, detail: str, tone: str) -> None:
    with column:
        st.markdown(f'<div class="infra-tile {tone}"><small>{escape(label)}</small><strong>{escape(value)}</strong><small>{escape(detail)}</small></div>', unsafe_allow_html=True)

def _show_site(item: dict[str, Any]) -> None:
    alert = _alert(item)
    initials = "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", alert.location_name)[:2]).upper() or "SI"
    st.markdown(f'<div class="infra-record"><div class="infra-avatar">{initials}</div><div><div class="infra-kicker">Site health record</div><div class="infra-name">{escape(alert.location_name)}</div><small>Last checked {_text(item.get("last_detected_at"))}</small></div></div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4, gap="small")
    tone = "red" if alert.priority == "P1" else "amber"
    _tile(c1,"Reported site health",f"{alert.priority} · {alert.site_status.title()}","Status reported by ITOM",tone)
    _tile(c2,"Reported site score",_text(alert.site_score),_text(alert.site_reason),tone)
    _tile(c3,"Affected SolarWinds devices",str(alert.affected_count),f"{alert.critical_devices} critical/down · {alert.degraded} warning","amber")
    _tile(c4,"Automation",_text(item.get("ticket_status"),"Not attempted").title(),f"Ticket {_text(item.get('ticket_id'),'Pending')}","blue")
    st.markdown(f'<div class="infra-explain"><strong>Data explanation:</strong> ITOM reports {escape(alert.location_name)} as {escape(alert.site_status)} with score {escape(_text(alert.site_score))}. TechAdmin maps that reported status to {escape(alert.priority)}. The affected list contains {alert.affected_count} SolarWinds devices. TechAdmin does not calculate the site score or independently determine the site status.</div>', unsafe_allow_html=True)
    overview, devices_tab, automation_tab = st.tabs(["Overview",f"SolarWinds devices ({alert.affected_count})","Ticket and notification"])
    with overview:
        a,b,c,d = st.columns(4)
        a.metric("Monitored",alert.total_devices); b.metric("Up",alert.healthy); c.metric("Affected",alert.affected_count); d.metric("Not assessed",alert.not_assessed)
    with devices_tab:
        frame = pd.DataFrame([{"Device":d.device_name,"Status":d.device_status,"Type":_text(d.ci_type),"Location":_text(d.source_location),"Unreachable for":_text(d.device_silent_for)} for d in alert.devices])
        st.dataframe(frame,hide_index=True,width="stretch",height=360)
        st.download_button("Download SolarWinds device CSV",frame.to_csv(index=False).encode("utf-8-sig"),re.sub(r"\W+","_",alert.location_name)+"_solarwinds.csv","text/csv")
    with automation_tab:
        st.write(f"**iEngage ticket:** {_text(item.get('ticket_id'),'Pending')}")
        st.write(f"**Email:** {_text(item.get('email_status'),'Not sent').title()}")
        description,prompt = build_ticket_description(alert)
        with st.expander("Investigation guide for SolarWinds"):
            st.code(prompt, language=None, wrap_lines=True)
        with st.expander("Details sent to new iEngage tickets"):
            st.code(description, language=None, wrap_lines=True)

def render_infrastructure_agent_page(claims: dict[str, Any], access: dict[str, Any]) -> None:
    del claims,access
    _css(); repository=InfrastructureStateRepository(); status=scheduler_status()
    with st.container(key="content"):
        left,right=st.columns([5,1.4],vertical_alignment="center")
        left.markdown('<div class="ta-greet"><h1>Infrastructure Agent</h1></div>',unsafe_allow_html=True)
        if right.button("Run poll now",icon=":material/refresh:",width="stretch"):
            with st.spinner("Checking SolarWinds site health..."):
                process_infrastructure_sites(trigger_type="manual")
            st.rerun()
        _countdown(status)
        sites_tab,history_tab=st.tabs(["Site health","Check history"])
        with sites_tab:
            records=[r for r in repository.list_incidents() if r.get("current_status")!="recovered"]
            m1,m2,m3,m4=st.columns(4);m1.metric("Sites needing attention",len(records));m2.metric("Critical",sum(r.get("priority")=="P1" for r in records));m3.metric("Warning",sum(r.get("priority")=="P2" for r in records));m4.metric("With tickets",sum(bool(r.get("ticket_id")) for r in records))
            table=pd.DataFrame([{"Site":_text(r.get("location_name"),""),"Priority":_text(r.get("priority"),""),"Health":_text(r.get("current_status"),"").title(),"Affected SolarWinds devices":len(_alert(r).devices),"Ticket":_text(r.get("ticket_id"),"Pending"),"Last checked":_text(r.get("last_detected_at"))} for r in records])
            event=st.dataframe(table,hide_index=True,width="stretch",height=365,on_select="rerun",selection_mode="single-row",key="infra_sites")
            selected=list(event.selection.rows) if hasattr(event,"selection") else []
            pick=int(selected[0]) if selected else (0 if records else -1)
            if 0<=pick<len(records):
                _show_site(records[pick])
        with history_tab:
            history=repository.list_poll_runs(100)
            frame=pd.DataFrame([{"Check":_text(r.get("trigger_type"),"").title(),"Result":_text(r.get("status"),"").replace("_"," ").title(),"Sites":int(r.get("alerts_found") or 0),"Tickets":int(r.get("tickets_created") or 0),"Emails":int(r.get("emails_sent") or 0),"Started":_text(r.get("started_at")),"Completed":_text(r.get("completed_at"))} for r in history])
            st.dataframe(frame,hide_index=True,width="stretch",height=430)
