from __future__ import annotations
import json
from typing import Protocol, TypeVar
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from App.core.settings import RuntimeSettings
T=TypeVar('T',bound=BaseModel)
class LLMInvocationError(RuntimeError): pass
class StructuredLLM(Protocol):
    def complete(self,system:str,user:str,schema:type[T])->T: ...
class OllamaClient:
    def __init__(self,s:RuntimeSettings):
        from langchain_ollama import ChatOllama
        self.model=ChatOllama(model=s.ollama_model,base_url=s.ollama_base_url,temperature=0,client_kwargs={'timeout':s.llm_timeout_seconds})
    def complete(self,system:str,user:str,schema:type[T])->T:
        try:
            out=self.model.with_structured_output(schema,method='json_schema').invoke([SystemMessage(content=system),HumanMessage(content=user)])
            return out if isinstance(out,schema) else schema.model_validate(out)
        except Exception as e: raise LLMInvocationError(f'Ollama failed: {type(e).__name__}: {e}') from e
class GeminiClient:
    def __init__(self,s:RuntimeSettings):
        from langchain_google_genai import ChatGoogleGenerativeAI
        self.model=ChatGoogleGenerativeAI(model=s.gemini_model,api_key=s.gemini_api_key.get_secret_value(),temperature=0,timeout=s.llm_timeout_seconds,max_retries=s.llm_max_retries,response_mime_type='application/json')
    def complete(self,system:str,user:str,schema:type[T])->T:
        prompt=system+'\nReturn one JSON object matching this schema:\n'+json.dumps(schema.model_json_schema())
        try:
            response=self.model.invoke([SystemMessage(content=prompt),HumanMessage(content=user)])
            content=response.content if isinstance(response.content,str) else ''.join(x.get('text','') for x in response.content if isinstance(x,dict))
            return schema.model_validate_json(content)
        except Exception as e: raise LLMInvocationError(f'Gemini failed: {type(e).__name__}: {e}') from e
def build_llm(s:RuntimeSettings)->StructuredLLM:
    return OllamaClient(s) if s.llm_provider=='ollama' else GeminiClient(s)
