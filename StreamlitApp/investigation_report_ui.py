"""Visual renderer for CrowdStrike Windows authentication investigation reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

KERBEROS_REASONS = {
    "0x6": ("Unknown account", "The account was not found in the Kerberos database."),
    "0x12": ("Credentials revoked", "The account may be disabled, expired, locked, or outside permitted logon hours."),
    "0x17": ("Password expired", "The account password has expired."),
    "0x18": (
        "Incorrect or stale password",
        "Kerberos rejected the password. Common causes include a mistyped password or an old password stored in a service, scheduled task, mapped drive, mobile client, or cached credential.",
    ),
    "0x25": ("Clock skew", "The client and domain controller clocks may differ beyond the permitted Kerberos tolerance."),
}

NTSTATUS_REASONS = {
    "0xc0000064": ("Unknown username", "The supplied account does not exist."),
    "0xc000006a": ("Incorrect password", "The account exists, but the supplied password was incorrect."),
    "0xc000006d": ("Invalid credentials", "The username or authentication information was invalid."),
    "0xc000006e": ("Account restriction", "An account restriction prevented the logon."),
    "0xc000006f": ("Logon-hours restriction", "The account was used outside permitted logon hours."),
    "0xc0000070": ("Workstation restriction", "The account cannot sign in from the source workstation."),
    "0xc0000071": ("Password expired", "The account password has expired."),
    "0xc0000072": ("Account disabled", "The account is disabled."),
    "0xc0000193": ("Account expired", "The account has expired."),
    "0xc0000224": ("Password change required", "The user must change the password before signing in."),
    "0xc0000234": ("Account locked", "The account is locked out."),
}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "::", "0.0.0.0", "Unknown", "None", "null"}:
        return None
    return text


def _format_time(value: Any) -> str:
    if value is None:
        return "Not available"
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            parsed = datetime.fromtimestamp(number, tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y, %I:%M:%S %p")
    except (ValueError, TypeError, OSError):
        return str(value)


def _event_reason(event: dict[str, Any]) -> tuple[str, str]:
    try:
        event_id = int(event.get("event_id", 0) or 0)
    except (TypeError, ValueError):
        event_id = 0

    codes = []
    for key in ("failure_code", "sub_status", "status"):
        value = _clean(event.get(key))
        if value:
            codes.append(value.casefold())

    if event_id == 4740:
        return (
            "Account lockout confirmed",
            "Windows recorded Event 4740, confirming that repeated authentication failures crossed the configured lockout threshold.",
        )

    if event_id == 4771:
        for code in codes:
            if code in KERBEROS_REASONS:
                return KERBEROS_REASONS[code]
        return (
            "Kerberos pre-authentication failed",
            _clean(event.get("failure_reason"))
            or "The domain controller rejected Kerberos pre-authentication. Review the failure code and source system.",
        )

    if event_id == 4625:
        for code in codes:
            if code in NTSTATUS_REASONS:
                return NTSTATUS_REASONS[code]
        return (
            "Windows logon failed",
            _clean(event.get("failure_reason"))
            or "Windows rejected the logon attempt. Review Status, SubStatus, source, and logon type.",
        )

    return "Authentication event", "Review the available event evidence."


def _deterministic_analysis(report: dict[str, Any]) -> dict[str, Any]:
    events = report.get("timeline") if isinstance(report.get("timeline"), list) else []
    counts = report.get("event_counts") if isinstance(report.get("event_counts"), dict) else {}
    failed = int(counts.get("4625", 0) or 0)
    lockouts = int(counts.get("4740", 0) or 0)
    kerberos = int(counts.get("4771", 0) or 0)

    reason_counts: dict[str, int] = {}
    descriptions: dict[str, str] = {}
    for event in events:
        title, description = _event_reason(event)
        reason_counts[title] = reason_counts.get(title, 0) + 1
        descriptions[title] = description

    primary = max(reason_counts, key=reason_counts.get) if reason_counts else "No matching evidence"
    sequence: list[str] = []
    if kerberos:
        sequence.append(f"{kerberos} Kerberos pre-authentication failure(s) were recorded.")
    if failed:
        sequence.append(f"{failed} Windows failed-logon event(s) were recorded.")
    if lockouts:
        sequence.append(f"{lockouts} account-lockout event(s) confirmed that the threshold was reached.")
    if not sequence:
        sequence.append("No matching Windows Security authentication events were returned.")

    if lockouts and kerberos:
        conclusion = (
            "Repeated Kerberos authentication failures were followed by confirmed account lockout events. "
            "The strongest supported explanation is that one or more recurring sources continued submitting invalid, expired, revoked, or stale credentials until the Active Directory lockout threshold was reached."
        )
    elif kerberos:
        conclusion = (
            "Kerberos authentication failures were detected, but no Event 4740 lockout evidence was returned in the selected period. "
            "The most likely issue is an invalid or stale credential on a user device, service, scheduled task, mapped drive, or application."
        )
    elif failed:
        conclusion = (
            "Windows rejected one or more logon attempts. The Status and SubStatus values shown in the evidence timeline identify whether the cause was an incorrect password, unknown account, account restriction, expiry, disablement, or lockout."
        )
    else:
        conclusion = "The selected period did not return enough matching Windows Security evidence to determine a cause."

    evidence = [
        f"Event 4625 count: {failed}",
        f"Event 4771 count: {kerberos}",
        f"Event 4740 count: {lockouts}",
    ]
    for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:3]:
        evidence.append(f"{reason}: {count} event(s)")

    return {
        "executive_summary": conclusion,
        "primary_cause": primary,
        "primary_cause_detail": descriptions.get(primary, "Evidence is insufficient for a more specific conclusion."),
        "confidence": "High" if lockouts and events else "Medium" if events else "Low",
        "event_sequence": sequence,
        "evidence": evidence,
        "limitations": (
            "Windows Security evidence can show authentication outcomes and source systems, but it may not identify the exact application, service, scheduled task, or person that submitted the credential."
        ),
        "analysis_source": "Validated automated evidence analysis",
    }


def render_investigation_report(report: dict[str, Any]) -> None:
    """Render a non-technical investigation report plus detailed evidence."""

    events = report.get("timeline") if isinstance(report.get("timeline"), list) else []
    counts = report.get("event_counts") if isinstance(report.get("event_counts"), dict) else {}
    analysis = report.get("analysis") if isinstance(report.get("analysis"), dict) else None
    if not analysis:
        analysis = _deterministic_analysis(report)

    st.markdown("## Authentication investigation report")
    st.caption(
        f"Target: {report.get('target_user', 'Unknown')}  |  "
        f"Window: {report.get('time_window', 'Unknown')}  |  "
        f"Generated: {_format_time(report.get('generated_at_utc'))}"
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Failed logons", int(counts.get("4625", 0) or 0))
    col2.metric("Account lockouts", int(counts.get("4740", 0) or 0))
    col3.metric("Kerberos failures", int(counts.get("4771", 0) or 0))
    col4.metric("Total evidence", int(report.get("total_matching_events", len(events)) or 0))

    with st.container(border=True):
        st.markdown("### Investigation conclusion")
        st.write(analysis.get("executive_summary") or report.get("assessment") or "No conclusion is available.")
        left, right = st.columns(2)
        left.metric("Analysis confidence", analysis.get("confidence") or "Not available")
        right.metric("Lockout confirmed", "Yes" if report.get("lockout_detected") else "No")
        if analysis.get("primary_cause"):
            st.markdown("**Primary likely cause**")
            st.write(analysis["primary_cause"])
            if analysis.get("primary_cause_detail"):
                st.caption(analysis["primary_cause_detail"])

    sequence = analysis.get("event_sequence")
    if isinstance(sequence, list) and sequence:
        with st.container(border=True):
            st.markdown("### What happened")
            for index, item in enumerate(sequence, start=1):
                st.write(f"{index}. {item}")

    evidence = analysis.get("evidence")
    if isinstance(evidence, list) and evidence:
        with st.container(border=True):
            st.markdown("### Evidence supporting the conclusion")
            for item in evidence:
                st.write(f"• {item}")

    source_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for event in events:
        source = (
            _clean(event.get("workstation"))
            or _clean(event.get("source_ip"))
            or _clean(event.get("computer"))
            or "Not available"
        )
        source_counts[source] = source_counts.get(source, 0) + 1
        reason, _ = _event_reason(event)
        rows.append(
            {
                "Time": _format_time(event.get("timestamp")),
                "Event": f"{event.get('event_id')} | {event.get('event_name')}",
                "Reason": reason,
                "Source device": _clean(event.get("workstation")) or _clean(event.get("computer")) or "Not available",
                "Source IP": _clean(event.get("source_ip")) or "Not available",
                "Failure code": _clean(event.get("failure_code")) or _clean(event.get("sub_status")) or _clean(event.get("status")) or "Not available",
                "Service": _clean(event.get("service_name")) or "Not available",
            }
        )

    if source_counts:
        top_source = max(source_counts, key=source_counts.get)
        with st.container(border=True):
            st.markdown("### Where the attempts came from")
            st.write(
                f"The most frequent source was **{top_source}**, associated with "
                f"**{source_counts[top_source]}** matching event(s)."
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Source": source, "Events": count}
                        for source, count in sorted(
                            source_counts.items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

    if rows:
        st.markdown("### Evidence timeline")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No evidence timeline is available for this investigation.")

    with st.expander("Recommended actions", expanded=True):
        st.write("1. Identify and validate the source devices or IP addresses shown above.")
        if int(counts.get("4771", 0) or 0):
            st.write("2. Check services, scheduled tasks, mapped drives, mobile clients, and cached credentials for an outdated password.")
        if int(counts.get("4740", 0) or 0):
            st.write("3. Stop repeated authentication attempts before unlocking the account, otherwise the account may immediately lock again.")
        st.write("4. Validate the activity with the account owner and escalate unrecognized or unusually frequent sources to security operations.")

    if analysis.get("limitations"):
        st.caption(f"Limitation: {analysis['limitations']}")

    if rows:
        st.download_button(
            "Download evidence as CSV",
            data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8"),
            file_name=f"authentication-investigation-{report.get('target_user', 'user')}.csv",
            mime="text/csv",
        )
