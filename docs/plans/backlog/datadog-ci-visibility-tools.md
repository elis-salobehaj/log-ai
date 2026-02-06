---
title: "Datadog CI Visibility & Test Optimization Tools"
status: backlog
priority: medium
date_created: 2026-02-05
datadog_urls:
  pipelines: https://app.datadoghq.com/ci/pipelines/
  tests: https://app.datadoghq.com/ci/test/
completion:
  - [ ] list_ci_pipelines tool
  - [ ] get_pipeline_details tool
  - [ ] list_test_runs tool
  - [ ] get_test_failure_details tool
related_files:
  - src/server.py
  - src/datadog_integration.py
---

# Datadog CI Visibility & Test Optimization Tools

## Overview

Add MCP tools to query Datadog CI Visibility for pipeline status and test results. This enables AI agents to investigate CI/CD failures, identify flaky tests, and correlate build issues with code changes.

**Use Case from 2026-02-05 Interaction**:
When investigating real-time-service issues, we found events like:
- "[Triggered on {@ci.pipeline.name:pasonsystems/repos/dma/products/Real-Time-Service}] Basilisk Pipeline PROD Smoke Tests"
- "Functional Test qa: pason-realtime-service_ca"

Having dedicated CI tools would let agents drill into these failures.

---

## Tools

### 1. `list_ci_pipelines`

List recent CI/CD pipeline runs with status filtering.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repository` | string | No | Filter by repo (e.g., "pasonsystems/repos/dma/products/Real-Time-Service") |
| `branch` | string | No | Filter by branch (e.g., "main", "develop") |
| `status` | enum | No | Filter by status: success, failed, running, canceled |
| `env` | enum | No | Environment: cistable, qa, production |
| `hours_back` | int | No | Time range (default: 24) |
| `limit` | int | No | Max results (default: 50) |

**Use Cases**:
- "What pipelines failed in the last 24h for Real-Time-Service?"
- "Show running pipelines for main branch"
- "List all failed QA deployments today"

**Response Format**:
```json
{
  "pipelines": [
    {
      "id": "pipeline_123",
      "name": "Real-Time-Service CI",
      "repository": "pasonsystems/repos/dma/products/Real-Time-Service",
      "branch": "main",
      "commit_sha": "abc123",
      "status": "failed",
      "started_at": "2026-02-05T10:00:00Z",
      "duration_ms": 300000,
      "failed_jobs": ["smoke-test-against-qaca"]
    }
  ],
  "count": 1,
  "time_range": {"start": "...", "end": "..."}
}
```

### 2. `get_pipeline_details`

Get specific pipeline execution details including jobs and stages.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pipeline_id` | string | Yes | Pipeline execution ID |
| `include_jobs` | bool | No | Include job-level details (default: true) |
| `include_logs` | bool | No | Include job log snippets (default: false) |

**Use Cases**:
- "Show me the failing job in pipeline X"
- "What stage failed in the last deployment?"
- "Get the error logs from the failed test job"

**Response Format**:
```json
{
  "pipeline": {
    "id": "pipeline_123",
    "name": "Real-Time-Service CI",
    "status": "failed",
    "stages": [
      {
        "name": "build",
        "status": "success",
        "duration_ms": 120000
      },
      {
        "name": "test",
        "status": "failed",
        "duration_ms": 180000,
        "jobs": [
          {
            "name": "smoke-test-against-qaca",
            "status": "failed",
            "error_message": "Connection timeout to QA environment"
          }
        ]
      }
    ]
  }
}
```

### 3. `list_test_runs`

List test execution results with filtering.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | No | Service/project name |
| `test_suite` | string | No | Filter by test suite |
| `status` | enum | No | passed, failed, skipped |
| `branch` | string | No | Git branch |
| `is_flaky` | bool | No | Filter for flaky tests (default: false) |
| `hours_back` | int | No | Time range (default: 24) |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "Show flaky tests for pason-realtime-service"
- "What tests failed in the last CI run?"
- "List all skipped tests this week"

**Response Format**:
```json
{
  "tests": [
    {
      "test_id": "test_abc123",
      "name": "testHealthEndpoint",
      "suite": "HealthCheckTests",
      "service": "pason-realtime-service",
      "status": "failed",
      "duration_ms": 5000,
      "is_flaky": true,
      "failure_count_30d": 15,
      "pass_rate_30d": 0.85
    }
  ],
  "count": 1,
  "summary": {
    "passed": 150,
    "failed": 3,
    "skipped": 2,
    "flaky": 5
  }
}
```

### 4. `get_test_failure_details`

Get detailed test failure information including stack traces and history.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `test_id` | string | Yes | Test fingerprint ID |
| `include_history` | bool | No | Show failure history (default: true) |
| `include_trace` | bool | No | Include stack trace (default: true) |
| `history_days` | int | No | Days of history (default: 30) |

**Use Cases**:
- "Why is this test failing?"
- "Is this a new failure or recurring?"
- "Show the stack trace for the failed assertion"

**Response Format**:
```json
{
  "test": {
    "test_id": "test_abc123",
    "name": "testHealthEndpoint",
    "suite": "HealthCheckTests",
    "status": "failed",
    "error_type": "AssertionError",
    "error_message": "Expected status 200 but got 503",
    "stack_trace": "at HealthCheckTests.testHealthEndpoint(HealthCheckTests.java:45)...",
    "first_failure": "2026-01-20T10:00:00Z",
    "failure_history": [
      {"date": "2026-02-05", "failures": 2, "passes": 8},
      {"date": "2026-02-04", "failures": 1, "passes": 9}
    ],
    "is_new_failure": false,
    "suggested_cause": "Service health check timeout - may indicate infrastructure issue"
  }
}
```

---

## Implementation Notes

### API Reference

- Datadog CI Visibility API: https://docs.datadoghq.com/api/latest/ci-visibility-pipelines/
- Test Visibility API: https://docs.datadoghq.com/api/latest/ci-visibility-tests/

### Required Permissions

- `ci_visibility_read` - Read CI pipeline data
- `ci_visibility_tests_read` - Read test results

### Integration with Existing Tools

These tools complement existing Datadog tools:
- `search_datadog_events` - Already shows CI-related events
- `query_datadog_apm` - Can correlate with deployment traces

### Example Workflow

1. User reports: "QA smoke tests are failing for realtime-service"
2. Agent uses `list_ci_pipelines(service="pason-realtime-service", env="qa", status="failed")`
3. Finds recent failed pipeline, uses `get_pipeline_details(pipeline_id="...")`
4. Identifies failing test, uses `get_test_failure_details(test_id="...")`
5. Correlates with `search_datadog_events` for deployment timeline
