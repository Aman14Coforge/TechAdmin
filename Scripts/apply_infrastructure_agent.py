"""Polished Infrastructure Agent workspace."""
from __future__ import annotations
import json,re
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from App.services.infrastructure.models import InfrastructureDevice,InfrastructureSiteAlert
from App.services.infrastructure.processor import process_infrastructure_sites
from App.services.infrastructure.prompt_builder import build_solarwinds_prompt,build_ticket_description
from App.services.infrastructure.scheduler import scheduler_status
from App.services.infrastructure.state_repository import InfrastructureStateRepository

def _t(v:Any,f="Not available")->str:
    if v in (None,""):return f
    if isinstance(v,Decimal):return format(v,"f")
    if isinstance(v,datetime):return v.astimezone().strftime("%d %b %Y, %H:%M %Z")
    return str(v)
def _details(v):
    if isinstance(v,dict):return v
    try:return json.loads(v) if v else {}
    except:return {}
def _alert(item):
    d=_details(item.get("detail_json"));devices=[]
    for x in d.get("devices") or []:
        if str(x.get("source_system") or "").upper()=="SOLARWINDS":devices.append(InfrastructureDevice("SOLARWINDS",_t(x.get("device_name"),""),x.get("ci_type"),_t(x.get("device_status"),""),x.get("source_location"),None,None,x.get("device_silent_for")))
    return InfrastructureSiteAlert(str(item.get("sync_run_id") or ""),_t(item.get("location_name"),""),None,_t(item.get("current_status"),"").lower(),float(item["site_score"]) if item.get("site_score") is not None else None,item.get("site_reason"),_t(item.get("priority"),""),None,None,None,int(d.get("total_devices") or 0),int(d.get("healthy") or 0),int(d.get("critical_devices") or 0),int(d.get("degraded") or 0),int(d.get("not_assessed") or 0),float(d["healthy_pct"]) if d.get("healthy_pct") is not None else None,devices)
def _css():
    st.markdown('''<style>.ih{display:flex;gap:12px;align-items:center;margin:8px 0 16px}.ia{width:50px;height:50px;border-radius:14px;background:#fee9e3;color:#d92d20;display:flex;align-items:center;justify-content:center;font-weight:800}.ik{font-size:11px;color:#197a4a;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.in{font-size:22px;font-weight:720}.it{height:128px;border-radius:13px;padding:16px;box-sizing:border-box;background:#ecf8f1;border:1px solid #cce8d7}.it.red{background:#fff0ed;border-color:#f6c0b7}.it.amber{background:#fff7e8;border-color:#f4d7a5}.it.blue{background:#eef5ff;border-color:#cadcf4}.it small{color:#667085}.it b{display:block;font-size:20px;margin:8px 0;color:#157347}.it.red b{color:#b42318}.it.amber b{color:#b54708}.it.blue b{color:#175cd3}</style>''',unsafe_allow_html=True)
def _countdown(s):
    n=s.get("next_run_time")
    if not s.get("running") or not n:st.caption("Automatic monitoring is stopped.");return
    components.html(f'''<div style="font:14px Segoe UI;color:#667085">Automatic monitoring active · Next check in <b id=c style="color:#197a4a"></b></div><script>const t=new Date({json.dumps(n)}).getTime(),e=document.getElementById('c');let q=false;function x(){{let r=t-Date.now(),s=Math.max(0,Math.floor(r/1000));e.textContent=`${{Math.floor(s/60)}}m ${{String(s%60).padStart(2,'0')}}s`;if(r<=0&&!q){{q=true;e.textContent='refreshing...';setTimeout(()=>window.parent.location.reload(),12000)}}}}x();setInterval(x,1000);</script>''',height=25)
def _tile(col,label,value,sub,tone=""):
    with col:st.markdown(f'<div class="it {tone}"><small>{escape(label)}</small><b>{escape(str(value))}</b><small>{escape(sub)}</small></div>',unsafe_allow_html=True)
