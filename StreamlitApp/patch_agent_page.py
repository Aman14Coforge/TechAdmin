"""Security Agent workspace using MCP for reports and ticket operations."""
from __future__ import annotations
from datetime import date
from html import escape
from typing import Any
import pandas as pd
import re
import streamlit as st
from loguru import logger
from App.integration.iengage.client import IEngageClient
from App.mcp_client.patch_mcp_client import PatchMCPClient
from App.services.patch.analytics_service import PatchAnalyticsService
from App.services.patch.security_history import finish_security_query, start_security_query
from App.services.patch.semantic import PatchSemanticInterpreter
from App.services.patch.security_query_service import SecurityPatchQueryService

SORTS={"Missing patches: high to low":"missing_desc","Risk score: high to low":"risk_desc","Days open: high to low":"days_desc","Device name: A to Z":"name_asc"}

def _selected_device_names(frame:pd.DataFrame,indices:list[Any])->list[str]:
    names=[]
    for index in indices:
        if isinstance(index,int) and 0<=index<len(frame):
            name=str(frame.iloc[index].get("Device") or "").strip()
            if name and name not in names:names.append(name)
    return names

def _init():
    defaults={"security_selected":[],"security_selected_by_page":{},"security_details":None,"security_report":None,"security_job":None,"security_ticket_job":None,"security_ticket_results":None,"security_page":1,"security_search":"","security_sort":next(iter(SORTS)),"security_size":25,"security_date":date.today().isoformat(),"security_conversation":[],"security_browse_devices":False,"security_patch_search_results":None,"security_device_list":None}
    for k,v in defaults.items():st.session_state.setdefault(k,v)

def _reset():
    for k in ("security_details","security_report","security_job","security_ticket_job","security_ticket_results"):st.session_state[k]=None
    st.session_state.security_selected=[]
    st.session_state.security_selected_by_page={}
    st.session_state.security_conversation=[]
    st.session_state.security_patch_search_results=None
    st.session_state.security_device_list=None
    st.session_state.security_report_audit_id=None

def _unwrap(response:dict[str,Any])->dict[str,Any]:
    tool=response if isinstance(response,dict) and "success" in response else response.get("result") if isinstance(response,dict) else None
    if not isinstance(tool,dict):raise RuntimeError(response.get("message") if isinstance(response,dict) else "Invalid MCP response")
    if not tool.get("success") and not (isinstance(tool.get("result"), dict) and "tickets" in tool["result"]):raise RuntimeError(tool.get("error") or tool.get("message") or "MCP tool failed")
    result=tool.get("result")
    if not isinstance(result,dict):raise RuntimeError("MCP tool returned no structured result")
    return result

def _working(text):st.markdown('<div class="ta-asst-head"><div class="ta-icon-tile"><span class="material-symbols-rounded">security</span></div><div><div class="who">Security Agent</div><div class="ta-working"><i></i><i></i><i></i><span>'+escape(text)+'</span></div></div></div>',unsafe_allow_html=True)

def _audit_start(query:str,operator:str,action:str,target:str|None=None)->str|None:
    access=st.session_state.get("app_user_access") or {}
    return start_security_query(requester_id=access.get("user_id") or operator,requester_name=access.get("display_name") or operator,query_text=query,action=action,target=target,request_metadata={"snapshot":st.session_state.get("security_date")})

def _audit_finish(query_id:str|None,*,status:str,summary:dict[str,Any]|None=None,error:str|None=None)->None:
    finish_security_query(query_id,status=status,response_summary=summary,error_message=error)

def _reported_ticket_id(result:dict[str,Any])->str|None:
    ticket_id=result.get("ticket_id")
    if ticket_id:return str(ticket_id)
    message=result.get("message") or ""
    return IEngageClient._extract_ticket_id_from_message({"message":message})

def _latest_snapshot()->date:
    try:return SecurityPatchQueryService().latest_snapshot_date() or date.today()
    except Exception:return date.today()

def _queue_report(kind:str,devices:list[str],snapshot:date,query_id:str|None)->None:
    st.session_state.security_details=None
    st.session_state.security_patch_search_results=None
    st.session_state.security_report=None
    st.session_state.security_job={"type":kind,"devices":devices,"date":snapshot.isoformat(),"audit_id":query_id}

def _queue_device_list(snapshot:date,status:str,query_id:str|None,search:str="")->None:
    st.session_state.security_details=None;st.session_state.security_report=None
    st.session_state.security_job=None;st.session_state.security_patch_search_results=None
    st.session_state.security_selected_by_page={};st.session_state.security_selected=[]
    st.session_state.security_device_list={"date":snapshot.isoformat(),"status":status,"page":1,"audit_id":query_id,"search":search}

