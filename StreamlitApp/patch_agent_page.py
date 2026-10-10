"""Security Agent workspace using MCP for reports and ticket operations."""
from __future__ import annotations
from datetime import date
from html import escape
from typing import Any
import pandas as pd
import re
import streamlit as st
from loguru import logger
from App.mcp_client.patch_mcp_client import PatchMCPClient
from App.services.patch.analytics_service import PatchAnalyticsService
from App.services.patch.semantic import PatchSemanticInterpreter
from App.services.patch.security_query_service import SecurityPatchQueryService

SORTS={"Missing patches: high to low":"missing_desc","Risk score: high to low":"risk_desc","Days open: high to low":"days_desc","Device name: A to Z":"name_asc"}

def _init():
    defaults={"security_selected":[],"security_details":None,"security_report":None,"security_job":None,"security_ticket_job":None,"security_ticket_results":None,"security_page":1,"security_search":"","security_sort":next(iter(SORTS)),"security_size":25,"security_date":date.today().isoformat(),"security_conversation":[],"security_browse_devices":False,"security_patch_search_results":None}
    for k,v in defaults.items():st.session_state.setdefault(k,v)

def _reset():
    for k in ("security_details","security_report","security_job","security_ticket_job","security_ticket_results"):st.session_state[k]=None
    st.session_state.security_selected=[]
    st.session_state.security_conversation=[]
    st.session_state.security_patch_search_results=None

def _unwrap(response:dict[str,Any])->dict[str,Any]:
    tool=response if isinstance(response,dict) and "success" in response else response.get("result") if isinstance(response,dict) else None
    if not isinstance(tool,dict):raise RuntimeError(response.get("message") if isinstance(response,dict) else "Invalid MCP response")
    if not tool.get("success") and not (isinstance(tool.get("result"), dict) and "tickets" in tool["result"]):raise RuntimeError(tool.get("error") or tool.get("message") or "MCP tool failed")
    result=tool.get("result")
    if not isinstance(result,dict):raise RuntimeError("MCP tool returned no structured result")
    return result

def _working(text):st.markdown('<div class="ta-asst-head"><div class="ta-icon-tile"><span class="material-symbols-rounded">security</span></div><div><div class="who">Security Agent</div><div class="ta-working"><i></i><i></i><i></i><span>'+escape(text)+'</span></div></div></div>',unsafe_allow_html=True)

def _run_job():
    job=st.session_state.security_job
    if not job:return
    _working("Analyzing patch evidence with Ollama through MCP...")
    day=date.fromisoformat(job["date"])
    try:
        client=PatchMCPClient()
        if job["type"]=="device":result=_unwrap(client.device_report(job["devices"][0],day))
        elif job["type"]=="selected":result=_unwrap(client.selected_report(job["devices"],day))
        else:result=_unwrap(client.fleet_report(day))
        st.session_state.security_report=result
        ai=result.get("ai") or {}
        summary=(ai.get("analysis") or {}).get("executive_summary") if ai.get("available") else None
        st.session_state.security_conversation.append({"role":"assistant","content":summary or "The report is ready. Open the AI analysis tab for the analysis and the other tabs for evidence."})
    except Exception as mcp_error:
        logger.exception("PATCH_AI_REPORT_MCP_FAILED | scope={} | devices={}",job.get("type"),job.get("devices"))
        try:
            analytics=PatchAnalyticsService()
            if job["type"]=="device":result=analytics.device_report(job["devices"][0],report_date=day)
            elif job["type"]=="selected":result=analytics.fleet_report(report_date=day,device_names=job["devices"])
            else:result=analytics.fleet_report(report_date=day)
            result["mcp_warning"]=f"MCP report service was unavailable; report generated through the local analytics fallback ({type(mcp_error).__name__}: {mcp_error})."
            st.session_state.security_report=result
            ai=result.get("ai") or {}
            summary=(ai.get("analysis") or {}).get("executive_summary") if ai.get("available") else None
            st.session_state.security_conversation.append({"role":"assistant","content":summary or "The report is ready using local analytics. Open the AI analysis tab for details."})
        except Exception as fallback_error:
            logger.exception("PATCH_AI_REPORT_FALLBACK_FAILED | scope={}",job.get("type"))
            st.session_state.security_report={
                "error":f"MCP report failed ({type(mcp_error).__name__}: {mcp_error}); local report generation also failed ({type(fallback_error).__name__}: {fallback_error})."
            }
            st.session_state.security_conversation.append({"role":"assistant","content":st.session_state.security_report["error"]})
    st.session_state.security_job=None;st.rerun()

