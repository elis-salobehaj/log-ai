---
title: "Datadog Infrastructure Monitoring Tools"
status: backlog
priority: medium
date_created: 2026-02-05
datadog_urls:
  infrastructure: https://app.datadoghq.com/infrastructure
  hostmap: https://app.datadoghq.com/infrastructure/map
  containers: https://app.datadoghq.com/containers
  processes: https://app.datadoghq.com/process
completion:
  - [ ] list_hosts tool
  - [ ] get_host_details tool
  - [ ] list_containers tool
  - [ ] get_container_metrics tool
  - [ ] list_processes tool
  - [ ] get_ecs_service_status tool
related_files:
  - src/server.py
  - src/datadog_integration.py
  - src/infrastructure_monitoring.py
---

# Datadog Infrastructure Monitoring Tools

## Overview

Add MCP tools to query Datadog Infrastructure for host, container, and process visibility. This enables AI agents to investigate resource issues, container restarts, and system-level problems.

**Use Case from 2026-02-05 Interaction**:
When investigating real-time-service container restarts, we found events like:
- "ECS Deployment on service hub-ca-pason-realtime-service-stream"
- "(service hub-ca-pason-realtime-service-stream) has begun draining connections on 6 tasks"
- "Unexpected Container Restart (PROD)"

Dedicated infrastructure tools would provide deeper visibility into these container/host issues.

---

## Tools

### 1. `list_hosts`

List infrastructure hosts with health and basic metrics.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filter` | string | No | Tag query (e.g., "env:production,service:auth") |
| `sort_by` | enum | No | cpu, memory, status, name |
| `include_metrics` | bool | No | Include CPU/memory metrics (default: false) |
| `mute_status` | enum | No | muted, unmuted, all |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "Show hosts with high CPU in production"
- "List all syslog servers"
- "Which hosts are muted?"

**Response Format**:
```json
{
  "hosts": [
    {
      "id": "host_abc123",
      "name": "syslog.awstst.pason.com",
      "aliases": ["i-0abc123def456"],
      "apps": ["java", "nginx", "datadog-agent"],
      "tags": ["env:production", "service:syslog", "region:us-east-1"],
      "up": true,
      "muted": false,
      "last_reported": "2026-02-05T17:00:00Z",
      "metrics": {
        "cpu_user": 45.2,
        "cpu_system": 12.3,
        "memory_used_pct": 78.5,
        "load_avg_1": 2.5
      }
    }
  ],
  "count": 1,
  "summary": {
    "total": 50,
    "up": 48,
    "down": 2,
    "muted": 5
  }
}
```

### 2. `get_host_details`

Get detailed host information including apps, containers, processes.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `host_name` | string | Yes | Hostname or host ID |
| `include_processes` | bool | No | List top processes (default: true) |
| `include_containers` | bool | No | List containers (default: true) |
| `include_apps` | bool | No | List installed apps (default: false) |
| `include_metrics` | bool | No | Include detailed metrics (default: true) |

**Use Cases**:
- "What's running on syslog.awstst.pason.com?"
- "Show container details for this host"
- "What processes are using the most CPU?"

**Response Format**:
```json
{
  "host": {
    "id": "host_abc123",
    "name": "syslog.awstst.pason.com",
    "platform": "linux",
    "os": "Amazon Linux 2",
    "agent_version": "7.45.0",
    "uptime_seconds": 8640000,
    "metrics": {
      "cpu": {"user": 45.2, "system": 12.3, "iowait": 5.1},
      "memory": {"total_mb": 32768, "used_mb": 25600, "pct": 78.1},
      "disk": {"read_bytes_sec": 1024000, "write_bytes_sec": 512000},
      "network": {"rx_bytes_sec": 50000, "tx_bytes_sec": 30000}
    },
    "top_processes": [
      {"name": "java", "pid": 1234, "cpu_pct": 35.0, "mem_pct": 40.0},
      {"name": "ripgrep", "pid": 5678, "cpu_pct": 10.0, "mem_pct": 2.0}
    ],
    "containers": [
      {"name": "hub-ca-auth", "id": "abc123", "cpu_pct": 5.0, "mem_mb": 512}
    ]
  }
}
```

### 3. `list_containers`

List running containers with resource usage.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | No | Filter by service name |
| `env` | enum | No | cistable, qa, production |
| `cluster` | string | No | ECS/K8s cluster name |
| `status` | enum | No | running, stopped, restarting |
| `image` | string | No | Container image filter |
| `sort_by` | enum | No | cpu, memory, restarts, name |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "Show containers for pason-realtime-service in QA"
- "List restarting containers in production"
- "Which containers are using the most memory?"

**Response Format**:
```json
{
  "containers": [
    {
      "id": "container_abc123",
      "name": "hub-ca-pason-realtime-service",
      "short_id": "abc123def",
      "image": "879270876743.dkr.ecr.us-east-1.amazonaws.com/pason-realtime-service:3.6.4",
      "status": "running",
      "host": "ecs-datahub-fargate-01",
      "cluster": "datahub_fargate_01",
      "env": "production",
      "service": "pason-realtime-service",
      "created": "2026-02-04T17:28:00Z",
      "restart_count": 2,
      "metrics": {
        "cpu_pct": 15.5,
        "memory_mb": 1024,
        "memory_limit_mb": 2048,
        "memory_pct": 50.0,
        "network_rx_bytes": 1000000,
        "network_tx_bytes": 500000
      }
    }
  ],
  "count": 1,
  "summary": {
    "total": 150,
    "running": 145,
    "stopped": 3,
    "restarting": 2
  }
}
```

### 4. `get_container_metrics`

Get detailed container resource metrics over time.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `container_id` | string | Yes | Container ID or name |
| `metrics` | list | No | List: cpu, memory, network, io (default: all) |
| `hours_back` | int | No | Time range for metrics (default: 1) |
| `rollup` | enum | No | Aggregation: avg, max, min, sum |

**Use Cases**:
- "Is this container memory-bound?"
- "Show CPU usage history for this container"
- "Was there a memory spike before the restart?"

**Response Format**:
```json
{
  "container": {
    "id": "container_abc123",
    "name": "hub-ca-pason-realtime-service"
  },
  "metrics": {
    "cpu": {
      "avg": 15.5,
      "max": 85.0,
      "min": 2.0,
      "current": 12.3,
      "series": [
        {"timestamp": "2026-02-05T16:00:00Z", "value": 10.0},
        {"timestamp": "2026-02-05T16:05:00Z", "value": 15.0}
      ]
    },
    "memory": {
      "avg_mb": 900,
      "max_mb": 1900,
      "limit_mb": 2048,
      "current_mb": 1024,
      "oom_kills": 1
    },
    "network": {
      "rx_bytes_total": 10000000,
      "tx_bytes_total": 5000000
    }
  },
  "time_range": {"start": "...", "end": "..."}
}
```

### 5. `list_processes`

List running processes on hosts.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `host` | string | No | Hostname filter |
| `user` | string | No | Process user filter |
| `command_filter` | string | No | Command name/args filter (supports wildcards) |
| `sort_by` | enum | No | cpu, memory, rss, name |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "What Java processes are on this host?"
- "Show top CPU processes across all syslog servers"
- "Find ripgrep processes"

**Response Format**:
```json
{
  "processes": [
    {
      "pid": 1234,
      "name": "java",
      "user": "app",
      "host": "syslog.awstst.pason.com",
      "command": "java -jar /app/realtime-service.jar",
      "cpu_pct": 35.0,
      "memory_pct": 40.0,
      "rss_mb": 4096,
      "threads": 150,
      "start_time": "2026-02-04T17:30:00Z",
      "state": "running"
    }
  ],
  "count": 1
}
```

### 6. `get_ecs_service_status`

Get ECS-specific service health and task status. Special tool for AWS ECS/Fargate environments.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cluster` | string | Yes | ECS cluster name (e.g., "datahub_fargate_01") |
| `service_name` | string | Yes | ECS service name |
| `env` | enum | No | cistable, qa, production |
| `include_events` | bool | No | Include recent service events (default: true) |
| `include_tasks` | bool | No | Include task details (default: true) |

