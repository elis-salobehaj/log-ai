"""Sentry integration for error tracking and performance monitoring"""
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import os
import logging
import requests
from typing import Optional, Dict, List, Any
from src.config import ServiceConfig
from src.config_loader import get_config

def init_sentry():
    """Initialize Sentry SDK with default/fallback DSN (per-service DSNs used at capture time)"""
    # Check if we should enable Sentry at all
    # We don't require a global DSN anymore - services can have individual DSNs
    print("[SENTRY] Initialized (per-service DSN mode)")
    print("[SENTRY] Services will send to their configured Sentry projects")
    return True
    
    # Parse configuration
    environment = os.environ.get("SENTRY_ENVIRONMENT", "qa")
    traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0"))
    profiles_sample_rate = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))
    
    sentry_sdk.init(
        dsn=dsn,
        
        # Enable performance monitoring
        traces_sample_rate=traces_sample_rate,
        
        # Enable profiling
        profiles_sample_rate=profiles_sample_rate,
        
        # Integrations
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            ),
        ],
        
        # Environment (qa, production, etc.)
        environment=environment,
        
        # Release tracking (from git)
        release=f"log-ai@{get_git_version()}",
        
        # Additional context
        before_send=enrich_event,
    )
    
    print(f"[SENTRY] Initialized (DSN: {dsn[:30]}..., environment: {environment}, release: {get_git_version()})")
    return True


def get_git_version() -> str:
    """Get current git commit hash for release tracking"""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=os.path.dirname(os.path.dirname(__file__))  # Go to repo root
        )
        return result.stdout.strip() or "unknown"
    except:
        return "unknown"


def enrich_event(event, hint):
    """Add custom context to Sentry events"""
    # Add SSH session info if available
    ssh_connection = os.environ.get("SSH_CONNECTION")
    if ssh_connection:
        event.setdefault("tags", {})["ssh_client_ip"] = ssh_connection.split()[0]
    
    # Add user info
    user = os.environ.get("USER") or os.environ.get("SYSLOG_USER")
    if user:
        event.setdefault("user", {})["username"] = user
    
    return event


def _send_to_service_sentry(dsn: str, capture_func):
    """
    Temporarily configure Sentry with service-specific DSN and capture event
    
    This allows each service to send errors/metrics to its own Sentry project
    """
    # Parse environment
    environment = os.environ.get("SENTRY_ENVIRONMENT", "qa")
    traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0"))
    profiles_sample_rate = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))
    
    # Initialize Sentry with this service's DSN
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        environment=environment,
        release=f"log-ai@{get_git_version()}",
        before_send=enrich_event,
    )
    
    # Capture the event
    try:
        capture_func()
    finally:
        # Flush events before potentially re-initializing with different DSN
        sentry_sdk.flush()


def capture_search_performance(
    service_config: ServiceConfig,
    pattern: str,
    duration_ms: float,
    matched_files: int,
    result_count: int,
    cache_hit: bool = False
):
    """
    Track search performance in Sentry, associated with service's Sentry project
    
    Uses per-service DSN from service_config.sentry_dsn to send metrics to
    the correct Sentry project for that service.
    """
    # Check if service has Sentry configured
    if not service_config.sentry_dsn:
        return  # No DSN configured for this service, skip
    
    # Use service-specific DSN
    _send_to_service_sentry(service_config.sentry_dsn, lambda: _capture_performance(
        service_config, pattern, duration_ms, matched_files, result_count, cache_hit
    ))

