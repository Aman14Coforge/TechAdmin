"""Visual renderer for CrowdStrike Windows authentication investigation reports."""
from __future__ import annotations

import ipaddress
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

EXCLUDED_LAST_OCTETS = {252, 253}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "::", "0.0.0.0", "Unknown", "None", "null", "Not available"}:
        return None
    return text


def _normalize_source_ip(value: Any) -> str | None:
    """Normalize IPv4-mapped IPv6 and suppress infrastructure .252/.253 addresses."""
    text = _clean(value)
    if not text:
        return None
    if text.casefold().startswith("::ffff:"):
        text = text[7:]
    try:
        parsed = ipaddress.ip_address(text)
    except ValueError:
        return text
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        parsed = parsed.ipv4_mapped
    if isinstance(parsed, ipaddress.IPv4Address) and int(str(parsed).split(".")[-1]) in EXCLUDED_LAST_OCTETS:
        return None
    return str(parsed)


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            number = float(value)
            while number > 10_000_000_000:
                number /= 1000.0
            return datetime.fromtimestamp(number, tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _format_time(value: Any) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "Not available" if value is None else str(value)
    return parsed.astimezone().strftime("%d %b %Y, %I:%M:%S %p")


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
            _clean(event.get("failure_reason")) or "The domain controller rejected Kerberos pre-authentication.",
        )
    if event_id == 4625:
        for code in codes:
            if code in NTSTATUS_REASONS:
                return NTSTATUS_REASONS[code]
        return (
            "Windows logon failed",
            _clean(event.get("failure_reason")) or "Windows rejected the logon attempt.",
        )
    return "Authentication event", "Review the available event evidence."


def _deterministic_analysis(report: dict[str, Any]) -> dict[str, Any]:
    events = report.get("timeline") if isinstance(report.get("timeline"), list) else []
    counts = report.get("event_counts") if isinstance(report.get("event_counts"), dict) else {}
    failed = int(counts.get("4625", 0) or 0)
    lockouts = int(counts.get("4740", 0) or 0)
    kerberos = int(counts.get("4771", 0) or 0)
    source_rows = report.get("source_statistics") if isinstance(report.get("source_statistics"), list) else []

    reason_counts: dict[str, int] = {}
    descriptions: dict[str, str] = {}
    for event in events:
        title, description = _event_reason(event)
        reason_counts[title] = reason_counts.get(title, 0) + 1
        descriptions[title] = description

    primary = max(reason_counts, key=reason_counts.get) if reason_counts else "No matching evidence"
    sequence = []
    if kerberos:
        sequence.append(f"{kerberos} Kerberos pre-authentication failure(s) were recorded.")
    if failed:
        sequence.append(f"{failed} Windows failed-logon event(s) were recorded.")
    if lockouts:
        sequence.append(f"{lockouts} account-lockout event(s) confirmed that the threshold was reached.")
    if not sequence:
        sequence.append("No matching Windows Security authentication events were returned.")

    top_source = source_rows[0] if source_rows else None
    if lockouts and (kerberos or failed):
        conclusion = "Repeated authentication failures were associated with confirmed account lockout evidence. Review the highest-frequency source first for stale or invalid stored credentials."
    elif kerberos or failed:
        conclusion = "Authentication failures were detected without a matching Event 4740 lockout record in the effective window. Review recurring sources and failure codes."
    else:
        conclusion = "The effective time window did not return enough matching evidence to determine a cause."
    if top_source:
        conclusion += f" The leading visible source was {top_source.get('source')} with {top_source.get('total_events')} event(s)."

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
        "limitations": "Windows Security evidence may not identify the exact application, service, scheduled task, or person that submitted a credential.",
        "analysis_source": "Validated deterministic evidence analysis",
    }


