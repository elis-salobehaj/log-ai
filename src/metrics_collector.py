"""
Metrics Collection Module for Phase 3.3

Provides comprehensive application and infrastructure metrics collection.
Extends Phase 3.2 APM tracing with additional business logic metrics.

Metrics Categories:
1. Cache Performance - Hit rates, efficiency metrics
2. System Health - Semaphore utilization, connection pool status
3. Error Tracking - Error rates by type
4. Business Metrics - Overflow rates, search patterns
"""

import sys
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from datadog_integration import record_metric, is_configured as is_datadog_configured

logger = logging.getLogger("log-ai.metrics")


@dataclass
class MetricsCollector:
    """
    Collects and tracks application metrics over time.
    
    Maintains running totals and rates for gauge metrics.
    Sends metrics to Datadog when configured.
    """
    
    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Search metrics
    total_searches: int = 0
    searches_with_overflow: int = 0
    searches_with_timeout: int = 0
    
    # Error metrics
    errors_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Tracking state
    last_metrics_report: Optional[datetime] = None
    
    def record_cache_hit(self, service: str):
        """Record cache hit and update rates"""
        self.cache_hits += 1
        self.total_searches += 1
        self._update_cache_metrics(service)
    
    def record_cache_miss(self, service: str):
        """Record cache miss and update rates"""
        self.cache_misses += 1
        self.total_searches += 1
        self._update_cache_metrics(service)
    
    def record_overflow(self, service: str):
        """Record search with overflow"""
        self.searches_with_overflow += 1
        self._update_overflow_rate(service)
    
    def record_timeout(self, service: str):
        """Record search timeout"""
        self.searches_with_timeout += 1
    
    def record_error(self, error_type: str, service: Optional[str] = None):
        """
        Record error occurrence.
        
        Args:
            error_type: Type/category of error (e.g., "ServiceNotFound", "TimeoutError")
            service: Optional service name for tagging
        """
        self.errors_by_type[error_type] += 1
        
        # Send to Datadog
        if is_datadog_configured():
            tags = [f"error_type:{error_type}"]
            if service:
                tags.append(f"service:{service}")
            
            record_metric(
                "log_ai.errors.total",
                1,
                tags=tags,
                metric_type="count"
            )
    
    def _update_cache_metrics(self, service: str):
        """Calculate and send cache hit rate as gauge"""
        if not is_datadog_configured():
            return
        
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return
        
        hit_rate = (self.cache_hits / total) * 100.0
        
        record_metric(
            "log_ai.search.cache_hit_rate",
            hit_rate,
            tags=[f"service:{service}"],
            metric_type="gauge"
        )
    
    def _update_overflow_rate(self, service: str):
        """Calculate and send overflow rate as gauge"""
        if not is_datadog_configured():
            return
        
        if self.total_searches == 0:
            return
        
        overflow_rate = (self.searches_with_overflow / self.total_searches) * 100.0
        
        record_metric(
            "log_ai.search.overflow_rate",
            overflow_rate,
            tags=[f"service:{service}"],
            metric_type="gauge"
        )
    
    def report_semaphore_utilization(self, available_slots: int, max_slots: int):
        """
        Report current semaphore utilization.
        
        Args:
            available_slots: Number of available search slots
            max_slots: Maximum configured slots
        """
        if not is_datadog_configured():
            return
        
        utilization_pct = ((max_slots - available_slots) / max_slots) * 100.0
        
        record_metric(
            "log_ai.semaphore.available",
            available_slots,
            tags=[f"limit:{max_slots}"],
            metric_type="gauge"
        )
        
        record_metric(
            "log_ai.semaphore.utilization_pct",
            utilization_pct,
            tags=[f"limit:{max_slots}"],
            metric_type="gauge"
        )
    
    def report_redis_pool_status(self, active_connections: int, max_connections: int):
        """
        Report Redis connection pool status.
        
        Args:
            active_connections: Number of active connections
            max_connections: Maximum pool size
        """
        if not is_datadog_configured():
            return
        
        record_metric(
            "log_ai.redis.connection_pool",
            active_connections,
            tags=[f"max:{max_connections}"],
            metric_type="gauge"
        )
        
        pool_utilization = (active_connections / max_connections) * 100.0
        record_metric(
            "log_ai.redis.pool_utilization_pct",
            pool_utilization,
            tags=[f"max:{max_connections}"],
            metric_type="gauge"
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get current metrics summary.
        
        Returns:
            Dictionary with current metric values
        """
        total = self.cache_hits + self.cache_misses
        cache_hit_rate = (self.cache_hits / total * 100.0) if total > 0 else 0.0
        overflow_rate = (self.searches_with_overflow / self.total_searches * 100.0) if self.total_searches > 0 else 0.0
        
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate_pct": round(cache_hit_rate, 2),
            "total_searches": self.total_searches,
            "searches_with_overflow": self.searches_with_overflow,
            "overflow_rate_pct": round(overflow_rate, 2),
            "searches_with_timeout": self.searches_with_timeout,
            "errors_by_type": dict(self.errors_by_type)
        }
    
    def reset(self):
        """Reset all counters (useful for testing)"""
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_searches = 0
        self.searches_with_overflow = 0
        self.searches_with_timeout = 0
        self.errors_by_type.clear()
        self.last_metrics_report = None


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get the global metrics collector instance.
    
    Returns:
        MetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
        sys.stderr.write("[METRICS] Metrics collector initialized\n")
    return _metrics_collector


def reset_metrics_collector():
    """Reset the global metrics collector (for testing)"""
    global _metrics_collector
    if _metrics_collector:
        _metrics_collector.reset()
    else:
        _metrics_collector = MetricsCollector()
