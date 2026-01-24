"""Tests for Phase 3.4 - Infrastructure Monitoring

Tests system-level infrastructure monitoring and reporting.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime
import psutil

# Import modules under test
from src.infrastructure_monitoring import (
    InfrastructureMonitor,
    SystemMetrics,
    get_infrastructure_monitor,
    reset_infrastructure_monitor
)


@pytest.fixture(autouse=True)
def reset_monitor_state():
    """Reset infrastructure monitor before each test"""
    reset_infrastructure_monitor()
    yield
    reset_infrastructure_monitor()


def test_infrastructure_monitor_initialization():
    """Test that infrastructure monitor initializes correctly"""
    monitor = InfrastructureMonitor()
    
    assert monitor.process is not None
    assert monitor.process.pid == psutil.Process().pid


def test_infrastructure_monitor_with_log_dir():
    """Test infrastructure monitor with log directory"""
    log_dir = Path("/tmp/test-logs")
    monitor = InfrastructureMonitor(log_dir=log_dir)
    
    assert monitor.log_dir == log_dir


def test_collect_metrics():
    """Test collecting system metrics snapshot"""
    monitor = InfrastructureMonitor()
    
    metrics = monitor.collect_metrics()
    
    # Verify metrics object structure
    assert isinstance(metrics, SystemMetrics)
    assert isinstance(metrics.timestamp, datetime)
    
    # CPU metrics
    assert metrics.cpu_percent >= 0
    assert metrics.cpu_count > 0
    assert metrics.load_avg_1min >= 0
    
    # Memory metrics
    assert metrics.memory_total_mb > 0
    assert metrics.memory_used_mb >= 0
    assert metrics.memory_available_mb >= 0
    assert 0 <= metrics.memory_percent <= 100
    
    # Disk metrics
    assert metrics.disk_total_gb > 0
    assert metrics.disk_used_gb >= 0
    assert metrics.disk_free_gb >= 0
    assert 0 <= metrics.disk_percent <= 100
    
    # Process metrics
    assert metrics.process_memory_mb >= 0
    assert metrics.process_cpu_percent >= 0
    assert metrics.process_threads > 0


def test_cpu_metrics_reasonable():
    """Test that CPU metrics are within reasonable bounds"""
    monitor = InfrastructureMonitor()
    metrics = monitor.collect_metrics()
    
    # CPU percent should be 0-100 per core (can exceed 100 on multi-core)
    assert 0 <= metrics.cpu_percent <= 100 * metrics.cpu_count
    
    # Load average should be non-negative
    assert metrics.load_avg_1min >= 0
    assert metrics.load_avg_5min >= 0
    assert metrics.load_avg_15min >= 0


def test_memory_metrics_consistency():
    """Test that memory metrics are internally consistent"""
    monitor = InfrastructureMonitor()
    metrics = monitor.collect_metrics()
    
    # Used + available should approximately equal total
    # (There's some margin due to buffers/cache)
    total_accounted = metrics.memory_used_mb + metrics.memory_available_mb
    assert abs(total_accounted - metrics.memory_total_mb) < metrics.memory_total_mb * 0.5
    
    # Percent should match used/total ratio (within 5% tolerance)
    calculated_percent = (metrics.memory_used_mb / metrics.memory_total_mb) * 100
    assert abs(calculated_percent - metrics.memory_percent) < 5


def test_disk_metrics_consistency():
    """Test that disk metrics are internally consistent"""
    monitor = InfrastructureMonitor()
    metrics = monitor.collect_metrics()
    
    # Used + free should approximately equal total
    total_accounted = metrics.disk_used_gb + metrics.disk_free_gb
    assert abs(total_accounted - metrics.disk_total_gb) < 1.0  # Within 1 GB
    
    # Percent should match used/total ratio
    calculated_percent = (metrics.disk_used_gb / metrics.disk_total_gb) * 100
    assert abs(calculated_percent - metrics.disk_percent) < 2


@patch('src.infrastructure_monitoring.is_datadog_configured', return_value=True)
@patch('src.infrastructure_monitoring.record_metric')
def test_report_to_datadog(mock_record_metric, mock_is_configured):
    """Test that metrics are reported to Datadog"""
    monitor = InfrastructureMonitor()
    metrics = monitor.collect_metrics()
    
    monitor.report_to_datadog(metrics)
    
    # Verify all metric types were reported
    metric_names = [call[0][0] for call in mock_record_metric.call_args_list]
    
    # CPU metrics (4 metrics)
    assert "log_ai.system.cpu.percent" in metric_names
    assert "log_ai.system.cpu.load_avg_1min" in metric_names
    assert "log_ai.system.cpu.load_avg_5min" in metric_names
    assert "log_ai.system.cpu.load_avg_15min" in metric_names
    
    # Memory metrics (4 metrics)
    assert "log_ai.system.memory.total_mb" in metric_names
    assert "log_ai.system.memory.used_mb" in metric_names
    assert "log_ai.system.memory.available_mb" in metric_names
    assert "log_ai.system.memory.percent" in metric_names
    
    # Disk metrics (4 metrics)
    assert "log_ai.system.disk.total_gb" in metric_names
    assert "log_ai.system.disk.used_gb" in metric_names
    assert "log_ai.system.disk.free_gb" in metric_names
    assert "log_ai.system.disk.percent" in metric_names
    
    # Process metrics (4 metrics)
    assert "log_ai.process.memory_mb" in metric_names
    assert "log_ai.process.cpu_percent" in metric_names
    assert "log_ai.process.threads" in metric_names
    assert "log_ai.process.open_files" in metric_names
    
    # Total: 16 metrics
    assert len(mock_record_metric.call_args_list) == 16


@patch('src.infrastructure_monitoring.is_datadog_configured', return_value=False)
@patch('src.infrastructure_monitoring.record_metric')
def test_report_to_datadog_disabled(mock_record_metric, mock_is_configured):
    """Test that no metrics are sent when Datadog is disabled"""
    monitor = InfrastructureMonitor()
    metrics = monitor.collect_metrics()
    
    monitor.report_to_datadog(metrics)
    
    # Should not call record_metric when Datadog is disabled
    mock_record_metric.assert_not_called()


def test_monitor_log_directory_nonexistent():
    """Test monitoring log directory that doesn't exist"""
    monitor = InfrastructureMonitor(log_dir=Path("/nonexistent/path"))
    
    result = monitor.monitor_log_directory()
    
    assert result is None