@st.dialog("Show non-compliant devices")
def _device_list_dialog(operator:str)->None:
    latest=_latest_snapshot()
    with st.form("security_list_devices_form",border=False):
        snapshot=st.date_input("Snapshot date",value=latest,max_value=date.today())
        status=st.selectbox("Devices to show",["Non-compliant","Resolved","All devices"])
        submit=st.form_submit_button("Show devices",type="primary",width="stretch")
    if submit:
        scope={"Non-compliant":"non_compliant","Resolved":"resolved","All devices":"all"}[status]
        query=f"Show {scope.replace('_',' ')} endpoints for {snapshot.isoformat()}"
        query_id=_audit_start(query,operator,"device_list",scope)
        st.session_state.security_conversation.append({"role":"user","content":query})
        _queue_device_list(snapshot,scope,query_id)
        st.rerun()

@st.dialog("Search by device")
def _device_search_dialog(operator:str)->None:
    with st.form("security_device_search_form",border=False):
        device=st.text_input("Device name",placeholder="Enter all or part of an endpoint name")
        snapshot=st.date_input("Snapshot date",value=_latest_snapshot(),max_value=date.today())
        status=st.selectbox("Include",["Non-compliant in snapshot","Resolved by this date","All devices in snapshot"])
        submit=st.form_submit_button("Search devices",type="primary",width="stretch")
    if submit:
        term=device.strip()
        if not term:st.error("Enter a device name or part of a name.");return
        query=f"Search devices matching {term} on {snapshot.isoformat()}"
        query_id=_audit_start(query,operator,"device_search",term)
        st.session_state.security_conversation.append({"role":"user","content":query})
        scope={"Non-compliant in snapshot":"non_compliant","Resolved by this date":"resolved","All devices in snapshot":"all"}[status]
        _queue_device_list(snapshot,scope,query_id,search=term)
        st.rerun()

@st.dialog("Device patch report")
def _device_report_dialog(operator:str)->None:
    with st.form("security_device_report_form",border=False):
        device=st.text_input("Device name",placeholder="Enter an endpoint hostname")
        snapshot=st.date_input("Report date",value=_latest_snapshot(),max_value=date.today())
        submit=st.form_submit_button("Generate report",type="primary",width="stretch")
    if submit:
        name=device.strip()
        if not name:st.error("Enter a device name.");return
        text=f"Generate a patch report for device {name} on {snapshot.isoformat()}"
        qid=_audit_start(text,operator,"device_report",name)
        st.session_state.security_conversation.append({"role":"user","content":text})
        _queue_report("device",[name],snapshot,qid)
        st.rerun()

@st.dialog("Search patch or KB")
def _patch_search_dialog(operator:str)->None:
    with st.form("security_patch_search_form",border=False):
        patch=st.text_input("Patch name or KB number",placeholder="For example, KB5002912")
        snapshot=st.date_input("Search snapshot date",value=_latest_snapshot(),max_value=date.today())
        submit=st.form_submit_button("Find affected devices",type="primary",width="stretch")
    if submit:
        value=patch.strip()
        if not value:st.error("Enter a patch name or KB number.");return
        query_id=_audit_start(f"Find devices missing {value} on {snapshot.isoformat()}",operator,"patch_search",value)
        try:
            result=SecurityPatchQueryService().list_devices(report_date=snapshot,patch_query=value,page=1,page_size=25)
            st.session_state.security_patch_search_results={"patch":value,"date":snapshot.isoformat(),"page":1,**result}
            st.session_state.security_details=None;st.session_state.security_report=None
            _audit_finish(query_id,status="completed",summary={"matches":result["total"],"snapshot":snapshot.isoformat()})
            st.session_state.security_conversation.extend([
                {"role":"user","content":f"Find devices missing {value} on {snapshot.isoformat()}"},
                {"role":"assistant","content":f"Found {result['total']} device(s) matching {value} in the {snapshot.isoformat()} snapshot."},
            ])
        except Exception as exc:
            _audit_finish(query_id,status="failed",error=f"{type(exc).__name__}: {exc}")
            st.error(f"Patch search failed: {type(exc).__name__}: {exc}")
            return
        st.rerun()

@st.dialog("Show devices")
def _fleet_report_dialog(operator:str)->None:
    latest=_latest_snapshot()
    st.caption("Choose which endpoint records to view from a stored Ivanti snapshot.")
    with st.form("security_fleet_report_form",border=False):
        snapshot=st.date_input("Report date",value=latest,max_value=date.today())
        status=st.selectbox("Endpoints",["Non-compliant","Resolved","All devices"])
        submit=st.form_submit_button("Show devices",type="primary",width="stretch")
    if submit:
        scope={"Non-compliant":"non_compliant","Resolved":"resolved","All devices":"all"}[status]
        query=f"Show {scope.replace('_',' ')} endpoints on {snapshot.isoformat()}"
        qid=_audit_start(query,operator,"device_list",f"{status} · {snapshot.isoformat()}")
        st.session_state.security_conversation.append({"role":"user","content":query})
        _queue_device_list(snapshot,scope,qid)
        st.rerun()

