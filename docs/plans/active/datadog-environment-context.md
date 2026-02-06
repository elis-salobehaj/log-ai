---
title: "Datadog Tools - Environment Context Enhancement"
status: active
priority: high
date_created: 2026-02-05
date_updated: 2026-02-05
completion:
  - [ ] Step 1: Add env parameter to tool schemas
  - [ ] Step 2: Update MCP handler functions
  - [ ] Step 3: Update datadog_integration.py functions
  - [ ] Step 4: Add Datadog URL hints in responses
  - [ ] Step 5: Add tests for env filtering
  - [ ] Step 6: Manual validation with MCP Inspector
related_files:
  - src/server.py
  - src/datadog_integration.py
  - tests/test_phase3_6_datadog_queries.py
evidence:
  interaction_date: 2026-02-05
  issue: "User asked for 'realtime-service issues in QA' but tools lack env parameter"
  workaround: "Manual query construction with env:qa prefix"
  findings:
    - "100 events mixed across qa/production/cistable"
    - "Container restarts found for hub-ca-pason-realtime-service-stream"
    - "Monitor 'RTS might be going wonky soon' triggered multiple times"
---

# Datadog Tools - Environment Context Enhancement

**Problem**: When agents search Datadog for service issues in a specific environment (qa/cistable/production), they must manually construct queries with `env:` prefix. This is error-prone and not intuitive.

**Evidence from 2026-02-05 Interaction**:
- User request: "find datadog issues for real-time-service in QA"
- Current behavior: `search_datadog_events(query="realtime")` returns mixed environments
- Found 100 events spanning production, qa, and cistable
- Key findings:
  - Container restarts on `hub-ca-pason-realtime-service-stream` (Feb 4, 14:58 & 15:28 UTC)
  - Monitor "Unexpected Container Restart (PROD)" triggered twice
  - QA anomaly alerts: "Anomaly Request Duration" (Feb 5, 10:19 UTC)
  - Deployment v3.6.3 → v3.6.4 on Feb 4, 17:25 UTC

**Solution**: Add `env` parameter to all Datadog MCP tools.

---

## Implementation Steps

### Step 1: Add `env` Parameter to Tool Schemas