def _render_report(report):
    if report.get("error"):st.error(report["error"]);return
    if report.get("mcp_warning"):st.warning(report["mcp_warning"])
    ev=report.get("evidence",{});summary=ev.get("summary",{});columns=st.columns(min(4,max(1,len(summary))))
    for i,(k,v) in enumerate(list(summary.items())[:4]):columns[i].metric(k.replace("_"," ").title(),v)
    if ev.get("unavailable_devices"):st.warning("No evidence at this snapshot for: " + ", ".join(ev["unavailable_devices"]))
    if ev.get("data_errors"):st.warning(f"Evidence retrieval failed for {len(ev['data_errors'])} device(s).");st.dataframe(ev["data_errors"],hide_index=True)
    overview,priority,exposure,analysis=st.tabs(["Overview","Priority devices","Patch exposure","AI analysis"])
    with overview:
        trend=pd.DataFrame(ev.get("trend") or [])
        if not trend.empty:st.line_chart(trend.set_index("Date")[["Missing patches"]],height=260)
        severity=ev.get("severity") or {}
        if severity:st.bar_chart(pd.DataFrame({"Severity":severity.keys(),"Count":severity.values()}).set_index("Severity"),height=240)
    with priority:
        frame=pd.DataFrame(ev.get("priority_devices") or [])
        if frame.empty:st.info("Priority ranking is available for selected-device and fleet reports.")
        else:st.dataframe(frame,hide_index=True,width="stretch")
    with exposure:
        rows=ev.get("top_missing_patches") or ev.get("persistent_patches") or []
        if rows and isinstance(rows[0],(list,tuple)):
            rows=[{"Patch":row[0],"Snapshots affected":row[1]} for row in rows]
        frame=pd.DataFrame(rows)
        if frame.empty:st.info("No aggregate patch exposure was available.")
        else:st.dataframe(frame,hide_index=True,width="stretch")
        if ev.get("release_age"):
            st.markdown("**Release-age distribution (observed patch instances)**")
            st.bar_chart(pd.DataFrame(list(ev["release_age"].items()),columns=["Age","Count"]).set_index("Age"))
    with analysis:
        ai=report.get("ai") or {}
        if not ai.get("available"):
            st.error("Ollama analysis failed. Deterministic analytics are still valid.");st.code(ai.get("error") or "Unknown Ollama error",language=None);st.caption(f"Model: {ai.get('model')} · Host: {ai.get('host')}")
        else:
            data=ai["analysis"];st.markdown("### Executive summary");st.write(data.get("executive_summary"))
            for title,key in (("Compliance assessment","compliance"),("Risk assessment","risk"),("Fleet risk","fleet_risk"),("Ticket recommendation","ticket_recommendation")):
                value=data.get(key)
                if value:
                    st.markdown(f"**{title}**")
                    if isinstance(value,dict):
                        for field,detail in value.items():st.write(f"{field.replace('_',' ').title()}: {detail}")
                    else:st.write(value)
            for title,key in (("Key findings","key_findings"),("Persistent exposure","persistent_exposure"),("Release-age insights","release_age_insights"),("Priority devices","priority_devices"),("Top patch exposures","top_patch_exposures"),("Cross-fleet patterns","cross_fleet_patterns"),("Operator checks","operator_checks"),("Hypotheses — require verification","hypotheses"),("Recommended actions","recommended_actions"),("Data limitations","data_limitations")):
                values=data.get(key) or []
                if values:
                    st.markdown(f"**{title}**")
                    for value in values:
                        if isinstance(value,dict):
                            with st.container(border=True):
                                for field,detail in value.items():
                                    st.markdown(f"**{field.replace('_',' ').title()}**")
                                    if isinstance(detail,list):
                                        for entry in detail:st.write("• " + str(entry))
                                    else:st.write(detail)
                        else:st.write("• " + str(value))

