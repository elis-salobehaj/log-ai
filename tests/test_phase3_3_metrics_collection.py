"""Tests for Phase 3.3 - Metrics Collection

Tests comprehensive application and infrastructure metrics collection.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

# Import modules under test
from src.metrics_collector import (
    MetricsCollector,
    get_metrics_collector,
    reset_metrics_collector
)


@pytest.fixture(autouse=True)
def reset_metrics_state():
    """Reset metrics collector before each test"""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


def test_metrics_collector_initialization():
    """Test that metrics collector initializes with zero counters"""
    collector = MetricsCollector()
    
    assert collector.cache_hits == 0
    assert collector.cache_misses == 0
    assert collector.total_searches == 0
    assert collector.searches_with_overflow == 0
    assert collector.searches_with_timeout == 0
    assert len(collector.errors_by_type) == 0


def test_cache_hit_recording():
    """Test recording cache hits updates counters"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        collector.record_cache_hit("hub-ca-auth")
        collector.record_cache_hit("hub-ca-auth")
        collector.record_cache_hit("hub-ca-auth")
    
    assert collector.cache_hits == 3
    assert collector.cache_misses == 0
    assert collector.total_searches == 3


def test_cache_miss_recording():
    """Test recording cache misses updates counters"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        collector.record_cache_miss("hub-ca-auth")
        collector.record_cache_miss("hub-ca-auth")
    
    assert collector.cache_hits == 0
    assert collector.cache_misses == 2
    assert collector.total_searches == 2


def test_cache_hit_rate_calculation():
    """Test that cache hit rate is calculated correctly"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        # 3 hits, 1 miss = 75% hit rate
        collector.record_cache_hit("test-service")
        collector.record_cache_hit("test-service")
        collector.record_cache_hit("test-service")
        collector.record_cache_miss("test-service")
    
    summary = collector.get_summary()
    assert summary["cache_hit_rate_pct"] == 75.0
    assert summary["total_searches"] == 4


@patch('src.metrics_collector.is_datadog_configured', return_value=True)
@patch('src.metrics_collector.record_metric')
def test_cache_hit_rate_sent_to_datadog(mock_record_metric, mock_is_configured):
    """Test that cache hit rate gauge is sent to Datadog"""
    collector = MetricsCollector()
    
    # Record some cache hits and misses
    collector.record_cache_hit("hub-ca-auth")
    collector.record_cache_miss("hub-ca-auth")
    
    # Verify gauge metric was sent
    calls = [call for call in mock_record_metric.call_args_list 
             if call[0][0] == "log_ai.search.cache_hit_rate"]
    assert len(calls) >= 1
    
    # Check the gauge value (50% hit rate)
    last_call = calls[-1]
    assert last_call[0][1] == 50.0  # 1 hit / 2 total = 50%
    assert "metric_type" in last_call[1]
    assert last_call[1]["metric_type"] == "gauge"


def test_overflow_recording():
    """Test recording overflow events"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        collector.record_cache_miss("test-service")  # Start a search
        collector.record_overflow("test-service")
        collector.record_overflow("test-service")
    
    assert collector.searches_with_overflow == 2
    assert collector.total_searches == 1


def test_overflow_rate_calculation():
    """Test that overflow rate is calculated correctly"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        # 2 searches, 1 with overflow = 50% overflow rate
        collector.record_cache_miss("test-service")
        collector.record_overflow("test-service")
        collector.record_cache_miss("test-service")
    
    summary = collector.get_summary()
    assert summary["overflow_rate_pct"] == 50.0
    assert summary["searches_with_overflow"] == 1
    assert summary["total_searches"] == 2


@patch('src.metrics_collector.is_datadog_configured', return_value=True)
@patch('src.metrics_collector.record_metric')
def test_overflow_rate_sent_to_datadog(mock_record_metric, mock_is_configured):
    """Test that overflow rate gauge is sent to Datadog"""
    collector = MetricsCollector()
    
    # Record search with overflow
    collector.record_cache_miss("hub-ca-auth")
    collector.record_overflow("hub-ca-auth")
    
    # Verify overflow rate gauge was sent
    calls = [call for call in mock_record_metric.call_args_list 
             if call[0][0] == "log_ai.search.overflow_rate"]
    assert len(calls) == 1
    assert calls[0][0][1] == 100.0  # 1 overflow / 1 search = 100%


def test_timeout_recording():
    """Test recording timeout events"""
    collector = MetricsCollector()
    
    collector.record_timeout("test-service")
    collector.record_timeout("test-service")
    
    assert collector.searches_with_timeout == 2