@st.dialog("Raise a remediation ticket")
def _raise_ticket_dialog(operator:str)->None:
    with st.form("security_ticket_request_form",border=False):
        device=st.text_input("Device name",placeholder="Enter the affected endpoint")
        st.caption("A confirmation step will appear before we send the remediation request to iEngage.")
        submit=st.form_submit_button("Continue to approval",type="primary",width="stretch")
    if submit:
        name=device.strip()
        if not name:st.error("Enter the affected device name.");return
        query=f"Raise a remediation ticket for {name}"
        query_id=_audit_start(query,operator,"patch_ticket",name)
        st.session_state.security_conversation.append({"role":"user","content":query})
        st.session_state.security_details=None;st.session_state.security_report=None;st.session_state.security_patch_search_results=None
        st.session_state.security_ticket_job={"devices":[name],"reason":"Patch remediation requested from Security Agent.","operator":operator,"audit_id":query_id}
        st.session_state.security_ticket_results=None
        st.rerun()

def _run_job():
    job=st.session_state.security_job
    if not job:return
    _working("Analyzing endpoint evidence and preparing the report…")
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
        _audit_finish(job.get("audit_id"),status="completed",summary={"report_type":result.get("report_type"),"evidence_summary":result.get("evidence",{}).get("summary",{}),"ai_available":ai.get("available")})
        if job.get("audit_id"):st.session_state.security_report_audit_id=job["audit_id"]
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
            _audit_finish(job.get("audit_id"),status="completed",summary={"report_type":result.get("report_type"),"evidence_summary":result.get("evidence",{}).get("summary",{}),"ai_available":ai.get("available"),"mcp_fallback":True})
            if job.get("audit_id"):
                st.session_state.security_report_audit_id=job["audit_id"]
        except Exception as fallback_error:
            logger.exception("PATCH_AI_REPORT_FALLBACK_FAILED | scope={}",job.get("type"))
            st.session_state.security_report={
                "error":f"MCP report failed ({type(mcp_error).__name__}: {mcp_error}); local report generation also failed ({type(fallback_error).__name__}: {fallback_error})."
            }
            st.session_state.security_conversation.append({"role":"assistant","content":st.session_state.security_report["error"]})
            _audit_finish(job.get("audit_id"),status="failed",error=st.session_state.security_report["error"])
    st.session_state.security_job=None;st.rerun()

