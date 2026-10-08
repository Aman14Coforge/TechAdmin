"""Patch Agent and embedded scheduler configuration."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT=Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT/".env",override=True)

def env_bool(name:str,default:bool)->bool:
    return os.getenv(name,str(default)).strip().casefold() in {"1","true","yes","on"}

def env_int(name:str,default:int)->int:
    return int(os.getenv(name,str(default)))

@dataclass(frozen=True)
class PatchSettings:
    base_url:str=os.getenv("IVANTI_BASE_URL","https://mluprd-sfc.ivanticloud.com").rstrip("/")
    tenant_id:str=os.getenv("IVANTI_TENANT_ID","").strip()
    client_id:str=os.getenv("IVANTI_CLIENT_ID","").strip()
    client_secret:str=os.getenv("IVANTI_CLIENT_SECRET","").strip()
    people_token_path:str=os.getenv("IVANTI_PEOPLE_TOKEN_PATH","/api/apigatewaydataservices/v1/token").strip()
    patch_token_url:str=os.getenv("IVANTI_PATCH_TOKEN_URL","").strip()
    patch_scope:str=os.getenv("IVANTI_PATCH_SCOPE","").strip()
    people_bearer_override:str=os.getenv("IVANTI_PEOPLE_BEARER_TOKEN","").strip()
    timeout:int=env_int("IVANTI_HTTP_TIMEOUT_SECONDS",60)
    scheduler_enabled:bool=env_bool("PATCH_SCHEDULER_ENABLED",True)
    scheduler_hour:int=env_int("PATCH_SCHEDULER_HOUR",1)
    scheduler_minute:int=env_int("PATCH_SCHEDULER_MINUTE",0)
    scheduler_timezone:str=os.getenv("PATCH_SCHEDULER_TIMEZONE","Asia/Kolkata").strip()
    scheduler_run_on_startup:bool=env_bool("PATCH_SCHEDULER_RUN_ON_STARTUP",False)
    scheduler_startup_delay_seconds:int=env_int("PATCH_SCHEDULER_STARTUP_DELAY_SECONDS",30)
    scheduler_require_preflight:bool=env_bool("PATCH_SCHEDULER_REQUIRE_PREFLIGHT",True)
    scan_lock_key:int=env_int("PATCH_SCAN_ADVISORY_LOCK_KEY",741852963)
    days:int=env_int("PATCH_PERSISTENCE_DAYS",14)
    retention:int=env_int("PATCH_OBSERVATION_RETENTION_DAYS",400)
    auto_ticket:bool=env_bool("PATCH_AUTO_TICKET_ENABLED",False)
    ticket_dry_run:bool=env_bool("PATCH_TICKET_DRY_RUN",True)
    ticket_url:str=os.getenv("PATCH_TICKET_API_URL","").strip()
    ticket_token:str=os.getenv("PATCH_TICKET_API_TOKEN","").strip()
    assignment_group:str=os.getenv("PATCH_TICKET_ASSIGNMENT_GROUP","").strip()

    def validate(self)->None:
        missing=[key for key,value in {
            "IVANTI_TENANT_ID":self.tenant_id,
            "IVANTI_CLIENT_ID":self.client_id,
            "IVANTI_CLIENT_SECRET":self.client_secret,
            "IVANTI_PATCH_TOKEN_URL":self.patch_token_url,
        }.items() if not value]
        if missing:raise RuntimeError("Missing patch configuration: "+", ".join(missing))
settings=PatchSettings()