@st.dialog("Patch ticket approval",width="large")
def _ticket_dialog():
    job=st.session_state.security_ticket_job;results=st.session_state.security_ticket_results
    if results is not None:
        ok=sum(bool(x.get("success")) for x in results);failed=len(results)-ok
        (st.success if failed==0 else st.warning)(f"Ticket processing finished: {ok} succeeded, {failed} failed.")
        for result in results:
            with st.container(border=True):
                st.markdown(f"**{result.get('device_name','Device')}**")
                if result.get("dry_run"):
                    st.warning(result.get("message") or "Dry run completed; no ticket was sent to iEngage.")
                    st.caption("Preview reference: " + str(result.get("ticket_id") or "DRY-RUN"))
                elif result.get("success"):
                    status=result.get("status")
                    if result.get("ticket_id"):
                        st.success(result.get("message") or "Ticket created successfully.")
                        st.metric("iEngage ticket ID",result["ticket_id"])
                    elif status in {"ACCEPTED","ALREADY_EXISTS"}:
                        st.success(result.get("message") or "iEngage accepted the request without returning a ticket reference.")
                        st.info("No ticket ID was returned by iEngage. Check the iEngage request history before retrying.")
                    else:
                        st.success(result.get("message") or "Ticket operation completed.")
                else:
                    st.error(result.get("message") or "Ticket creation failed.")
                    if result.get("ticket_id"):st.caption(f"Returned reference: {result['ticket_id']}")
                st.caption(f"Status: {result.get('status','Unknown')} · Dry run: {result.get('dry_run',False)}")
        if st.button("Close",type="primary",width="stretch"):
            st.session_state.security_ticket_job=None;st.session_state.security_ticket_results=None;st.rerun()
        return
    if not job:st.info("No ticket operation is pending.");return
    st.warning(f"Create remediation tickets for {len(job['devices'])} selected device(s)?");st.write(", ".join(job["devices"]));left,right=st.columns(2)
    if left.button("Approve and create",type="primary",width="stretch",key="security_ticket_approve"):
        with st.spinner("Creating tickets in iEngage through MCP..."):
            try:
                payload=_unwrap(PatchMCPClient().raise_tickets(job["devices"],reason=job["reason"],requested_by=job["operator"]))
                results=payload.get("tickets") or []
                if not results:
                    raise RuntimeError("MCP completed without returning per-device ticket results.")
            except Exception as exc:results=[{"success":False,"status":"FAILED","ticket_id":None,"device_name":d,"dry_run":False,"message":f"{type(exc).__name__}: {exc}"} for d in job["devices"]]
        st.session_state.security_ticket_results=results
        st.rerun()
    if right.button("Cancel",width="stretch",key="security_ticket_cancel"):
        st.session_state.security_ticket_job=None
        st.session_state.security_ticket_results=None
        st.rerun()


def _submit_security_query(query:str,operator:str)->None:
    text=str(query or "").strip()
    if not text:return
    st.session_state.security_conversation.append({"role":"user","content":text})
    metadata=PatchSemanticInterpreter().interpret(text,selected_device=(st.session_state.security_selected[0] if len(st.session_state.security_selected)==1 else None))
    action=metadata.get("action")
    explicit_date=re.search(r"\b(20\d{2}-\d{2}-\d{2})\b",text)
    snapshot=explicit_date.group(1) if explicit_date else st.session_state.security_date
    try:
        date.fromisoformat(snapshot)
    except ValueError:
        st.session_state.security_conversation.append({"role":"assistant","content":f"Invalid snapshot date: {snapshot}. Use YYYY-MM-DD."})
        return
    if action=="device_report" and metadata.get("device_name"):
        st.session_state.security_details=None;st.session_state.security_patch_search_results=None
        st.session_state.security_report=None
        st.session_state.security_job={"type":"device","devices":[metadata["device_name"]],"date":snapshot}
        return
    if action=="patch_report":
        st.session_state.security_details=None;st.session_state.security_patch_search_results=None
        st.session_state.security_report=None
        selected=list(st.session_state.security_selected)
        selected_scope=bool(selected and any(term in text.casefold() for term in ("selected", "these devices", "chosen devices")))
        st.session_state.security_job={"type":"selected" if selected_scope and len(selected)>1 else "device" if selected_scope else "fleet","devices":selected if selected_scope else [],"date":snapshot}
        return
    if action=="patch_search" and metadata.get("patch_query"):
        try:
            result=SecurityPatchQueryService().list_devices(report_date=date.fromisoformat(snapshot),patch_query=metadata["patch_query"],page_size=100)
            st.session_state.security_patch_search_results={"patch":metadata["patch_query"],**result}
            st.session_state.security_details=None;st.session_state.security_report=None
            st.session_state.security_conversation.append({"role":"assistant","content":f"Found {result['total']} device(s) with confirmed missing matches for {metadata['patch_query']}. Results use the {snapshot} snapshot."})
        except Exception as exc:
            st.session_state.security_conversation.append({"role":"assistant","content":f"Patch search failed: {type(exc).__name__}: {exc}"})
        return
    if action=="patch_ticket":
        st.session_state.security_details=None;st.session_state.security_report=None;st.session_state.security_patch_search_results=None
        names=[metadata["device_name"]] if metadata.get("device_name") else list(st.session_state.security_selected)
        if not names:
            st.session_state.security_conversation.append({"role":"assistant","content":"Select one or more devices in Browse compliance devices, or include a specific device name in your request."})
            return
        st.session_state.security_ticket_job={"devices":names,"reason":metadata.get("reason") or text,"operator":operator}
        st.session_state.security_ticket_results=None
        return
    if action=="eligible_ticket_batch":
        st.session_state.security_details=None;st.session_state.security_report=None;st.session_state.security_patch_search_results=None
        names=list(st.session_state.security_selected)
        if not names:
            st.session_state.security_conversation.append({"role":"assistant","content":"Select the eligible devices in Browse compliance devices before requesting ticket approval."})
            return
        st.session_state.security_ticket_job={"devices":names,"reason":metadata.get("reason") or text,"operator":operator}
        st.session_state.security_ticket_results=None
        return
    if action=="redirect_identity":
        st.session_state.security_conversation.append({"role":"assistant","content":"This is an identity-management request. Opening Identity Agent."})
        st.session_state.security_redirect_query=text
        st.session_state.page="assistant"
        return
    if action=="unsupported_security":
        answer=metadata.get("explanation") or "That Security Agent operation is not available yet."
    elif action=="patch_scan":
        answer="Starting a live Ivanti scan from chat is not enabled. Use the administrator scan control or wait for the scheduled scan."
    else:
        answer=metadata.get("clarification_question") or "Try a device hostname, KB number, or ask for the non-compliant fleet report."
    st.session_state.security_conversation.append({"role":"assistant","content":answer})

