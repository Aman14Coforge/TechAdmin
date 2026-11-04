"""Idempotently integrate rich classified reports into patch_agent_page.py.

This version does not depend on one exact semantic-routing text block. It uses
function boundaries and smaller stable anchors, validates every modification,
creates a timestamped backup, and restores the original file on any failure.
"""
from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "StreamlitApp" / "patch_agent_page.py"

IMPORT_BLOCK = """from App.services.patch.classified_report_service import (
    ClassifiedComplianceReportService,
    category_from_report_query,
)
"""

QUEUE_BLOCK = '''
    classified_report_category = category_from_report_query(text)
    if classified_report_category:
        explicit_report_date = re.search(
            r"\\b(20\\d{2}-\\d{2}-\\d{2})\\b",
            text,
        )
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
        st.session_state.security_details = None
        st.session_state.security_patch_search_results = None
        st.session_state.security_device_list = None
        st.session_state.classified_compliance_request = None
        st.session_state.security_report = None
        st.session_state.security_job = {
            "type": "classified",
            "category": classified_report_category,
            "devices": [],
            "date": report_snapshot.isoformat(),
            "audit_id": query_id,
        }
        return

'''

RUN_BLOCK = '''
        if job.get("type") == "classified":
            result = ClassifiedComplianceReportService().build(
                report_date=day,
                category=job["category"],
            )
            st.session_state.security_report = result
            ai = result.get("ai") or {}
            analysis = ai.get("analysis") or {}
            summary_text = analysis.get("executive_summary")
            st.session_state.security_conversation.append(
                {
                    "role": "assistant",
                    "content": summary_text
                    or "The classified compliance report is ready.",
                }
            )
            _audit_finish(
                job.get("audit_id"),
                status="completed",
                summary={
                    "report_type": result.get("report_type"),
                    "classification_category": result.get(
                        "classification_category"
                    ),
                    "evidence_summary": result.get("evidence", {}).get(
                        "summary", {}
                    ),
                    "ai_available": ai.get("available"),
                },
            )
            if job.get("audit_id"):
                st.session_state.security_report_audit_id = job["audit_id"]
            st.session_state.security_job = None
            st.rerun()
            return

'''


def _function_bounds(text: str, function_name: str) -> tuple[int, int]:
    match = re.search(
        rf"(?m)^def {re.escape(function_name)}\([^\n]*\).*?:\n",
        text,
    )
    if not match:
        raise RuntimeError(f"Could not locate function: {function_name}")
    next_function = re.search(r"(?m)^def [A-Za-z_]\w*\(", text[match.end():])
    end = match.end() + next_function.start() if next_function else len(text)
    return match.start(), end


def _replace_function(text: str, function_name: str, body: str) -> str:
    start, end = _function_bounds(text, function_name)
    return text[:start] + body + text[end:]


def _remove_previous_immediate_branch(submit_function: str) -> str:
    # Remove the earlier synchronous report branch added by the prior script.
    pattern = re.compile(
        r"\n    classified_report_category = category_from_report_query\(text\)\n"
        r"    if classified_report_category:\n"
        r".*?"
        r"        return\n(?=\n    metadata = PatchSemanticInterpreter\(\)\.interpret\()",
        re.DOTALL,
    )
    return pattern.sub("\n", submit_function, count=1)


def _insert_queue(submit_function: str) -> str:
    if '"type": "classified"' in submit_function:
        return submit_function

    submit_function = _remove_previous_immediate_branch(submit_function)

    # Insert immediately after the user turn is appended. This anchor has
    # remained stable across the supplied patch_agent_page versions.
    append_pattern = re.compile(
        r"(\n    st\.session_state\.security_conversation\.append\(\s*"
        r"\{\s*\"role\"\s*:\s*\"user\"\s*,\s*"
        r"\"content\"\s*:\s*text\s*\}\s*\)\s*\n)",
        re.DOTALL,
    )
    match = append_pattern.search(submit_function)
    if not match:
        raise RuntimeError(
            "Could not locate the user-message append inside "
            "_submit_security_query()."
        )
    return (
        submit_function[: match.end()]
        + QUEUE_BLOCK
        + submit_function[match.end():]
    )


def _insert_runner(run_function: str) -> str:
    if 'job.get("type") == "classified"' in run_function:
        return run_function

    # Insert after the existing `try:` and before MCP/local analytics routing.
    try_match = re.search(r"(?m)^    try:\s*$", run_function)
    if not try_match:
        raise RuntimeError("Could not locate the try block inside _run_job().")
    insertion_point = try_match.end()
    return run_function[:insertion_point] + "\n" + RUN_BLOCK + run_function[insertion_point:]


def _install_import(text: str) -> str:
    # Remove any earlier version to make the operation repeatable.
    text = re.sub(
        r"from App\.services\.patch\.classified_report_service import \([^)]*\)\n",
        "",
        text,
        flags=re.DOTALL,
    )
    marker = "from App.services.patch.analytics_service import PatchAnalyticsService\n"
    if text.count(marker) != 1:
        raise RuntimeError(
            "Could not locate the PatchAnalyticsService import exactly once."
        )
    return text.replace(marker, marker + IMPORT_BLOCK, 1)


def _validate(text: str) -> None:
    required = (
        "ClassifiedComplianceReportService",
        "category_from_report_query",
        '"type": "classified"',
        'job.get("type") == "classified"',
    )
    missing = [value for value in required if value not in text]
    if missing:
        raise RuntimeError(
            "Integration validation failed. Missing: " + ", ".join(missing)
        )
    if text.count('job.get("type") == "classified"') != 1:
        raise RuntimeError("Classified report runner exists more than once.")


def main() -> None:
    if not PAGE.exists():
        raise FileNotFoundError(f"File not found: {PAGE}")

    original = PAGE.read_text(encoding="utf-8")
    backup = PAGE.with_name(
        "patch_agent_page.py.before_rich_classified_report_"
        f"{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(PAGE, backup)

    try:
        updated = _install_import(original)

        submit_start, submit_end = _function_bounds(
            updated,
            "_submit_security_query",
        )
        submit_function = updated[submit_start:submit_end]
        updated = _replace_function(
            updated,
            "_submit_security_query",
            _insert_queue(submit_function),
        )

        run_start, run_end = _function_bounds(updated, "_run_job")
        run_function = updated[run_start:run_end]
        updated = _replace_function(
            updated,
            "_run_job",
            _insert_runner(run_function),
        )

        _validate(updated)
        PAGE.write_text(updated, encoding="utf-8")
        py_compile.compile(str(PAGE), doraise=True)
    except Exception:
        PAGE.write_text(original, encoding="utf-8")
        print(f"[RESTORED] {PAGE}")
        raise

    print(f"[BACKUP] {backup}")
    print("[DONE] Rich classified report integration installed")


if __name__ == "__main__":
    main()
