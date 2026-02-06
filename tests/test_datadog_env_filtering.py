"""
Tests for Datadog environment filtering functionality.

Validates that env parameter is correctly injected into queries for:
- APM traces
- Metrics
- Logs
- Monitors
- Events
- Service dependencies (documents limitation)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from src.datadog_integration import (
    query_apm_traces,
    query_metrics,
    query_logs,
    list_monitors,
    search_events,
    get_service_dependencies
)


class TestAPMTraceEnvFiltering:
    """Test env parameter in APM trace queries"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_apm_with_env_filter(self, mock_client):
        """Test that env parameter is added to APM query"""
        # Setup mock with proper response structure
        mock_response = Mock()
        mock_response.data = []  # Empty list of spans
        mock_api = Mock()
        mock_api.list_spans_get.return_value = mock_response
        
        with patch("datadog_api_client.v2.api.spans_api.SpansApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_apm_traces(
                service="test-service",
                start_time=start,
                end_time=end,
                env="qa"
            )
            
            # Verify search was called
            assert mock_api.list_spans_get.called
            call_args = mock_api.list_spans_get.call_args[1]
            
            # Check that env:qa is in the filter_query
            query = call_args["filter_query"]
            assert "service:test-service" in query
            assert "env:qa" in query
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_apm_without_env_filter(self, mock_client):
        """Test that APM query works without env parameter"""
        mock_response = Mock()
        mock_response.data = []
        mock_api = Mock()
        mock_api.list_spans_get.return_value = mock_response
        
        with patch("datadog_api_client.v2.api.spans_api.SpansApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_apm_traces(
                service="test-service",
                start_time=start,
                end_time=end,
                env=None  # No env filter
            )
            
            assert mock_api.list_spans_get.called
            call_args = mock_api.list_spans_get.call_args[1]
            query = call_args["filter_query"]
            
            # Should have service but not env
            assert "service:test-service" in query
            assert "env:" not in query
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_apm_with_operation_and_env(self, mock_client):
        """Test that env combines correctly with other filters"""
        mock_response = Mock()
        mock_response.data = []
        mock_api = Mock()
        mock_api.list_spans_get.return_value = mock_response
        
        with patch("datadog_api_client.v2.api.spans_api.SpansApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_apm_traces(
                service="test-service",
                start_time=start,
                end_time=end,
                operation="log_search",
                min_duration_ms=100,
                env="production"
            )
            
            assert mock_api.list_spans_get.called
            call_args = mock_api.list_spans_get.call_args[1]
            query = call_args["filter_query"]
            
            # Should have all filters
            assert "service:test-service" in query
            assert "env:production" in query
            assert "operation_name:log_search" in query
            assert "@duration:>100ms" in query