def render_patch_agent_page(claims:dict[str,Any],access:dict[str,Any])->None:
    _init()
    operator=access.get("user_principal_name") or claims.get("preferred_username") or claims.get("name") or "operator"
    redirected_query=st.session_state.pop("patch_query_prefill",None)
    if redirected_query:
        _submit_security_query(redirected_query,operator)
    with st.container(key="content"):
        head,action=st.columns([5,1.4],vertical_alignment="center")
        head.markdown('<div class="ta-greet"><h1>Security Agent</h1><p>Ask about a device, a KB, or the latest non-compliant fleet. Actions that create tickets require approval.</p></div>',unsafe_allow_html=True)
        if action.button("New conversation",icon=":material/add_comment:",width="stretch",key="security_new_conversation"):
            _reset()
            st.session_state.security_browse_devices=False
            st.rerun()

        if not st.session_state.security_conversation and not st.session_state.security_job:
            st.markdown('<div class="ta-hello"><h3>How can I help with endpoint security?</h3><p>Choose a starting point or ask in your own words. Reports use stored Ivanti scan evidence.</p></div>',unsafe_allow_html=True)
            cards=st.columns(4)
            for col,label,query in zip(cards,("Device report","Search a KB","Fleet AI report","Raise tickets"),(
                "Generate a patch report for device DESKTOP-QGK3G0J",
                "Find devices missing KB5002912",
                "Generate an AI report for all non-compliant devices today",
                "Raise a ticket for the selected devices",
            )):
                if col.button(label,key=f"security_quick_{label.casefold().replace(' ','_')}",icon=":material/security:",width="stretch"):
                    _submit_security_query(query,operator)
                    st.rerun()
        selected_date=date.fromisoformat(st.session_state.security_date)
        chosen_date=st.date_input("Evidence snapshot date",value=selected_date,max_value=date.today(),key="security_snapshot_date")
        st.session_state.security_date=chosen_date.isoformat()

        with st.expander("Browse compliance devices",expanded=st.session_state.security_browse_devices):
            with st.form("security_filters",border=False):
                a,b,c,d=st.columns([2,1.2,1.5,.8])
                search=a.text_input("Search",value=st.session_state.security_search,placeholder="Device, discovery ID or IP")
                snapshot=b.date_input("Snapshot date",date.fromisoformat(st.session_state.security_date),max_value=date.today())
                sort=c.selectbox("Sort",list(SORTS),index=list(SORTS).index(st.session_state.security_sort))
                size=d.selectbox("Rows",[10,25,50,100],index=[10,25,50,100].index(st.session_state.security_size))
                apply=st.form_submit_button("Load compliance",type="primary")
            if apply:
                st.session_state.security_search=search.strip();st.session_state.security_date=snapshot.isoformat()
                st.session_state.security_sort=sort;st.session_state.security_size=size;st.session_state.security_page=1
                st.session_state.security_details=None;st.session_state.security_report=None
                st.session_state.security_patch_search_results=None
                st.rerun()
            data=SecurityPatchQueryService().list_devices(report_date=date.fromisoformat(st.session_state.security_date),search=st.session_state.security_search,sort=SORTS[st.session_state.security_sort],page=st.session_state.security_page,page_size=st.session_state.security_size,include_resolved=False)
            frame=pd.DataFrame([{"Device":r["device_name"],"IP address":r["ip_address"],"Operating system":r["os_name"],"Missing patches":r["missing_patch_count"],"Risk score":r["risk_score"],"Days open":r["consecutive_days"],"Ticket eligible":r["ticket_eligible"]} for r in data["rows"]])
            if not frame.empty:
                event=st.dataframe(frame,hide_index=True,width="stretch",height=360,on_select="rerun",selection_mode="multi-row",key="security_devices")
                indices=list(event.selection.rows) if event and hasattr(event,"selection") else []
                st.session_state.security_selected=[str(frame.iloc[i]["Device"]) for i in indices]
            else:
                st.info("No non-compliant devices match this date and filter.")
            selected=st.session_state.security_selected
            st.caption(f"Selected devices: {len(selected)} of {data['total']}")
            a,b,c=st.columns(3)
            if a.button("View selected patches",disabled=not selected,width="stretch",key="security_view_patches"):
                details=[]
                for device in selected:
                    try:details.append(SecurityPatchQueryService().device_details(device))
                    except Exception as exc:st.warning(f"Could not load {device}: {exc}")
                st.session_state.security_details=details;st.session_state.security_report=None;st.session_state.security_patch_search_results=None;st.rerun()
            if b.button("Selected AI report",disabled=not selected,width="stretch",key="security_selected_report"):
                st.session_state.security_details=None;st.session_state.security_patch_search_results=None
                st.session_state.security_report=None
                st.session_state.security_job={"type":"device" if len(selected)==1 else "selected","devices":selected,"date":st.session_state.security_date}
                st.rerun()
            if c.button("Raise tickets",disabled=not selected,width="stretch",key="security_raise_tickets"):
                st.session_state.security_details=None;st.session_state.security_report=None;st.session_state.security_patch_search_results=None
                st.session_state.security_ticket_job={"devices":selected,"reason":"Patch remediation requested from Security Agent.","operator":operator}
                st.session_state.security_ticket_results=None
                st.rerun()

        for turn in st.session_state.security_conversation:
            if turn.get("role")=="user":
                st.markdown(f'<div class="ta-user-bubble" style="margin:14px 0 14px auto;width:fit-content">{escape(turn["content"])}</div>',unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="ta-note" style="margin:10px 0">{escape(turn["content"])}</div>',unsafe_allow_html=True)

        if st.session_state.get("security_patch_search_results"):
            result=st.session_state.security_patch_search_results
            st.markdown(f"### Devices missing {escape(result['patch'])}")
            st.caption(f"Snapshot {result['date']} · {result['total']} matching device(s)")
            st.dataframe(pd.DataFrame([{"Device":r["device_name"],"IP address":r["ip_address"],"Missing patches":r["missing_patch_count"],"Days open":r["consecutive_days"],"Risk score":r["risk_score"]} for r in result["rows"]]),hide_index=True,width="stretch")

        if st.session_state.get("security_details"):
            st.markdown("### Selected-device missing patches")
            for details in st.session_state.security_details:
                with st.expander(details["device_name"]):
                    for snap in details.get("history",[]):
                        st.markdown(f"**{snap['scan_date']} · {snap['missing_patch_count']} missing**")
                        patches=pd.DataFrame(snap.get("patches") or [])
                        if not patches.empty:st.dataframe(patches,hide_index=True,width="stretch")

        if st.session_state.security_job:_run_job()
        if st.session_state.security_report:_render_report(st.session_state.security_report)

    query=st.chat_input("Ask about a device, KB, non-compliant devices, or request a ticket…",key="security_chat_input")
    if query:
        _submit_security_query(query,operator)
        st.rerun()
    if st.session_state.get("security_ticket_job"):
        _ticket_dialog()