def _render_report(report):
    if report.get("error"):st.error(report["error"]);return
    if st.session_state.get("security_report_audit_id"):
        st.caption(f"Security report · {report.get('report_type','patch').replace('_',' ')} · {report.get('evidence',{}).get('snapshot','')}")
    if report.get("mcp_warning"):st.warning(report["mcp_warning"])
    ev=report.get("evidence",{});summary=ev.get("summary",{})
    ai=report.get("ai") or {};analysis=ai.get("analysis") or {}
    if analysis.get("executive_summary"):
        st.markdown(f'<div class="ta-note" style="margin:12px 0 16px"><strong>Executive summary</strong><br>{escape(str(analysis["executive_summary"]))}</div>',unsafe_allow_html=True)
    metric_specs=[
        ("Snapshots" if report.get("report_type")=="device" else "Devices",summary.get("snapshots",summary.get("devices","—"))),
        ("Missing instances",summary.get("total_missing_instances",summary.get("current_missing","—"))),
        ("Ticket eligible",summary.get("ticket_eligible","—")),
        ("High-risk devices",summary.get("high_risk_devices","—")),
        ("Persistent ≥14 days",summary.get("persistent_14_day_devices","—")),
        ("Resolved devices",summary.get("resolved_devices","—")),
    ]
    visible=[(label,value) for label,value in metric_specs if value!="—"]
    columns=st.columns(max(1,len(visible)))
    for column,(label,value) in zip(columns,visible):column.metric(label,value)
    if ev.get("unavailable_devices"):st.warning("No evidence at this snapshot for: " + ", ".join(ev["unavailable_devices"]))
    if ev.get("data_errors"):st.warning(f"Evidence retrieval failed for {len(ev['data_errors'])} device(s).");st.dataframe(ev["data_errors"],hide_index=True)
    device_scope=report.get("report_type")=="device"
    tab_labels=["Overview","Patch exposure","AI analysis"] if device_scope else ["Overview","Priority devices","Patch exposure","AI analysis"]
    tabs=st.tabs(tab_labels)
    overview=tabs[0]
    if device_scope:
        exposure,analysis=tabs[1:]
        priority=None
    else:
        priority,exposure,analysis=tabs[1:]
    with overview:
        trend=pd.DataFrame(ev.get("trend") or [])
        if not trend.empty:
            date_key="date" if "date" in trend else "Date" if "Date" in trend else None
            missing_key="missing_instances" if "missing_instances" in trend else "missing_patches" if "missing_patches" in trend else "Missing patches" if "Missing patches" in trend else None
            if date_key and missing_key:
                chart=trend.set_index(date_key)[[missing_key]].rename(columns={missing_key:"Missing patch instances"})
                st.markdown("**Fleet exposure over the last 14 calendar days with stored scans**" if report.get("report_type")=="fleet" else "**Device compliance trend**")
                st.line_chart(chart,height=260)
            if "devices" in trend and report.get("report_type")=="fleet":
                st.line_chart(trend.set_index(date_key)[["devices"]],height=200)
        severity=ev.get("severity") or ev.get("latest_severity_counts") or {}
        if severity:
            st.markdown("**Ivanti severity codes (as returned by inventory)**")
            st.bar_chart(pd.DataFrame({"Severity code":severity.keys(),"Affected missing-patch instances":severity.values()}).set_index("Severity code"),height=240)
        operating_systems=ev.get("operating_systems") or []
        if operating_systems:
            st.markdown("**Affected endpoints by operating system**")
            os_frame=pd.DataFrame(operating_systems)
            if {"operating_system","devices"}.issubset(os_frame.columns):
                st.bar_chart(os_frame.set_index("operating_system")[["devices"]],height=240)
    if priority is not None:
        with priority:
            frame=pd.DataFrame(ev.get("priority_devices") or [])
            if frame.empty:st.info("Priority ranking is not available for this result.")
            else:st.dataframe(frame,hide_index=True,width="stretch")
    with exposure:
        rows=ev.get("top_missing_patches") or ev.get("persistent_patch_ids") or ev.get("persistent_patches") or []
        if rows and isinstance(rows[0],(list,tuple)):
            rows=[{"Patch":row[0],"Snapshots affected":row[1]} for row in rows]
        frame=pd.DataFrame(rows)
        if frame.empty:st.info("No patch exposure details were available for this snapshot.")
        else:st.dataframe(frame,hide_index=True,width="stretch")
        age_counts=ev.get("release_age") or ev.get("latest_release_age_counts") or {}
        if age_counts:
            st.markdown("**Release-age distribution (observed patch instances)**")
            st.bar_chart(pd.DataFrame(list(age_counts.items()),columns=["Age","Count"]).set_index("Age"))
        if device_scope:
            st.markdown("**Change since the previous snapshot**")
            changes=ev.get("summary",{})
            c1,c2,c3=st.columns(3)
            c1.metric("Newly missing",changes.get("new_since_previous_snapshot","—"))
            c2.metric("Cleared",changes.get("cleared_since_previous_snapshot","—"))
            c3.metric("Persistent",changes.get("persistent_across_all_snapshots","—"))
            for label,key in (("New patch IDs","new_patch_ids_since_previous"),("Cleared patch IDs","cleared_patch_ids_since_previous"),("Persistent patch IDs","persistent_patch_ids")):
                values=ev.get(key) or []
                if values:st.markdown(f"**{label}:** " + ", ".join(map(str,values[:30])))
            for snapshot in ev.get("history",[]):
                with st.expander(f"{snapshot.get('scan_date')} · {snapshot.get('missing_patch_count',0)} missing updates"):
                    patches=pd.DataFrame(snapshot.get("patches") or [])
                    if not patches.empty:st.dataframe(patches,hide_index=True,width="stretch")
    with analysis:
        ai=report.get("ai") or {}
        if not ai.get("available"):
            st.warning("AI analysis is temporarily unavailable. This evidence-based analysis is generated from stored Ivanti data.")
        data=ai.get("analysis") or {}
        st.markdown("### Executive summary")
        st.write(data.get("executive_summary") or "No analysis summary was returned.")
        for title,key in (("Compliance assessment","compliance"),("Risk assessment","risk"),("Fleet risk","fleet_risk"),("Risk concentration","risk_concentration"),("Ticket recommendation","ticket_recommendation")):
            value=data.get(key)
            if value:
                st.markdown(f"**{title}**")
                if isinstance(value,dict):
                    for field,detail in value.items():st.write(f"{field.replace('_',' ').title()}: {detail}")
                else:st.write(value)
        for title,key in (("Key findings","key_findings"),("Change since previous snapshot","change_since_previous_snapshot"),("Trend insights","trend_insights"),("Persistent exposure","persistent_exposure"),("Release-age insights","release_age_insights"),("Priority devices","priority_devices"),("Top patch exposures","top_patch_exposures"),("Cross-fleet patterns","cross_fleet_patterns"),("Operator checks","operator_checks"),("Hypotheses — require verification","hypotheses"),("Recommended actions","recommended_actions"),("Data limitations","data_limitations")):
            values=data.get(key) or []
            if isinstance(values,dict):values=[values]
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
        created=sum(bool(x.get("success") and _reported_ticket_id(x) and not x.get("dry_run")) for x in results)
        accepted=sum(bool(x.get("success") and not _reported_ticket_id(x) and not x.get("dry_run")) for x in results)
        previews=sum(bool(x.get("dry_run")) for x in results)
        failed=sum(not bool(x.get("success")) for x in results)
        if created and not failed and not accepted and not previews:
            st.success(f"{created} remediation ticket{'s' if created != 1 else ''} created successfully.")
        elif failed:
            st.warning(f"{created} ticket{'s' if created != 1 else ''} created; {failed} request{'s' if failed != 1 else ''} could not be completed.")
        elif previews:
            st.warning("The ticket request could not be submitted. Please contact the service desk.")
        elif accepted:
            st.success("iEngage accepted the remediation request. The confirmation message is shown below.")
        _audit_finish(job.get("audit_id") if job else None,status="completed" if failed==0 else "partial",summary={"created_with_id":created,"accepted_without_id":accepted,"dry_run":previews,"failed":failed,"devices":[{"device":item.get("device_name"),"status":item.get("status"),"ticket_id":_reported_ticket_id(item)} for item in results]})
        for result in results:
            with st.container(border=True):
                st.markdown(f"**{result.get('device_name','Device')}**")
                if result.get("dry_run"):
                    st.warning("The ticket request could not be submitted. Please contact the service desk.")
                elif result.get("success"):
                    status=result.get("status")
                    ticket_id=_reported_ticket_id(result)
                    if ticket_id:
                        st.success("Ticket created successfully.")
                        st.markdown(f"**Ticket ID:** {escape(ticket_id)}")
                    elif status in {"ACCEPTED","ALREADY_EXISTS"}:
                        st.success(str(result.get("message") or "The remediation request was accepted successfully."))
                    else:
                        st.success(result.get("message") or "Ticket operation completed.")
                else:
                    st.error(result.get("message") or "Ticket creation failed.")
                    if result.get("ticket_id"):st.caption(f"Returned reference: {result['ticket_id']}")
                if not result.get("success"):
                    st.caption(result.get("message") or "No changes were made.")
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
        _audit_finish(job.get("audit_id"),status="cancelled",summary={"cancelled":True})
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
    snapshot=explicit_date.group(1) if explicit_date else _latest_snapshot().isoformat()
    try:
        date.fromisoformat(snapshot)
    except ValueError:
        st.session_state.security_conversation.append({"role":"assistant","content":f"Invalid snapshot date: {snapshot}. Use YYYY-MM-DD."})
        return
    st.session_state.security_date=snapshot
    target=metadata.get("device_name") or metadata.get("patch_query") or ("Fleet" if action=="patch_report" else None)
    st.session_state.security_details=None
    st.session_state.security_report=None
    st.session_state.security_patch_search_results=None
    query_id=_audit_start(text,operator,action or "unknown",target)
    if action=="device_report" and metadata.get("device_name"):
        st.session_state.security_details=None;st.session_state.security_patch_search_results=None
        st.session_state.security_report=None
        st.session_state.security_job={"type":"device","devices":[metadata["device_name"]],"date":snapshot,"audit_id":query_id}
        return
    if action=="device_list":
        status=metadata.get("device_status") or ("resolved" if "resolved" in text.casefold() else "all" if any(word in text.casefold() for word in ("all devices","all endpoints","all status")) else "non_compliant")
        st.session_state.security_conversation.append({"role":"assistant","content":f"Showing {status.replace('_',' ')} devices from the {snapshot} snapshot."})
        _queue_device_list(date.fromisoformat(snapshot),status,query_id)
        return
    if action=="patch_report":
        st.session_state.security_details=None;st.session_state.security_patch_search_results=None
        st.session_state.security_report=None
        selected=list(st.session_state.security_selected)
        selected_scope=bool(selected and any(term in text.casefold() for term in ("selected", "these devices", "chosen devices")))
        st.session_state.security_job={"type":"selected" if selected_scope and len(selected)>1 else "device" if selected_scope else "fleet","devices":selected if selected_scope else [],"date":snapshot,"audit_id":query_id}
        return
    if action=="patch_search" and metadata.get("patch_query"):
        try:
            result=SecurityPatchQueryService().list_devices(report_date=date.fromisoformat(snapshot),patch_query=metadata["patch_query"],page=1,page_size=25)
            st.session_state.security_patch_search_results={"patch":metadata["patch_query"],"page":1,**result}
            st.session_state.security_details=None;st.session_state.security_report=None
            st.session_state.security_conversation.append({"role":"assistant","content":f"Found {result['total']} device(s) with confirmed missing matches for {metadata['patch_query']}. Results use the {snapshot} snapshot."})
            _audit_finish(query_id,status="completed",summary={"matches":result["total"],"snapshot":snapshot,"patch":metadata["patch_query"]})
        except Exception as exc:
            st.session_state.security_conversation.append({"role":"assistant","content":f"Patch search failed: {type(exc).__name__}: {exc}"})
            _audit_finish(query_id,status="failed",error=f"{type(exc).__name__}: {exc}")
        return
    if action=="patch_ticket":
        st.session_state.security_details=None;st.session_state.security_report=None;st.session_state.security_patch_search_results=None
        names=[metadata["device_name"]] if metadata.get("device_name") else list(st.session_state.security_selected)
        if not names:
            answer="Enter a device name in the ticket dialog, or choose endpoints in the device selector."
            st.session_state.security_conversation.append({"role":"assistant","content":answer})
            _audit_finish(query_id,status="needs_input",summary={"response":answer})
            return
        st.session_state.security_ticket_job={"devices":names,"reason":metadata.get("reason") or text,"operator":operator,"audit_id":query_id}
        st.session_state.security_ticket_results=None
        return
    if action=="eligible_ticket_batch":
        st.session_state.security_details=None;st.session_state.security_report=None;st.session_state.security_patch_search_results=None
        names=list(st.session_state.security_selected)
        if not names:
            answer="Choose endpoints in the device selector before requesting ticket approval."
            st.session_state.security_conversation.append({"role":"assistant","content":answer})
            _audit_finish(query_id,status="needs_input",summary={"response":answer})
            return
        st.session_state.security_ticket_job={"devices":names,"reason":metadata.get("reason") or text,"operator":operator,"audit_id":query_id}
        st.session_state.security_ticket_results=None
        return
    if action=="redirect_identity":
        st.session_state.security_redirect_query=text
        st.session_state.security_redirect_audit_id=query_id
        st.session_state.security_redirect_pending=True
        return
    if action=="unsupported_security":
        answer=metadata.get("explanation") or "That Security Agent operation is not available yet."
    elif action=="patch_scan":
        answer="Starting a live Ivanti scan from chat is not enabled. Use the administrator scan control or wait for the scheduled scan."
    else:
        answer=metadata.get("clarification_question") or "Try a device hostname, KB number, or ask for the non-compliant fleet report."
    st.session_state.security_conversation.append({"role":"assistant","content":answer})
    _audit_finish(query_id,status="completed",summary={"response":answer})