class TestMetricsEnvFiltering:
    """Test env parameter in metrics queries"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_metrics_with_wildcard_tags(self, mock_client):
        """Test env injection into wildcard metric query"""
        mock_api = Mock()
        mock_api.query_metrics.return_value = {"series": []}
        
        with patch("datadog_api_client.v1.api.metrics_api.MetricsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_metrics(
                metric_query="avg:my.metric{*}",
                start_time=start,
                end_time=end,
                env="qa"
            )
            
            assert mock_api.query_metrics.called
            call_args = mock_api.query_metrics.call_args[1]
            
            # Should inject env into wildcard
            assert call_args["query"] == "avg:my.metric{env:qa}"
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_metrics_with_existing_tags(self, mock_client):
        """Test env appended to existing metric tags"""
        mock_api = Mock()
        mock_api.query_metrics.return_value = {"series": []}
        
        with patch("datadog_api_client.v1.api.metrics_api.MetricsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_metrics(
                metric_query="avg:my.metric{service:test,host:localhost}",
                start_time=start,
                end_time=end,
                env="cistable"
            )
            
            assert mock_api.query_metrics.called
            call_args = mock_api.query_metrics.call_args[1]
            
            # Should append env to existing tags
            query = call_args["query"]
            assert "service:test" in query
            assert "host:localhost" in query
            assert "env:cistable" in query
            assert query == "avg:my.metric{service:test,host:localhost,env:cistable}"
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_metrics_duplicate_env_prevention(self, mock_client):
        """Test that env is not duplicated if already in query"""
        mock_api = Mock()
        mock_api.query_metrics.return_value = {"series": []}
        
        with patch("datadog_api_client.v1.api.metrics_api.MetricsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_metrics(
                metric_query="avg:my.metric{env:production}",
                start_time=start,
                end_time=end,
                env="qa"  # Try to add different env
            )
            
            assert mock_api.query_metrics.called
            call_args = mock_api.query_metrics.call_args[1]
            
            # Should NOT modify query since env: already present
            assert call_args["query"] == "avg:my.metric{env:production}"
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_metrics_without_env(self, mock_client):
        """Test metrics query works without env parameter"""
        mock_api = Mock()
        mock_api.query_metrics.return_value = {"series": []}
        
        with patch("datadog_api_client.v1.api.metrics_api.MetricsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_metrics(
                metric_query="avg:my.metric{*}",
                start_time=start,
                end_time=end,
                env=None
            )
            
            assert mock_api.query_metrics.called
            call_args = mock_api.query_metrics.call_args[1]
            
            # Should not modify query
            assert call_args["query"] == "avg:my.metric{*}"


class TestLogsEnvFiltering:
    """Test env parameter in log queries"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_logs_with_env_filter(self, mock_client):
        """Test that env is appended to log query"""
        mock_api = Mock()
        mock_api.list_logs_get.return_value = {"data": []}
        
        with patch("datadog_api_client.v2.api.logs_api.LogsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_logs(
                query="service:test-service status:error",
                start_time=start,
                end_time=end,
                env="production"
            )
            
            assert mock_api.list_logs_get.called
            call_args = mock_api.list_logs_get.call_args[1]
            
            # Should append env to query
            filter_query = call_args["filter_query"]
            assert "service:test-service status:error" in filter_query
            assert "env:production" in filter_query
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_logs_duplicate_env_prevention(self, mock_client):
        """Test that env is not duplicated if already in query"""
        mock_api = Mock()
        mock_api.list_logs_get.return_value = {"data": []}
        
        with patch("datadog_api_client.v2.api.logs_api.LogsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = query_logs(
                query="service:test env:qa",
                start_time=start,
                end_time=end,
                env="production"  # Try to override
            )
            
            assert mock_api.list_logs_get.called
            call_args = mock_api.list_logs_get.call_args[1]
            
            # Should NOT modify query
            assert call_args["filter_query"] == "service:test env:qa"


class TestMonitorsEnvFiltering:
    """Test env parameter in monitor queries"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_monitors_with_service_and_env(self, mock_client):
        """Test that env is appended to monitor tags"""
        mock_api = Mock()
        mock_api.list_monitors.return_value = []
        
        with patch("datadog_api_client.v1.api.monitors_api.MonitorsApi", return_value=mock_api):
            result = list_monitors(
                service="test-service",
                env="qa"
            )
            
            assert mock_api.list_monitors.called
            call_args = mock_api.list_monitors.call_args[1]
            
            # Should have both service and env in tags
            tags = call_args["tags"]
            assert tags == "service:test-service,env:qa"
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_monitors_with_env_only(self, mock_client):
        """Test that env works without service filter"""
        mock_api = Mock()
        mock_api.list_monitors.return_value = []
        
        with patch("datadog_api_client.v1.api.monitors_api.MonitorsApi", return_value=mock_api):
            result = list_monitors(
                service=None,
                env="production"
            )
            
            assert mock_api.list_monitors.called
            call_args = mock_api.list_monitors.call_args[1]
            
            # Should have only env tag
            tags = call_args["tags"]
            assert tags == "env:production"


class TestEventsEnvFiltering:
    """Test env parameter in event queries"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_events_with_env_filter(self, mock_client):
        """Test that env is added to event query"""
        mock_api = Mock()
        mock_api.list_events.return_value = {"data": []}
        
        with patch("datadog_api_client.v2.api.events_api.EventsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = search_events(
                query="tags:deployment",
                start_time=start,
                end_time=end,
                env="cistable"
            )
            
            assert mock_api.list_events.called
            call_args = mock_api.list_events.call_args[1]
            
            # Should append env to query
            filter_query = call_args["filter_query"]
            assert "tags:deployment" in filter_query
            assert "env:cistable" in filter_query
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_events_with_sources_and_env(self, mock_client):
        """Test that env combines with source filters"""
        mock_api = Mock()
        mock_api.list_events.return_value = {"data": []}
        
        with patch("datadog_api_client.v2.api.events_api.EventsApi", return_value=mock_api):
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            end = datetime.now(timezone.utc)
            
            result = search_events(
                query="tags:deployment",
                start_time=start,
                end_time=end,
                sources=["deployment", "alert"],
                env="qa"
            )
            
            assert mock_api.list_events.called
            call_args = mock_api.list_events.call_args[1]
            
            # Should have env and sources
            filter_query = call_args["filter_query"]
            assert "env:qa" in filter_query
            assert "source:deployment" in filter_query
            assert "source:alert" in filter_query


