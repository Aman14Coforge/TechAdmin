"""Patch the V3 Security Agent page for single active report and fixed composer."""
from __future__ import annotations
import py_compile, shutil
from pathlib import Path
P=Path("StreamlitApp/patch_agent_page.py")

def rep(t,o,n,label):
    if n in t:print('[SKIP]',label);return t
    c=t.count(o)
    if c!=1:raise RuntimeError(f'{label}: expected 1 match, found {c}')
    print('[OK]',label);return t.replace(o,n,1)

def main():
    original=P.read_text(encoding='utf-8');shutil.copy2(P,P.with_name('patch_agent_page.py.before_v4'));t=original
    try:
        t=rep(t,
'''def _init():\n    for k,v in {"security_conversation":[],"security_pending":None,"security_selected_device":None}.items():st.session_state.setdefault(k,v)''',
'''def _init():\n    defaults = {\n        "security_conversation": [],\n        "security_pending": None,\n        "security_selected_device": None,\n    }\n    for key, value in defaults.items():\n        st.session_state.setdefault(key, value)\n\ndef _new_security_conversation():\n    st.session_state.security_conversation = []\n    st.session_state.security_pending = None\n    st.session_state.security_selected_device = None\n    st.session_state.pop("patch_query_prefill", None)''','state and reset')
        t=rep(t,
'''        if a.button("View missing patches",type="primary",key=f"view_{key}"):\n            try:r=SecurityReportService().device_report(selected);_append("assistant",{"type":"report","message":f"Comprehensive device report for {selected}.","report":r});st.rerun()\n            except Exception as exc:st.error(str(exc))\n        if b.button("Generate device report",key=f"report_{key}"):\n            try:r=SecurityReportService().device_report(selected);_append("assistant",{"type":"report","message":f"Downloadable IT operations report for {selected}.","report":r});st.rerun()\n            except Exception as exc:st.error(str(exc))''',
'''        if a.button("View missing patches", type="primary", key=f"view_{key}"):\n            try:\n                r = SecurityReportService().device_report(selected)\n                item["content"]["active_report"] = r\n                item["content"]["active_report_mode"] = "details"\n                item["content"]["active_device"] = selected\n                st.rerun()\n            except Exception as exc:\n                st.error(str(exc))\n        if b.button("Generate device report", key=f"report_{key}"):\n            try:\n                r = SecurityReportService().device_report(selected)\n                item["content"]["active_report"] = r\n                item["content"]["active_report_mode"] = "download"\n                item["content"]["active_device"] = selected\n                st.rerun()\n            except Exception as exc:\n                st.error(str(exc))''','replace report instead of append')
        t=rep(t,
'''        if c.button("Raise patch ticket",key=f"ticket_{key}"):\n            st.session_state.security_pending={"parsed":{"action":"patch_ticket","device_name":selected,"reason":"Manual ticket requested from Security Agent table."},"operator":_operator(claims,access),"audit_id":item["content"].get("audit_id")};st.rerun()''',
'''        if c.button("Raise patch ticket", key=f"ticket_{key}"):\n            st.session_state.security_pending = {\n                "parsed": {\n                    "action": "patch_ticket",\n                    "device_name": selected,\n                    "reason": "Manual ticket requested from Security Agent table.",\n                },\n                "operator": _operator(claims, access),\n                "audit_id": item["content"].get("audit_id"),\n            }\n            st.rerun()\n\n    active_report = item["content"].get("active_report")\n    if isinstance(active_report, dict):\n        st.markdown("---")\n        st.caption(\n            "Current selected device: "\n            + str(item["content"].get("active_device") or "")\n        )\n        _report(active_report, f"active_{key}")''','render current report inline')
        t=rep(t,
'''def render_patch_agent_page(claims:dict[str,Any],access:dict[str,Any])->None:\n    _init();st.markdown('<div class="ta-greet"><h1>Security Agent</h1><p>Ask about endpoint security, Ivanti patch compliance, device history, patch impact, or remediation tickets.</p></div>',unsafe_allow_html=True)''',
'''def render_patch_agent_page(claims:dict[str,Any],access:dict[str,Any])->None:\n    _init()\n    st.markdown(\n        """<style>\n        .st-key-security_composer_spacer {height: 88px;}\n        div[data-testid="stChatInput"] {\n            position: fixed;\n            bottom: 16px;\n            left: max(286px, calc((100vw - 1000px) / 2 + 260px));\n            right: max(24px, calc((100vw - 1000px) / 2));\n            z-index: 999;\n            background: white;\n            border-radius: 16px;\n            box-shadow: 0 8px 28px rgba(16, 24, 40, .16);\n        }\n        @media (max-width: 850px) {\n            div[data-testid="stChatInput"] {left: 16px; right: 16px;}\n        }\n        </style>""",\n        unsafe_allow_html=True,\n    )\n    head, action = st.columns([5, 1.45], vertical_alignment="center")\n    with head:\n        st.markdown('<div class="ta-greet"><h1>Security Agent</h1><p>Ask about endpoint security, Ivanti patch compliance, device history, patch impact, or remediation tickets.</p></div>',unsafe_allow_html=True)\n    with action:\n        if st.button(\n            "New conversation",\n            icon=":material/add_comment:",\n            width="stretch",\n            key="security_new_conversation",\n        ):\n            _new_security_conversation()\n            st.rerun()''','header new conversation fixed composer')
        t=rep(t,
'''    prefill=st.session_state.pop("patch_query_prefill",None);query=st.chat_input("Ask the Security Agent about Ivanti or endpoint security…") or prefill\n    if query:_execute(query,claims,access);st.rerun()''',
'''    st.container(key="security_composer_spacer").write("")\n    prefill = st.session_state.pop("patch_query_prefill", None)\n    query = st.chat_input(\n        "Ask the Security Agent about Ivanti or endpoint security…",\n        key="security_chat_input",\n    ) or prefill\n    if query:\n        _execute(query, claims, access)\n        st.rerun()''','composer')
        P.write_text(t,encoding='utf-8');py_compile.compile(str(P),doraise=True)
    except Exception:
        P.write_text(original,encoding='utf-8');raise
    print('[DONE] Security Agent V4 patch applied')
if __name__=='__main__':main()