def _show(item):
    a=_alert(item);initial="".join(w[0] for w in re.findall(r"[A-Za-z0-9]+",a.location_name)[:2]).upper() or "SI"
    st.markdown(f'<div class=ih><div class=ia>{initial}</div><div><div class=ik>Site health record</div><div class=in>{escape(a.location_name)}</div><small>Last checked {_t(item.get("last_detected_at"))}</small></div></div>',unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4,gap="small");_tile(c1,"Reported health",f"{a.priority} · {a.site_status.title()}","Latest ITOM snapshot","red" if a.priority=="P1" else "amber");_tile(c2,"Reported score",_t(a.site_score),_t(a.site_reason),"red" if a.priority=="P1" else "amber");_tile(c3,"Affected SolarWinds devices",a.affected_count,f"{a.critical_devices} critical/down · {a.degraded} warning","amber");_tile(c4,"Automation",_t(item.get("ticket_status"),"Not attempted").title(),f"Ticket {_t(item.get('ticket_id'),'Pending')}","blue")
    ov,dev,act=st.tabs(["Overview",f"SolarWinds devices ({a.affected_count})","Ticket and notification"])
    with ov:
        x,y,z,w=st.columns(4);x.metric("Monitored",a.total_devices);y.metric("Up",a.healthy);z.metric("Affected",a.affected_count);w.metric("Not assessed",a.not_assessed)
    with dev:
        frame=pd.DataFrame([{"Device":d.device_name,"Status":d.device_status,"Type":_t(d.ci_type),"Location":_t(d.source_location),"Unreachable for":_t(d.device_silent_for)} for d in a.devices]);st.dataframe(frame,hide_index=True,width="stretch",height=360);st.download_button("Download SolarWinds device CSV",frame.to_csv(index=False).encode("utf-8-sig"),re.sub(r"\W+","_",a.location_name)+"_solarwinds.csv","text/csv")
    with act:
        st.write(f"**iEngage ticket:** {_t(item.get('ticket_id'),'Pending')}");st.write(f"**Email:** {_t(item.get('email_status'),'Not sent').title()}");description,prompt=build_ticket_description(a)
        with st.expander("Investigation guide for SolarWinds"):st.code(prompt,language=None,wrap_lines=True)
        with st.expander("Details sent to new iEngage tickets"):st.code(description,language=None,wrap_lines=True)
def render_infrastructure_agent_page(claims,access):
    del claims,access;_css();repo=InfrastructureStateRepository();status=scheduler_status()
    with st.container(key="content"):
        l,r=st.columns([5,1.4],vertical_alignment="center");l.markdown('<div class="ta-greet"><h1>Infrastructure Agent</h1></div>',unsafe_allow_html=True)
        if r.button("Run poll now",icon=":material/refresh:",width="stretch"):
            with st.spinner("Checking SolarWinds site health..."):process_infrastructure_sites(trigger_type="manual")
            st.rerun()
        _countdown(status);sites,hist=st.tabs(["Site health","Check history"])
        with sites:
            rows=[x for x in repo.list_incidents() if x.get("current_status")!="recovered"]
            m1,m2,m3,m4=st.columns(4);m1.metric("Sites needing attention",len(rows));m2.metric("Critical",sum(x.get("priority")=="P1" for x in rows));m3.metric("Warning",sum(x.get("priority")=="P2" for x in rows));m4.metric("With tickets",sum(bool(x.get("ticket_id")) for x in rows))
            table=pd.DataFrame([{"Site":_t(x.get("location_name"),""),"Priority":_t(x.get("priority"),""),"Health":_t(x.get("current_status"),"").title(),"Affected SolarWinds devices":len(_alert(x).devices),"Ticket":_t(x.get("ticket_id"),"Pending"),"Last checked":_t(x.get("last_detected_at"))} for x in rows]);event=st.dataframe(table,hide_index=True,width="stretch",height=365,on_select="rerun",selection_mode="single-row",key="infra_sites");selected=list(event.selection.rows) if hasattr(event,"selection") else [];requested=str(st.query_params.get("infrastructure_site","")).casefold();idx=next((i for i,x in enumerate(rows) if str(x.get("location_name") or "").casefold()==requested),-1);pick=int(selected[0]) if selected else (idx if idx>=0 else (0 if rows else -1));
            if 0<=pick<len(rows):_show(rows[pick])
        with hist:
            h=repo.list_poll_runs(100);st.dataframe(pd.DataFrame([{"Check":_t(x.get("trigger_type"),"").title(),"Result":_t(x.get("status"),"").replace("_"," ").title(),"Sites":int(x.get("alerts_found") or 0),"Tickets":int(x.get("tickets_created") or 0),"Emails":int(x.get("emails_sent") or 0),"Started":_t(x.get("started_at")),"Completed":_t(x.get("completed_at"))} for x in h]),hide_index=True,width="stretch",height=430)