def _capture_performance(
    service_config: ServiceConfig,
    pattern: str,
    duration_ms: float,
    matched_files: int,
    result_count: int,
    cache_hit: bool
):
    """Internal function to capture performance after DSN is set"""
    service_name = service_config.sentry_service_name or service_config.name
    
    with sentry_sdk.push_scope() as scope:
        # Tag with service for routing to correct Sentry project
        scope.set_tag("service", service_name)
        scope.set_tag("log_ai_service", service_config.name)
        scope.set_tag("cache_hit", cache_hit)
        
        with sentry_sdk.start_transaction(
            op="search",
            name=f"search_logs:{service_name}"
        ) as transaction:
            transaction.set_tag("service", service_name)
            transaction.set_tag("pattern_length", len(pattern))
            transaction.set_measurement("duration_ms", duration_ms)
            transaction.set_measurement("matched_files", matched_files)
            transaction.set_measurement("result_count", result_count)
            
            # Flag slow searches
            if duration_ms > 5000:
                transaction.set_tag("slow_search", True)
            
            # Add breadcrumb
            sentry_sdk.add_breadcrumb(
                category="search",
                message=f"Search completed: {result_count} results in {duration_ms:.0f}ms",
                level="info",
                data={
                    "service": service_name,
                    "matched_files": matched_files,
                    "cache_hit": cache_hit
                }
            )


def capture_error_context(
    error: Exception,
    service_config: ServiceConfig,
    search_params: dict,
    user_ip: Optional[str] = None
):
    """
    Capture error with full context, routed to service's Sentry project
    
    Uses per-service DSN to send errors to the correct Sentry project.
    """
    # Check if service has Sentry configured
    if not service_config.sentry_dsn:
        return  # No DSN configured for this service, skip
    
    # Use service-specific DSN
    _send_to_service_sentry(service_config.sentry_dsn, lambda: _capture_error(
        error, service_config, search_params, user_ip
    ))

def _capture_error(
    error: Exception,
    service_config: ServiceConfig,
    search_params: dict,
    user_ip: Optional[str]
):
    """Internal function to capture error after DSN is set"""
    service_name = service_config.sentry_service_name or service_config.name
    
    with sentry_sdk.push_scope() as scope:
        # Tag for routing to correct service project
        scope.set_tag("service", service_name)
        scope.set_tag("log_ai_service", service_config.name)
        
        # Add search context
        scope.set_context("search", {
            "service": service_config.name,
            "sentry_service": service_name,
            "pattern": search_params.get("query", "")[:100],  # Truncate long patterns
            "date": search_params.get("date", ""),
            "hours_back": search_params.get("hours_back"),
            "minutes_back": search_params.get("minutes_back"),
        })
        
        # Add user context
        if user_ip:
            scope.set_user({"ip_address": user_ip})
        
        # Add breadcrumb before capture
        sentry_sdk.add_breadcrumb(
            category="error",
            message=f"Search failed for {service_config.name}",
            level="error",
            data={"error_type": type(error).__name__}
        )
        
        # Capture exception
        sentry_sdk.capture_exception(error)


def add_search_breadcrumb(service_name: str, action: str, **kwargs):
    """Add a breadcrumb for debugging complex search flows"""
    sentry_sdk.add_breadcrumb(
        category="search",
        message=f"{action}: {service_name}",
        level="info",
        data=kwargs
    )


def set_user_context(username: str = None, ip_address: str = None):
    """Set user context for all subsequent Sentry events"""
    user_data = {}
    
    if username:
        user_data["username"] = username
    
    if ip_address:
        user_data["ip_address"] = ip_address
    
    if user_data:
        sentry_sdk.set_user(user_data)


# =============================================================================
# SENTRY API CLIENT - Query issues, traces, events
# =============================================================================