class TestServiceDependenciesEnvNote:
    """Test service dependencies with env parameter (documents limitation)"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_service_dependencies_with_env_parameter(self, mock_client):
        """Test that env parameter is accepted but Service Catalog doesn't filter by it"""
        mock_api = Mock()
        
        # Mock successful service definition response
        mock_definition = MagicMock()
        mock_definition.data.attributes.schema.dd_service = "test-service"
        mock_api.get_service_definition.return_value = mock_definition
        
        with patch("datadog_api_client.v2.api.service_definition_api.ServiceDefinitionApi", return_value=mock_api):
            result = get_service_dependencies(
                service="test-service",
                env="qa"  # Parameter accepted but may not filter results
            )
            
            # Should succeed without error
            assert "service" in result
            assert result["service"] == "test-service"
            
            # Note: Service Catalog API doesn't support env filtering
            # This test documents the limitation


class TestBackwardCompatibility:
    """Test that all functions work without env parameter (backward compatibility)"""
    
    @patch("src.datadog_integration._initialized", True)
    @patch("src.datadog_integration._api_client")
    def test_all_functions_accept_none_env(self, mock_client):
        """Test that env=None works for all functions"""
        
        # Mock all API responses
        mock_spans_api = Mock()
        mock_spans_api.list_spans_get.return_value = {"data": [], "meta": {"page": {"after": None}}}
        
        mock_metrics_api = Mock()
        mock_metrics_api.query_metrics.return_value = {"series": []}
        
        mock_logs_api = Mock()
        mock_logs_api.list_logs_get.return_value = {"data": []}
        
        mock_monitors_api = Mock()
        mock_monitors_api.list_monitors.return_value = []
        
        mock_events_api = Mock()
        mock_events_api.list_events.return_value = {"data": []}
        
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)
        
        # Test all functions with env=None
        with patch("datadog_api_client.v2.api.spans_api.SpansApi", return_value=mock_spans_api), \
             patch("datadog_api_client.v1.api.metrics_api.MetricsApi", return_value=mock_metrics_api), \
             patch("datadog_api_client.v2.api.logs_api.LogsApi", return_value=mock_logs_api), \
             patch("datadog_api_client.v1.api.monitors_api.MonitorsApi", return_value=mock_monitors_api), \
             patch("datadog_api_client.v2.api.events_api.EventsApi", return_value=mock_events_api):
            
            # All should work without errors
            query_apm_traces("test", start, end, env=None)
            query_metrics("avg:test{*}", start, end, env=None)
            query_logs("test", start, end, env=None)
            list_monitors(service="test", env=None)
            search_events("test", start, end, env=None)
            
            # Verify no env filters were added
            assert "env:" not in mock_spans_api.list_spans_get.call_args[1]["body"]["filter"]["query"]
            assert "env:" not in mock_metrics_api.query_metrics.call_args[1]["query"]
            assert "env:" not in mock_logs_api.list_logs_get.call_args[1]["filter_query"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
