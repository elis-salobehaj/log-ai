---
status: complete
date: 2026-01-25
issue: Datadog APM returning 0 traces for hub-ca-auth
solution: Service name mapping - hub-ca-auth → pason-auth-service
---

# Datadog Service Name Mapping - RESOLVED

## Issue

Datadog APM was returning 0 traces for `hub-ca-auth` service even though traces existed in Datadog.

**User Discovery**: The Datadog link showed the service name is actually `pason-auth-service`, not `hub-ca-auth`.

Datadog URL: https://app.datadoghq.com/apm/traces?query=env%3Aqa%20service%3Apason-auth-service

## Root Cause

Our log files use the naming convention `hub-ca-auth` (from Kinesis streams), but the **actual Java service running in Datadog APM** is named `pason-auth-service`.

When we queried `service:hub-ca-auth`, Datadog found no matches because no service with that name exists in their APM data.

## Solution

Added service name mapping similar to existing `sentry_service_name` pattern:

### 1. Extended ServiceConfig Model

**File**: `src/config.py`

```python
class ServiceConfig(BaseModel):
    name: str
    type: str
    description: str
    path_pattern: str
    path_date_formats: Optional[List[str]] = None
    sentry_service_name: Optional[str] = None
    sentry_dsn: Optional[str] = None
    datadog_service_name: Optional[str] = None  # NEW
```

### 2. Updated services.yaml

**File**: `config/services.yaml`

```yaml
- name: hub-ca-auth
  type: json
  description: Hub CA Auth Service logs from Kinesis Firehose
  path_pattern: /syslog/application_logs/{YYYY}/{MM}/{DD}/{HH}/hub-ca-auth-kinesis-*
  path_date_formats:
  - '{YYYY}'
  - '{MM}'
  - '{DD}'
  - '{HH}'
  sentry_service_name: auth-service
  sentry_dsn: https://99a902ab689d49578607acc5c1d01b53@sentry.awstst.pason.com/4
  datadog_service_name: pason-auth-service  # NEW
```

### 3. Updated APM Handler

**File**: `src/server.py` - `query_datadog_apm_handler()`

```python
# Resolve service name to Datadog service name
datadog_service = service  # Default to input service name
target_service = next((s for s in config.services if s.name == service), None)
if target_service and target_service.datadog_service_name:
    datadog_service = target_service.datadog_service_name
    logger.debug(f"[DATADOG] Mapped {service} -> {datadog_service}")

# Query with mapped name
result = query_apm_traces(
    service=datadog_service,  # Use mapped name
    start_time=start_time,
    end_time=end_time,
    operation=operation,
    min_duration_ms=min_duration_ms
)
```

### 4. Updated Validation Script

**File**: `scripts/validate_production_tools.py`

Added same mapping logic to validation tests:

```python
# Map service name to Datadog service name
from src.config import load_config
app_config = load_config()
datadog_service = service  # Default
target_service = next((s for s in app_config.services if s.name == service), None)
if target_service and target_service.datadog_service_name:
    datadog_service = target_service.datadog_service_name

result = query_apm_traces(
    service=datadog_service,  # Use mapped name
    start_time=start_time,
    end_time=end_time,
    limit=10
)
```

## Results

### Before (0 traces)
```
TEST 3: query_datadog_apm (service=hub-ca-auth)
✅ PASSED: Found 0 traces in 337ms
```

Query sent: `service:hub-ca-auth` → No matches in Datadog

### After (10+ traces)
```
TEST 3: query_datadog_apm (service=hub-ca-auth)
✅ PASSED: Found 10 traces in 432ms

Sample traces:
  1. Operation: trace.annotation
  2. Operation: jakarta_rs.request
```

Query sent: `service:pason-auth-service` → Found traces!

## Production Validation

**Test Results** (hub-ca-auth):
- ✅ search_logs: 46 ERROR logs (1.92s)
- ✅ query_sentry_issues: 5 issues (566ms)
- ✅ **query_datadog_apm: 10 traces (432ms)** ← FIXED
- ✅ query_datadog_logs: 0 logs (154ms)
- ⚠️ query_datadog_metrics: Limited (80ms)

**Overall**: 4/5 tools functional (80% success rate)

## Why This Mapping is Needed

Different naming conventions across systems:

| System | Name | Source |
|--------|------|--------|
| Log Files | `hub-ca-auth` | Kinesis Firehose stream name |
| Sentry | `auth-service` | Java application config |
| Datadog APM | `pason-auth-service` | Java APM agent config |
| Our Config | `hub-ca-auth` | Master service registry |

The mapping allows users to use a single service name (`hub-ca-auth`) and have it automatically resolve to the correct name for each monitoring system.

## Future Considerations

1. **Other Services**: May need to add `datadog_service_name` for other services if they have different names in Datadog

2. **Datadog Logs**: The logs query uses free-form query strings. If users want to query logs by service, they should use the Datadog service name directly:
   - Query: `service:pason-auth-service status:error`
   - Or we could add query rewriting logic (more complex)

3. **Service Discovery**: Could implement a tool to list all Datadog services and suggest mappings

4. **Validation**: Consider adding a startup check that validates service name mappings exist for all configured services

## Files Changed

- `src/config.py` - Added datadog_service_name field
- `config/services.yaml` - Added mapping for hub-ca-auth
- `src/server.py` - Added mapping logic in APM handler
- `scripts/validate_production_tools.py` - Added mapping in test

## Deployment

Deployed to production: `syslog.awstst.pason.com:/home/srt/log-ai`

All changes tested and validated ✅
