"""Idempotently integrate Infrastructure Agent navigation and startup into app.py."""
from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "StreamlitApp" / "app.py"
BACKUP = APP.with_name(f"app.py.before_infrastructure_{datetime.now():%Y%m%d_%H%M%S}")


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
    original = APP.read_text(encoding="utf-8")
    shutil.copy2(APP, BACKUP)
    text = original
    try:
        text = replace_once(
            text,
            "    from patch_agent_page import (\n        render_patch_agent_page,\n    )  # noqa: E402\n",
            "    from patch_agent_page import (\n        render_patch_agent_page,\n    )  # noqa: E402\n    from infrastructure_agent_page import render_infrastructure_agent_page  # noqa: E402\n",
            "live page import",
        )
        text = replace_once(
            text,
            "    render_patch_agent_page = None\n    PatchSemanticInterpreter = None\n",
            "    render_patch_agent_page = None\n    render_infrastructure_agent_page = None\n    PatchSemanticInterpreter = None\n",
            "preview placeholder",
        )
        text = replace_once(
            text,
            '    (\n        "security",\n        "Compliance Agent",\n        ":material/security:",\n    ),\n',
            '    (\n        "security",\n        "Compliance Agent",\n        ":material/security:",\n    ),\n    (\n        "infrastructure",\n        "Infrastructure Agent",\n        ":material/lan:",\n    ),\n',
            "page registration",
        )
        compliance_button = '''                # Future Network Agent placeholder\n                html_block(\n                    '&lt;div class="ta-agent-soon"&gt;'\n                    '&lt;span '\n                    'class="material-symbols-rounded"&gt;'\n                    'lan'\n                    '&lt;/span&gt;'\n                    '&lt;span class="nm"&gt;'\n                    'Network Agent'\n                    '&lt;/span&gt;'\n                    '&lt;span class="pill"&gt;'\n                    'Soon'\n                    '&lt;/span&gt;'\n                    '&lt;/div&gt;'\n                )\n'''
        infrastructure_button = '''                with st.container(\n                    key=(\n                        "agent_infrastructure_active"\n                        if page == "infrastructure"\n                        else "agent_infrastructure"\n                    )\n                ):\n                    if st.button(\n                        "Infrastructure Agent",\n                        key="navbtn_infrastructure",\n                        icon=":material/lan:",\n                        width="stretch",\n                    ):\n                        st.session_state.page = "infrastructure"\n                        st.session_state.pending_run = None\n                        st.session_state.pending_confirmation = None\n                        st.session_state.security_pending = None\n                        st.rerun()\n'''
        text = replace_once(text, compliance_button, infrastructure_button, "sidebar navigation")
        startup_old = '''            from App.services.patch.bootstrap import start_patch_background_services\n\n            start_patch_background_services()\n'''
        startup_new = '''            from App.services.patch.bootstrap import start_patch_background_services\n            from App.services.infrastructure.bootstrap import start_infrastructure_background_services\n\n            start_patch_background_services()\n            start_infrastructure_background_services()\n'''
        text = replace_once(text, startup_old, startup_new, "background bootstrap")
        marker = '''    if current_page == "security":\n'''
        route = '''    if current_page == "infrastructure":\n        if PREVIEW_MODE or render_infrastructure_agent_page is None:\n            with st.container(key="content"):\n                st.info("Infrastructure Agent requires live ITOM, PostgreSQL, SMTP, and iEngage configuration.")\n            return\n        render_infrastructure_agent_page(claims, access_info())\n        return\n\n'''
        text = replace_once(text, marker, route + marker, "page routing")
        APP.write_text(text, encoding="utf-8")
        py_compile.compile(str(APP), doraise=True)
    except Exception:
        APP.write_text(original, encoding="utf-8")
        print("[RESTORED] app.py because integration validation failed")
        raise
    print(f"[BACKUP] {BACKUP}")
    print("[DONE] Infrastructure Agent integrated and app.py compiled")


if __name__ == "__main__":
    main()
