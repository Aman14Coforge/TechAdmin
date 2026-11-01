"""Update only StreamlitApp/app.py for Infrastructure Agent integration.

Designed for the exact app.py structure supplied by the user. The script:
- creates a timestamped backup;
- changes only Infrastructure Agent import, page registration, sidebar entry,
  scheduler startup, and route;
- compiles app.py;
- restores app.py automatically on any failure;
- is idempotent and will not add duplicate blocks.
"""
from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / "StreamlitApp" / "app.py").exists():
    # Script may be stored in D:\TechAdminDev\scripts.
    ROOT = ROOT.parent

APP = ROOT / "StreamlitApp" / "app.py"
INFRA_PAGE = ROOT / "StreamlitApp" / "infrastructure_agent_page.py"


def add_after(text: str, marker: str, addition: str, label: str) -> str:
    if addition in text:
        print(f"[SKIP] {label}")
        return text
    if text.count(marker) != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {text.count(marker)}")
    print(f"[OK] {label}")
    return text.replace(marker, marker + addition, 1)


def add_before(text: str, marker: str, addition: str, label: str) -> str:
    if addition in text:
        print(f"[SKIP] {label}")
        return text
    if text.count(marker) != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {text.count(marker)}")
    print(f"[OK] {label}")
    return text.replace(marker, addition + marker, 1)


def main() -> None:
    if not APP.exists():
        raise FileNotFoundError(f"app.py not found: {APP}")
    if not INFRA_PAGE.exists():
        raise FileNotFoundError(
            f"Infrastructure page not found: {INFRA_PAGE}. Copy the Infrastructure Agent package first."
        )

    original = APP.read_text(encoding="utf-8")
    backup = APP.with_name(f"app.py.before_infrastructure_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(APP, backup)
    text = original

    try:
        # 1. Preview mode placeholder.
        text = add_after(
            text,
            "    render_patch_agent_page = None\n",
            "    render_infrastructure_agent_page = None\n",
            "preview placeholder",
        )

        # 2. Live page import. The marker is the exact block from supplied app.py.
        live_import_marker = (
            "    from patch_agent_page import (\n"
            "        render_patch_agent_page,\n"
            "    )  # noqa: E402\n"
        )
        text = add_after(
            text,
            live_import_marker,
            "    from infrastructure_agent_page import render_infrastructure_agent_page  # noqa: E402\n",
            "live page import",
        )

        # 3. Register Infrastructure Agent as a valid page.
        compliance_page = (
            "    (\n"
            "        \"security\",\n"
            "        \"Compliance Agent\",\n"
            "        \":material/security:\",\n"
            "    ),\n"
        )
        infrastructure_page = (
            "    (\n"
            "        \"infrastructure\",\n"
            "        \"Infrastructure Agent\",\n"
            "        \":material/lan:\",\n"
            "    ),\n"
        )
        text = add_after(text, compliance_page, infrastructure_page, "page registration")

        # 4. Add sidebar button before the existing Network Agent placeholder.
        sidebar_marker = "                # Future Network Agent placeholder\n"
        sidebar_block = '''                # Infrastructure Agent navigation
                with st.container(
                    key=(
                        "agent_infrastructure_active"
                        if page == "infrastructure"
                        else "agent_infrastructure"
                    )
                ):
                    if st.button(
                        "Infrastructure Agent",
                        key="navbtn_infrastructure",
                        icon=":material/lan:",
                        width="stretch",
                    ):
                        st.session_state.page = "infrastructure"

                        # Do not carry Identity or Compliance operations into
                        # Infrastructure Agent.
                        st.session_state.pending_run = None
                        st.session_state.pending_confirmation = None
                        st.session_state.security_pending = None

                        st.rerun()

'''
        text = add_before(text, sidebar_marker, sidebar_block, "sidebar navigation")

        # 5. Start the isolated background service alongside patch services.
        patch_import = (
            "            from App.services.patch.bootstrap import "
            "start_patch_background_services\n"
        )
        infra_import = (
            "            from App.services.infrastructure.bootstrap import "
            "start_infrastructure_background_services\n"
        )
        text = add_after(text, patch_import, infra_import, "infrastructure bootstrap import")

        patch_start = "            start_patch_background_services()\n"
        infra_start = "            start_infrastructure_background_services()\n"
        text = add_after(text, patch_start, infra_start, "infrastructure bootstrap call")

        # 6. Route the new page immediately before the existing Compliance route.
        security_route_marker = '    if current_page == "security":\n'
        infrastructure_route = '''    if current_page == "infrastructure":
        if PREVIEW_MODE or render_infrastructure_agent_page is None:
            with st.container(key="content"):
                st.info(
                    "Infrastructure Agent requires live ITOM, PostgreSQL, "
                    "SMTP, and iEngage configuration."
                )
            return

        render_infrastructure_agent_page(
            claims,
            access_info(),
        )
        return

'''
        text = add_before(text, security_route_marker, infrastructure_route, "page routing")

        APP.write_text(text, encoding="utf-8")
        py_compile.compile(str(INFRA_PAGE), doraise=True)
        py_compile.compile(str(APP), doraise=True)

    except Exception:
        APP.write_text(original, encoding="utf-8")
        print("[RESTORED] app.py because validation failed")
        raise

    print(f"[BACKUP] {backup}")
    print("[DONE] app.py updated and compiled successfully")


if __name__ == "__main__":
    main()
