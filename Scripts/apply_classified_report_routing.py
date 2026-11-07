"""Route classified fleet report queries to the classified report service."""
from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "StreamlitApp" / "patch_agent_page.py"


def main() -> None:
    original = PAGE.read_text(encoding="utf-8")
    backup = PAGE.with_name(
        f"patch_agent_page.py.before_classified_report_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(PAGE, backup)

    try:
        text = original
        import_line = (
            "from App.services.patch.classified_report_service import (\n"
            "    ClassifiedComplianceReportService,\n"
            "    category_from_report_query,\n"
            ")\n"
        )
        marker = "from App.services.patch.analytics_service import PatchAnalyticsService\n"
        if import_line not in text:
            if text.count(marker) != 1:
                raise RuntimeError("Could not locate analytics import marker")
            text = text.replace(marker, marker + import_line, 1)

        # Insert before PatchSemanticInterpreter so explicit classified report
        # language cannot be misrouted to the old raw fleet report.
        target = '''    st.session_state.security_conversation.append({"role": "user", "content": text})
    metadata = PatchSemanticInterpreter().interpret(
'''
        replacement = '''    st.session_state.security_conversation.append({"role": "user", "content": text})

    classified_report_category = category_from_report_query(text)
    if classified_report_category:
        explicit_report_date = re.search(r"\\b(20\\d{2}-\\d{2}-\\d{2})\\b", text)
        report_snapshot = (
            date.fromisoformat(explicit_report_date.group(1))
            if explicit_report_date
            else _latest_snapshot()
        )
        query_id = _audit_start(
            text,
            operator,
            "classified_report",
            classified_report_category,
        )
        try:
            report = ClassifiedComplianceReportService().build(
                report_date=report_snapshot,
                category=classified_report_category,
            )
            st.session_state.security_details = None
            st.session_state.security_patch_search_results = None
            st.session_state.security_device_list = None
            st.session_state.classified_compliance_request = None
            st.session_state.security_report = report
            st.session_state.security_report_audit_id = query_id
            summary = report.get("evidence", {}).get("summary", {})
            st.session_state.security_conversation.append(
                {
                    "role": "assistant",
                    "content": (
                        "The classified compliance report is ready for "
                        f"{report_snapshot.isoformat()} with "
                        f"{int(summary.get('devices') or 0):,} endpoint(s)."
                    ),
                }
            )
            _audit_finish(
                query_id,
                status="completed",
                summary={
                    "report_type": "classified_fleet",
                    "category": classified_report_category,
                    "snapshot": report_snapshot.isoformat(),
                    "devices": int(summary.get("devices") or 0),
                },
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            st.session_state.security_conversation.append(
                {"role": "assistant", "content": f"Report generation failed: {error}"}
            )
            _audit_finish(query_id, status="failed", error=error)
        return

    metadata = PatchSemanticInterpreter().interpret(
'''
        if target not in text:
            if replacement not in text:
                raise RuntimeError("Could not locate semantic interpreter marker")
        else:
            text = text.replace(target, replacement, 1)

        PAGE.write_text(text, encoding="utf-8")
        py_compile.compile(str(PAGE), doraise=True)
    except Exception:
        PAGE.write_text(original, encoding="utf-8")
        raise

    print(f"[BACKUP] {backup}")
    print("[DONE] Classified report queries now use the sidecar population")


if __name__ == "__main__":
    main()
