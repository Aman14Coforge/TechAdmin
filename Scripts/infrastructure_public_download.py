"""Unauthenticated, signed, expiring SolarWinds CSV download handler."""
from __future__ import annotations
import re
import pandas as pd
import streamlit as st
from App.services.infrastructure.itom_repository import ITOMSiteRepository
from App.services.infrastructure.public_link import validate_public_csv_request

def render_public_infrastructure_csv_if_requested()->bool:
    if str(st.query_params.get("public_infra_csv","")).strip()!="1":return False
    site=str(st.query_params.get("site","")).strip();expires=str(st.query_params.get("expires","")).strip();signature=str(st.query_params.get("signature","")).strip()
    valid,message=validate_public_csv_request(site,expires,signature)
    st.set_page_config(page_title="TechAdmin SolarWinds CSV",layout="centered")
    if not valid:
        st.error(message);return True
    alert=ITOMSiteRepository().get_site_alert(site)
    if alert is None:
        st.error("This site is not present in the latest affected SolarWinds data.");return True
    frame=pd.DataFrame([{"Device":d.device_name,"Status":d.device_status,"Type":d.ci_type or "Not available","Location":d.source_location or "Not available","Last seen IST":str(d.device_last_seen_ist or "Not available"),"Unreachable for":d.device_silent_for or "Not available"} for d in alert.devices])
    st.title(f"{alert.location_name} · SolarWinds devices")
    st.caption(f"{alert.priority} · {alert.site_status.title()} · {len(frame)} affected devices")
    st.dataframe(frame,hide_index=True,width="stretch",height=480)
    filename=re.sub(r"[^A-Za-z0-9_-]+","_",alert.location_name)+"_solarwinds_devices.csv"
    st.download_button("Download CSV",frame.to_csv(index=False).encode("utf-8-sig"),filename,"text/csv",type="primary",width="stretch")
    return True
