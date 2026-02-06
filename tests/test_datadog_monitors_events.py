"""
Tests for Datadog monitors and events tools (Phase 3.6+)
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from src.datadog_integration import list_monitors, search_events


@pytest.fixture
def mock_datadog_client():
    """Mock Datadog API client"""
    with patch('src.datadog_integration._api_client') as mock_client:
        with patch('src.datadog_integration._initialized', True):
            yield mock_client


class TestListMonitors:
    """Tests for list_monitors function"""
    
    def test_list_monitors_not_initialized(self):
        """Test list_monitors returns error when not initialized"""
        with patch('src.datadog_integration._initialized', False):
            result = list_monitors()
            
            assert "error" in result
            assert "not initialized" in result["error"].lower()
    
    def test_list_monitors_basic(self, mock_datadog_client):
        """Test basic monitor listing"""
        # Mock API response
        mock_monitor = Mock()
        mock_monitor.id = 12345
        mock_monitor.name = "High Error Rate - Auth Service"
        mock_monitor.type = "metric alert"
        mock_monitor.overall_state = "Alert"
        mock_monitor.message = "Error rate exceeded threshold"
        mock_monitor.tags = ["service:pason-auth-service", "env:prod"]
        mock_monitor.query = "avg:error.rate{service:pason-auth-service} > 100"
        mock_monitor.created = datetime(2025, 1, 20, 10, 0, 0)
        mock_monitor.modified = datetime(2026, 1, 24, 15, 30, 0)
        mock_monitor.priority = 1
        
        with patch('datadog_api_client.v1.api.monitors_api.MonitorsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_monitors.return_value = [mock_monitor]
            mock_api_class.return_value = mock_api_instance
            
            result = list_monitors(service="pason-auth-service", limit=50)
            
            assert "monitors" in result
            assert result["count"] == 1
            assert result["monitors"][0]["id"] == 12345
            assert result["monitors"][0]["name"] == "High Error Rate - Auth Service"
            assert result["monitors"][0]["status"] == "Alert"
    
    def test_list_monitors_with_status_filter(self, mock_datadog_client):
        """Test monitor listing with status filter"""
        with patch('datadog_api_client.v1.api.monitors_api.MonitorsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_monitors.return_value = []
            mock_api_class.return_value = mock_api_instance
            
            result = list_monitors(
                service="pason-auth-service",
                status_filter=["Alert", "Warn"],
                limit=50
            )
            
            # Verify API was called with correct parameters
            call_args = mock_api_instance.list_monitors.call_args
            assert call_args[1]["monitor_tags"] == "service:pason-auth-service"
            assert "alert,warn" in call_args[1]["group_states"]
    
    def test_list_monitors_no_service_filter(self, mock_datadog_client):
        """Test monitor listing without service filter"""
        with patch('datadog_api_client.v1.api.monitors_api.MonitorsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_monitors.return_value = []
            mock_api_class.return_value = mock_api_instance
            
            result = list_monitors(limit=50)
            
            # Verify API was called without service filter
            call_args = mock_api_instance.list_monitors.call_args
            assert call_args[1]["monitor_tags"] is None
    
    def test_list_monitors_api_error(self, mock_datadog_client):
        """Test error handling when API fails"""
        with patch('datadog_api_client.v1.api.monitors_api.MonitorsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_monitors.side_effect = Exception("API Error")
            mock_api_class.return_value = mock_api_instance
            
            result = list_monitors(service="pason-auth-service")
            
            assert "error" in result
            assert "API Error" in result["error"]


class TestSearchEvents:
    """Tests for search_events function"""
    
    def test_search_events_not_initialized(self):
        """Test search_events returns error when not initialized"""
        with patch('src.datadog_integration._initialized', False):
            start_time = datetime.now(timezone.utc) - timedelta(hours=24)
            end_time = datetime.now(timezone.utc)
            
            result = search_events(
                query="source:deployment",
                start_time=start_time,
                end_time=end_time
            )
            
            assert "error" in result
            assert "not initialized" in result["error"].lower()
    
    def test_search_events_basic(self, mock_datadog_client):
        """Test basic event search"""
        # Mock API response
        mock_event = Mock()
        mock_event.id = "evt_12345"
        mock_event.attributes = Mock()
        mock_event.attributes.timestamp = datetime(2026, 1, 24, 15, 30, 0, tzinfo=timezone.utc)
        mock_event.attributes.tags = ["service:auth", "env:prod"]
        mock_event.attributes.attributes = {
            "title": "Deployment: auth-service v1.2.3",
            "message": "Deployed auth-service to production",
            "source_type_name": "deployment",
            "priority": "normal",
            "aggregation_key": "deploy_auth_123"
        }
        
        mock_response = Mock()
        mock_response.data = [mock_event]
        
        with patch('datadog_api_client.v2.api.events_api.EventsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_events.return_value = mock_response
            mock_api_class.return_value = mock_api_instance
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=24)
            end_time = datetime.now(timezone.utc)
            
            result = search_events(
                query="source:deployment",
                start_time=start_time,
                end_time=end_time,
                limit=100
            )
            
            assert "events" in result
            assert result["count"] == 1
            assert result["events"][0]["id"] == "evt_12345"
            assert result["events"][0]["title"] == "Deployment: auth-service v1.2.3"
            assert result["events"][0]["source"] == "deployment"
    
    def test_search_events_with_sources_filter(self, mock_datadog_client):
        """Test event search with sources filter"""
        mock_response = Mock()
        mock_response.data = []
        
        with patch('datadog_api_client.v2.api.events_api.EventsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_events.return_value = mock_response
            mock_api_class.return_value = mock_api_instance
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=24)
            end_time = datetime.now(timezone.utc)
            
            result = search_events(
                query="tags:service:auth",
                start_time=start_time,
                end_time=end_time,
                sources=["deployment", "alert"],
                limit=100
            )
            
            # Verify query includes sources
            call_args = mock_api_instance.list_events.call_args
            filter_query = call_args[1]["filter_query"]
            assert "source:deployment" in filter_query
            assert "source:alert" in filter_query
    
    def test_search_events_no_results(self, mock_datadog_client):
        """Test event search with no results"""
        mock_response = Mock()
        mock_response.data = []
        
        with patch('datadog_api_client.v2.api.events_api.EventsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_events.return_value = mock_response
            mock_api_class.return_value = mock_api_instance
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            end_time = datetime.now(timezone.utc)
            
            result = search_events(
                query="source:deployment",
                start_time=start_time,
                end_time=end_time
            )
            
            assert result["count"] == 0
            assert result["events"] == []
    
    def test_search_events_api_error(self, mock_datadog_client):
        """Test error handling when API fails"""
        with patch('datadog_api_client.v2.api.events_api.EventsApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.list_events.side_effect = Exception("Network error")
            mock_api_class.return_value = mock_api_instance
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            end_time = datetime.now(timezone.utc)
            
            result = search_events(
                query="source:deployment",
                start_time=start_time,
                end_time=end_time
            )
            
            assert "error" in result
            assert "Network error" in result["error"]


class TestIntegration:
    """Integration tests for monitors and events"""
    
    def test_monitors_and_events_combined_workflow(self, mock_datadog_client):
        """Test a realistic workflow combining monitors and events"""
        # Scenario: Check monitors for alerts, then search for deployment events
        
        # Mock monitor with alert
        mock_monitor = Mock()
        mock_monitor.id = 99999
        mock_monitor.name = "Error Rate Spike"
        mock_monitor.type = "metric alert"
        mock_monitor.overall_state = "Alert"
        mock_monitor.message = "Error rate spiked"
        mock_monitor.tags = ["service:pason-auth-service"]
        mock_monitor.query = "error.rate > 100"
        mock_monitor.created = datetime(2026, 1, 24, 10, 0, 0)
        mock_monitor.modified = datetime(2026, 1, 24, 15, 0, 0)
        mock_monitor.priority = 1
        
        # Mock deployment event
        mock_event = Mock()
        mock_event.id = "evt_deploy_123"
        mock_event.attributes = Mock()
        mock_event.attributes.timestamp = datetime(2026, 1, 24, 14, 50, 0, tzinfo=timezone.utc)
        mock_event.attributes.tags = ["service:auth"]
        mock_event.attributes.attributes = {
            "title": "Deployment v1.2.3",
            "message": "Deployed to prod",
            "source_type_name": "deployment",
            "priority": "normal"
        }
        
        with patch('datadog_api_client.v1.api.monitors_api.MonitorsApi') as mock_monitors_api:
            with patch('datadog_api_client.v2.api.events_api.EventsApi') as mock_events_api:
                # Setup monitors API
                mock_monitors_instance = Mock()
                mock_monitors_instance.list_monitors.return_value = [mock_monitor]
                mock_monitors_api.return_value = mock_monitors_instance
                
                # Setup events API
                mock_events_instance = Mock()
                mock_response = Mock()
                mock_response.data = [mock_event]
                mock_events_instance.list_events.return_value = mock_response
                mock_events_api.return_value = mock_events_instance
                
                # Step 1: List monitors with alerts
                monitors_result = list_monitors(
                    service="pason-auth-service",
                    status_filter=["Alert"]
                )
                
                assert monitors_result["count"] == 1
                assert monitors_result["monitors"][0]["status"] == "Alert"
                
                # Step 2: Search for deployment events around alert time
                start_time = datetime(2026, 1, 24, 14, 0, 0, tzinfo=timezone.utc)
                end_time = datetime(2026, 1, 24, 16, 0, 0, tzinfo=timezone.utc)
                
                events_result = search_events(
                    query="tags:service:auth",
                    start_time=start_time,
                    end_time=end_time,
                    sources=["deployment"]
                )
                
                assert events_result["count"] == 1
                assert events_result["events"][0]["source"] == "deployment"
                
                # Correlation: deployment at 14:50, alert at 15:00
                # This would indicate the deployment likely caused the error spike


class TestGetServiceDependencies:
    """Tests for get_service_dependencies function"""
    
    def test_get_service_dependencies_not_initialized(self):
        """Test get_service_dependencies returns error when not initialized"""
        with patch('src.datadog_integration._initialized', False):
            from src.datadog_integration import get_service_dependencies
            result = get_service_dependencies(service="pason-auth-service")
            
            assert "error" in result
            assert "not initialized" in result["error"].lower()
    
    def test_get_service_dependencies_success(self, mock_datadog_client):
        """Test successful service dependencies retrieval"""
        from src.datadog_integration import get_service_dependencies
        
        # Mock service definition response
        mock_attrs = Mock()
        mock_attrs.dependencies = ["database-service", "cache-service"]
        mock_attrs.team = "auth-team"
        mock_attrs.description = "Authentication service"
        mock_attrs.lifecycle = "production"
        mock_attrs.tier = "tier1"
        mock_attrs.links = []
        
        mock_service_def = Mock()
        mock_service_def.attributes = mock_attrs
        
        mock_response = Mock()
        mock_response.data = mock_service_def
        
        with patch('datadog_api_client.v2.api.service_definition_api.ServiceDefinitionApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.get_service_definition.return_value = mock_response
            mock_api_class.return_value = mock_api_instance
            
            result = get_service_dependencies(service="pason-auth-service")
            
            assert result["service"] == "pason-auth-service"
            assert "dependencies" in result
            assert "database-service" in result["dependencies"]["upstream"]
            assert "cache-service" in result["dependencies"]["upstream"]
            assert result["metadata"]["team"] == "auth-team"
    
    def test_get_service_dependencies_not_found(self, mock_datadog_client):
        """Test service not found in catalog"""
        from src.datadog_integration import get_service_dependencies
        
        with patch('datadog_api_client.v2.api.service_definition_api.ServiceDefinitionApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.get_service_definition.side_effect = Exception("Service not found")
            mock_api_class.return_value = mock_api_instance
            
            result = get_service_dependencies(service="unknown-service")
            
            assert result["service"] == "unknown-service"
            assert result["available"] == False
            assert "Service Catalog" in result["metadata"]["note"]
    
    def test_get_service_dependencies_api_error(self, mock_datadog_client):
        """Test error handling when API fails"""
        from src.datadog_integration import get_service_dependencies
        
        with patch('datadog_api_client.v2.api.service_definition_api.ServiceDefinitionApi') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_instance.get_service_definition.side_effect = Exception("API Error")
            mock_api_class.return_value = mock_api_instance
            
            result = get_service_dependencies(service="pason-auth-service")
            
            # Should return graceful error response
            assert "service" in result or "error" in result
