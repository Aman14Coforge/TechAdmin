"""
Configuration Module
Author: Aman Gupta
Purpose: Load and manage application configuration
"""

import os
import yaml
from dotenv import load_dotenv
from loguru import logger
from pathlib import Path

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Application configuration class.
    Loads settings from environment variables and config files.
    
    TODO: Load from YAML config files in Configs/ directory
    """
    
    # Ollama Configuration
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    MODEL_NAME = os.getenv("MODEL_NAME", "qwen3:14b")
    
    # API Configuration
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "60"))
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Microsoft Graph Configuration
    GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID")
    GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET")
    GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID")
    GRAPH_SCOPE = os.getenv("GRAPH_SCOPE", "https://graph.microsoft.com/.default")
    GRAPH_AUTH_MODE = os.getenv("GRAPH_AUTH_MODE", "delegated")
    GRAPH_USERNAME = os.getenv("GRAPH_USERNAME")
    GRAPH_PASSWORD = os.getenv("GRAPH_PASSWORD")
    
    # TODO: Load additional configs from Configs/app_config.yaml
    # - Intent mapping configuration
    # - Agent configuration
    # - Tool configuration
    # - API endpoints
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required configuration is set.
        
        TODO: Add validation for required parameters
        """
        required_vars = [
            "OLLAMA_HOST",
            "MODEL_NAME"
        ]
        
        for var in required_vars:
            if not getattr(cls, var, None):
                logger.error(f"Missing required config: {var}")
                return False
        
        logger.info("Configuration validated successfully")
        return True


def load_llm_config() -> dict:
    """
    Load LLM configuration from YAML file.
    
    Returns:
        Configuration dictionary
    """
    config_path = Path(__file__).parent.parent.parent / "Configs" / "llm_config.yaml"
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded LLM config from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Error loading LLM config: {str(e)}")
        return {"llm": {"model_name": Config.MODEL_NAME}}


class Logger:
    """
    Logger configuration and setup.
    
    TODO: Enhance with file logging and structured logging
    """
    
    @staticmethod
    def setup():
        """
        Setup logging configuration.
        
        TODO: Configure:
        - Log level from Config.LOG_LEVEL
        - Log format
        - File output to logs/ directory
        - Rotation policy
        """
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        logger.add(
            str(log_dir / "techadmin.log"),
            level=Config.LOG_LEVEL,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="500 MB",
            retention="30 days"
        )
        logger.info("Logger configured successfully")


# Initialize on import
config = load_llm_config()
model = config.get("llm", {}).get("model_name", Config.MODEL_NAME)