"""Tests for Datadog APM and metrics integration (Phase 3)"""
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

# Import the module under test
from src.datadog_integration import (
    init_datadog,
    trace_search_operation,
    record_metric,
    query_apm_traces,
    query_metrics,
    _reset_for_testing
)


@pytest.fixture(autouse=True)
def reset_datadog_state():
    """Reset Datadog module state before each test"""
    _reset_for_testing()
    yield
    _reset_for_testing()


def test_datadog_disabled_by_default():
    """Test that Datadog is disabled when not configured"""
    # Without proper credentials, init should return False
    result = init_datadog(
        api_key=None,
        app_key=None,
        site="datadoghq.com",
        service_name="test-service"
    )
    assert result is False, "Datadog should be disabled without credentials"


@patch('src.datadog_integration.dd_initialize')
@patch('src.datadog_integration.patch_all')
@patch('src.datadog_integration.ApiClient')
@patch('src.datadog_integration.Configuration')
def test_datadog_initialization(mock_config, mock_api_client, mock_patch_all, mock_dd_init):
    """Test successful Datadog initialization with all components"""
    # Setup mocks
    mock_api_instance = MagicMock()
    mock_api_client.return_value = mock_api_instance
    
    # Call init with valid credentials
    result = init_datadog(
        api_key="test-api-key",
        app_key="test-app-key",
        site="datadoghq.com",
        service_name="log-ai-mcp",
        env="test",
        version="1.0.0",
        agent_host="localhost",
        agent_port=8125,
        trace_agent_port=8126
    )
    
    # Verify initialization succeeded
    assert result is True, "Datadog should initialize with valid config"
    
    # Verify dd_initialize was called (for StatsD)
    mock_dd_init.assert_called_once()
    
    # Verify patch_all was called for auto-instrumentation
    mock_patch_all.assert_called_once_with(asyncio=True, redis=True)


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._tracer')
@patch('src.datadog_integration._config', {"service_name": "log-ai-mcp"})
def test_trace_context_manager(mock_tracer):
    """Test trace_search_operation context manager creates spans"""
    mock_span = MagicMock()
    mock_tracer.trace.return_value = mock_span
    
    # Use the context manager
    with trace_search_operation(
        service="hub-ca-auth",
        pattern="ERROR",
        time_range={"hours_back": 24}
    ) as span:
        assert span is not None
        if span:
            span.set_tag("custom.tag", "value")
    
    # Verify trace was called
    mock_tracer.trace.assert_called_once_with(
        "log_search",
        service="log-ai-mcp",
        resource="search:hub-ca-auth",
        span_type="custom"
    )


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_metric_recording(mock_statsd_client):
    """Test metric recording via DogStatsD"""
    # Record a metric
    record_metric(
        metric_name="search.duration",
        value=1.25,
        tags=["service:hub-ca-auth", "status:success"],
        metric_type="histogram"
    )
    
    # Verify histogram was called on the statsd client
    # Note: metric name is NOT prefixed with "log_ai." in the actual implementation
    mock_statsd_client.histogram.assert_called_once_with(
        "search.duration",
        1.25,
        tags=["service:hub-ca-auth", "status:success"]
    )


def test_uninitialized_graceful_degradation():
    """Test that functions handle uninitialized state gracefully"""
    # These should not raise exceptions even if Datadog is not initialized
    from datetime import datetime, timedelta
    
    # Tracing context manager should return nullcontext/None
    with trace_search_operation(
        service="test-service",
        pattern="pattern",
        time_range={"hours_back": 1}
    ) as span:
        # Should work but be a no-op (span will be None)
        if span is not None:
            span.set_tag("test", "value")  # Should be safe to call if not None
    
    # Metric recording should be silent no-op
    record_metric(
        metric_name="test.metric",
        value=1.0,
        metric_type="gauge",
        tags=["env:test"]
    )
    
    # Query functions should return placeholder results
    now = datetime.utcnow()
    traces_result = query_apm_traces(
        service="test-service",
        start_time=now - timedelta(hours=1),
        end_time=now
    )
    assert isinstance(traces_result, dict)
    assert "error" in traces_result
    
    metrics_result = query_metrics(
        metric_query="test.metric{*}",
        start_time=now - timedelta(hours=1),
        end_time=now
    )
    assert isinstance(metrics_result, dict)
    assert "error" in metrics_result


@pytest.mark.parametrize("metric_type,expected_method", [
    ("gauge", "gauge"),
    ("count", "increment"),  # Changed from "counter" to "count"
    ("histogram", "histogram"),
    ("rate", "rate"),  # Changed from "distribution" to "rate"
])
@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_metric_types(mock_statsd_client, metric_type, expected_method):
    """Test different metric types are handled correctly"""
    record_metric(
        metric_name="test.metric",
        value=42,
        metric_type=metric_type,
        tags=["env:test"]
    )
    
    # Verify the correct method was called
    getattr(mock_statsd_client, expected_method).assert_called_once()


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._tracer')
@patch('src.datadog_integration._config', {"service_name": "log-ai-mcp"})
def test_trace_operation_with_error(mock_tracer):
    """Test that span captures errors when exceptions occur"""
    mock_span = MagicMock()
    mock_tracer.trace.return_value = mock_span
    
    try:
        with trace_search_operation(
            service="test-service",
            pattern="pattern",
            time_range={"hours_back": 1}
        ) as span:
            raise ValueError("Test error")
    except ValueError:
        pass
    
    # Verify span was created
    mock_tracer.trace.assert_called_once()
    # Verify span.finish() was called (happens in finally block)
    mock_span.finish.assert_called_once()