**Use Cases**:
- "Show task status for hub-ca-pason-realtime-service-stream"
- "Why did the service have task failures?"
- "What's the deployment status?"

**Response Format**:
```json
{
  "service": {
    "name": "hub-ca-pason-realtime-service-stream",
    "cluster": "datahub_fargate_01",
    "status": "ACTIVE",
    "desired_count": 6,
    "running_count": 6,
    "pending_count": 0,
    "deployment_status": "COMPLETED",
    "current_version": "3.6.4.20260203.183922",
    "previous_version": "3.6.3.20260122.161556",
    "last_deployment": "2026-02-04T17:25:48Z"
  },
  "tasks": [
    {
      "task_id": "abc123",
      "status": "RUNNING",
      "health_status": "HEALTHY",
      "started_at": "2026-02-04T17:30:00Z",
      "container_instance": "ecs-fargate-01",
      "cpu_pct": 15.0,
      "memory_mb": 1024
    }
  ],
  "events": [
    {
      "timestamp": "2026-02-04T17:28:43Z",
      "message": "ECS Deployment on service hub-ca-pason-realtime-service-stream"
    },
    {
      "timestamp": "2026-02-04T17:26:50Z",
      "message": "has begun draining connections on 6 tasks"
    }
  ],
  "recent_restarts": 2,
  "restart_reasons": [
    {"timestamp": "2026-02-04T15:28:00Z", "reason": "Essential container exited", "exit_code": 137}
  ]
}
```

---

## Implementation Notes

### API Reference

- Hosts API: https://docs.datadoghq.com/api/latest/hosts/
- Containers API: https://docs.datadoghq.com/api/latest/containers/
- Processes API: https://docs.datadoghq.com/api/latest/processes/

### Required Permissions

- `hosts_read` - Read host data
- `containers_read` - Read container data
- `processes_read` - Read process data

### Integration with Existing Tools

These tools complement existing Datadog tools:
- `search_datadog_events` - Shows ECS deployment events
- `query_datadog_metrics` - Can query infrastructure metrics
- `list_datadog_monitors` - Infrastructure monitors

### Example Workflow (Container Restart Investigation)

1. User reports: "realtime-service containers keep restarting"
2. Agent uses `search_datadog_events(query="realtime restart")` - sees restart events
3. Uses `list_containers(service="pason-realtime-service", env="production")`
4. Finds container with high restart count, uses `get_container_metrics(container_id="...")`
5. Sees memory spike before restart (OOM), uses `get_ecs_service_status` for full picture
6. Correlates with `query_datadog_apm` for request patterns during OOM