@st.dialog("Open Identity Agent?")
def _identity_redirect_dialog()->None:
    query=st.session_state.get("security_redirect_query","")
    st.write("This looks like an identity-management request. Continue in Identity Agent?")
    if query:st.caption(query)
    left,right=st.columns(2)
    if left.button("Open Identity Agent",type="primary",width="stretch",key="security_to_identity_confirm"):
        st.session_state.page="assistant"
        st.session_state.queued_query=query
        st.session_state.identity_security_redirect_bypass=True
        _audit_finish(st.session_state.get("security_redirect_audit_id"),status="redirected",summary={"destination":"Identity Agent"})
        st.session_state.security_redirect_pending=False
        st.rerun()
    if right.button("Stay here",width="stretch",key="security_to_identity_cancel"):
        _audit_finish(st.session_state.get("security_redirect_audit_id"),status="cancelled",summary={"redirect_cancelled":True})
        st.session_state.security_redirect_pending=False
        st.session_state.security_redirect_query=None
        st.rerun()


def _render_patch_search_page(operator:str)->None:
    current=st.session_state.security_patch_search_results
    if not current:return
    page=int(current.get("page",1));snapshot=date.fromisoformat(current["date"])
    result=SecurityPatchQueryService().list_devices(report_date=snapshot,patch_query=current["patch"],page=page,page_size=25)
    st.markdown(f"### Devices missing {escape(current['patch'])}")
    st.caption(f"{result['total']:,} matching endpoints · snapshot {snapshot.isoformat()}")
    frame=pd.DataFrame([{"Device":row["device_name"],"IP address":row["ip_address"],"Operating system":row["os_name"],"Missing patches":row["missing_patch_count"],"Days open":row["consecutive_days"],"Risk score":row["risk_score"]} for row in result["rows"]])
    if not frame.empty:
        key=f"security_kb_{re.sub(r'[^A-Za-z0-9]','_',current['patch'])}_{snapshot.isoformat()}_{page}"
        event=st.dataframe(frame,hide_index=True,width="stretch",height=360,on_select="rerun",selection_mode="multi-row",key=key)
        indices=list(event.selection.rows) if event and hasattr(event,"selection") else []
        st.session_state.security_selected=_selected_device_names(frame,indices)
        selected=st.session_state.security_selected
        left,mid,right=st.columns([1,2,1])
        if left.button("View patches",disabled=not selected,key=f"kb_view_{page}"):
            st.session_state.security_details=[SecurityPatchQueryService().device_details(name) for name in selected]
            st.session_state.security_patch_search_results=None;st.rerun()
        mid.markdown(f"<div class='ta-page-copy'>Page {result['page']} of {result['pages']} · {len(selected)} selected</div>",unsafe_allow_html=True)
        if right.button("Next",disabled=page>=result["pages"],key=f"kb_next_{page}"):
            st.session_state.security_patch_search_results={**current,"page":page+1};st.rerun()
        if page>1 and st.button("Previous",key=f"kb_prev_{page}"):
            st.session_state.security_patch_search_results={**current,"page":page-1};st.rerun()
        if selected:=st.session_state.security_selected:
            c1,c2=st.columns(2)
            if c1.button("Selected devices AI report",key=f"kb_report_{page}"):
                q=f"Generate AI report for endpoints missing {current['patch']}: {', '.join(selected)}"
                qid=_audit_start(q,operator,"selected_report",", ".join(selected[:5]))
                st.session_state.security_conversation.append({"role":"user","content":q})
                _queue_report("device" if len(selected)==1 else "selected",selected,snapshot,qid);st.rerun()
            if c2.button("Raise selected tickets",key=f"kb_ticket_{page}"):
                qid=_audit_start(f"Raise remediation tickets for {', '.join(selected)}",operator,"patch_ticket",", ".join(selected[:5]))
                st.session_state.security_ticket_job={"devices":selected,"reason":f"Missing patch {current['patch']} remediation.","operator":operator,"audit_id":qid}
                st.session_state.security_ticket_results=None;st.rerun()
    else:st.info("No matching endpoint has stored evidence for this snapshot.")