**File**: [src/server.py](src/server.py#L1250-L1450)

Add to each Datadog tool's `inputSchema`:

```python
"env": {
    "type": "string",
    "enum": ["cistable", "qa", "production"],
    "description": "Environment filter (cistable=dev, qa=staging, production)"
}
```

**Tools to update**:
- `query_datadog_apm` (line ~1250)
- `query_datadog_metrics` (line ~1289)
- `query_datadog_logs` (line ~1320)
- `list_datadog_monitors` (line ~1356)
- `search_datadog_events` (line ~1395)
- `get_service_dependencies` (line ~1440)

### Step 2: Update MCP Handler Functions

**File**: [src/server.py](src/server.py#L2209-L2600)

For each handler, extract `env` and inject into query:

```python
async def query_datadog_apm_handler(args: dict) -> list[types.TextContent]:
    service = args.get("service")
    env = args.get("env")  # NEW
    # ...
    
    # Resolve service name
    datadog_service = service
    # ... existing resolution logic ...
    
    # Query with env filter
    result = query_apm_traces(
        service=datadog_service,
        env=env,  # NEW
        start_time=start_time,
        end_time=end_time,
        # ...
    )
```

**Handlers to update**:
- `query_datadog_apm_handler` (line ~2209)
- `query_datadog_metrics_handler` (line ~2284)
- `query_datadog_logs_handler` (line ~2361)
- `list_datadog_monitors_handler` (line ~2429)
- `search_datadog_events_handler` (line ~2506)
- `get_service_dependencies_handler` (line ~2583)

### Step 3: Update datadog_integration.py Functions

**File**: [src/datadog_integration.py](src/datadog_integration.py)

Update function signatures and query building:

```python
def query_apm_traces(
    service: str,
    start_time: datetime,
    end_time: datetime,
    env: Optional[str] = None,  # NEW
    operation: Optional[str] = None,
    min_duration_ms: Optional[int] = None,
    limit: int = 100
) -> Dict[str, Any]:
    # Build query filter
    query_parts = [f"service:{service}"]
    if env:
        query_parts.append(f"env:{env}")  # NEW
    # ... rest of query building
```

**Functions to update**:
- `query_apm_traces` (line ~289)
- `query_logs` (line ~461)
- `list_monitors` (line ~539)
- `search_events` (line ~657)

### Step 4: Add Datadog URL Hints in Responses

Add helpful URLs in text format responses:

```python
# In query_datadog_apm_handler
lines = [
    f"=== Datadog APM Traces: {service} ===",
    f"Environment: {env or 'all'}",
    f"Time Range: {result['time_range']['start']} to {result['time_range']['end']} UTC",
    f"Total Traces: {result['count']}",
    f"",
]
if env:
    lines.append(f"📊 View in Datadog: https://app.datadoghq.com/apm/traces?query=env%3A{env}%20service%3A{datadog_service}")
```

### Step 5: Add Tests

**File**: `tests/test_datadog_env_filtering.py` (new)

```python
import pytest
from datetime import datetime, timedelta, timezone

@pytest.mark.asyncio
async def test_query_apm_with_env_filter():
    """Test that env parameter is correctly injected into APM query."""
    from src.datadog_integration import query_apm_traces
    
    # Mock or integration test
    # Verify query string contains env:qa
    
@pytest.mark.asyncio
async def test_search_events_with_env_filter():
    """Test events search with environment filter."""
    from src.datadog_integration import search_events
    
    # Verify events are filtered by env tag

@pytest.mark.asyncio
async def test_query_logs_with_env_filter():
    """Test logs query with environment filter."""
    from src.datadog_integration import query_logs
    
    # Verify query prepends env filter
```

### Step 6: Manual Validation

Test with MCP Inspector:
```bash
npx @anthropic/mcp-inspector uv run python -m src.server
```

Queries to test:
1. `query_datadog_apm(service="pason-realtime-service", env="qa", hours_back=168)`
2. `search_datadog_events(query="container restart", env="qa", hours_back=168)`
3. `list_datadog_monitors(service="pason-realtime-service", env="production")`

---

## Verification

```bash
# Run new tests
uv run pytest tests/test_datadog_env_filtering.py -v

# Run all Datadog tests
uv run pytest tests/test_phase3_6_datadog_queries.py tests/test_datadog_env_filtering.py -v

# Manual test
npx @anthropic/mcp-inspector uv run python -m src.server
```

---

## Reference: Datadog URLs by Environment

| Tool | URL Pattern |
|------|-------------|
| APM Traces | `https://app.datadoghq.com/apm/traces?query=env%3A{env}%20service%3A{service}` |
| Logs | `https://app.datadoghq.com/logs?query=env%3A{env}%20service%3A{service}` |
| Events | `https://app.datadoghq.com/event/explorer?query=env%3A{env}` |
| Monitors | `https://app.datadoghq.com/monitors/manage?q=tag%3A%22env%3A{env}%22` |
| Profiling | `https://app.datadoghq.com/profiling/explorer?query=env%3A{env}` |
| Service APM | `https://app.datadoghq.com/apm/entity/service%3A{service}?env={env}` |

---

## Interaction Evidence Summary

**What Worked**:
- `query_datadog_apm(service="pason-realtime-service", hours_back=168)` → Found 100 traces
- `search_datadog_events(query="realtime", hours_back=168)` → Found 100 events

**What Was Missing**:
- No `env` parameter to filter to QA specifically
- Had to guess event query syntax (`tags:env:qa` failed with 400 error)
- Manual filtering needed for specific environment events

**Key Findings from Real-Time-Service Investigation**:
| Time (UTC) | Event | Environment |
|------------|-------|-------------|
| Feb 4, 14:58 | Container restart trigger | Production |
| Feb 4, 15:28 | Container restart trigger | Production |
| Feb 4, 17:25-17:28 | Deployment v3.6.3 → v3.6.4 | All |
| Feb 5, 10:19 | Request duration anomaly | QA |
| Feb 3, 19:19 | "tasks failed to start" | cistable |
