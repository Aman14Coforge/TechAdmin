from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=True)
def env_bool(n: str, d: bool) -> bool: return os.getenv(n, str(d)).strip().casefold() in {"1","true","yes","on"}
def env_int(n: str, d: int) -> int: return int(os.getenv(n, str(d)))
@dataclass(frozen=True)
class PatchSettings:
    base_url: str = os.getenv("IVANTI_BASE_URL", "").strip().rstrip("/")
    tenant_id: str = os.getenv("IVANTI_TENANT_ID", "").strip()
    client_id: str = os.getenv("IVANTI_CLIENT_ID", "").strip()
    client_secret: str = os.getenv("IVANTI_CLIENT_SECRET", "").strip()
    people_token_path: str = os.getenv("IVANTI_PEOPLE_TOKEN_PATH", "/api/apigatewaydataservices/v1/token").strip()
    patch_token_url: str = os.getenv("IVANTI_PATCH_TOKEN_URL", "").strip()
    patch_scope: str = os.getenv("IVANTI_PATCH_SCOPE", "").strip()
    people_bearer_override: str = os.getenv("IVANTI_PEOPLE_BEARER_TOKEN", "").strip()
    timeout: int = env_int("IVANTI_HTTP_TIMEOUT_SECONDS", 60)
    scheduler_enabled: bool = env_bool("PATCH_SCHEDULER_ENABLED", True)
    scheduler_hour: int = env_int("PATCH_SCHEDULER_HOUR", 1)
    scheduler_minute: int = env_int("PATCH_SCHEDULER_MINUTE", 0)
    scheduler_timezone: str = os.getenv("PATCH_SCHEDULER_TIMEZONE", "Asia/Kolkata").strip()
    scheduler_require_preflight: bool = env_bool("PATCH_SCHEDULER_REQUIRE_PREFLIGHT", True)
    scheduler_run_on_startup: bool = env_bool("PATCH_SCHEDULER_RUN_ON_STARTUP", True)
    scheduler_startup_delay_seconds: int = env_int("PATCH_SCHEDULER_STARTUP_DELAY_SECONDS", 30)
    scan_lock_key: int = env_int("PATCH_SCAN_ADVISORY_LOCK_KEY", 741852963)
    days: int = env_int("PATCH_PERSISTENCE_DAYS", 14)
    retention: int = env_int("PATCH_OBSERVATION_RETENTION_DAYS", 400)
    auto_ticket: bool = env_bool("PATCH_AUTO_TICKET_ENABLED", False)
    bulk_enabled: bool = env_bool("PATCH_BULK_TICKETING_ENABLED", True)
    max_manual_batch: int = env_int("PATCH_MAX_MANUAL_BATCH_SIZE", 25)
    max_auto_per_run: int = env_int("PATCH_MAX_AUTOMATIC_TICKETS_PER_RUN", 100)
    max_batch_pass: int = env_int("PATCH_MAX_BATCH_ITEMS_PER_WORKER_PASS", 100)
    ticket_delay_seconds: int = env_int("PATCH_TICKET_DELAY_SECONDS", 1)
    ticket_max_retries: int = env_int("PATCH_TICKET_MAX_RETRIES", 3)
    ai_enabled: bool = env_bool("PATCH_AI_ANALYSIS_ENABLED", True)
    ai_model: str = os.getenv("PATCH_AI_MODEL_NAME", "").strip() or os.getenv("MODEL_NAME", "qwen3:14b").strip()
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip("/")
    def validate(self) -> None:
        missing = [k for k,v in {"IVANTI_BASE_URL":self.base_url,"IVANTI_TENANT_ID":self.tenant_id,"IVANTI_CLIENT_ID":self.client_id,"IVANTI_CLIENT_SECRET":self.client_secret,"IVANTI_PATCH_TOKEN_URL":self.patch_token_url}.items() if not v]
        if missing: raise RuntimeError("Missing patch configuration: " + ", ".join(missing))
settings = PatchSettings()
