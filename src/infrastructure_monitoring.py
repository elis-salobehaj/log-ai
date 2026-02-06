"""
Infrastructure Monitoring Module for Phase 3.4

Monitors host-level infrastructure metrics and reports to Datadog.
Provides system health visibility for the MCP server environment.

Metrics Categories:
1. System Resources - CPU, memory, disk usage
2. Process Health - MCP server process metrics
3. Network Stats - Connection counts, bandwidth
4. File System - Log directory size, inode usage
"""

import sys
import os
import psutil
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from src.datadog_integration import record_metric, is_configured as is_datadog_configured

logger = logging.getLogger("log-ai.infrastructure")


@dataclass
class SystemMetrics:
    """Container for system-level metrics snapshot"""
    
    # CPU metrics
    cpu_percent: float
    cpu_count: int
    load_avg_1min: float
    load_avg_5min: float
    load_avg_15min: float
    
    # Memory metrics
    memory_total_mb: float
    memory_used_mb: float
    memory_available_mb: float
    memory_percent: float
    
    # Disk metrics
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_percent: float
    
    # Process metrics
    process_memory_mb: float
    process_cpu_percent: float
    process_threads: int
    process_open_files: int
    
    # Timestamp
    timestamp: datetime


class InfrastructureMonitor:
    """
    Monitors infrastructure metrics and reports to Datadog.
    
    Collects system-level metrics using psutil and sends them
    to Datadog when configured.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialize infrastructure monitor.
        
        Args:
            log_dir: Optional path to log directory for file system monitoring
        """
        self.log_dir = log_dir
        self.process = psutil.Process(os.getpid())
        self._last_cpu_times = None
        
        sys.stderr.write("[INFRA] Infrastructure monitoring initialized\n")
    
    def collect_metrics(self) -> SystemMetrics:
        """
        Collect current infrastructure metrics snapshot.
        
        Returns:
            SystemMetrics object with current readings
        """
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0.0, 0.0, 0.0)
        
        # Memory metrics
        mem = psutil.virtual_memory()
        memory_total_mb = mem.total / (1024 * 1024)
        memory_used_mb = mem.used / (1024 * 1024)
        memory_available_mb = mem.available / (1024 * 1024)
        memory_percent = mem.percent
        
        # Disk metrics (root partition)
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024 * 1024 * 1024)
        disk_used_gb = disk.used / (1024 * 1024 * 1024)
        disk_free_gb = disk.free / (1024 * 1024 * 1024)
        disk_percent = disk.percent
        
        # Process metrics (current MCP server process)
        try:
            process_mem_info = self.process.memory_info()
            process_memory_mb = process_mem_info.rss / (1024 * 1024)
            process_cpu_percent = self.process.cpu_percent(interval=0.1)
            process_threads = self.process.num_threads()
            
            # Count open files
            try:
                process_open_files = len(self.process.open_files())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                process_open_files = 0
        except Exception as e:
            logger.warning(f"Failed to get process metrics: {e}")
            process_memory_mb = 0
            process_cpu_percent = 0
            process_threads = 0
            process_open_files = 0
        
        return SystemMetrics(
            cpu_percent=cpu_percent,
            cpu_count=cpu_count,
            load_avg_1min=load_avg[0],
            load_avg_5min=load_avg[1],
            load_avg_15min=load_avg[2],
            memory_total_mb=memory_total_mb,
            memory_used_mb=memory_used_mb,
            memory_available_mb=memory_available_mb,
            memory_percent=memory_percent,
            disk_total_gb=disk_total_gb,
            disk_used_gb=disk_used_gb,
            disk_free_gb=disk_free_gb,
            disk_percent=disk_percent,
            process_memory_mb=process_memory_mb,
            process_cpu_percent=process_cpu_percent,
            process_threads=process_threads,
            process_open_files=process_open_files,
            timestamp=datetime.now()
        )
    
    def report_to_datadog(self, metrics: SystemMetrics):
        """
        Send infrastructure metrics to Datadog.
        
        Args:
            metrics: SystemMetrics snapshot to report
        """
        if not is_datadog_configured():
            return
        
        # CPU metrics
        record_metric("log_ai.system.cpu.percent", metrics.cpu_percent, 
                     tags=["host:mcp-server"], metric_type="gauge")
        record_metric("log_ai.system.cpu.load_avg_1min", metrics.load_avg_1min,
                     tags=["host:mcp-server"], metric_type="gauge")
        record_metric("log_ai.system.cpu.load_avg_5min", metrics.load_avg_5min,
                     tags=["host:mcp-server"], metric_type="gauge")
        record_metric("log_ai.system.cpu.load_avg_15min", metrics.load_avg_15min,
                     tags=["host:mcp-server"], metric_type="gauge")
        
        # Memory metrics
        record_metric("log_ai.system.memory.total_mb", metrics.memory_total_mb,
                     tags=["host:mcp-server"], metric_type="gauge")
        record_metric("log_ai.system.memory.used_mb", metrics.memory_used_mb,
                     tags=["host:mcp-server"], metric_type="gauge")
        record_metric("log_ai.system.memory.available_mb", metrics.memory_available_mb,
                     tags=["host:mcp-server"], metric_type="gauge")
        record_metric("log_ai.system.memory.percent", metrics.memory_percent,
                     tags=["host:mcp-server"], metric_type="gauge")
        
        # Disk metrics
        record_metric("log_ai.system.disk.total_gb", metrics.disk_total_gb,
                     tags=["host:mcp-server", "mount:/"], metric_type="gauge")
        record_metric("log_ai.system.disk.used_gb", metrics.disk_used_gb,
                     tags=["host:mcp-server", "mount:/"], metric_type="gauge")
        record_metric("log_ai.system.disk.free_gb", metrics.disk_free_gb,
                     tags=["host:mcp-server", "mount:/"], metric_type="gauge")
        record_metric("log_ai.system.disk.percent", metrics.disk_percent,
                     tags=["host:mcp-server", "mount:/"], metric_type="gauge")
        
        # Process metrics
        record_metric("log_ai.process.memory_mb", metrics.process_memory_mb,
                     tags=["process:mcp-server"], metric_type="gauge")
        record_metric("log_ai.process.cpu_percent", metrics.process_cpu_percent,
                     tags=["process:mcp-server"], metric_type="gauge")
        record_metric("log_ai.process.threads", metrics.process_threads,
                     tags=["process:mcp-server"], metric_type="gauge")
        record_metric("log_ai.process.open_files", metrics.process_open_files,
                     tags=["process:mcp-server"], metric_type="gauge")
    
    def monitor_log_directory(self) -> Optional[Dict[str, Any]]:
        """
        Monitor log directory size and file counts.
        
        Returns:
            Dictionary with log directory stats, or None if log_dir not set
        """
        if not self.log_dir or not self.log_dir.exists():
            return None
        
        try:
            total_size = 0
            file_count = 0
            
            for item in self.log_dir.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
                    file_count += 1
            
            total_size_mb = total_size / (1024 * 1024)
            
            # Report to Datadog
            if is_datadog_configured():
                record_metric("log_ai.logs.directory_size_mb", total_size_mb,
                            tags=["directory:log-ai"], metric_type="gauge")
                record_metric("log_ai.logs.file_count", file_count,
                            tags=["directory:log-ai"], metric_type="gauge")
            
            return {
                "total_size_mb": total_size_mb,
                "file_count": file_count,
                "directory": str(self.log_dir)
            }
        
        except Exception as e:
            logger.warning(f"Failed to monitor log directory: {e}")
            return None
    
    def get_network_stats(self) -> Dict[str, Any]:
        """
        Get network interface statistics.
        
        Returns:
            Dictionary with network stats
        """
        try:
            net_io = psutil.net_io_counters()
            net_connections = len(psutil.net_connections(kind='inet'))
            
            stats = {
                "bytes_sent_mb": net_io.bytes_sent / (1024 * 1024),
                "bytes_recv_mb": net_io.bytes_recv / (1024 * 1024),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "errin": net_io.errin,
                "errout": net_io.errout,
                "dropin": net_io.dropin,
                "dropout": net_io.dropout,
                "connections": net_connections
            }
            
            # Report to Datadog
            if is_datadog_configured():
                record_metric("log_ai.network.connections", net_connections,
                            tags=["host:mcp-server"], metric_type="gauge")
            
            return stats
        
        except Exception as e:
            logger.warning(f"Failed to get network stats: {e}")
            return {}
    
    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get overall system health summary.
        
        Returns:
            Dictionary with health status and key metrics
        """
        metrics = self.collect_metrics()
        
        # Determine health status based on thresholds
        health_issues = []
        
        if metrics.cpu_percent > 90:
            health_issues.append("High CPU usage")
        if metrics.memory_percent > 90:
            health_issues.append("High memory usage")
        if metrics.disk_percent > 90:
            health_issues.append("Low disk space")
        if metrics.process_memory_mb > 1024:  # 1GB
            health_issues.append("High process memory")
        
        health_status = "healthy" if not health_issues else "degraded"
        if len(health_issues) >= 3:
            health_status = "critical"
        
        return {
            "status": health_status,
            "issues": health_issues,
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "disk_percent": metrics.disk_percent,
            "process_memory_mb": metrics.process_memory_mb,
            "timestamp": metrics.timestamp.isoformat()
        }


# Global infrastructure monitor instance
_infrastructure_monitor: Optional[InfrastructureMonitor] = None


def get_infrastructure_monitor(log_dir: Optional[Path] = None) -> InfrastructureMonitor:
    """
    Get the global infrastructure monitor instance.
    
    Args:
        log_dir: Optional log directory path for first initialization
    
    Returns:
        InfrastructureMonitor instance
    """
    global _infrastructure_monitor
    if _infrastructure_monitor is None:
        _infrastructure_monitor = InfrastructureMonitor(log_dir=log_dir)
    return _infrastructure_monitor


def reset_infrastructure_monitor():
    """Reset the global infrastructure monitor (for testing)"""
    global _infrastructure_monitor
    _infrastructure_monitor = None
