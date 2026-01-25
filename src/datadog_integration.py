"""
Datadog integration for APM, metrics, and infrastructure monitoring.

This module provides:
1. APM Tracing - Distributed tracing for log search operations
2. Metrics Collection - DogStatsD metrics for performance monitoring
3. API Queries - Query Datadog for traces, metrics, logs

Architecture:
- ddtrace: APM tracer (automatic async instrumentation)
- datadog.statsd: Metrics submission (DogStatsD protocol)
- datadog_api_client: Query API for dashboards/alerts

CRITICAL: Never write to stdout (corrupts MCP JSON-RPC protocol)
Use sys.stderr or logging for all debug output.

Configuration: Uses Pydantic Settings (config_loader.py), NOT environment variables.
"""

import sys
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from contextlib import contextmanager

# Datadog SDK imports
from ddtrace import tracer, patch_all, config as ddtrace_config
from datadog import initialize as dd_initialize, statsd
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.logs_api import LogsApi
from datadog_api_client.v2.api.metrics_api import MetricsApi

logger = logging.getLogger("log-ai.datadog")

# =============================================================================
# GLOBAL STATE (Module-level singletons)
# =============================================================================

_initialized: bool = False
_tracer: Optional[Any] = None
_statsd_client: Optional[Any] = None
_api_client: Optional[ApiClient] = None
_config: Optional[Dict[str, Any]] = None


def init_datadog(
    api_key: str,
    app_key: str,
    site: str = "datadoghq.com",
    service_name: str = "log-ai-mcp",
    env: str = "production",
    version: str = "1.0.0",
    agent_host: str = "localhost",
    agent_port: int = 8125,
    trace_agent_port: int = 8126
) -> bool:
    """
    Initialize Datadog APM tracer, StatsD client, and API client.
    
    This function is synchronous and should be called during server startup
    (similar to init_sentry in sentry_integration.py).
    
    Args:
        api_key: Datadog API key (for metrics/APM submission)
        app_key: Datadog Application key (for API queries)
        site: Datadog site (datadoghq.com, datadoghq.eu, etc.)
        service_name: Service name for APM traces
        env: Environment (production, staging, development)
        version: Application version for release tracking
        agent_host: Datadog Agent hostname
        agent_port: DogStatsD port (default: 8125)
        trace_agent_port: APM trace agent port (default: 8126)
        
    Returns:
        True if initialization successful, False otherwise
    
    Example:
        >>> if config.dd_configured:
        >>>     init_datadog(
        >>>         api_key=config.dd_api_key,
        >>>         app_key=config.dd_app_key,
        >>>         site=config.dd_site
        >>>     )
    """
    global _initialized, _tracer, _statsd_client, _api_client, _config
    
    if _initialized:
        logger.warning("[DATADOG] Already initialized")
        sys.stderr.write("[DATADOG] Already initialized\n")
        return True
    
    # Validate required credentials
    if not api_key or not app_key:
        sys.stderr.write("[DATADOG] Missing credentials (api_key or app_key)\n")
        return False
    
    try:
        # Store configuration for later use
        _config = {
            "api_key": api_key,
            "app_key": app_key,
            "site": site,
            "service_name": service_name,
            "env": env,
            "version": version,
            "agent_host": agent_host,
            "agent_port": agent_port,
            "trace_agent_port": trace_agent_port
        }
        
        # 1. Initialize DogStatsD client for metrics
        dd_initialize(
            api_key=api_key,
            app_key=app_key,
            statsd_host=agent_host,
            statsd_port=agent_port
        )
        _statsd_client = statsd
        sys.stderr.write(f"[DATADOG] StatsD client initialized: {agent_host}:{agent_port}\n")
        
        # 2. Configure APM tracer using ddtrace.config (no environment variables)
        ddtrace_config.service = service_name
        ddtrace_config.env = env
        ddtrace_config.version = version
        
        # Configure agent URL programmatically
        tracer._agent_url = f"http://{agent_host}:{trace_agent_port}"
        
        _tracer = tracer
        
        # 3. Auto-instrument async libraries
        patch_all(asyncio=True, redis=True)
        sys.stderr.write(f"[DATADOG] APM tracer configured: service={service_name}, env={env}\n")
        
        # 4. Initialize API client for queries
        configuration = Configuration()
        configuration.api_key["apiKeyAuth"] = api_key
        configuration.api_key["appKeyAuth"] = app_key
        configuration.server_variables["site"] = site
        _api_client = ApiClient(configuration)
        sys.stderr.write(f"[DATADOG] API client initialized: site={site}\n")
        
        _initialized = True
        logger.info(f"[DATADOG] Fully initialized: service={service_name}, env={env}, site={site}")
        return True
        
    except Exception as e:
        logger.error(f"[DATADOG] Initialization failed: {e}", exc_info=True)
        sys.stderr.write(f"[DATADOG] ERROR: {e}\n")
        return False