def _source_statistics(report: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supplied = report.get("source_statistics")
    if isinstance(supplied, list):
        rows = []
        for item in supplied:
            if not isinstance(item, dict):
                continue
            source = _normalize_source_ip(item.get("source")) or _clean(item.get("source"))
            if not source:
                continue
            row = dict(item)
            row["source"] = source
            rows.append(row)
        return sorted(rows, key=lambda item: int(item.get("total_events", item.get("count", 0)) or 0), reverse=True)

    aggregate: dict[str, dict[str, Any]] = {}
    for event in events:
        ip = _normalize_source_ip(event.get("source_ip"))
        device = _clean(event.get("workstation")) or _clean(event.get("computer"))
        source = ip or device
        if not source:
            continue
        row = aggregate.setdefault(source, {
            "source": source,
            "source_type": "IP address" if ip else "Device",
            "failed_logons": 0,
            "lockouts": 0,
            "kerberos_failures": 0,
            "total_events": 0,
            "first_seen": event.get("timestamp"),
            "last_seen": event.get("timestamp"),
        })
        event_id = int(event.get("event_id", 0) or 0)
        if event_id == 4625:
            row["failed_logons"] += 1
        elif event_id == 4740:
            row["lockouts"] += 1
        elif event_id == 4771:
            row["kerberos_failures"] += 1
        row["total_events"] += 1
        current = _parse_time(event.get("timestamp"))
        first = _parse_time(row.get("first_seen"))
        last = _parse_time(row.get("last_seen"))
        if current and (first is None or current < first):
            row["first_seen"] = event.get("timestamp")
        if current and (last is None or current > last):
            row["last_seen"] = event.get("timestamp")
    return sorted(aggregate.values(), key=lambda item: item["total_events"], reverse=True)


def render_investigation_report(report: dict[str, Any]) -> None:
    """Render source-first investigation report with consistent filtered statistics."""
    events = report.get("timeline") if isinstance(report.get("timeline"), list) else []
    counts = report.get("event_counts") if isinstance(report.get("event_counts"), dict) else {}
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), dict) else {}
    analysis = report.get("analysis") if isinstance(report.get("analysis"), dict) else None
    if not analysis:
        analysis = _deterministic_analysis(report)

    sources = _source_statistics(report, events)

    st.markdown("## Authentication investigation report")
    st.caption(
        f"Target: {report.get('target_user', 'Unknown')}  |  "
        f"Requested window: {report.get('requested_time_window', report.get('time_window', 'Unknown'))}  |  "
        f"Generated: {_format_time(report.get('generated_at_utc'))}"
    )

    # Source frequency is intentionally the first substantive report section.
    with st.container(border=True):
        st.markdown("### Where the attempts came from")
        if sources:
            top = sources[0]
            st.write(
                f"The most frequent visible source was **{top.get('source')}**, associated with "
                f"**{int(top.get('total_events', top.get('count', 0)) or 0)}** matching event(s)."
            )
            source_frame = pd.DataFrame([
                {
                    "Source": row.get("source"),
                    "Type": row.get("source_type") or "Source",
                    "Failed logons": int(row.get("failed_logons", 0) or 0),
                    "Lockouts": int(row.get("lockouts", 0) or 0),
                    "Kerberos failures": int(row.get("kerberos_failures", 0) or 0),
                    "Total events": int(row.get("total_events", row.get("count", 0)) or 0),
                    "First seen": _format_time(row.get("first_seen")),
                    "Last seen": _format_time(row.get("last_seen")),
                }
                for row in sources
            ])
            st.dataframe(source_frame, hide_index=True, width="stretch")
        else:
            st.info("No visible source remained after address normalization and infrastructure-source filtering.")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Failed logons", int(counts.get("4625", 0) or 0))
    col2.metric("Account lockouts", int(counts.get("4740", 0) or 0))
    col3.metric("Kerberos failures", int(counts.get("4771", 0) or 0))
    col4.metric("Filtered evidence", int(report.get("total_matching_events", len(events)) or 0))

    with st.container(border=True):
        st.markdown("### Time-window and evidence coverage")
        coverage_rows = [
            ("Requested window", report.get("requested_time_window") or report.get("time_window")),
            ("Effective start", _format_time(report.get("effective_start_utc"))),
            ("Effective end", _format_time(report.get("effective_end_utc"))),
            ("First matching event", _format_time(report.get("first_event_utc"))),
            ("Last matching event", _format_time(report.get("last_event_utc"))),
            ("Raw events returned", diagnostics.get("raw_events_returned")),
            ("Valid account events", diagnostics.get("valid_account_events")),
            ("Outside requested window", diagnostics.get("events_outside_requested_window")),
            ("Excluded infrastructure IP events", diagnostics.get("excluded_source_events")),
            ("Duplicate events removed", diagnostics.get("duplicate_events_removed")),
            ("Final matching events", diagnostics.get("matching_events")),
        ]
        frame = pd.DataFrame([{"Field": label, "Value": value} for label, value in coverage_rows if value not in (None, "")])
        st.dataframe(frame, hide_index=True, width="stretch")

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
        st.caption(f"Analysis source: {analysis.get('analysis_source', 'Not available')}")

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

    rows = []
    for event in events:
        source_ip = _normalize_source_ip(event.get("source_ip"))
        reason, _ = _event_reason(event)
        rows.append({
            "Time": _format_time(event.get("timestamp")),
            "Event": f"{event.get('event_id')} | {event.get('event_name')}",
            "Reason": reason,
            "Source device": _clean(event.get("workstation")) or _clean(event.get("computer")) or "Not available",
            "Source IP": source_ip or "Not available",
            "Failure code": _clean(event.get("failure_code")) or _clean(event.get("sub_status")) or _clean(event.get("status")) or "Not available",
            "Service": _clean(event.get("service_name")) or "Not available",
        })

    if rows:
        st.markdown("### Evidence timeline")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No evidence timeline is available for this investigation.")

    recommendations = analysis.get("recommended_actions")
    with st.expander("Recommended actions", expanded=True):
        if isinstance(recommendations, list) and recommendations:
            for index, item in enumerate(recommendations, start=1):
                st.write(f"{index}. {item}")
        else:
            st.write("1. Validate the highest-frequency source device or IP shown above.")
            st.write("2. Check services, scheduled tasks, mapped drives, mobile clients, and cached credentials for an outdated password.")
            if int(counts.get("4740", 0) or 0):
                st.write("3. Stop repeated attempts before unlocking the account to prevent immediate relockout.")
            st.write("4. Escalate unrecognized or unusually frequent sources to security operations.")

    if analysis.get("limitations"):
        st.caption(f"Limitation: {analysis['limitations']}")

    if rows:
        st.download_button(
            "Download evidence as CSV",
            data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8"),
            file_name=f"authentication-investigation-{report.get('target_user', 'user')}.csv",
            mime="text/csv",
        )
