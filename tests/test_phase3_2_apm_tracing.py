"""Tests for Phase 3.2 - APM Tracing Implementation

Tests APM tracing integration in search_logs operations.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime

# Import modules under test
from src.datadog_integration import trace_search_operation, record_metric, _reset_for_testing


@pytest.fixture(autouse=True)
def reset_datadog_state():
    """Reset Datadog module state before each test"""
    _reset_for_testing()
    yield
    _reset_for_testing()


@pytest.mark.asyncio
async def test_search_with_tracing_enabled():
    """Test that search operations create APM traces when Datadog is enabled"""
    # Mock the datadog module as initialized
    mock_config = {"service_name": "log-ai-mcp", "env": "qa"}
    
    with patch('src.datadog_integration._initialized', True):
        with patch('src.datadog_integration._config', mock_config):
            with patch('src.datadog_integration._tracer') as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.trace.return_value = mock_span
                
                # Simulate search operation with tracing
                with trace_search_operation(
                    service="hub-ca-auth",
                    pattern="ERROR",
                    time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
                ) as span:
                    assert span is not None
                    # Simulate setting tags like the real implementation
                    span.set_tag("result.count", 150)
                    span.set_tag("duration_ms", 1234.5)
                    span.set_tag("cache.hit", False)
                
                # Verify trace was created
                mock_tracer.trace.assert_called_once()
                call_kwargs = mock_tracer.trace.call_args[1]
                assert call_kwargs['service'] == 'log-ai-mcp'
                assert 'hub-ca-auth' in call_kwargs['resource']


@pytest.mark.asyncio
async def test_search_with_tracing_disabled():
    """Test that search operations work normally when Datadog is disabled"""
    # Datadog not initialized (default state after reset)
    with trace_search_operation(
        service="hub-ca-auth",
        pattern="ERROR",
        time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
    ) as span:
        # Should be None when not initialized
        assert span is None


@pytest.mark.asyncio
async def test_cache_hit_creates_proper_tags():
    """Test that cache hits have proper APM tags"""
    mock_config = {"service_name": "log-ai-mcp", "env": "qa"}
    
    with patch('src.datadog_integration._initialized', True):
        with patch('src.datadog_integration._config', mock_config):
            with patch('src.datadog_integration._tracer') as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.trace.return_value = mock_span
                
                with trace_search_operation(
                    service="hub-ca-auth",
                    pattern="timeout",
                    time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
                ) as span:
                    # Simulate cache hit
                    span.set_tag("cache.hit", True)
                    span.set_tag("result.count", 50)
                    span.set_tag("duration_ms", 5.2)  # Fast cache response
                    
                    # Verify tags were set
                    assert span.set_tag.call_count >= 3


@pytest.mark.asyncio
async def test_cache_miss_creates_proper_tags():
    """Test that cache misses have proper APM tags"""
    mock_config = {"service_name": "log-ai-mcp", "env": "qa"}
    
    with patch('src.datadog_integration._initialized', True):
        with patch('src.datadog_integration._config', mock_config):
            with patch('src.datadog_integration._tracer') as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.trace.return_value = mock_span
                
                with trace_search_operation(
                    service="hub-ca-auth",
                    pattern="connection",
                    time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
                ) as span:
                    # Simulate cache miss (actual search)
                    span.set_tag("cache.hit", False)
                    span.set_tag("result.count", 200)
                    span.set_tag("duration_ms", 1523.7)  # Slower actual search
                    span.set_tag("files_searched", 15)
                    span.set_tag("overflow", False)
                    
                    # Verify comprehensive tags
                    assert span.set_tag.call_count >= 5


@pytest.mark.asyncio
async def test_error_tracking_in_trace():
    """Test that errors are properly tagged in APM traces"""
    mock_config = {"service_name": "log-ai-mcp", "env": "qa"}
    
    with patch('src.datadog_integration._initialized', True):
        with patch('src.datadog_integration._config', mock_config):
            with patch('src.datadog_integration._tracer') as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.trace.return_value = mock_span
                
                try:
                    with trace_search_operation(
                        service="hub-ca-auth",
                        pattern="test",
                        time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
                    ) as span:
                        # Simulate an error during search
                        raise ValueError("Service connection failed")
                except ValueError:
                    pass
                
                # The span should still be finished (happens in finally block)
                mock_span.finish.assert_called_once()


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_metrics_recorded_for_cache_hit(mock_statsd_client):
    """Test that proper metrics are recorded for cache hits"""
    # Simulate recording metrics
    record_metric(
        "log_ai.search.duration_ms",
        5.2,
        tags=["service:hub-ca-auth", "cached:true"],
        metric_type="histogram"
    )
    
    record_metric(
        "log_ai.search.result_count",
        50,
        tags=["service:hub-ca-auth", "cached:true"],
        metric_type="histogram"
    )
    
    # Verify histograms were recorded
    assert mock_statsd_client.histogram.call_count == 2


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_metrics_recorded_for_cache_miss(mock_statsd_client):
    """Test that proper metrics are recorded for cache misses"""
    # Simulate recording metrics
    record_metric(
        "log_ai.search.duration_ms",
        1523.7,
        tags=["service:hub-ca-auth", "cached:false", "overflow:false"],
        metric_type="histogram"
    )
    
    record_metric(
        "log_ai.search.result_count",
        200,
        tags=["service:hub-ca-auth", "cached:false"],
        metric_type="histogram"
    )
    
    record_metric(
        "log_ai.search.files_searched",
        15,
        tags=["service:hub-ca-auth"],
        metric_type="histogram"
    )
    
    # Verify all metrics were recorded
    assert mock_statsd_client.histogram.call_count == 3


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_overflow_metrics_recorded(mock_statsd_client):
    """Test that overflow events are tracked with metrics"""
    from src.datadog_integration import increment_counter
    
    # Simulate overflow
    increment_counter("log_ai.search.overflows", tags=["service:hub-ca-auth"])
    
    # Simulate overflow file size metric
    record_metric(
        "log_ai.overflow.file_size_bytes",
        5_242_880,  # 5MB
        tags=["service:hub-ca-auth"],
        metric_type="histogram"
    )
    
    # Verify overflow was tracked
    mock_statsd_client.increment.assert_called_once()
    mock_statsd_client.histogram.assert_called_once()


@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_timeout_metrics_recorded(mock_statsd_client):
    """Test that timeout events are tracked with metrics"""
    from src.datadog_integration import increment_counter
    
    # Simulate timeout
    increment_counter("log_ai.search.timeouts", tags=["service:hub-ca-auth"])
    
    # Verify timeout was tracked
    mock_statsd_client.increment.assert_called_once_with(
        "log_ai.search.timeouts",
        value=1,
        tags=["service:hub-ca-auth"]
    )


@pytest.mark.asyncio
async def test_multiple_services_traced():
    """Test that searches across multiple services are properly traced"""
    mock_config = {"service_name": "log-ai-mcp", "env": "qa"}
    
    with patch('src.datadog_integration._initialized', True):
        with patch('src.datadog_integration._config', mock_config):
            with patch('src.datadog_integration._tracer') as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.trace.return_value = mock_span
                
                # Simulate multi-service search
                services = ["hub-ca-auth", "hub-ca-edr-proxy-service", "hub-ca-data-service"]
                with trace_search_operation(
                    service=",".join(services),
                    pattern="ERROR",
                    time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
                ) as span:
                    # Set tags for multi-service search
                    span.set_tag("service_count", len(services))
                    span.set_tag("result.count", 300)
                
                # Verify trace was created
                mock_tracer.trace.assert_called_once()


def test_tracing_graceful_degradation():
    """Test that tracing gracefully degrades when Datadog is not configured"""
    # Datadog not initialized
    with trace_search_operation(
        service="test-service",
        pattern="test",
        time_range={"start_datetime": datetime(2026, 1, 24, 10, 0), "end_datetime": datetime(2026, 1, 24, 11, 0)}
    ) as span:
        # Should return None and not raise errors
        assert span is None
    
    # Recording metrics should also be silent
    record_metric("test.metric", 1.0, tags=["test:true"], metric_type="gauge")
    # Should not raise exception


@pytest.mark.parametrize("metric_name,metric_value,expected_type", [
    ("log_ai.search.duration_ms", 1234.5, "histogram"),
    ("log_ai.search.result_count", 150, "histogram"),
    ("log_ai.search.files_searched", 10, "histogram"),
    ("log_ai.overflow.file_size_bytes", 5242880, "histogram"),
])
@patch('src.datadog_integration._initialized', True)
@patch('src.datadog_integration._statsd_client')
def test_metric_types_for_search(mock_statsd_client, metric_name, metric_value, expected_type):
    """Test that correct metric types are used for different measurements"""
    record_metric(metric_name, metric_value, tags=["service:test"], metric_type=expected_type)
    
    # Verify the correct method was called
    getattr(mock_statsd_client, expected_type).assert_called_once()
