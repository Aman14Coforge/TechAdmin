from functools import lru_cache
from pathlib import Path
from pydantic import TypeAdapter
import yaml
from App.schemas.models import AppSettings, IntentMappingEntry, LLMYamlSettings
CONFIG_DIR=Path(__file__).resolve().parents[2]/"Configs"
def _yaml(name:str)->dict:
    with (CONFIG_DIR/name).open(encoding='utf-8') as f: return yaml.safe_load(f) or {}
@lru_cache
def load_intent_mapping()->dict[str,IntentMappingEntry]:
    return TypeAdapter(dict[str,IntentMappingEntry]).validate_python(_yaml('intent_mapping.yaml'))
@lru_cache
def load_llm_config()->LLMYamlSettings:
    return LLMYamlSettings.model_validate(_yaml('llm_config.yaml')['llm'])
@lru_cache
def load_app_config()->AppSettings:
    return AppSettings.model_validate(_yaml('app_config.yaml')['app'])