class SentryAPI:
    """
    Client for Sentry API to query issues, traces, and events.
    Requires SENTRY_AUTH_TOKEN environment variable.
    
    API Documentation: https://docs.sentry.io/api/
    """
    
    def __init__(self):
        # Try to get Sentry URL from multiple sources
        sentry_url = os.environ.get("SENTRY_URL")  # Preferred
        
        if not sentry_url:
            # Try extracting from SENTRY_DSN if available
            sentry_dsn = os.environ.get("SENTRY_DSN", "")
            config = get_config()
            if config.computed_sentry_url in sentry_dsn:
                sentry_url = config.computed_sentry_url
            elif sentry_dsn:
                # Extract base URL from DSN (https://key@host/project -> https://host)
                parts = sentry_dsn.replace("https://", "").split("@")
                if len(parts) > 1:
                    host = parts[1].split("/")[0]
                    sentry_url = f"https://{host}"
        
        # Default to org's Sentry instance from config
        if not sentry_url:
            config = get_config()
            sentry_url = config.computed_sentry_url
        
        self.base_url = sentry_url
        config = get_config()
        self.org = config.org_name  # Organization name from config
        
        self.auth_token = config.sentry_auth_token
        self.environment = os.environ.get("SENTRY_ENVIRONMENT", "qa")
        self._project_cache: Dict[str, int] = {}  # Cache for service \u2192 project ID mapping
        
        if not self.auth_token:
            print("[SENTRY API] WARNING: SENTRY_AUTH_TOKEN not set, API queries disabled")
    
    def _headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
    
    def is_available(self) -> bool:
        """Check if API is configured and available"""
        return bool(self.auth_token and self.base_url)
    
    def _get_project_id(self, service_name: str) -> Optional[int]:
        """
        Resolve service name to Sentry project ID.
        Searches for project with matching slug containing the service name.
        
        Args:
            service_name: Service name (e.g., "auth", "hub-ca-auth")
            
        Returns:
            Project ID or None if not found
        """
        # Check cache first
        if service_name in self._project_cache:
            return self._project_cache[service_name]
        
        try:
            # Fetch all projects
            url = f"{self.base_url}/api/0/organizations/{self.org}/projects/"
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            
            projects = response.json()
            
            # Try exact match first
            for p in projects:
                if p['slug'].lower() == service_name.lower():
                    self._project_cache[service_name] = p['id']
                    return p['id']
            
            # Try partial match (e.g., "auth" → "auth-service")
            service_clean = service_name.lower().replace('hub-ca-', '').replace('hub-us-', '').replace('hub-na-', '').replace('-', '')
            for p in projects:
                slug_clean = p['slug'].lower().replace('-', '')
                if service_clean in slug_clean or slug_clean in service_clean:
                    self._project_cache[service_name] = p['id']
                    return p['id']
                    
            return None
            
        except Exception as e:
            logger.error(f"Failed to resolve project ID for {service_name}: {e}")
            return None
    
    def query_issues(
        self,
        service_name: Optional[str] = None,
        project: Optional[str] = None,
        query: str = "is:unresolved",
        limit: int = 25,
        statsPeriod: str = "24h",
        include_environment: bool = False
    ) -> Dict[str, Any]:
        """
        Query issues for a specific project or service.
        
        Args:
            service_name: Service name (e.g., "auth", "hub-ca-auth") - will be resolved to project ID
            project: Project ID (numeric) - use if known, otherwise service_name is resolved
            query: Sentry query string (e.g., "is:unresolved issue.priority:[high, medium]")
            limit: Max number of issues to return
            statsPeriod: Time period for stats (1h, 24h, 7d, 14d, 30d)
            include_environment: Whether to filter by environment (default: False)
        
        Returns:
            Dict with issues data or error
        
        Example:
            query_issues(service_name="auth", query="is:unresolved", limit=10)
        """
        if not self.is_available():
            return {"error": "Sentry API not configured (missing SENTRY_AUTH_TOKEN)"}
        
        # Resolve service_name to project ID if needed
        if service_name and not project:
            project_id = self._get_project_id(service_name)
            if not project_id:
                return {
                    "error": f"Could not find Sentry project for service: {service_name}",
                    "suggestion": "Check that the service has a corresponding Sentry project"
                }
            project = str(project_id)
        elif not project:
            return {"error": "Must provide either service_name or project parameter"}
        
        try:
            url = f"{self.base_url}/api/0/organizations/{self.org}/issues/"
            
            # Build query string
            query_str = query
            if include_environment:
                query_str = f"{query} environment:{self.environment}"
            
            params = {
                "project": project,
                "query": query_str,
                "limit": limit,
                "statsPeriod": statsPeriod
            }
            
            response = requests.get(url, headers=self._headers(), params=params, timeout=10)
            response.raise_for_status()
            
            issues = response.json()
            
            return {
                "success": True,
                "service": service_name if service_name else f"project-{project}",
                "project_id": project,
                "count": len(issues),
                "issues": issues[:limit],
                "query": query
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Sentry API request failed: {str(e)}",
                "service": service_name if service_name else f"project-{project}"
            }
    
    def get_issue_details(self, issue_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific issue
        
        Args:
            issue_id: Issue ID (e.g., "18")
        
        Returns:
            Dict with issue details or error
        
        Example URL:
        https://sentry.{ORG_DOMAIN}/api/0/organizations/{ORG_NAME}/issues/18/
        """
        if not self.is_available():
            return {"error": "Sentry API not configured"}
        
        try:
            url = f"{self.base_url}/api/0/organizations/{self.org}/issues/{issue_id}/"
            
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            
            issue = response.json()
            
            return {
                "success": True,
                "issue_id": issue_id,
                "issue": issue
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to fetch issue {issue_id}: {str(e)}"
            }
    
    def get_issue_events(self, issue_id: str, limit: int = 10) -> Dict[str, Any]:
        """
        Get recent events for an issue
        
        Args:
            issue_id: Issue ID
            limit: Max number of events
        
        Returns:
            Dict with events or error
        """
        if not self.is_available():
            return {"error": "Sentry API not configured"}
        
        try:
            url = f"{self.base_url}/api/0/organizations/{self.org}/issues/{issue_id}/events/"
            
            params = {"limit": limit}
            
            response = requests.get(url, headers=self._headers(), params=params, timeout=10)
            response.raise_for_status()
            
            events = response.json()
            
            return {
                "success": True,
                "issue_id": issue_id,
                "count": len(events),
                "events": events
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to fetch events for issue {issue_id}: {str(e)}"
            }
    
    def search_traces(
        self,
        project: str,
        query: str = "",
        limit: int = 10,
        statsPeriod: str = "24h"
    ) -> Dict[str, Any]:
        """
        Search performance traces for a project
        
        Args:
            project: Project slug
            query: Search query (e.g., "transaction.duration:>5s")
            limit: Max traces to return
            statsPeriod: Time period
        
        Returns:
            Dict with traces or error
        """
        if not self.is_available():
            return {"error": "Sentry API not configured"}
        
        try:
            url = f"{self.base_url}/api/0/organizations/{self.org}/events/"
            
            params = {
                "project": project,
                "query": f"{query} environment:{self.environment}" if query else f"environment:{self.environment}",
                "field": ["transaction", "transaction.duration", "timestamp"],
                "sort": "-timestamp",
                "per_page": limit,
                "statsPeriod": statsPeriod
            }
            
            response = requests.get(url, headers=self._headers(), params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                "success": True,
                "project": project,
                "environment": self.environment,
                "traces": data.get("data", []),
                "query": query
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to search traces: {str(e)}"
            }
    
    def get_project_stats(self, project: str, statsPeriod: str = "24h") -> Dict[str, Any]:
        """
        Get project-level statistics
        
        Args:
            project: Project slug
            statsPeriod: Time period
        
        Returns:
            Dict with stats or error
        """
        if not self.is_available():
            return {"error": "Sentry API not configured"}
        
        try:
            # Query for error count
            issues_data = self.query_issues(project, query="is:unresolved", statsPeriod=statsPeriod)
            
            return {
                "success": True,
                "project": project,
                "environment": self.environment,
                "period": statsPeriod,
                "unresolved_issues": issues_data.get("count", 0) if issues_data.get("success") else None,
                "stats": {
                    "errors": issues_data.get("count", 0)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get project stats: {str(e)}"
            }


# Global Sentry API client
_sentry_api_client: Optional[SentryAPI] = None


def get_sentry_api() -> SentryAPI:
    """Get or create Sentry API client singleton"""
    global _sentry_api_client
    if _sentry_api_client is None:
        _sentry_api_client = SentryAPI()
    return _sentry_api_client
