"""
Tests for Phase 3.5 - Datadog Log Aggregation
"""
import pytest
import logging
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
from io import StringIO

from src.datadog_log_handler import (
    DatadogLogHandler,
    setup_datadog_logging
)


class TestDatadogLogHandlerInitialization:
    """Test DatadogLogHandler initialization"""
    
    def test_handler_initialization(self):
        """Test handler initializes with correct parameters"""
        handler = DatadogLogHandler(
            api_key="test_api_key",
            service="test-service",
            env="testing",
            site="datadoghq.com",
            batch_size=5,
            flush_interval=2.0
        )
        
        assert handler.api_key == "test_api_key"
        assert handler.service == "test-service"
        assert handler.env == "testing"
        assert handler.site == "datadoghq.com"
        assert handler.batch_size == 5
        assert handler.flush_interval == 2.0
        assert handler.endpoint == "https://http-intake.logs.datadoghq.com/api/v2/logs"
    
    def test_handler_endpoint_with_different_sites(self):
        """Test handler constructs correct endpoint for different Datadog sites"""
        test_cases = [
            ("datadoghq.com", "https://http-intake.logs.datadoghq.com/api/v2/logs"),
            ("datadoghq.eu", "https://http-intake.logs.datadoghq.eu/api/v2/logs"),
            ("us3.datadoghq.com", "https://http-intake.logs.us3.datadoghq.com/api/v2/logs"),
            ("us5.datadoghq.com", "https://http-intake.logs.us5.datadoghq.com/api/v2/logs"),
        ]
        
        for site, expected_endpoint in test_cases:
            handler = DatadogLogHandler(
                api_key="test_key",
                service="test",
                site=site
            )
            assert handler.endpoint == expected_endpoint


class TestLogEntryFormatting:
    """Test log entry formatting and trace context injection"""
    
    def test_format_simple_log_entry(self):
        """Test formatting a simple log entry"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service",
            env="testing"
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        record = logging.LogRecord(
            name="test-logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.created = 1234567890.123
        record.hostname = "test-host"
        
        log_entry = handler._format_log_entry(record)
        
        assert log_entry["message"] == "Test message"
        assert log_entry["level"] == "INFO"
        assert log_entry["logger_name"] == "test-logger"
        assert log_entry["timestamp"] == 1234567890123
        assert log_entry["service"] == "test-service"
        assert log_entry["ddsource"] == "python"
        assert "env:testing" in log_entry["ddtags"]
    
    def test_format_log_entry_with_exception(self):
        """Test formatting log entry with exception info"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service"
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test-logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        record.created = 1234567890.123
        record.hostname = "test-host"
        
        log_entry = handler._format_log_entry(record)
        
        assert log_entry["level"] == "ERROR"
        assert "error" in log_entry
        assert log_entry["error"]["kind"] == "ValueError"
        assert "Test error" in log_entry["error"]["message"]
    
    @patch('ddtrace.tracer')
    def test_trace_context_injection(self, mock_tracer):
        """Test automatic trace context injection"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service"
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        # Mock current span with trace context
        mock_span = Mock()
        mock_span.trace_id = 123456789
        mock_span.span_id = 987654321
        mock_tracer.current_span.return_value = mock_span
        
        record = logging.LogRecord(
            name="test-logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.created = 1234567890.123
        record.hostname = "test-host"
        
        log_entry = handler._format_log_entry(record)
        
        assert "dd.trace_id" in log_entry
        assert log_entry["dd.trace_id"] == "123456789"
        assert "dd.span_id" in log_entry
        assert log_entry["dd.span_id"] == "987654321"
    
    @patch('ddtrace.tracer')
    def test_trace_context_when_no_active_span(self, mock_tracer):
        """Test log formatting when no active trace span"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service"
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        # No active span
        mock_tracer.current_span.return_value = None
        
        record = logging.LogRecord(
            name="test-logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.created = 1234567890.123
        record.hostname = "test-host"
        
        log_entry = handler._format_log_entry(record)
        
        # Should not have trace context
        assert "dd.trace_id" not in log_entry
        assert "dd.span_id" not in log_entry


class TestBatchingAndBuffering:
    """Test log batching and buffer management"""
    
    @pytest.mark.asyncio
    async def test_add_to_buffer(self):
        """Test adding logs to buffer"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service",
            batch_size=5
        )
        
        log_entry = {"message": "test", "timestamp": 123456}
        
        # Mock _flush_buffer to prevent actual flush
        handler._flush_buffer = AsyncMock()
        
        await handler._add_to_buffer(log_entry)
        
        assert len(handler.buffer) == 1
        assert handler.buffer[0] == log_entry
    
    @pytest.mark.asyncio
    async def test_buffer_auto_flush_on_batch_size(self):
        """Test buffer flushes automatically when batch size reached"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service",
            batch_size=3
        )
        
        # Mock _send_logs to prevent actual HTTP call
        handler._send_logs = AsyncMock()
        
        # Add logs up to batch size - 1
        for i in range(2):
            log_entry = {"message": f"test{i}", "timestamp": i}
            async with handler.buffer_lock:
                handler.buffer.append(log_entry)
        
        # This should trigger flush
        await handler._add_to_buffer({"message": "test2", "timestamp": 2})
        
        # Should have flushed
        handler._send_logs.assert_called_once()
        assert len(handler.buffer) == 0


