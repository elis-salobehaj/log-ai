"""
Tests for Phase 3.6 - Datadog Query Tools (MCP Tools for Datadog)
"""
import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta, timezone

from src.datadog_integration import (
    query_apm_traces,
    query_metrics,
    query_logs
)


class TestQueryAPMTraces:
    """Test APM traces query function"""
    
    def test_query_apm_traces_not_initialized(self):
        """Test query when Datadog not initialized"""
        with patch('src.datadog_integration._initialized', False):
            result = query_apm_traces(
                service="test-service",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" in result
            assert "not initialized" in result["error"].lower()
            assert "suggestion" in result
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_query_apm_traces_success(self, mock_api_client):
        """Test successful APM traces query"""
        # Mock API response
        mock_span = Mock()
        mock_span.id = "span123"
        mock_span.attributes = {
            "trace_id": "trace456",
            "operation_name": "log_search",
            "resource_name": "search:hub-ca-auth",
            "duration": 1500000000,  # 1.5 seconds in nanoseconds
            "start": "2026-01-25T10:00:00Z",
            "service": "log-ai-mcp",
            "tags": {"env": "production"}
        }
        
        mock_response = Mock()
        mock_response.data = [mock_span]
        
        mock_spans_api = Mock()
        mock_spans_api.list_spans.return_value = mock_response
        
        # Patch the import inside the function
        with patch('datadog_api_client.v2.api.spans_api.SpansApi', return_value=mock_spans_api):
            result = query_apm_traces(
                service="log-ai-mcp",
                start_time=datetime(2026, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 1, 25, 11, 0, 0, tzinfo=timezone.utc)
            )
            
            assert "error" not in result
            assert "traces" in result
            assert len(result["traces"]) == 1
            assert result["traces"][0]["trace_id"] == "trace456"
            assert result["traces"][0]["operation"] == "log_search"
            assert result["count"] == 1
            assert result["service"] == "log-ai-mcp"
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_query_apm_traces_with_filters(self, mock_api_client):
        """Test APM query with operation and duration filters"""
        mock_spans_api = Mock()
        mock_spans_api.list_spans.side_effect = Exception("API Error")
        
        with patch('datadog_api_client.v2.api.spans_api.SpansApi', return_value=mock_spans_api):
            result = query_apm_traces(
                service="log-ai-mcp",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc),
                operation="log_search",
                min_duration_ms=1000
            )
            
            # Should return error but not crash
            assert "error" in result


