from __future__ import annotations
import os
from datetime import date, datetime, timezone
from typing import Any
ACTIVE_FRESH="ACTIVE_NON_COMPLIANT"; PERSISTENT="PERSISTENT_14_DAYS"; STALE="STALE_REPORTING"; UNKNOWN="UNKNOWN_FRESHNESS"; RESOLVED="RESOLVED"
def active_device_days()->int:return max(1,int(os.getenv("PATCH_ACTIVE_DEVICE_DAYS","7")))
def classify(*,scan_date:date,last_scanned_at:datetime|None,missing_patches:int)->dict[str,Any]:
    if missing_patches<=0:return {"category":RESOLVED,"freshness":"NOT_APPLICABLE","scan_age_days":None,"reason":"Ivanti reports no missing patches."}
    if last_scanned_at is None:return {"category":UNKNOWN,"freshness":"UNKNOWN","scan_age_days":None,"reason":"Missing patches are reported, but Ivanti did not return lastScannedDate."}
    if last_scanned_at.tzinfo is None:last_scanned_at=last_scanned_at.replace(tzinfo=timezone.utc)
    age=max(0,(scan_date-last_scanned_at.date()).days); threshold=active_device_days()
    if age>threshold:return {"category":STALE,"freshness":"STALE","scan_age_days":age,"reason":f"Missing patches are reported, but the endpoint last reported {age} days before the snapshot."}
    return {"category":ACTIVE_FRESH,"freshness":"FRESH","scan_age_days":age,"reason":f"Endpoint reported within {threshold} days and has missing patches."}
def management_sources(status:dict[str,Any])->list[str]:
    mapping={"managedByPatchCloud":"Ivanti Patch Cloud","managedByDsm":"DSM","managedByEpm":"EPM","managedByIes":"IES","managedByIsec":"Security Controls","managedBySccm":"SCCM","managedByIntune":"Intune"}
    return [label for key,label in mapping.items() if status.get(key) is True]
