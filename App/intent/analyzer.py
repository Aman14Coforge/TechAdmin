from App.core.llm_client import StructuredLLM
from App.intent.prompts import SYSTEM_PROMPT
from App.schemas.models import LLMExtraction
class IntentAnalyzer:
    def __init__(self,llm:StructuredLLM): self.llm=llm
    def analyze(self,query:str)->LLMExtraction: return self.llm.complete(SYSTEM_PROMPT,query,LLMExtraction)