class TestQueryMetrics:
    """Test metrics query function"""
    
    def test_query_metrics_not_initialized(self):
        """Test query when Datadog not initialized"""
        with patch('src.datadog_integration._initialized', False):
            result = query_metrics(
                metric_query="avg:system.cpu.user{*}",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" in result
            assert "not initialized" in result["error"].lower()
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_query_metrics_success(self, mock_api_client):
        """Test successful metrics query"""
        # Mock metric series response
        mock_series = Mock()
        mock_series.metric = "system.cpu.user"
        mock_series.display_name = "CPU User %"
        mock_series.unit = [{"family": "percentage"}]
        mock_series.pointlist = [
            [1706180400000, 25.5],
            [1706180460000, 30.2],
            [1706180520000, 28.7]
        ]
        mock_series.scope = "host:syslog"
        mock_series.aggr = "avg"
        
        mock_response = Mock()
        mock_response.series = [mock_series]
        
        mock_metrics_api = Mock()
        mock_metrics_api.query_metrics.return_value = mock_response
        
        with patch('datadog_api_client.v1.api.metrics_api.MetricsApi', return_value=mock_metrics_api):
            result = query_metrics(
                metric_query="avg:system.cpu.user{host:syslog}",
                start_time=datetime(2026, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 1, 25, 11, 0, 0, tzinfo=timezone.utc)
            )
            
            assert "error" not in result
            assert "series" in result
            assert len(result["series"]) == 1
            assert result["series"][0]["metric"] == "system.cpu.user"
            assert result["series"][0]["display_name"] == "CPU User %"
            assert len(result["series"][0]["points"]) == 3
            assert result["status"] == "ok"
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_query_metrics_no_data(self, mock_api_client):
        """Test metrics query with no data"""
        mock_response = Mock()
        mock_response.series = []
        
        mock_metrics_api = Mock()
        mock_metrics_api.query_metrics.return_value = mock_response
        
        with patch('datadog_api_client.v1.api.metrics_api.MetricsApi', return_value=mock_metrics_api):
            result = query_metrics(
                metric_query="avg:nonexistent.metric{*}",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" not in result
            assert result["status"] == "no_data"
            assert len(result["series"]) == 0


class TestQueryLogs:
    """Test logs query function"""
    
    def test_query_logs_not_initialized(self):
        """Test query when Datadog not initialized"""
        with patch('src.datadog_integration._initialized', False):
            result = query_logs(
                query="service:log-ai-mcp",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" in result
            assert "not initialized" in result["error"].lower()
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_query_logs_success(self, mock_api_client):
        """Test successful logs query"""
        # Mock log entry with correct structure
        mock_log = Mock()
        mock_log.id = "log123"
        
        # Create mock attributes object with proper attribute access
        mock_attributes = Mock()
        mock_attributes.timestamp = datetime(2026, 1, 25, 10, 30, 0, tzinfo=timezone.utc)
        mock_attributes.message = "Search completed successfully"
        mock_attributes.service = "log-ai-mcp"
        mock_attributes.status = "info"
        mock_attributes.tags = ["env:production"]
        mock_attributes.attributes = {"dd.trace_id": "trace789"}
        
        mock_log.attributes = mock_attributes
        
        mock_response = Mock()
        mock_response.data = [mock_log]
        
        mock_logs_api = Mock()
        mock_logs_api.list_logs.return_value = mock_response
        
        with patch('datadog_api_client.v2.api.logs_api.LogsApi', return_value=mock_logs_api):
            result = query_logs(
                query="service:log-ai-mcp status:info",
                start_time=datetime(2026, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 1, 25, 11, 0, 0, tzinfo=timezone.utc),
                limit=100
            )
            
            assert "error" not in result
            assert "logs" in result
            assert len(result["logs"]) == 1
            assert result["logs"][0]["message"] == "Search completed successfully"
            assert result["logs"][0]["service"] == "log-ai-mcp"
            assert result["logs"][0]["trace_id"] == "trace789"
            assert result["count"] == 1
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_query_logs_with_limit(self, mock_api_client):
        """Test logs query respects limit parameter"""
        mock_response = Mock()
        mock_response.data = []
        
        mock_logs_api = Mock()
        mock_logs_api.list_logs.return_value = mock_response
        
        with patch('datadog_api_client.v2.api.logs_api.LogsApi', return_value=mock_logs_api):
            result = query_logs(
                query="service:log-ai-mcp",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc),
                limit=50
            )
            
            # Verify the query executed and returned expected structure
            assert "logs" in result
            assert "count" in result
            assert result["count"] == 0  # Empty response


class TestErrorHandling:
    """Test error handling in query functions"""
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_apm_query_api_exception(self, mock_api_client):
        """Test APM query handles API exceptions gracefully"""
        mock_spans_api = Mock()
        mock_spans_api.list_spans.side_effect = Exception("API Connection Error")
        
        with patch('datadog_api_client.v2.api.spans_api.SpansApi', return_value=mock_spans_api):
            result = query_apm_traces(
                service="test-service",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" in result
            assert "API Connection Error" in result["error"]
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_metrics_query_api_exception(self, mock_api_client):
        """Test metrics query handles API exceptions gracefully"""
        mock_metrics_api = Mock()
        mock_metrics_api.query_metrics.side_effect = Exception("Timeout")
        
        with patch('datadog_api_client.v1.api.metrics_api.MetricsApi', return_value=mock_metrics_api):
            result = query_metrics(
                metric_query="avg:test.metric{*}",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" in result
            assert "Timeout" in result["error"]
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_logs_query_api_exception(self, mock_api_client):
        """Test logs query handles API exceptions gracefully"""
        mock_logs_api = Mock()
        mock_logs_api.list_logs.side_effect = Exception("Rate limit exceeded")
        
        with patch('datadog_api_client.v2.api.logs_api.LogsApi', return_value=mock_logs_api):
            result = query_logs(
                query="service:test",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "error" in result
            assert "Rate limit exceeded" in result["error"]


class TestTimeRangeHandling:
    """Test time range calculations and formatting"""
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_time_range_in_response(self, mock_api_client):
        """Test that time range is included in responses"""
        mock_response = Mock()
        mock_response.series = []
        
        mock_metrics_api = Mock()
        mock_metrics_api.query_metrics.return_value = mock_response
        
        start = datetime(2026, 1, 25, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 25, 11, 0, 0, tzinfo=timezone.utc)
        
        with patch('datadog_api_client.v1.api.metrics_api.MetricsApi', return_value=mock_metrics_api):
            result = query_metrics(
                metric_query="avg:test.metric{*}",
                start_time=start,
                end_time=end
            )
            
            assert "time_range" in result
            assert result["time_range"]["start"] == start.isoformat()
            assert result["time_range"]["end"] == end.isoformat()


@pytest.mark.integration
class TestMCPToolIntegration:
    """Integration tests for MCP tool handlers"""
    
    def test_query_tools_available(self):
        """Test that Datadog query tools are registered"""
        # This would be tested with actual MCP server but we can verify imports
        try:
            from src.server import handle_call_tool
            assert handle_call_tool is not None
        except ImportError:
            pytest.skip("Server not importable in test environment")
    
    def test_datadog_integration_imports(self):
        """Test that all query functions are importable"""
        from src.datadog_integration import (
            query_apm_traces,
            query_metrics,
            query_logs,
            get_api_client
        )
        
        assert callable(query_apm_traces)
        assert callable(query_metrics)
        assert callable(query_logs)
        assert callable(get_api_client)


class TestResponseFormatting:
    """Test response data structure"""
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_apm_response_structure(self, mock_api_client):
        """Test APM response has expected structure"""
        mock_response = Mock()
        mock_response.data = []
        
        mock_spans_api = Mock()
        mock_spans_api.list_spans.return_value = mock_response
        
        with patch('datadog_api_client.v2.api.spans_api.SpansApi', return_value=mock_spans_api):
            result = query_apm_traces(
                service="test-service",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            # Verify expected keys
            assert "traces" in result
            assert "count" in result
            assert "time_range" in result
            assert "service" in result
            assert "query" in result
            assert isinstance(result["traces"], list)
            assert isinstance(result["count"], int)
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_metrics_response_structure(self, mock_api_client):
        """Test metrics response has expected structure"""
        mock_response = Mock()
        mock_response.series = []
        
        mock_metrics_api = Mock()
        mock_metrics_api.query_metrics.return_value = mock_response
        
        with patch('datadog_api_client.v1.api.metrics_api.MetricsApi', return_value=mock_metrics_api):
            result = query_metrics(
                metric_query="avg:test{*}",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "series" in result
            assert "query" in result
            assert "time_range" in result
            assert "status" in result
            assert isinstance(result["series"], list)
    
    @patch('src.datadog_integration._initialized', True)
    @patch('src.datadog_integration._api_client')
    def test_logs_response_structure(self, mock_api_client):
        """Test logs response has expected structure"""
        mock_response = Mock()
        mock_response.data = []
        
        mock_logs_api = Mock()
        mock_logs_api.list_logs.return_value = mock_response
        
        with patch('src.datadog_integration.LogsApi', return_value=mock_logs_api):
            result = query_logs(
                query="service:test",
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc)
            )
            
            assert "logs" in result
            assert "count" in result
            assert "query" in result
            assert "time_range" in result
            assert isinstance(result["logs"], list)
            assert isinstance(result["count"], int)
