"""Try file formats against iEngage ISD/ISD/FileUpload and decode the replies.

Run from the folder that has .env:   python probe_upload.py INC000108047
Each accepted try attaches a tiny test file to that ticket. Keys are never printed.
"""
import base64, io, json, os, re, sys, zipfile
import httpx
from dotenv import load_dotenv

load_dotenv(".env") or load_dotenv("../.env")
digits = "".join(c for c in (sys.argv[1] if len(sys.argv) > 1 else "") if c.isdigit())
if not digits:
    sys.exit("Usage: python probe_upload.py INC000108047")
request_id = str(int(digits))
root = os.getenv("IENGAGE_URL", "").split("/Misc/")[0]
url = f"{root}/ISD/ISD/FileUpload"
verify = os.getenv("IENGAGE_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}


def decode(text):
    """Replies are junk + base64 JSON; pull out and decode the JSON part."""
    found = []
    for chunk in re.findall(r"eyJ[A-Za-z0-9+/=_-]{8,}", text):
        chunk = chunk[: len(chunk) - len(chunk) % 4]
        try:
            found.append(base64.b64decode(chunk + "==", altchars=b"-_" if "-" in chunk else None).decode("utf-8", "replace"))
        except Exception:
            pass
    return " | ".join(found) or " ".join(text.split())[:160]


def tiny_xlsx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Devices" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>TEST-DEVICE</t></is></c></row></sheetData></worksheet>')
    return buf.getvalue()


csv = b"Device,Status\r\nTEST-DEVICE,Test upload from TechAdmin probe\r\n"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
tries = [
    ("probe_1.xlsx", tiny_xlsx(), XLSX),
    ("probe_2.xlsx", tiny_xlsx(), "application/vnd.ms-excel"),
    ("probe_3.csv", csv, "application/vnd.ms-excel"),
    ("probe_4.csv", csv, "application/octet-stream"),
    ("probe_5.xlsx", tiny_xlsx(), "application/octet-stream"),
]
for with_keys in (True, False):
    for name, content, ctype in tries:
        form = [("files", (name, content, ctype)), ("RequestID", (None, request_id))]
        if with_keys:
            form += [("ECSerp", (None, os.getenv("IENGAGE_ECSERP", ""))), ("AuthKey", (None, os.getenv("IENGAGE_AUTH_KEY", "")))]
        try:
            r = httpx.post(url, files=form, timeout=30, verify=verify, follow_redirects=False)
            loc = r.headers.get("location", "")
            print(f"keys={with_keys!s:5} {name:13} {ctype:68} {r.status_code} {('-> ' + loc) if loc else ''} {decode(r.text)}")
        except Exception as exc:
            print(f"keys={with_keys!s:5} {name:13} {ctype:68} ERR {type(exc).__name__}: {exc}")
