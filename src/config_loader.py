"""
Configuration loader for log-ai MCP server.
Loads settings from environment variables with sensible defaults.
"""
import os
from typing import Optional


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
        """Load configuration from environment variables with defaults"""
        
        # Redis Configuration
        self.REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
        self.REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
        self.REDIS_MAX_MEMORY = os.environ.get("REDIS_MAX_MEMORY", "500mb")
        self.REDIS_PERSISTENCE = os.environ.get("REDIS_PERSISTENCE", "false").lower() in ("true", "1", "yes")
        self.REDIS_ENABLED = os.environ.get("REDIS_ENABLED", "true").lower() in ("true", "1", "yes")
        
        # Global Concurrency Limits
        self.MAX_GLOBAL_SEARCHES = int(os.environ.get("MAX_GLOBAL_SEARCHES", "20"))
        self.MAX_PARALLEL_SEARCHES_PER_CALL = int(os.environ.get("MAX_PARALLEL_SEARCHES_PER_CALL", "5"))
        
        # Cache Configuration
        self.CACHE_MAX_SIZE_MB = int(os.environ.get("CACHE_MAX_SIZE_MB", "500"))
        self.CACHE_MAX_ENTRIES = int(os.environ.get("CACHE_MAX_ENTRIES", "100"))
        self.CACHE_TTL_MINUTES = int(os.environ.get("CACHE_TTL_MINUTES", "10"))
        
        # Search Limits
        self.AUTO_CANCEL_TIMEOUT_SECONDS = int(os.environ.get("AUTO_CANCEL_TIMEOUT_SECONDS", "300"))
        self.MAX_IN_MEMORY_MATCHES = int(os.environ.get("MAX_IN_MEMORY_MATCHES", "1000"))
        
        # File Output
        self.FILE_RETENTION_HOURS = int(os.environ.get("FILE_RETENTION_HOURS", "24"))
        self.CLEANUP_INTERVAL_HOURS = int(os.environ.get("CLEANUP_INTERVAL_HOURS", "1"))
        
        # Logging
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.environ.get("LOG_FORMAT", "text")
        
        # Sentry Configuration (Chunk 2)
        self.SENTRY_DSN = os.environ.get("SENTRY_DSN")
        self.SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0"))
        self.SENTRY_PROFILES_SAMPLE_RATE = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))
        self.SENTRY_ALERT_TEAMS_WEBHOOK = os.environ.get("SENTRY_ALERT_TEAMS_WEBHOOK")
        self.SENTRY_ALERT_SLACK_WEBHOOK = os.environ.get("SENTRY_ALERT_SLACK_WEBHOOK")
        
        # Datadog Configuration (Chunk 3)
        self.DD_API_KEY = os.environ.get("DD_API_KEY")
        self.DD_APP_KEY = os.environ.get("DD_APP_KEY")
        self.DD_SITE = os.environ.get("DD_SITE", "datadoghq.com")
    
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