def test_error_recording():
    """Test recording errors by type"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        collector.record_error("TimeoutError", "hub-ca-auth")
        collector.record_error("TimeoutError", "hub-ca-auth")
        collector.record_error("ServiceNotFound", "unknown-service")
    
    assert collector.errors_by_type["TimeoutError"] == 2
    assert collector.errors_by_type["ServiceNotFound"] == 1


@patch('src.metrics_collector.is_datadog_configured', return_value=True)
@patch('src.metrics_collector.record_metric')
def test_error_metrics_sent_to_datadog(mock_record_metric, mock_is_configured):
    """Test that error counts are sent to Datadog"""
    collector = MetricsCollector()
    
    collector.record_error("ValueError", "test-service")
    collector.record_error("ConnectionError", "test-service")
    
    # Verify error metrics were sent
    calls = [call for call in mock_record_metric.call_args_list 
             if call[0][0] == "log_ai.errors.total"]
    assert len(calls) == 2


@patch('src.metrics_collector.is_datadog_configured', return_value=True)
@patch('src.metrics_collector.record_metric')
def test_semaphore_utilization_reporting(mock_record_metric, mock_is_configured):
    """Test reporting semaphore utilization"""
    collector = MetricsCollector()
    
    collector.report_semaphore_utilization(available_slots=15, max_slots=20)
    
    # Verify both metrics were sent
    available_calls = [call for call in mock_record_metric.call_args_list 
                      if call[0][0] == "log_ai.semaphore.available"]
    utilization_calls = [call for call in mock_record_metric.call_args_list 
                        if call[0][0] == "log_ai.semaphore.utilization_pct"]
    
    assert len(available_calls) == 1
    assert len(utilization_calls) == 1
    
    # Check values
    assert available_calls[0][0][1] == 15
    assert utilization_calls[0][0][1] == 25.0  # (20-15)/20 * 100


@patch('src.metrics_collector.is_datadog_configured', return_value=True)
@patch('src.metrics_collector.record_metric')
def test_redis_pool_reporting(mock_record_metric, mock_is_configured):
    """Test reporting Redis connection pool status"""
    collector = MetricsCollector()
    
    collector.report_redis_pool_status(active_connections=8, max_connections=10)
    
    # Verify both metrics were sent
    pool_calls = [call for call in mock_record_metric.call_args_list 
                 if call[0][0] == "log_ai.redis.connection_pool"]
    utilization_calls = [call for call in mock_record_metric.call_args_list 
                        if call[0][0] == "log_ai.redis.pool_utilization_pct"]
    
    assert len(pool_calls) == 1
    assert len(utilization_calls) == 1
    
    # Check values
    assert pool_calls[0][0][1] == 8
    assert utilization_calls[0][0][1] == 80.0  # 8/10 * 100


def test_metrics_summary():
    """Test that metrics summary contains all expected fields"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        # Simulate some activity
        collector.record_cache_hit("test-service")
        collector.record_cache_miss("test-service")
        collector.record_overflow("test-service")
        collector.record_timeout("test-service")
        collector.record_error("TestError", "test-service")
    
    summary = collector.get_summary()
    
    assert "cache_hits" in summary
    assert "cache_misses" in summary
    assert "cache_hit_rate_pct" in summary
    assert "total_searches" in summary
    assert "searches_with_overflow" in summary
    assert "overflow_rate_pct" in summary
    assert "searches_with_timeout" in summary
    assert "errors_by_type" in summary
    
    assert summary["cache_hits"] == 1
    assert summary["cache_misses"] == 1
    assert summary["total_searches"] == 2
    assert summary["searches_with_overflow"] == 1
    assert summary["searches_with_timeout"] == 1
    assert summary["errors_by_type"]["TestError"] == 1


def test_metrics_reset():
    """Test that metrics can be reset to zero"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        # Add some data
        collector.record_cache_hit("test-service")
        collector.record_cache_miss("test-service")
        collector.record_error("TestError", "test-service")
    
    # Reset
    collector.reset()
    
    # Verify all counters are zero
    assert collector.cache_hits == 0
    assert collector.cache_misses == 0
    assert collector.total_searches == 0
    assert collector.searches_with_overflow == 0
    assert collector.searches_with_timeout == 0
    assert len(collector.errors_by_type) == 0


def test_global_metrics_collector():
    """Test that get_metrics_collector returns singleton instance"""
    collector1 = get_metrics_collector()
    collector2 = get_metrics_collector()
    
    assert collector1 is collector2
    
    # Modify via one reference
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        collector1.record_cache_hit("test-service")
    
    # Verify via other reference
    assert collector2.cache_hits == 1


def test_metrics_with_no_datadog():
    """Test that metrics collection works gracefully when Datadog is disabled"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        # Should not raise exceptions
        collector.record_cache_hit("test-service")
        collector.record_cache_miss("test-service")
        collector.record_overflow("test-service")
        collector.record_error("TestError")
        collector.report_semaphore_utilization(10, 20)
        collector.report_redis_pool_status(5, 10)
    
    # Counters should still update
    summary = collector.get_summary()
    assert summary["total_searches"] == 2
    assert summary["searches_with_overflow"] == 1


@pytest.mark.parametrize("hit_count,miss_count,expected_rate", [
    (10, 0, 100.0),    # 100% hit rate
    (0, 10, 0.0),      # 0% hit rate
    (5, 5, 50.0),      # 50% hit rate
    (7, 3, 70.0),      # 70% hit rate
    (1, 9, 10.0),      # 10% hit rate
])
def test_cache_hit_rate_calculations(hit_count, miss_count, expected_rate):
    """Test various cache hit rate scenarios"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        for _ in range(hit_count):
            collector.record_cache_hit("test-service")
        for _ in range(miss_count):
            collector.record_cache_miss("test-service")
    
    summary = collector.get_summary()
    assert summary["cache_hit_rate_pct"] == expected_rate


@pytest.mark.parametrize("total_searches,overflows,expected_rate", [
    (10, 0, 0.0),      # 0% overflow rate
    (10, 10, 100.0),   # 100% overflow rate
    (10, 5, 50.0),     # 50% overflow rate
    (20, 3, 15.0),     # 15% overflow rate
])
def test_overflow_rate_calculations(total_searches, overflows, expected_rate):
    """Test various overflow rate scenarios"""
    collector = MetricsCollector()
    
    with patch('src.metrics_collector.is_datadog_configured', return_value=False):
        for _ in range(total_searches):
            collector.record_cache_miss("test-service")
        for _ in range(overflows):
            collector.record_overflow("test-service")
    
    summary = collector.get_summary()
    assert summary["overflow_rate_pct"] == expected_rate