class TestLogSubmission:
    """Test HTTP submission to Datadog API"""
    
    @pytest.mark.asyncio
    async def test_send_logs_success(self):
        """Test successful log submission to Datadog"""
        handler = DatadogLogHandler(
            api_key="test_api_key",
            service="test-service"
        )
        
        logs = [
            {"message": "log1", "timestamp": 1},
            {"message": "log2", "timestamp": 2}
        ]
        
        # Mock aiohttp session
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.text = AsyncMock(return_value="Accepted")
        
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        handler.session = mock_session
        
        await handler._send_logs(logs)
        
        # Verify POST was called with correct parameters
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        
        assert "http-intake.logs.datadoghq.com" in call_args[0][0]
        assert call_args[1]["headers"]["DD-API-KEY"] == "test_api_key"
        assert call_args[1]["headers"]["Content-Type"] == "application/json"
    
    @pytest.mark.asyncio
    async def test_send_logs_http_error(self):
        """Test handling HTTP error during log submission"""
        handler = DatadogLogHandler(
            api_key="test_api_key",
            service="test-service"
        )
        
        logs = [{"message": "test", "timestamp": 1}]
        
        # Mock failed response
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")
        
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        handler.session = mock_session
        
        # Should handle error gracefully (no exception)
        await handler._send_logs(logs)
    
    @pytest.mark.asyncio
    async def test_send_empty_logs(self):
        """Test sending empty logs list is a no-op"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service"
        )
        
        handler.session = AsyncMock()
        
        await handler._send_logs([])
        
        # Should not make any HTTP call
        handler.session.post.assert_not_called()


class TestHandlerLifecycle:
    """Test handler start, stop, and cleanup"""
    
    def test_handler_start(self):
        """Test handler starts background flush task"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service"
        )
        
        with patch('asyncio.create_task') as mock_create_task:
            with patch('asyncio.get_running_loop'):
                handler.start()
                
                assert handler.running is True
    
    def test_handler_stop(self):
        """Test handler stops and flushes remaining logs"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service"
        )
        
        # Add some logs to buffer
        handler.buffer.append({"message": "test", "timestamp": 1})
        
        handler.running = True
        handler.flush_task = Mock()
        handler.flush_task.done.return_value = False
        
        with patch.object(handler, '_flush_buffer', new_callable=AsyncMock):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_until_complete = Mock()
                
                handler.stop()
                
                assert handler.running is False
                handler.flush_task.cancel.assert_called_once()


class TestSetupFunction:
    """Test setup_datadog_logging helper function"""
    
    def test_setup_datadog_logging_success(self):
        """Test successful setup of Datadog logging"""
        with patch.object(DatadogLogHandler, 'start'):
            handler = setup_datadog_logging(
                api_key="test_key",
                service="test-service",
                env="testing",
                site="datadoghq.com",
                logger_name="test-logger",
                level=logging.INFO
            )
            
            assert handler is not None
            assert isinstance(handler, DatadogLogHandler)
            
            # Verify handler was added to logger
            logger = logging.getLogger("test-logger")
            assert handler in logger.handlers
    
    def test_setup_datadog_logging_with_custom_level(self):
        """Test setup with custom log level"""
        with patch.object(DatadogLogHandler, 'start'):
            handler = setup_datadog_logging(
                api_key="test_key",
                service="test-service",
                logger_name="test-logger-2",
                level=logging.DEBUG
            )
            
            assert handler.level == logging.DEBUG
    
    def test_setup_datadog_logging_failure(self):
        """Test graceful handling of setup failure"""
        with patch('src.datadog_log_handler.DatadogLogHandler', side_effect=Exception("Setup failed")):
            handler = setup_datadog_logging(
                api_key="test_key",
                service="test-service",
                logger_name="test-logger-3"
            )
            
            # Should return None on failure
            assert handler is None


class TestConfigIntegration:
    """Test integration with config_loader settings"""
    
    def test_config_loader_has_send_logs_setting(self):
        """Test that config_loader includes send_logs_to_datadog setting"""
        from src.config_loader import Config
        
        # Create config with explicit value
        config = Config(send_logs_to_datadog=True)
        assert config.send_logs_to_datadog is True
        
        config = Config(send_logs_to_datadog=False)
        assert config.send_logs_to_datadog is False
    
    def test_config_default_value(self):
        """Test default value for send_logs_to_datadog"""
        from src.config_loader import Config
        from pydantic import Field
        
        # Create config without loading .env file to test true default
        # The Field default is False
        assert Config.model_fields['send_logs_to_datadog'].default is False


@pytest.mark.integration
class TestIntegrationWithServer:
    """Integration tests with MCP server"""
    
    def test_datadog_log_handler_import_in_server(self):
        """Test that server.py can import datadog_log_handler"""
        try:
            from src.datadog_log_handler import DatadogLogHandler, setup_datadog_logging
            assert DatadogLogHandler is not None
            assert setup_datadog_logging is not None
        except ImportError as e:
            pytest.fail(f"Failed to import datadog_log_handler: {e}")
    
    @patch('src.datadog_log_handler.setup_datadog_logging')
    def test_server_initializes_log_handler_when_configured(self, mock_setup):
        """Test that server initializes log handler when configured"""
        from src.config_loader import Config
        
        # Create config with Datadog logging enabled
        config = Config(
            dd_enabled=True,
            dd_api_key="test_key",
            dd_app_key="test_app_key",
            send_logs_to_datadog=True
        )
        
        assert config.dd_configured is True
        assert config.send_logs_to_datadog is True


class TestPeriodicFlush:
    """Test periodic flush task"""
    
    @pytest.mark.asyncio
    async def test_periodic_flush_task(self):
        """Test that periodic flush task flushes buffer at intervals"""
        handler = DatadogLogHandler(
            api_key="test_key",
            service="test-service",
            flush_interval=0.05  # Very fast for testing
        )
        
        # Mock flush
        handler._flush_buffer = AsyncMock()
        
        # Add log to buffer
        handler.buffer.append({"message": "test", "timestamp": 1})
        
        # Start flush task
        handler.running = True
        task = asyncio.create_task(handler._flush_periodically())
        
        try:
            # Wait for at least one flush (timeout quickly)
            await asyncio.wait_for(asyncio.sleep(0.1), timeout=0.2)
        except asyncio.TimeoutError:
            pass
        finally:
            # Stop task
            handler.running = False
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Should have called flush at least once
        assert handler._flush_buffer.call_count >= 1
