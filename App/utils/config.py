from app.utils.config import load_llm_config

config = load_llm_config()

model = config["llm"]["model_name"]