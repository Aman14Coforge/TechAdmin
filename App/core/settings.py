from functools import lru_cache
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
class RuntimeSettings(BaseSettings):
    model_config=SettingsConfigDict(env_file='.env',extra='ignore')
    llm_provider:str='ollama'
    gemini_api_key:SecretStr|None=None
    gemini_model:str='gemini-2.5-flash'
    ollama_base_url:str='http://127.0.0.1:11434'
    ollama_model:str='qwen3:14b'
    llm_timeout_seconds:int=Field(default=60,ge=1,le=300)
    llm_max_retries:int=Field(default=1,ge=0,le=2)
    log_level:str='INFO'
    @model_validator(mode='after')
    def check(self):
        self.llm_provider=self.llm_provider.lower()
        if self.llm_provider not in {'ollama','gemini'}: raise ValueError('LLM_PROVIDER must be ollama or gemini')
        if self.llm_provider=='gemini' and not self.gemini_api_key: raise ValueError('GEMINI_API_KEY is required')
        return self
@lru_cache
def get_settings(): return RuntimeSettings()
