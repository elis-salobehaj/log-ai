"""
Datadog log handler for centralized logging with trace correlation.
Sends Python logs to Datadog Log Management API with automatic trace context injection.
"""
import logging
import json
import sys
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import aiohttp
from collections import deque


class DatadogLogHandler(logging.Handler):
    """
    Custom logging handler that sends logs to Datadog Log Management API.
    
    Features:
    - Automatic trace context injection (dd.trace_id, dd.span_id)
    - Asynchronous batch submission
    - Structured JSON logging
    - Graceful error handling
    """
    
    def __init__(
        self,
        api_key: str,
        service: str,
        env: str = "production",
        site: str = "datadoghq.com",
        batch_size: int = 10,
        flush_interval: float = 5.0
    ):
        """
        Initialize Datadog log handler.
        
        Args:
            api_key: Datadog API key
            service: Service name (e.g., "log-ai-mcp")
            env: Environment (production, staging, development)
            site: Datadog site (datadoghq.com, datadoghq.eu, etc.)
            batch_size: Number of logs to batch before sending
            flush_interval: Maximum seconds to wait before flushing batch
        """
        super().__init__()
        self.api_key = api_key
        self.service = service
        self.env = env
        self.site = site
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        # Datadog HTTP Logs API endpoint
        self.endpoint = f"https://http-intake.logs.{site}/api/v2/logs"
        
        # Log buffer for batching
        self.buffer: deque = deque()
        self.buffer_lock = asyncio.Lock()
        
        # Background flush task
        self.flush_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        
        sys.stderr.write(f"[DATADOG_LOGS] Handler initialized: endpoint={self.endpoint}, service={service}\n")
    
    def start(self):
        """Start background flush task"""
        if not self.running:
            self.running = True
            # Get or create event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            self.flush_task = loop.create_task(self._flush_periodically())
            sys.stderr.write("[DATADOG_LOGS] Background flush task started\n")
    
    def stop(self):
        """Stop background flush task and flush remaining logs"""
        self.running = False
        if self.flush_task and not self.flush_task.done():
            self.flush_task.cancel()
        
        # Flush remaining logs synchronously
        if self.buffer:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._flush_buffer())
            except Exception as e:
                sys.stderr.write(f"[DATADOG_LOGS] Error flushing remaining logs: {e}\n")
    
    def emit(self, record: logging.LogRecord):
        """
        Emit a log record to Datadog.
        Adds to buffer for batch submission.
        """
        try:
            log_entry = self._format_log_entry(record)
            
            # Add to buffer (non-blocking)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._add_to_buffer(log_entry))
            except RuntimeError:
                # No event loop - just add directly
                self.buffer.append(log_entry)
                if len(self.buffer) >= self.batch_size:
                    # Force synchronous flush
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(self._flush_buffer())
                        loop.close()
                    except Exception as e:
                        sys.stderr.write(f"[DATADOG_LOGS] Flush error: {e}\n")
            
        except Exception as e:
            self.handleError(record)
            sys.stderr.write(f"[DATADOG_LOGS] Error emitting log: {e}\n")
    
    def _format_log_entry(self, record: logging.LogRecord) -> Dict[str, Any]:
        """
        Format log record as Datadog log entry with trace context.
        
        Returns:
            Dictionary with Datadog log structure
        """
        # Base log entry
        log_entry = {
            "message": self.format(record),
            "level": record.levelname,
            "logger_name": record.name,
            "timestamp": int(record.created * 1000),  # Milliseconds
            "service": self.service,
            "ddsource": "python",
            "ddtags": f"env:{self.env},service:{self.service}",
            "hostname": record.hostname if hasattr(record, 'hostname') else "unknown",
        }
        
        # Add trace context if available
        trace_context = self._get_trace_context()
        if trace_context:
            log_entry["dd.trace_id"] = trace_context["trace_id"]
            log_entry["dd.span_id"] = trace_context["span_id"]
        
        # Add exception info if present
        if record.exc_info:
            log_entry["error"] = {
                "kind": record.exc_info[0].__name__ if record.exc_info[0] else "Exception",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "stack": self.formatter.formatException(record.exc_info) if self.formatter else ""
            }
        
        # Add extra attributes
        if hasattr(record, 'extra_attributes'):
            log_entry.update(record.extra_attributes)
        
        return log_entry
    
    def _get_trace_context(self) -> Optional[Dict[str, str]]:
        """
        Get current trace context from ddtrace if available.
        
        Returns:
            Dict with trace_id and span_id, or None
        """
        try:
            from ddtrace import tracer
            
            span = tracer.current_span()
            if span:
                return {
                    "trace_id": str(span.trace_id),
                    "span_id": str(span.span_id)
                }
        except ImportError:
            pass
        except Exception as e:
            sys.stderr.write(f"[DATADOG_LOGS] Error getting trace context: {e}\n")
        
        return None
    
    async def _add_to_buffer(self, log_entry: Dict[str, Any]):
        """Add log entry to buffer and flush if batch size reached"""
        should_flush = False
        
        async with self.buffer_lock:
            self.buffer.append(log_entry)
            
            if len(self.buffer) >= self.batch_size:
                should_flush = True
        
        # Flush outside the lock to avoid deadlock
        if should_flush:
            await self._flush_buffer()
    
    async def _flush_periodically(self):
        """Background task to flush buffer periodically"""
        while self.running:
            try:
                await asyncio.sleep(self.flush_interval)
                if self.buffer:
                    await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                sys.stderr.write(f"[DATADOG_LOGS] Periodic flush error: {e}\n")
    
    async def _flush_buffer(self):
        """Flush buffered logs to Datadog API"""
        async with self.buffer_lock:
            if not self.buffer:
                return
            
            # Get logs to send
            logs_to_send = list(self.buffer)
            self.buffer.clear()
        
        try:
            await self._send_logs(logs_to_send)
        except Exception as e:
            sys.stderr.write(f"[DATADOG_LOGS] Failed to send {len(logs_to_send)} logs: {e}\n")
            # Could implement retry logic here
    
    async def _send_logs(self, logs: list):
        """
        Send logs to Datadog HTTP API.
        
        Args:
            logs: List of log entry dictionaries
        """
        if not logs:
            return
        
        headers = {
            "DD-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Datadog expects array of log entries
        payload = json.dumps(logs)
        
        try:
            # Create session if needed
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.post(
                self.endpoint,
                headers=headers,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 202:
                    sys.stderr.write(f"[DATADOG_LOGS] Successfully sent {len(logs)} logs\n")
                else:
                    text = await response.text()
                    sys.stderr.write(
                        f"[DATADOG_LOGS] Failed to send logs: "
                        f"status={response.status}, response={text}\n"
                    )
        
        except aiohttp.ClientError as e:
            sys.stderr.write(f"[DATADOG_LOGS] Network error sending logs: {e}\n")
        except Exception as e:
            sys.stderr.write(f"[DATADOG_LOGS] Unexpected error sending logs: {e}\n")
    
    def close(self):
        """Close handler and cleanup resources"""
        self.stop()
        
        if self.session:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.session.close())
            except Exception:
                pass
        
        super().close()


def setup_datadog_logging(
    api_key: str,
    service: str,
    env: str = "production",
    site: str = "datadoghq.com",
    logger_name: str = "log-ai",
    level: int = logging.INFO
) -> Optional[DatadogLogHandler]:
    """
    Setup Datadog log handler for a logger.
    
    Args:
        api_key: Datadog API key
        service: Service name
        env: Environment name
        site: Datadog site
        logger_name: Logger name to attach handler to
        level: Logging level
    
    Returns:
        DatadogLogHandler instance or None if setup fails
    """
    try:
        handler = DatadogLogHandler(
            api_key=api_key,
            service=service,
            env=env,
            site=site
        )
        handler.setLevel(level)
        
        # Use JSON formatter for structured logging
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Add to logger
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        
        # Start background flush task
        handler.start()
        
        sys.stderr.write(f"[DATADOG_LOGS] Datadog logging enabled for logger '{logger_name}'\n")
        return handler
    
    except Exception as e:
        sys.stderr.write(f"[DATADOG_LOGS] Failed to setup Datadog logging: {e}\n")
        return None
