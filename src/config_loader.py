"""
Configuration loader for log-ai MCP server.
Loads settings from config/.env file.
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Central configuration for log-ai MCP server"""
    
    # Redis Configuration
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_MAX_MEMORY: str
    REDIS_PERSISTENCE: bool
    REDIS_ENABLED: bool
    
    # Global Concurrency Limits
    MAX_GLOBAL_SEARCHES: int
    MAX_PARALLEL_SEARCHES_PER_CALL: int
    
    # Cache Configuration
    CACHE_MAX_SIZE_MB: int
    CACHE_MAX_ENTRIES: int
    CACHE_TTL_MINUTES: int
    
    # Search Limits
    AUTO_CANCEL_TIMEOUT_SECONDS: int
    MAX_IN_MEMORY_MATCHES: int
    
    # File Output
    FILE_RETENTION_HOURS: int
    CLEANUP_INTERVAL_HOURS: int
    
    # Logging
    LOG_LEVEL: str
    LOG_FORMAT: str
    
    # Sentry Configuration (for future use)
    SENTRY_DSN: Optional[str]
    SENTRY_TRACES_SAMPLE_RATE: float
    SENTRY_PROFILES_SAMPLE_RATE: float
    SENTRY_ALERT_TEAMS_WEBHOOK: Optional[str]
    SENTRY_ALERT_SLACK_WEBHOOK: Optional[str]
    
    # Datadog Configuration (for future use)
    DD_API_KEY: Optional[str]
    DD_APP_KEY: Optional[str]
    DD_SITE: str
    
    def __init__(self):
        """Load configuration from config/.env file"""
        
        # Locate the .env file (should be in config/ relative to project root)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent  # Go up from src/ to project root
        env_file = project_root / "config" / ".env"
        
        if not env_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {env_file}\n"
                f"Please create config/.env file with required settings."
            )
        
        # Load environment variables from .env file
        load_dotenv(env_file)
        
        # Redis Configuration - Required
        self.REDIS_HOST = self._get_required("REDIS_HOST")
        self.REDIS_PORT = int(self._get_required("REDIS_PORT"))
        self.REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")  # Optional
        self.REDIS_DB = int(self._get_required("REDIS_DB"))
        self.REDIS_MAX_MEMORY = self._get_required("REDIS_MAX_MEMORY")
        self.REDIS_PERSISTENCE = self._get_bool("REDIS_PERSISTENCE")
        self.REDIS_ENABLED = self._get_bool("REDIS_ENABLED")
        self.REDIS_RETRY_DELAY = float(self._get_required("REDIS_RETRY_DELAY"))
        self.REDIS_MAX_RETRIES = int(self._get_required("REDIS_MAX_RETRIES"))
        
        # Global Concurrency Limits - Required
        self.MAX_GLOBAL_SEARCHES = int(self._get_required("MAX_GLOBAL_SEARCHES"))
        self.MAX_PARALLEL_SEARCHES_PER_CALL = int(self._get_required("MAX_PARALLEL_SEARCHES_PER_CALL"))
        
        # Cache Configuration - Required
        self.CACHE_MAX_SIZE_MB = int(self._get_required("CACHE_MAX_SIZE_MB"))
        self.CACHE_MAX_ENTRIES = int(self._get_required("CACHE_MAX_ENTRIES"))
        self.CACHE_TTL_MINUTES = int(self._get_required("CACHE_TTL_MINUTES"))
        
        # Search Limits - Required
        self.AUTO_CANCEL_TIMEOUT_SECONDS = int(self._get_required("AUTO_CANCEL_TIMEOUT_SECONDS"))
        self.PREVIEW_MATCHES_LIMIT = int(self._get_required("PREVIEW_MATCHES_LIMIT"))
        
        # File Output - Required
        self.FILE_OUTPUT_DIR = self._get_required("FILE_OUTPUT_DIR")
        self.FILE_RETENTION_HOURS = int(self._get_required("FILE_RETENTION_HOURS"))
        self.CLEANUP_INTERVAL_HOURS = int(self._get_required("CLEANUP_INTERVAL_HOURS"))
        
        # Logging - Required
        self.LOG_LEVEL = self._get_required("LOG_LEVEL")
        self.LOG_FORMAT = self._get_required("LOG_FORMAT")
        
        # Sentry Configuration - Optional
        self.SENTRY_DSN = os.environ.get("SENTRY_DSN")
        self.SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0"))
        self.SENTRY_PROFILES_SAMPLE_RATE = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))
        self.SENTRY_ALERT_TEAMS_WEBHOOK = os.environ.get("SENTRY_ALERT_TEAMS_WEBHOOK")
        self.SENTRY_ALERT_SLACK_WEBHOOK = os.environ.get("SENTRY_ALERT_SLACK_WEBHOOK")
        
        # Datadog Configuration - Optional
        self.DD_API_KEY = os.environ.get("DD_API_KEY")
        self.DD_APP_KEY = os.environ.get("DD_APP_KEY")
        self.DD_SITE = os.environ.get("DD_SITE", "datadoghq.com")
    
    def _get_required(self, key: str) -> str:
        """Get a required environment variable, raise error if missing"""
        value = os.environ.get(key)
        if value is None or value == "":
            raise ValueError(
                f"Required configuration '{key}' is missing in config/.env file"
            )
        return value
    
    def _get_bool(self, key: str) -> bool:
        """Get a boolean environment variable, raise error if missing"""
        value = self._get_required(key)
        return value.lower() in ("true", "1", "yes")
    
    def __repr__(self) -> str:
        """String representation (hide sensitive values)"""
        return (
            f"Config(\n"
            f"  Redis: {self.REDIS_HOST}:{self.REDIS_PORT} (enabled={self.REDIS_ENABLED})\n"
            f"  Max Global Searches: {self.MAX_GLOBAL_SEARCHES}\n"
            f"  Cache: {self.CACHE_MAX_SIZE_MB}MB, {self.CACHE_MAX_ENTRIES} entries, {self.CACHE_TTL_MINUTES}min TTL\n"
            f"  Sentry: {'enabled' if self.SENTRY_DSN else 'disabled'}\n"
            f"  Datadog: {'enabled' if self.DD_API_KEY else 'disabled'}\n"
            f")"
        )


# Global config instance
config = Config()


def get_config() -> Config:
    """Get the global configuration instance"""
    return config


def reload_config() -> Config:
    """Reload configuration from environment (useful for testing)"""
    global config
    config = Config()
    return config