def _render_device_list(operator:str)->None:
    job=st.session_state.security_device_list
    if not job:return
    snapshot=date.fromisoformat(job["date"]);scope=job["status"]
    try:
        result=SecurityPatchQueryService().list_devices(
            report_date=snapshot,page=int(job["page"]),page_size=25,
            include_resolved=scope=="all",device_status=scope,search=job.get("search", ""),
        )
    except Exception as exc:
        st.error(f"Could not load endpoints: {type(exc).__name__}: {exc}")
        _audit_finish(job.get("audit_id"),status="failed",error=f"{type(exc).__name__}: {exc}")
        return
    if not job.get("audited"):
        _audit_finish(job.get("audit_id"),status="completed",summary={"devices":result["total"],"snapshot":snapshot.isoformat(),"status":scope})
        job["audited"]=True
    title={"non_compliant":"Non-compliant devices","resolved":"Resolved devices","all":"Devices in this snapshot"}.get(scope,"Devices")
    st.markdown(f"### {title}")
    st.caption(f"{result['total']:,} endpoint(s) · snapshot {snapshot.isoformat()}"+(f" · matching {job['search']}" if job.get("search") else ""))
    if scope=="all":st.caption("The snapshot list contains endpoints reported with missing patches on that date; use the Resolved filter to view archived resolved devices.")
    rows=[]
    for item in result["rows"]:
        ticket=item.get("ticket_reference")
        rows.append({
            "Device":item["device_name"],"IP address":item.get("ip_address"),
            "Operating system":item.get("os_name"),"Missing patches":item.get("missing_patch_count"),
            "Risk score":item.get("risk_score"),"Days affected":item.get("consecutive_days"),
            "Status":"Resolved" if item.get("active") is False else "Non-compliant",
            "Ticket":"✓" if ticket else "—","Ticket ID":ticket or "—",
        })
    frame=pd.DataFrame(rows)
    if frame.empty:
        st.info("No endpoints match this view and date.")
        return
    selection_key=f"security_list_{scope}_{snapshot.isoformat()}_{job.get('search','')}_{result['page']}"
    event=st.dataframe(frame,hide_index=True,width="stretch",height=390,on_select="rerun",selection_mode="multi-row",key=selection_key)
    indices=list(event.selection.rows) if event and hasattr(event,"selection") else []
    st.session_state.security_selected_by_page[result["page"]]=_selected_device_names(frame,indices)
    selected=list(dict.fromkeys(name for names in st.session_state.security_selected_by_page.values() for name in names))
    st.session_state.security_selected=selected
    previous,summary,next_page=st.columns([1,3,1])
    if previous.button("Previous",disabled=result["page"]<=1,key=f"device_list_prev_{scope}_{result['page']}"):
        job["page"]=result["page"]-1;st.rerun()
    summary.markdown(f"<div class='ta-page-copy'>Page {result['page']} of {result['pages']} · {len(selected)} selected</div>",unsafe_allow_html=True)
    if next_page.button("Next",disabled=result["page"]>=result["pages"],key=f"device_list_next_{scope}_{result['page']}"):
        job["page"]=result["page"]+1;st.rerun()
    if selected:
        a,b=st.columns(2)
        if a.button("AI report for selected",key=f"list_report_{scope}_{result['page']}"):
            query=f"AI report for selected endpoints: {', '.join(selected)}"
            qid=_audit_start(query,operator,"selected_report",", ".join(selected[:5]))
            st.session_state.security_conversation.append({"role":"user","content":query})
            _queue_report("device" if len(selected)==1 else "selected",selected,snapshot,qid);st.rerun()
        if b.button("Raise tickets for selected",key=f"list_ticket_{scope}_{result['page']}"):
            query=f"Raise remediation tickets for {', '.join(selected)}"
            qid=_audit_start(query,operator,"patch_ticket",", ".join(selected[:5]))
            st.session_state.security_ticket_job={"devices":selected,"reason":"Patch remediation requested from Security Agent.","operator":operator,"audit_id":qid}
            st.session_state.security_ticket_results=None;st.rerun()


