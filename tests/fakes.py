from App.schemas.models import LLMExtraction
class FakeLLM:
 def __init__(self,data): self.data=LLMExtraction.model_validate(data); self.calls=0
 def complete(self,system,user,schema): self.calls+=1; return self.data
