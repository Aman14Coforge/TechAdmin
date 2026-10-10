"""Apply final UI/approval/report distinctions to StreamlitApp/patch_agent_page.py."""
from pathlib import Path
import py_compile,shutil
P=Path('StreamlitApp/patch_agent_page.py')

def r(t,o,n,label):
    if n in t:print('[SKIP]',label);return t
    c=t.count(o)
    if c!=1:raise RuntimeError(f'{label}: expected 1, found {c}')
    print('[OK]',label);return t.replace(o,n,1)

def main():
    old=P.read_text(encoding='utf-8');shutil.copy2(P,P.with_name('patch_agent_page.py.before_final_ui'));t=old
    try:
        t=r(t,'with st.container(key="security_content"):', 'with st.container(key="content"):', 'use exact Identity content container')
        t=r(t,
'''        if details.button("View missing patches", type="primary", key=f"view_{key}"):\n            try:\n                result = SecurityReportService().device_report(selected)\n                item["content"]["active_report"] = result\n                item["content"]["active_report_mode"] = "details"''',
'''        if details.button("View missing patches", type="primary", key=f"view_{key}"):\n            try:\n                result = SecurityPatchQueryService().device_details(selected)\n                item["content"]["active_report"] = {\n                    "report_type": "device_details",\n                    **result,\n                }\n                item["content"]["active_report_mode"] = "details"''','details action uses database only')
        t=r(t,
'''    active_report = item["content"].get("active_report")\n    if isinstance(active_report, dict):\n        st.markdown("---")\n        st.caption(\n            "Current selected device: "\n            + str(item["content"].get("active_device") or "")\n        )\n        _report(active_report, f"active_{key}")''',
'''    active_report = item["content"].get("active_report")\n    if isinstance(active_report, dict):\n        st.markdown("---")\n        st.caption(\n            "Current selected device: "\n            + str(item["content"].get("active_device") or "")\n        )\n        if item["content"].get("active_report_mode") == "details":\n            for snapshot in active_report.get("history", []):\n                with st.expander(\n                    f"{snapshot['scan_date']} · "\n                    f"{snapshot['missing_patch_count']} missing patches"\n                ):\n                    frame = pd.DataFrame(snapshot.get("patches") or [])\n                    if frame.empty:\n                        st.info("No detailed missing-patch rows were stored for this snapshot.")\n                    else:\n                        st.dataframe(frame, hide_index=True, width="stretch")\n        else:\n            _report(active_report, f"active_{key}")''','distinct active renderers')
        # Insert AI/analytics rendering in _report after metrics block.
        needle='''    if report["report_type"] == "device":'''
        insert='''    analysis = report.get("ai_analysis") or {}\n    if report.get("report_type") == "device" and report.get("trend"):\n        trend_frame = pd.DataFrame(report["trend"]).set_index("Date")\n        st.markdown("#### Compliance trend")\n        st.line_chart(trend_frame[["Missing patches"]], height=260)\n    if report.get("severity_distribution"):\n        severity_frame = pd.DataFrame(\n            {"Severity": list(report["severity_distribution"]),\n             "Count": list(report["severity_distribution"].values())}\n        ).set_index("Severity")\n        st.markdown("#### Severity distribution")\n        st.bar_chart(severity_frame, height=240)\n    if analysis:\n        st.markdown("#### AI operational analysis")\n        st.write(analysis.get("executive_summary") or "")\n        if analysis.get("risk_assessment"):\n            st.info(analysis["risk_assessment"])\n        for heading, field in (("Notable findings", "notable_findings"),\n                               ("Checks to perform", "likely_operational_checks"),\n                               ("Prioritized actions", "prioritized_actions"),\n                               ("Data limitations", "data_limitations")):\n            values = analysis.get(field) or []\n            if values:\n                st.markdown(f"**{heading}**")\n                for value in values:\n                    st.write("• " + str(value))\n\n    if report["report_type"] == "device":'''
        t=r(t,needle,insert,'AI analytics report renderer')
        # Add dialog before render page function.
        marker='''def render_patch_agent_page(\n    claims: dict[str, Any],'''
        dialog='''@st.dialog("Approve patch-remediation ticket")\ndef approve_patch_ticket_dialog() -> None:\n    pending = st.session_state.get("security_pending")\n    if not isinstance(pending, dict):\n        st.info("No Security Agent operation is awaiting approval.")\n        return\n    parsed = pending.get("parsed", {})\n    st.warning(\n        f"Create a remediation ticket for {parsed.get('device_name') or 'the selected device'}?"\n    )\n    st.caption("The ticket service prevents duplicate tickets for the same active episode.")\n    left, right = st.columns(2)\n    if left.button("Approve and create ticket", type="primary", width="stretch"):\n        _approve()\n        st.rerun()\n    if right.button("Cancel", width="stretch"):\n        st.session_state.security_pending = None\n        st.rerun()\n\n\n'''+marker
        t=r(t,marker,dialog,'approval dialog')
        t=r(t,
'''            st.session_state.security_pending = {\n                "parsed": {\n                    "action": "patch_ticket",\n                    "device_name": selected,\n                    "reason": "Manual ticket requested from Security Agent table.",\n                },\n                "operator": _operator(claims, access),\n                "audit_id": item["content"].get("audit_id"),\n            }\n            st.rerun()''',
'''            st.session_state.security_pending = {\n                "parsed": {\n                    "action": "patch_ticket",\n                    "device_name": selected,\n                    "reason": "Manual ticket requested from Security Agent table.",\n                },\n                "operator": _operator(claims, access),\n                "audit_id": item["content"].get("audit_id"),\n            }\n            approve_patch_ticket_dialog()''','open approval modal')
        # Suppress below approval for ticket modal; leave for query approvals.
        P.write_text(t,encoding='utf-8');py_compile.compile(str(P),doraise=True)
    except Exception:
        P.write_text(old,encoding='utf-8');raise
    print('[DONE] final Security UI fixes applied')
if __name__=='__main__':main()
