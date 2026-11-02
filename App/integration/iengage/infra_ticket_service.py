"""iEngage tickets for Infrastructure Agent site alerts.

Reuses the patch ticket payload layout and client. Category, subcategory,
priority, request type and location can be overridden for infrastructure
tickets with INFRA_IENGAGE_* variables; anything not set falls back to the
shared IENGAGE_* values. Every infra ticket uses the same combination
(e.g. Incident / Network, P1 sites High, P2 sites Medium), whatever the device types.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
from collections import Counter
from dataclasses import replace
from datetime import datetime
from typing import Optional

from App.integration.iengage.client import IEngageClient
from App.integration.iengage.config import IEngageConfig, get_text
from App.integration.iengage.models import IEngageAttachment, IEngageRequest, IEngageResult, InfraTicketInput
from App.integration.iengage.ticket_service import PatchTicketService

DESCRIPTION_HEADER = "Infrastructure alert raised from TechAdmin Infrastructure Agent."
PROMPT_START = "--- Copy the prompt below into SolarWinds chat ---"
PROMPT_END = "--- End of prompt ---"

# Excel columns: (header, key in the query 1 row). Missing keys are left blank.
CSV_COLUMNS = (
    ("Site", "location_name"),
    ("Priority", "priority"),
    ("Site status", "site_status"),
    ("Site score", "site_score"),
    ("Site reason", "site_reason"),
    ("Device name", "device_name"),
    ("Device status", "device_status"),
    ("Source system", "source_system"),
    ("Device type", "ci_type"),
    ("Source location", "source_location"),
    ("Last seen (IST)", "device_last_seen_ist"),
    ("Silent for", "device_silent_for"),
    ("Last pulled (IST)", "device_last_pulled_ist"),
    ("Sync completed (IST)", "sync_completed_ist"),
)


XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def attach_csv_enabled() -> bool:
    """INFRA_IENGAGE_ATTACH_CSV=true attaches the Excel device list.

    Off by default: iEngage's FileUpload currently needs a signed-in web session
    and refuses the API key, so the file never arrives. Turn it on once the
    iEngage team provides an API upload.
    """
    return (os.getenv("INFRA_IENGAGE_ATTACH_CSV") or "false").strip().casefold() in {"1", "true", "yes", "y", "on"}


def build_device_file(item: InfraTicketInput, now: Optional[datetime] = None) -> IEngageAttachment:
    """Excel workbook (.xlsx) with one row per selected device."""
    site_values = {
        "location_name": item.location_name,
        "priority": item.priority,
        "site_status": item.site_status,
        "site_score": item.site_score,
        "site_reason": item.site_reason,
    }
    rows = []
    for device in _unique_devices(item):
        row = {**site_values, **(device.details or {})}
        row.update({
            "device_name": device.device_name,
            "device_status": device.device_status or row.get("device_status"),
            "source_system": device.source_system or row.get("source_system"),
            "ci_type": device.ci_type or row.get("ci_type"),
        })
        rows.append([row.get(key) for _, key in CSV_COLUMNS])
    slug = re.sub(r"[^A-Za-z0-9]+", "_", item.location_name).strip("_") or "site"
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M")
    return IEngageAttachment(
        file_name=f"{slug}_{item.priority or 'alert'}_{stamp}_devices.xlsx",
        content=_xlsx_bytes([header for header, _ in CSV_COLUMNS], rows),
        content_type=(os.getenv("INFRA_IENGAGE_ATTACHMENT_CONTENT_TYPE") or XLSX_CONTENT_TYPE).strip(),
    )


# Older name kept so existing imports keep working.
build_device_csv = build_device_file


_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml(value: object) -> str:
    text = _XML_ILLEGAL.sub("", str(value))
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    """Minimal single-sheet .xlsx (no third-party packages): bold header, frozen top row, filter."""
    def cell(ref: str, value: object, style: int = 0) -> str:
        if value is None or value == "":
            return f'<c r="{ref}" s="{style}"/>'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
        if isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{_xml(value)}</t></is></c>'

    widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], min(len(str(value or "")), 60))
    last = _column_letter(len(headers) - 1)
    sheet_rows = ['<row r="1">' + "".join(cell(f"{_column_letter(i)}1", h, 1) for i, h in enumerate(headers)) + "</row>"]
    for r, row in enumerate(rows, start=2):
        sheet_rows.append(f'<row r="{r}">' + "".join(cell(f"{_column_letter(i)}{r}", v) for i, v in enumerate(row)) + "</row>")
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        "<cols>" + "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w + 3}" customWidth="1"/>' for i, w in enumerate(widths)) + "</cols>"
        "<sheetData>" + "".join(sheet_rows) + "</sheetData>"
        f'<autoFilter ref="A1:{last}{max(len(rows) + 1, 1)}"/>'
        "</worksheet>"
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Devices" sheetId="1" r:id="rId1"/></sheets>'
            f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">Devices!$A$1:${last}${max(len(rows) + 1, 1)}</definedName></definedNames>'
            "</workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FF0F1F33"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def infra_config_from_env(base: Optional[IEngageConfig] = None) -> IEngageConfig:
    """Apply INFRA_IENGAGE_* overrides on top of the shared iEngage config."""
    config = base or IEngageConfig.from_env()
    overrides = {
        field: get_text(name)
        for field, name in {
            "category_id": "INFRA_IENGAGE_CATEGORY_ID",
            "subcategory_id": "INFRA_IENGAGE_SUBCATEGORY_ID",
            "priority_id": "INFRA_IENGAGE_PRIORITY_ID",
            "priority_name": "INFRA_IENGAGE_PRIORITY_NAME",
            "request_type": "INFRA_IENGAGE_REQUEST_TYPE",
            "location_id": "INFRA_IENGAGE_LOCATION_ID",
            "location_name": "INFRA_IENGAGE_LOCATION_NAME",
        }.items()
        if get_text(name)
    }
    # iEngage accepts up to 4000 characters; infra tickets use all of it so the
    # SolarWinds prompt and device list fit. INFRA_IENGAGE_DESCRIPTION_MAX_LENGTH overrides.
    max_length = get_text("INFRA_IENGAGE_DESCRIPTION_MAX_LENGTH") or "4000"
    try:
        overrides["description_max_length"] = max(500, min(int(max_length), 4000))
    except ValueError:
        overrides["description_max_length"] = 4000
    return replace(config, **overrides)


# iEngage Office/Building Location names by ID (from the iengagedev Create Request dropdown).
# Sent as RequesterLocationName so the name always matches the ID. Override or extend
# with INFRA_IENGAGE_LOCATION_NAMES="9=USA; 99=Others".
IENGAGE_LOCATION_NAMES = {
    "1": "Bangalore", "2": "Gurugram", "3": "Noida-H7", "4": "Kolkata", "5": "Mumbai", "6": "UK",
    "7": "Campus Tower A,B,C", "8": "Campus Tower D", "9": "USA", "10": "New Jersey", "11": "Spain",
    "12": "UK", "13": "Augusta", "99": "Others", "100": "West Virginia", "101": "Phoenix",
    "102": "Coforge BPS - Green Park, Bangalore", "103": "Coforge BPS - Kolhapur",
    "104": "Coforge BPS - Marisoft, Pune", "105": "Coforge BPS - Commerzone, Pune",
    "106": "Coforge BPS - Vector 3, Manila", "107": "Coforge BPS- Axis 1, Manila",
    "108": "Coforge BPS - Dallas", "109": "COFORGE SF Hyderabad",
}


def location_name_for(location_id: str) -> str:
    names = dict(IENGAGE_LOCATION_NAMES)
    for part in re.split(r"[;\n]", os.getenv("INFRA_IENGAGE_LOCATION_NAMES", "")):
        key, sep, value = part.partition("=")
        if sep and key.strip() and value.strip():
            names[key.strip()] = value.strip()
    return names.get(str(location_id).strip(), "")


def site_location_ids() -> dict[str, str]:
    """INFRA_IENGAGE_SITE_LOCATION_IDS="United States=12; Pune=5; Greater Noida=7" -> {site: id}."""
    mapping: dict[str, str] = {}
    for part in re.split(r"[;\n]", os.getenv("INFRA_IENGAGE_SITE_LOCATION_IDS", "")):
        name, sep, value = part.partition("=")
        if sep and name.strip() and value.strip():
            mapping[_site_key(name)] = value.strip()
    return mapping


def _site_key(name: str) -> str:
    return " ".join(str(name).replace("/", " / ").split()).casefold()


def resolve_location_id(site_name: str, default_id: str) -> tuple[str, bool]:
    """iEngage location ID for a dashboard site, and whether it came from the mapping.

    Matches the full site name first ("Greater Noida / Tower B"), then the part
    before the first "/" ("Greater Noida"). Unmapped sites use the default ID.
    """
    mapping = site_location_ids()
    key = _site_key(site_name)
    for candidate in (key, key.split(" / ")[0].strip()):
        if candidate in mapping:
            return mapping[candidate], True
    return default_id, False


def _priority_override(priority: Optional[str]) -> dict[str, str]:
    """Optional per-priority IDs, e.g. INFRA_IENGAGE_P1_PRIORITY_ID."""
    if priority not in {"P1", "P2"}:
        return {}
    priority_id = os.getenv(f"INFRA_IENGAGE_{priority}_PRIORITY_ID", "").strip()
    priority_name = os.getenv(f"INFRA_IENGAGE_{priority}_PRIORITY_NAME", "").strip()
    if not priority_id:
        # Without an ID the name alone would contradict the priority actually sent.
        return {}
    result = {"RequestPriorityId": priority_id}
    if priority_name:
        result["RequestPriorityName"] = priority_name
    return result


class InfraTicketService(PatchTicketService):
    def __init__(
        self,
        config: Optional[IEngageConfig] = None,
        client: Optional[IEngageClient] = None,
    ) -> None:
        config = config or infra_config_from_env()
        super().__init__(config=config, client=client or IEngageClient(config=config))

    async def create_infra_ticket(self, ticket_input: InfraTicketInput) -> IEngageResult:
        """One ticket for the site; the full device list goes in the attached Excel file."""
        self._validate_input(ticket_input)
        service_details = self.build_service_details(ticket_input)
        attachments = [build_device_file(ticket_input)] if attach_csv_enabled() else []
        return await self.client.create_ticket(
            IEngageRequest(service_details=service_details, attachments=attachments)
        )

    def build_service_details(self, item: InfraTicketInput) -> dict[str, object]:
        details = self._build_service_details(item)
        details.update(_priority_override(item.priority))
        # iEngage shows Office/Building Location from the ID, not the name, so the
        # site selected in the dashboard is mapped to an ID via INFRA_IENGAGE_SITE_LOCATION_IDS.
        site = item.location_name.strip()
        if site:
            location_id, _ = resolve_location_id(site, str(self.config.location_id or ""))
            details["RequesterLocationId"] = location_id
            # The name must be iEngage's own name for that ID; the dashboard site
            # goes in OtherLocation (shown when the location is "Others").
            details["RequesterLocationName"] = location_name_for(location_id) or site
            details["OtherLocation"] = site
        return details

    def location_for(self, item: InfraTicketInput) -> tuple[str, bool]:
        return resolve_location_id(item.location_name.strip(), str(self.config.location_id or ""))

    def _build_description(self, item: InfraTicketInput) -> str:
        limit = self.config.description_max_length
        site = [f"Site: {item.location_name.strip()}"]
        qualifiers = [value for value in (
            item.priority,
            item.site_status,
            f"combined score {item.site_score:g}" if item.site_score is not None else None,
        ) if value]
        if qualifiers:
            site.append(f" ({', '.join(qualifiers)})")
        head = [DESCRIPTION_HEADER, "".join(site) + "."]
        if item.site_reason:
            head.append(f"Site reason: {_clip(item.site_reason, 200)}.")
        tail = []
        if item.additional_description:
            tail.append(f"Note: {_clip(item.additional_description, 250)}")
        tail.append(f"Raised by: {item.triggered_by}.")

        devices = _unique_devices(item)
        with_csv = attach_csv_enabled()
        head.append(f"Affected devices: {len(devices)} ({_counts(devices)}).")
        if with_csv:
            head.append("Full device list is in the attached Excel file.")

        # Ready-to-paste prompt for the SolarWinds chat assistant, with the device details.
        site_bits = ", ".join(v for v in (item.priority, item.site_status) if v)
        prompt_open = (
            f"Site {item.location_name.strip()}" + (f" ({site_bits})" if site_bits else "") + " has infrastructure alerts"
            + (f": {_clip(item.site_reason, 150)}" if item.site_reason else "") + ". "
            "These devices are affected:"
        )
        prompt_close = (
            "For each device, tell me the most likely cause and give quick troubleshooting steps and fixes, "
            "starting with the Down and Critical ones. Keep the steps short and practical."
        )
        more_text = "see attached Excel file" if with_csv else "full list in TechAdmin Infrastructure Agent"
        fixed = "\n".join([
            " ".join(head), PROMPT_START, prompt_open, "", prompt_close, PROMPT_END, " ".join(tail)
        ])
        budget = limit - len(fixed) - 2
        entries: list[str] = []
        for index, device in enumerate(devices):
            entry = _prompt_device_entry(device)
            remaining = len(devices) - index - 1
            more = f"; ... and {remaining} more devices ({more_text})" if remaining else ""
            if len("; ".join(entries + [entry])) + len(more) + 1 > budget:
                entries.append(f"... and {len(devices) - index} more devices ({more_text})")
                break
            entries.append(entry)
        device_text = "; ".join(entries) + "."
        text = "\n".join([
            " ".join(head), PROMPT_START, prompt_open, device_text, prompt_close, PROMPT_END, " ".join(tail)
        ])
        return text[:limit]

    @staticmethod
    def _validate_input(item: InfraTicketInput) -> None:
        if not item.location_name.strip():
            raise ValueError("location_name is required.")
        if not any(device.device_name.strip() for device in item.devices):
            raise ValueError("Select at least one device for the ticket.")


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _unique_devices(item: InfraTicketInput):
    seen: set[str] = set()
    result = []
    for device in item.devices:
        name = device.device_name.strip()
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            result.append(device)
    return result


def _counts(devices) -> str:
    """'Down 2, Critical 290; SOLARWINDS 292, INTUNE 4'"""
    by_status = Counter(device.device_status or "Unknown" for device in devices)
    by_source = Counter(device.source_system or "Unknown" for device in devices)
    status_text = ", ".join(f"{name} {count}" for name, count in by_status.most_common())
    source_text = ", ".join(f"{name} {count}" for name, count in by_source.most_common())
    return f"{status_text}; {source_text}"


def _device_entry(device) -> str:
    details = ", ".join(value for value in (device.device_status, device.source_system) if value)
    return f"{device.device_name.strip()} [{details}]" if details else device.device_name.strip()


def _prompt_device_entry(device) -> str:
    """'CFG_Access_SW_1 (Switch, Critical, silent 2d 3h, last seen 2026-10-31 18:40)'"""
    details = device.details or {}
    bits = [device.ci_type or details.get("ci_type"), device.device_status or details.get("device_status")]
    if details.get("device_silent_for"):
        bits.append(f"silent {details['device_silent_for']}")
    if details.get("device_last_seen_ist"):
        bits.append(f"last seen {str(details['device_last_seen_ist'])[:16]}")
    if device.source_system and not bits[0]:
        bits.append(device.source_system)
    text = ", ".join(str(b) for b in bits if b)
    return f"{device.device_name.strip()} ({text})" if text else device.device_name.strip()
