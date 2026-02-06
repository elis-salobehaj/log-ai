"""
Configuration loader for log-ai MCP server.
Loads settings from config/.env file using Pydantic v2.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Central configuration for log-ai MCP server"""
    
    model_config = SettingsConfigDict(
        env_file='config/.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )
    
    # Organization Configuration
    org_domain: str = Field(default="example.com", description="Organization domain name")
    org_name: str = Field(default="example", description="Organization name")
    
    # Redis Configuration
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: Optional[str] = Field(default=None)
    redis_db: int = Field(default=0)
    redis_max_memory: str = Field(default="500mb")
    redis_persistence: bool = Field(default=False)
    redis_enabled: bool = Field(default=True)
    redis_retry_delay: float = Field(default=0.5)
    redis_max_retries: int = Field(default=100)
    
    # Global Concurrency Limits
    max_global_searches: int = Field(default=20)
    max_parallel_searches_per_call: int = Field(default=5)
    
    # Cache Configuration
    cache_max_size_mb: int = Field(default=500)
    cache_max_entries: int = Field(default=100)
    cache_ttl_minutes: int = Field(default=10)
    
    # Search Limits
    auto_cancel_timeout_seconds: int = Field(default=300)
    preview_matches_limit: int = Field(default=50)
    
    # File Output
    file_output_dir: str = Field(default="/tmp/log-ai")
    file_retention_hours: int = Field(default=24)
    cleanup_interval_hours: int = Field(default=1)
    
    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="text")
    
    # Remote Server Configuration
    syslog_server: Optional[str] = Field(default=None)
    syslog_user: Optional[str] = Field(default=None)
    
    # Sentry Configuration (Optional)
    sentry_url: Optional[str] = Field(default=None)
    sentry_dsn: Optional[str] = Field(default=None)
    sentry_auth_token: Optional[str] = Field(default=None)
    sentry_environment: str = Field(default="qa")
    sentry_traces_sample_rate: float = Field(default=1.0)
    sentry_profiles_sample_rate: float = Field(default=0.1)
    sentry_alert_teams_webhook: Optional[str] = Field(default=None)
    sentry_alert_slack_webhook: Optional[str] = Field(default=None)
    
    # Datadog Configuration (Optional - Phase 3)
    dd_enabled: bool = Field(
        default=False,
        description="Enable Datadog APM and metrics collection"
    )
    dd_api_key: Optional[str] = Field(
        default=None,
        description="Datadog API key for metrics/APM submission"
    )
    dd_app_key: Optional[str] = Field(
        default=None,
        description="Datadog Application key for API queries"
    )
    dd_site: str = Field(
        default="datadoghq.com",
        description="Datadog site (datadoghq.com, datadoghq.eu, us3.datadoghq.com, us5.datadoghq.com)"
    )
    dd_service_name: str = Field(
        default="log-ai-mcp",
        description="Service name in Datadog APM"
    )
    dd_env: str = Field(
        default="production",
        description="Environment (production, staging, development)"
    )
    dd_version: str = Field(
        default="1.0.0",
        description="Application version for release tracking"
    )
    dd_agent_host: str = Field(
        default="localhost",
        description="Datadog Agent hostname (for StatsD/APM)"
    )
    dd_agent_port: int = Field(
        default=8125,
        description="DogStatsD port"
    )
    dd_trace_agent_port: int = Field(
        default=8126,
        description="APM trace agent port"
    )
    send_logs_to_datadog: bool = Field(
        default=False,
        description="Send Python application logs to Datadog for centralized search"
    )
    
    @computed_field
    @property
    def dd_configured(self) -> bool:
        """Check if Datadog is properly configured"""
        return bool(self.dd_enabled and self.dd_api_key and self.dd_app_key)
    
    @computed_field
    @property
    def computed_sentry_url(self) -> str:
        """Compute Sentry URL from org_domain if not explicitly set"""
        if self.sentry_url:
            return self.sentry_url
        return f"https://sentry.{self.org_domain}"
    
    @computed_field
    @property
    def computed_syslog_server(self) -> str:
        """Compute syslog server from org_domain if not explicitly set"""
        if self.syslog_server:
            return self.syslog_server
        return f"syslog.{self.org_domain}"
    def __repr__(self) -> str:
        """String representation (hide sensitive values)"""
        return (
            f"Config(\n"
            f"  Organization: {self.org_name} ({self.org_domain})\n"
            f"  Redis: {self.redis_host}:{self.redis_port} (enabled={self.redis_enabled})\n"
            f"  Max Global Searches: {self.max_global_searches}\n"
            f"  Cache: {self.cache_max_size_mb}MB, {self.cache_max_entries} entries, {self.cache_ttl_minutes}min TTL\n"
            f"  Sentry: {self.computed_sentry_url} ({'enabled' if self.sentry_dsn else 'disabled'})\n"
            f"  Datadog: {'enabled' if self.dd_api_key else 'disabled'}\n"
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