@contextmanager
def trace_search_operation(
    service: str,
    pattern: str,
    time_range: Dict[str, Any]
):
    """
    Create APM trace span for log search operation.
    
    Usage:
        with trace_search_operation("hub-ca-auth", "timeout", {"hours_back": 24}) as span:
            # Perform search
            matches = search_logs(...)
            
            # Add custom tags
            if span:
                span.set_tag("result_count", len(matches))
                span.set_tag("cached", False)
    
    Args:
        service: Service name being searched
        pattern: Search pattern/query
        time_range: Time range dict (hours_back, start_time, etc.)
        
    Yields:
        Span object (or None if Datadog not initialized)
    """
    if not _initialized or not _tracer:
        # Return no-op context manager
        from contextlib import nullcontext
        yield None
        return
    
    span = _tracer.trace(
        "log_search",
        service=_config.get("service_name", "log-ai-mcp"),
        resource=f"search:{service}",
        span_type="custom"
    )
    
    # Set initial tags
    span.set_tags({
        "service_name": service,
        "search_pattern": pattern[:100],  # Truncate long patterns
        "time_range_hours": time_range.get("hours_back", "N/A"),
        "operation": "search_logs"
    })
    
    try:
        yield span
    except Exception as e:
        # Tag error
        span.set_tag("error", True)
        span.set_tag("error.message", str(e))
        raise
    finally:
        span.finish()


def record_metric(
    metric_name: str,
    value: float,
    tags: Optional[List[str]] = None,
    metric_type: str = "gauge"
) -> None:
    """
    Record custom metric to Datadog via DogStatsD.
    
    Args:
        metric_name: Metric name (e.g., "log_ai.search.duration_ms")
        value: Metric value
        tags: Tags for filtering (e.g., ["service:hub-ca-auth", "cached:true"])
        metric_type: gauge, count, histogram, rate
        
    Example:
        >>> record_metric(
        >>>     "log_ai.search.duration_ms",
        >>>     1234.5,
        >>>     tags=["service:hub-ca-auth", "cached:false"],
        >>>     metric_type="histogram"
        >>> )
    """
    if not _initialized or not _statsd_client:
        return
    
    tags = tags or []
    
    try:
        if metric_type == "gauge":
            _statsd_client.gauge(metric_name, value, tags=tags)
        elif metric_type == "count":
            _statsd_client.increment(metric_name, value=int(value), tags=tags)
        elif metric_type == "histogram":
            _statsd_client.histogram(metric_name, value, tags=tags)
        elif metric_type == "rate":
            _statsd_client.rate(metric_name, value, tags=tags)
        else:
            logger.warning(f"[DATADOG] Unknown metric type: {metric_type}")
            
    except Exception as e:
        logger.error(f"[DATADOG] Failed to record metric {metric_name}: {e}")


def increment_counter(
    metric_name: str,
    value: int = 1,
    tags: Optional[List[str]] = None
) -> None:
    """Convenience method to increment a counter"""
    record_metric(metric_name, value, tags, metric_type="count")


def is_configured() -> bool:
    """Check if Datadog is initialized"""
    return _initialized


def _reset_for_testing() -> None:
    """Reset module state (for testing only)"""
    global _initialized, _tracer, _statsd_client, _api_client, _config
    _initialized = False
    _tracer = None
    _statsd_client = None
    _api_client = None
    _config = None