def test_monitor_log_directory_empty(tmp_path):
    """Test monitoring empty log directory"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    
    monitor = InfrastructureMonitor(log_dir=log_dir)
    
    with patch('src.infrastructure_monitoring.is_datadog_configured', return_value=False):
        result = monitor.monitor_log_directory()
    
    assert result is not None
    assert result["file_count"] == 0
    assert result["total_size_mb"] == 0
    assert result["directory"] == str(log_dir)


def test_monitor_log_directory_with_files(tmp_path):
    """Test monitoring log directory with files"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    
    # Create test files
    (log_dir / "test1.log").write_text("x" * 1024)  # 1 KB
    (log_dir / "test2.log").write_text("x" * 2048)  # 2 KB
    
    monitor = InfrastructureMonitor(log_dir=log_dir)
    
    with patch('src.infrastructure_monitoring.is_datadog_configured', return_value=False):
        result = monitor.monitor_log_directory()
    
    assert result is not None
    assert result["file_count"] == 2
    assert result["total_size_mb"] > 0
    assert result["total_size_mb"] < 1  # Should be < 1 MB


@patch('src.infrastructure_monitoring.is_datadog_configured', return_value=True)
@patch('src.infrastructure_monitoring.record_metric')
def test_monitor_log_directory_reports_to_datadog(mock_record_metric, mock_is_configured, tmp_path):
    """Test that log directory stats are reported to Datadog"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "test.log").write_text("test content")
    
    monitor = InfrastructureMonitor(log_dir=log_dir)
    monitor.monitor_log_directory()
    
    # Verify metrics were sent
    metric_names = [call[0][0] for call in mock_record_metric.call_args_list]
    assert "log_ai.logs.directory_size_mb" in metric_names
    assert "log_ai.logs.file_count" in metric_names


def test_get_network_stats():
    """Test getting network statistics"""
    monitor = InfrastructureMonitor()
    
    with patch('src.infrastructure_monitoring.is_datadog_configured', return_value=False):
        stats = monitor.get_network_stats()
    
    assert "bytes_sent_mb" in stats
    assert "bytes_recv_mb" in stats
    assert "packets_sent" in stats
    assert "packets_recv" in stats
    assert "connections" in stats
    
    # All values should be non-negative
    assert stats["bytes_sent_mb"] >= 0
    assert stats["bytes_recv_mb"] >= 0
    assert stats["connections"] >= 0


@patch('src.infrastructure_monitoring.is_datadog_configured', return_value=True)
@patch('src.infrastructure_monitoring.record_metric')
def test_get_network_stats_reports_to_datadog(mock_record_metric, mock_is_configured):
    """Test that network stats are reported to Datadog"""
    monitor = InfrastructureMonitor()
    monitor.get_network_stats()
    
    # Verify connections metric was sent
    metric_names = [call[0][0] for call in mock_record_metric.call_args_list]
    assert "log_ai.network.connections" in metric_names


def test_get_health_summary_healthy():
    """Test health summary when system is healthy"""
    monitor = InfrastructureMonitor()
    
    # Mock metrics to simulate healthy system
    with patch.object(monitor, 'collect_metrics') as mock_collect:
        mock_collect.return_value = SystemMetrics(
            cpu_percent=30.0,
            cpu_count=4,
            load_avg_1min=1.5,
            load_avg_5min=1.2,
            load_avg_15min=1.0,
            memory_total_mb=8192,
            memory_used_mb=4096,
            memory_available_mb=4096,
            memory_percent=50.0,
            disk_total_gb=500,
            disk_used_gb=250,
            disk_free_gb=250,
            disk_percent=50.0,
            process_memory_mb=256,
            process_cpu_percent=5.0,
            process_threads=10,
            process_open_files=20,
            timestamp=datetime.now()
        )
        
        health = monitor.get_health_summary()
    
    assert health["status"] == "healthy"
    assert len(health["issues"]) == 0
    assert health["cpu_percent"] == 30.0
    assert health["memory_percent"] == 50.0


def test_get_health_summary_degraded():
    """Test health summary when system is degraded"""
    monitor = InfrastructureMonitor()
    
    # Mock metrics to simulate degraded system (high CPU)
    with patch.object(monitor, 'collect_metrics') as mock_collect:
        mock_collect.return_value = SystemMetrics(
            cpu_percent=95.0,  # High CPU
            cpu_count=4,
            load_avg_1min=3.5,
            load_avg_5min=3.2,
            load_avg_15min=3.0,
            memory_total_mb=8192,
            memory_used_mb=4096,
            memory_available_mb=4096,
            memory_percent=50.0,
            disk_total_gb=500,
            disk_used_gb=250,
            disk_free_gb=250,
            disk_percent=50.0,
            process_memory_mb=256,
            process_cpu_percent=10.0,
            process_threads=10,
            process_open_files=20,
            timestamp=datetime.now()
        )
        
        health = monitor.get_health_summary()
    
    assert health["status"] == "degraded"
    assert "High CPU usage" in health["issues"]


def test_get_health_summary_critical():
    """Test health summary when system is critical"""
    monitor = InfrastructureMonitor()
    
    # Mock metrics to simulate critical system (multiple issues)
    with patch.object(monitor, 'collect_metrics') as mock_collect:
        mock_collect.return_value = SystemMetrics(
            cpu_percent=95.0,  # High CPU
            cpu_count=4,
            load_avg_1min=5.0,
            load_avg_5min=4.8,
            load_avg_15min=4.5,
            memory_total_mb=8192,
            memory_used_mb=7680,
            memory_available_mb=512,
            memory_percent=95.0,  # High memory
            disk_total_gb=500,
            disk_used_gb=475,
            disk_free_gb=25,
            disk_percent=95.0,  # High disk
            process_memory_mb=1536,  # High process memory
            process_cpu_percent=20.0,
            process_threads=50,
            process_open_files=200,
            timestamp=datetime.now()
        )
        
        health = monitor.get_health_summary()
    
    assert health["status"] == "critical"
    assert len(health["issues"]) >= 3
    assert "High CPU usage" in health["issues"]
    assert "High memory usage" in health["issues"]
    assert "Low disk space" in health["issues"]


def test_global_infrastructure_monitor():
    """Test that get_infrastructure_monitor returns singleton instance"""
    monitor1 = get_infrastructure_monitor()
    monitor2 = get_infrastructure_monitor()
    
    assert monitor1 is monitor2


def test_global_infrastructure_monitor_with_log_dir():
    """Test global infrastructure monitor initialization with log dir"""
    log_dir = Path("/tmp/test-logs")
    
    monitor = get_infrastructure_monitor(log_dir=log_dir)
    
    assert monitor.log_dir == log_dir
    
    # Subsequent calls should return same instance
    monitor2 = get_infrastructure_monitor()
    assert monitor2 is monitor
    assert monitor2.log_dir == log_dir


def test_metrics_collection_multiple_times():
    """Test that metrics can be collected multiple times"""
    monitor = InfrastructureMonitor()
    
    metrics1 = monitor.collect_metrics()
    metrics2 = monitor.collect_metrics()
    
    # Both should be valid SystemMetrics
    assert isinstance(metrics1, SystemMetrics)
    assert isinstance(metrics2, SystemMetrics)
    
    # Timestamps should be different
    assert metrics2.timestamp > metrics1.timestamp


@pytest.mark.parametrize("cpu,mem,disk,expected_issues", [
    (50, 50, 50, 0),          # All healthy
    (95, 50, 50, 1),          # High CPU
    (50, 95, 50, 1),          # High memory
    (50, 50, 95, 1),          # High disk
    (95, 95, 50, 2),          # CPU + memory
    (95, 95, 95, 3),          # All high
])
def test_health_thresholds(cpu, mem, disk, expected_issues):
    """Test various health threshold scenarios"""
    monitor = InfrastructureMonitor()
    
    with patch.object(monitor, 'collect_metrics') as mock_collect:
        mock_collect.return_value = SystemMetrics(
            cpu_percent=cpu,
            cpu_count=4,
            load_avg_1min=1.0,
            load_avg_5min=1.0,
            load_avg_15min=1.0,
            memory_total_mb=8192,
            memory_used_mb=8192 * mem / 100,
            memory_available_mb=8192 * (100 - mem) / 100,
            memory_percent=mem,
            disk_total_gb=500,
            disk_used_gb=500 * disk / 100,
            disk_free_gb=500 * (100 - disk) / 100,
            disk_percent=disk,
            process_memory_mb=256,
            process_cpu_percent=5.0,
            process_threads=10,
            process_open_files=20,
            timestamp=datetime.now()
        )
        
        health = monitor.get_health_summary()
    
    assert len(health["issues"]) == expected_issues
