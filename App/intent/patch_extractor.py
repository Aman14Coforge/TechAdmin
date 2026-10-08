from __future__ import annotations
import re
from datetime import date,datetime
from App.workflow.state import IntentType,PatchMetadata,UnifiedExtractionResult
_DEVICE=re.compile(r"\b(?:[A-Z]{2,8}-[A-Z0-9-]{4,}|DESKTOP-[A-Z0-9-]+|LAPTOP-[A-Z0-9-]+)\b",re.I)
_DATE_PATTERNS=("%Y-%m-%d","%d-%m-%Y","%d/%m/%Y","%d %B %Y","%B %d %Y")
class DeterministicPatchExtractor:
    KEYWORDS=("patch","noncompliant","non-compliant","compliance","kb","ivanti","vulnerability")
    def matches(self,text:str)->bool:
        q=(text or "").casefold();return any(k in q for k in self.KEYWORDS) and any(k in q for k in ("patch","ivanti","noncompliant","non-compliant"))
    def extract(self,text:str)->UnifiedExtractionResult:
        q=(text or "").strip();low=q.casefold();device=(_DEVICE.search(q).group(0).upper() if _DEVICE.search(q) else None)
        days=14 if "14 day" in low or "fourteen day" in low else 1
        m=re.search(r"(?:for|minimum|last)\s+(\d{1,3})\s+days?",low)
        if m: days=max(1,min(int(m.group(1)),365))
        as_of=None
        iso=re.search(r"\b(20\d{2}-\d{2}-\d{2})\b",q)
        if iso:
            try: as_of=date.fromisoformat(iso.group(1))
            except ValueError: pass
        intent=IntentType.PATCH_TICKET if any(k in low for k in ("raise ticket","create ticket","open ticket")) else IntentType.PATCH_REPORT
        if any(k in low for k in ("run patch scan","scan ivanti now","start patch scan")): intent=IntentType.PATCH_SCAN
        metadata=PatchMetadata(device_name=device,as_of_date=as_of,minimum_days=days,ticket_reason=q if intent is IntentType.PATCH_TICKET else None)
        return UnifiedExtractionResult(success=True,intent=intent,confidence=.99,explanation="Deterministic patch-domain extraction used; no LLM call was required.",metadata=metadata)