def get_api_client() -> Optional[ApiClient]:
    """Get Datadog API client (for querying traces, metrics, logs)"""
    return _api_client if _initialized else None


# =============================================================================
# API QUERY FUNCTIONS (Phase 3.6)
# =============================================================================

def query_apm_traces(
    service: str,
    start_time: datetime,
    end_time: datetime,
    operation: Optional[str] = None,
    min_duration_ms: Optional[int] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Query APM traces from Datadog APM API.
    
    Args:
        service: Service name to query (e.g., "log-ai-mcp")
        start_time: Start time (UTC)
        end_time: End time (UTC)
        operation: Optional operation name filter (e.g., "log_search")
        min_duration_ms: Optional minimum duration filter (milliseconds)
        limit: Maximum number of traces to return (default: 100)
        
    Returns:
        Dict with traces and metadata:
        {
            "traces": [{"trace_id": "...", "duration_ms": 123, ...}],
            "count": 10,
            "time_range": {"start": "...", "end": "..."},
            "service": "log-ai-mcp"
        }
    """
    if not _initialized or not _api_client:
        return {
            "error": "Datadog not initialized",
            "suggestion": "Enable Datadog by setting DD_ENABLED=true and providing credentials"
        }
    
    try:
        from datadog_api_client.v2.api.spans_api import SpansApi
        from datadog_api_client.v2.model.spans_list_request import SpansListRequest
        from datadog_api_client.v2.model.spans_query_filter import SpansQueryFilter
        from datadog_api_client.v2.model.spans_query_options import SpansQueryOptions
        from datadog_api_client.v2.model.spans_sort import SpansSort
        
        # Build query filter
        query_parts = [f"service:{service}"]
        if operation:
            query_parts.append(f"operation_name:{operation}")
        if min_duration_ms:
            query_parts.append(f"@duration:>{min_duration_ms}ms")
        
        query_str = " ".join(query_parts)
        
        # Create API instance
        api_instance = SpansApi(_api_client)
        
        # Build filter and options as dicts (SDK will convert to models)
        filter_dict = {
            "query": query_str,
            "from": start_time.isoformat() + "Z",
            "to": end_time.isoformat() + "Z"
        }
        
        options_dict = {
            "timezone": "UTC"
        }
        
        page_dict = {
            "limit": limit
        }
        
        # Build request with dict parameters
        request = SpansListRequest(
            filter=filter_dict,
            options=options_dict,
            sort="-timestamp",  # Sort by timestamp descending
            page=page_dict
        )
        
        # Execute query
        response = api_instance.list_spans(body=request)
        
        # Extract traces
        traces = []
        if hasattr(response, 'data') and response.data:
            for span in response.data:
                traces.append({
                    "trace_id": str(span.attributes.get("trace_id", "")),
                    "span_id": str(span.id),
                    "operation": span.attributes.get("operation_name", ""),
                    "resource": span.attributes.get("resource_name", ""),
                    "duration_ms": span.attributes.get("duration", 0) / 1000000,  # nanoseconds to ms
                    "timestamp": span.attributes.get("start", ""),
                    "service": span.attributes.get("service", ""),
                    "tags": span.attributes.get("tags", {})
                })
        
        return {
            "traces": traces,
            "count": len(traces),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "service": service,
            "query": query_str
        }
        
    except Exception as e:
        logger.error(f"[DATADOG] APM query failed: {e}", exc_info=True)
        return {
            "error": f"APM query failed: {str(e)}",
            "service": service
        }


def query_metrics(
    metric_query: str,
    start_time: datetime,
    end_time: datetime
) -> Dict[str, Any]:
    """
    Query metrics from Datadog Metrics API.
    
    Args:
        metric_query: Datadog metric query (e.g., "avg:log_ai.search.duration_ms{*}")
        start_time: Start time (UTC)
        end_time: End time (UTC)
        
    Returns:
        Dict with metric data:
        {
            "series": [{"metric": "...", "points": [[timestamp, value], ...]}],
            "query": "avg:log_ai.search.duration_ms{*}",
            "time_range": {"start": "...", "end": "..."}
        }
    """
    if not _initialized or not _api_client:
        return {
            "error": "Datadog not initialized",
            "suggestion": "Enable Datadog by setting DD_ENABLED=true and providing credentials"
        }
    
    try:
        from datadog_api_client.v1.api.metrics_api import MetricsApi as MetricsApiV1
        
        # Use V1 API for metric queries (more stable)
        api_instance = MetricsApiV1(_api_client)
        
        # Convert to Unix timestamps
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        
        # Query metrics
        response = api_instance.query_metrics(
            _from=start_ts,
            to=end_ts,
            query=metric_query
        )
        
        # Extract series data
        series = []
        if hasattr(response, 'series') and response.series:
            for s in response.series:
                series.append({
                    "metric": s.metric if hasattr(s, 'metric') else "",
                    "display_name": s.display_name if hasattr(s, 'display_name') else "",
                    "unit": getattr(s, 'unit', [{}])[0].get('family', '') if hasattr(s, 'unit') else "",
                    "points": s.pointlist if hasattr(s, 'pointlist') else [],
                    "scope": s.scope if hasattr(s, 'scope') else "",
                    "aggr": s.aggr if hasattr(s, 'aggr') else ""
                })
        
        return {
            "series": series,
            "query": metric_query,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "status": "ok" if series else "no_data"
        }
        
    except Exception as e:
        logger.error(f"[DATADOG] Metrics query failed: {e}", exc_info=True)
        return {
            "error": f"Metrics query failed: {str(e)}",
            "query": metric_query
        }


def query_logs(
    query: str,
    start_time: datetime,
    end_time: datetime,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Query logs from Datadog Log Management API.
    
    Args:
        query: Datadog log query (e.g., "service:log-ai-mcp status:error")
        start_time: Start time (UTC)
        end_time: End time (UTC)
        limit: Maximum number of logs to return (default: 100)
        
    Returns:
        Dict with log entries:
        {
            "logs": [{"timestamp": "...", "message": "...", ...}],
            "count": 10,
            "query": "service:log-ai-mcp status:error"
        }
    """
    if not _initialized or not _api_client:
        return {
            "error": "Datadog not initialized",
            "suggestion": "Enable Datadog by setting DD_ENABLED=true and providing credentials"
        }
    
    try:
        from datadog_api_client.v2.api.logs_api import LogsApi
        from datadog_api_client.v2.model.logs_list_request import LogsListRequest
        from datadog_api_client.v2.model.logs_query_filter import LogsQueryFilter
        from datadog_api_client.v2.model.logs_query_options import LogsQueryOptions
        from datadog_api_client.v2.model.logs_sort import LogsSort
        
        # Create API instance
        api_instance = LogsApi(_api_client)
        
        # Build request with dict parameters
        filter_dict = {
            "query": query,
            "from": start_time.isoformat() + "Z",
            "to": end_time.isoformat() + "Z"
        }
        
        options_dict = {
            "timezone": "UTC"
        }
        
        page_dict = {
            "limit": limit
        }
        
        request = LogsListRequest(
            filter=filter_dict,
            options=options_dict,
            sort="-timestamp",  # Sort by timestamp descending
            page=page_dict
        )
        
        # Execute query
        response = api_instance.list_logs(body=request)
        
        # Extract logs
        logs = []
        if hasattr(response, 'data') and response.data:
            for log in response.data:
                logs.append({
                    "id": log.id,
                    "timestamp": log.attributes.timestamp.isoformat() if hasattr(log.attributes, 'timestamp') else "",
                    "message": log.attributes.message if hasattr(log.attributes, 'message') else "",
                    "service": log.attributes.service if hasattr(log.attributes, 'service') else "",
                    "status": log.attributes.status if hasattr(log.attributes, 'status') else "",
                    "tags": log.attributes.tags if hasattr(log.attributes, 'tags') else [],
                    "trace_id": log.attributes.attributes.get("dd.trace_id", "") if hasattr(log.attributes, 'attributes') else ""
                })
        
        return {
            "logs": logs,
            "count": len(logs),
            "query": query,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"[DATADOG] Logs query failed: {e}", exc_info=True)
        return {
            "error": f"Logs query failed: {str(e)}",
            "query": query
        }
