"""Safely integrate the Security Agent page into StreamlitApp/app.py."""
from __future__ import annotations
import py_compile
import shutil
from datetime import datetime
from pathlib import Path

APP = Path("StreamlitApp/app.py")
THEME = Path("StreamlitApp/ui_theme.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[SKIP] {label}")
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact match, found {count}")
    print(f"[OK] {label}")
    return text.replace(old, new, 1)


def main() -> None:
    if not APP.exists():
        raise FileNotFoundError(APP)

    original = APP.read_text(encoding="utf-8")
    backup = APP.with_name(
        "app.py.before_security_agent_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    shutil.copy2(APP, backup)
    text = original

    try:
        # The production scheduler is a separate process, not a Streamlit import.
        text = text.replace("import patch_scheduler_bootstrap  # noqa: F401\n", "")

        text = replace_once(
            text,
            "from investigation_report_ui import render_investigation_report  # noqa: E402\n",
            "from investigation_report_ui import render_investigation_report  # noqa: E402\n"
            "from patch_agent_page import render_patch_agent_page  # noqa: E402\n"
            "from App.services.patch.semantic import PatchSemanticInterpreter  # noqa: E402\n",
            "Security Agent imports",
        )

        text = replace_once(
            text,
            '    ("assistant", "Identity Agent", ":material/smart_toy:"),\n'
            '    ("history", "Your History", ":material/history:"),',
            '    ("assistant", "Identity Agent", ":material/smart_toy:"),\n'
            '    ("security", "Security Agent", ":material/security:"),\n'
            '    ("history", "Your History", ":material/history:"),',
            "page registration",
        )

        old_sidebar = '''                html_block(\n                    '<div class="ta-agent-soon"><span class="material-symbols-rounded">shield</span>'\n                    '<span class="nm">Security Agent</span><span class="pill">Soon</span></div>'\n                    '<div class="ta-agent-soon"><span class="material-symbols-rounded">lan</span>'\n                    '<span class="nm">Network Agent</span><span class="pill">Soon</span></div>'\n                )'''
        new_sidebar = '''                with st.container(key="agent_security_active" if page == "security" else "agent_security"):\n                    if st.button("Security Agent", key="navbtn_security", icon=":material/security:", width="stretch"):\n                        st.session_state.page = "security"\n                        st.rerun()\n                html_block(\n                    '<div class="ta-agent-soon"><span class="material-symbols-rounded">lan</span>'\n                    '<span class="nm">Network Agent</span><span class="pill">Soon</span></div>'\n                )'''
        text = replace_once(text, old_sidebar, new_sidebar, "sidebar Security Agent")

        text = replace_once(
            text,
            "def handle_input(query: str) -> None:\n"
            "    pending = st.session_state.pending_confirmation",
            "def handle_input(query: str) -> None:\n"
            "    # Redirect patch requests instead of executing them in Identity Agent.\n"
            "    if (\n"
            "        st.session_state.get(\"page\") == \"assistant\"\n"
            "        and PatchSemanticInterpreter().matches(query)\n"
            "    ):\n"
            "        st.session_state.security_redirect_query = query\n"
            "        st.session_state.page = \"security\"\n"
            "        st.rerun()\n\n"
            "    pending = st.session_state.pending_confirmation",
            "cross-agent redirect",
        )

        text = replace_once(
            text,
            '    if page == "history":\n'
            '        page_history(history)\n'
            '    else:\n'
            '        page_assistant(claims)',
            '    if page == "history":\n'
            '        page_history(history)\n'
            '    elif page == "security":\n'
            '        with st.container(key="content"):\n'
            '            redirected = st.session_state.pop("security_redirect_query", None)\n'
            '            if redirected:\n'
            '                st.info(\n'
            '                    "This request belongs to the Security Agent. "\n'
            '                    "TechAdmin moved it here without executing it as an identity operation."\n'
            '                )\n'
            '                st.session_state.patch_query_prefill = redirected\n'
            '            render_patch_agent_page(claims, access_info())\n'
            '    else:\n'
            '        page_assistant(claims)',
            "main Security Agent routing",
        )

        APP.write_text(text, encoding="utf-8")
        py_compile.compile(str(APP), doraise=True)

    except Exception:
        APP.write_text(original, encoding="utf-8")
        print("[RESTORED] app.py because validation failed")
        raise

    if THEME.exists():
        theme = THEME.read_text(encoding="utf-8")
        marker = "/* SECURITY_AGENT_NAV */"
        if marker not in theme:
            addition = '''\n\n# Security Agent navigation styles added by integration script.\nSECURITY_AGENT_CSS = r"""\n<style>\n/* SECURITY_AGENT_NAV */\n[class*="st-key-agent_security"] .stButton > button {\n  height:32px; min-height:32px; padding:0 10px; font-size:13px; border-radius:8px;\n}\n.st-key-agent_security_active .stButton > button {\n  background:transparent !important; color:#fff !important;\n}\n.st-key-agent_security_active .stButton > button [data-testid="stIconMaterial"] {\n  color:#F27A62 !important;\n}\n.st-key-agent_security_active .stButton > button div[data-testid="stMarkdownContainer"] p::after {\n  content:""; width:6px; height:6px; border-radius:50%; background:#22A35A;\n}\n</style>\n"""\n\n_original_inject_app_css = inject_app_css\ndef inject_app_css() -> None:\n    _original_inject_app_css()\n    st.markdown(SECURITY_AGENT_CSS, unsafe_allow_html=True)\n'''
            THEME.write_text(theme + addition, encoding="utf-8")
            py_compile.compile(str(THEME), doraise=True)
            print("[OK] Security Agent CSS")

    print(f"[BACKUP] {backup}")
    print("[DONE] app.py and ui_theme.py compiled successfully")


if __name__ == "__main__":
    main()