def render_patch_agent_page(claims:dict[str,Any],access:dict[str,Any])->None:
    _init()
    operator=access.get("user_principal_name") or claims.get("preferred_username") or claims.get("name") or "operator"
    redirected_query=st.session_state.pop("patch_query_prefill",None)
    if redirected_query:_submit_security_query(redirected_query,operator)
    if st.session_state.get("security_redirect_pending"):_identity_redirect_dialog()

    with st.container(key="content"):
        head,action=st.columns([5,1.4],vertical_alignment="center")
        head.markdown('<div class="ta-greet"><h1>Security Agent</h1></div>',unsafe_allow_html=True)
        if action.button("New conversation",icon=":material/add_comment:",width="stretch",key="security_new_conversation"):
            _reset();st.session_state.security_selected_by_page={};st.session_state.security_browse_devices=False;st.rerun()

        if not st.session_state.security_conversation and not st.session_state.security_job:
            st.markdown('<div class="ta-hello"><h3>Quick actions</h3></div>',unsafe_allow_html=True)
            cards=st.columns(4)
            actions=(
                ("Show devices",":material/devices:",_fleet_report_dialog,(operator,)),
                ("Search by device",":material/search:",_device_search_dialog,(operator,)),
                ("Search patch or KB",":material/system_update:",_patch_search_dialog,(operator,)),
                ("Raise a ticket",":material/confirmation_number:",_raise_ticket_dialog,(operator,)),
            )
            for index,(label,icon,dialog,args) in enumerate(actions):
                if cards[index].button(label,key=f"security_quick_{label.casefold().replace(' ','_')}",icon=icon,width="stretch"):
                    dialog(*args)

        for turn in st.session_state.security_conversation:
            if turn.get("role")=="user":
                st.markdown(f'<div class="ta-user-bubble" style="margin:14px 0 14px auto;width:fit-content">{escape(turn["content"])}</div>',unsafe_allow_html=True)
            else:st.markdown(f'<div class="ta-note" style="margin:10px 0">{escape(turn["content"])}</div>',unsafe_allow_html=True)

        if st.session_state.security_patch_search_results:_render_patch_search_page(operator)
        if st.session_state.security_device_list:_render_device_list(operator)
        if st.session_state.get("security_details"):
            st.markdown("### Missing updates")
            for details in st.session_state.security_details:
                with st.expander(details["device_name"],expanded=True):
                    for snap in details.get("history",[]):
                        st.markdown(f"**{snap['scan_date']} · {snap['missing_patch_count']} missing**")
                        patches=pd.DataFrame(snap.get("patches") or [])
                        if not patches.empty:st.dataframe(patches,hide_index=True,width="stretch")
        if st.session_state.security_job:_run_job()
        if st.session_state.security_report:_render_report(st.session_state.security_report)

    query=st.chat_input("Ask about an endpoint, KB, scan snapshot, or remediation…",key="security_chat_input")
    if query:
        _submit_security_query(query,operator)
        st.rerun()
    if st.session_state.get("security_ticket_job"):_ticket_dialog()
