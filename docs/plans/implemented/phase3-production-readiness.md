---
title: "Phase 3 - Production Readiness: Fix All MCP Tools for Production"
status: "completed"
priority: "critical"
date_created: 2026-01-25
date_updated: 2026-02-06
date_completed: 2026-01-25
completion:
  - [x] Task 1: Fix Sentry API query_issues (400 Bad Request) ✅
  - [x] Task 2: Fix Datadog APM query format (400 Bad Request) ✅
  - [x] Task 3: Fix Datadog Logs query format (400 Bad Request) ✅
  - [x] Task 4: Resolve Datadog Metrics permissions (403 Forbidden) ✅ (org-level restriction documented)
  - [x] Task 5: Test all tools end-to-end with hub-ca-auth service ✅
  - [x] Task 6: Create production validation script ✅
  - [x] Task 7: Update documentation with working examples ✅
final_report: docs/reports/current/production-validation-final.md
related_files:
  - src/sentry_integration.py
  - src/datadog_integration.py
  - src/server.py
  - tests/test_phase3_6_datadog_queries.py
current_blockers:
  - Datadog APM/Logs API v2 requires complex request structure - SDK documentation unclear
  - Datadog Metrics requires API key with metrics_read permission
---

# Phase 3 - Production Readiness Plan

## Objective
Make ALL MCP tools production-ready for real-world usage with our production Datadog and Sentry instances.

**Priority**: CRITICAL - Must work in production environment
**Target Service**: hub-ca-auth (initial test case)

---

## Current Status Summary

### ✅ Working
- Config loading (Pydantic settings)
- Authentication (all APIs connecting)
- Import paths fixed
- Local tests passing (136/136)

### ❌ Broken in Production

#### 1. **Sentry API - query_issues (400 Bad Request)**
```
Error: Sentry API request failed: 400 Client Error: Bad Request
URL: https://sentry.awstst.pason.com/api/0/organizations/pason/issues/?project=hub-ca-auth&query=is%3Aunresolved+environment%3Aqa&limit=2&statsPeriod=24h
```

**Root Cause**: 
- Using `project` parameter with service name "hub-ca-auth"
- Sentry expects numeric project ID or exact project slug
- Need to map service names to Sentry project identifiers

**Impact**: All Sentry MCP tools non-functional
- `mcp_log-ai_query_sentry_issues`
- `mcp_log-ai_get_sentry_issue_details`
- `mcp_log-ai_search_sentry_traces`

#### 2. **Datadog APM - query_apm_traces (400 Bad Request)**
```
Error: document is missing required top-level members; must have one of: "data", "meta", "errors"
API: POST https://api.datadoghq.com/api/v2/spans/list
```

**Root Cause**:
- Request body format incompatible with Datadog API v2
- Using dict parameters, but API expects specific structure
- SpansListRequest model instantiation issue

**Impact**: APM tracing tool non-functional
- `mcp_log-ai_query_datadog_apm`

#### 3. **Datadog Logs - query_logs (400 Bad Request)**
```
Error: input_validation_error(Field 'input' is invalid: invalid argument)
API: POST https://api.datadoghq.com/api/v2/logs/list
```

**Root Cause**:
- Query format issue with LogsListRequest
- Time range or filter parameter mismatch
- Page parameter structure incorrect

**Impact**: Log search tool non-functional
- `mcp_log-ai_query_datadog_logs`

#### 4. **Datadog Metrics - query_metrics (403 Forbidden)**
```
Error: Forbidden - Failed permission authorization checks
API: GET https://api.datadoghq.com/api/v1/query
```

**Root Cause**:
- API key lacks `metrics_read` permission
- Need to update API key with correct scopes

**Impact**: Metrics tool non-functional
- `mcp_log-ai_query_datadog_metrics`

---

## Implementation Plan

### Task 1: Fix Sentry query_issues API (CRITICAL)

**Problem**: Service name → Sentry project mapping missing

**Solution**:
1. Add `sentry_project` field to ServiceConfig in config.py
2. Update services.yaml with Sentry project mappings
3. Modify SentryAPI.query_issues() to:
   - Accept service_name parameter
   - Resolve to Sentry project using ServiceConfig
   - Support multiple services (match to multiple projects)
4. Update MCP tool handler to use service_name

**Files to Change**:
- `src/config.py`: Add sentry_project field
- `config/services.yaml`: Add sentry_project for each service
- `src/sentry_integration.py`: Update query_issues() signature
- `src/server.py`: Update query_sentry_issues_handler()

**Test Case**:
```python
# Should work:
api.query_issues(service_name="auth")
# Resolves to projects: ["hub-ca-auth", "hub-us-auth", "hub-na-auth"]
```

---

### Task 2: Fix Datadog APM query_apm_traces (CRITICAL)

**Problem**: Request body structure incompatible with API v2

**Solution**:
1. Review Datadog API v2 documentation for correct SpansListRequest format
2. Use proper model instantiation instead of dict parameters
3. Test with minimal query first:
   ```python
   request = SpansListRequest(
       data=SpansListRequestData(
           attributes=SpansListRequestAttributes(
               filter=SpansQueryFilter(
                   from_="now-1h",
                   to="now",
                   query="service:log-ai-mcp"
               )
           )
       )
   )
   ```
4. Incrementally add filters, sort, pagination

**Files to Change**:
- `src/datadog_integration.py`: Rewrite query_apm_traces() with correct format

**Test Case**:
```python
# Should return traces:
query_apm_traces(
    service="log-ai-mcp",
    start_time=datetime.now(UTC) - timedelta(hours=1),
    end_time=datetime.now(UTC),
    limit=10
)
```

---

### Task 3: Fix Datadog Logs query_logs (HIGH)

**Problem**: LogsListRequest format issue

**Solution**:
1. Review Datadog Logs API v2 documentation
2. Correct LogsListRequest structure:
   ```python
   request = LogsListRequest(
       filter=LogsQueryFilter(
           from_="now-1h",
           to="now",
           query="service:log-ai-mcp"
       ),
       sort=LogsSort.TIMESTAMP_DESCENDING,
       page=LogsListRequestPage(limit=100)
   )
   ```
3. Test time range formatting (RFC3339)
4. Validate query syntax

**Files to Change**:
- `src/datadog_integration.py`: Rewrite query_logs() with correct format

**Test Case**:
```python
# Should return logs:
query_logs(
    query="service:log-ai-mcp",
    start_time=datetime.now(UTC) - timedelta(hours=1),
    end_time=datetime.now(UTC),
    limit=10
)
```

---

### Task 4: Resolve Datadog Metrics Permissions (MEDIUM)

**Problem**: API key lacks metrics_read permission

**Solution Options**:
1. **Update API key scopes** (preferred):
   - Go to Datadog → Organization Settings → API Keys
   - Edit existing key to add `metrics_read` permission
   - No code changes needed

2. **Create new API key** (if current can't be modified):
   - Generate new key with required scopes:
     - `metrics_read`
     - `logs_read_data`
     - `apm_read`
   - Update config/.env with new key

**Files to Change**:
- `config/.env`: Update DD_API_KEY if creating new key
- No code changes

**Test Case**:
```python
# Should return metrics:
query_metrics(
    metric_query="avg:system.cpu.user{*}",
    start_time=datetime.now(UTC) - timedelta(hours=1),
    end_time=datetime.now(UTC)
)
```

---

### Task 5: End-to-End Testing with hub-ca-auth

**Objective**: Validate all tools work with real service

**Test Scenarios**:
1. **Log Search**:
   ```
   mcp_log-ai_search_logs(
     service_name="hub-ca-auth",
     query="ERROR",
     start_time="2026-01-24T23:00:00Z",
     end_time="2026-01-25T01:00:00Z"
   )
   ```

2. **Sentry Issues**:
   ```
   mcp_log-ai_query_sentry_issues(
     service_name="auth",
     query="is:unresolved",
     limit=5
   )
   ```

3. **Datadog APM**:
   ```
   mcp_log-ai_query_datadog_apm(
     service="hub-ca-auth",
     hours_back=1,
     min_duration_ms=100
   )
   ```

4. **Datadog Logs**:
   ```
   mcp_log-ai_query_datadog_logs(
     query="service:hub-ca-auth status:error",
     hours_back=1
   )
   ```

5. **Datadog Metrics**:
   ```
   mcp_log-ai_query_datadog_metrics(
     metric_query="avg:trace.http.request.duration{service:hub-ca-auth}",
     hours_back=1
   )
   ```

**Success Criteria**:
- All 5 tools return valid data (not errors)
- Response times < 5 seconds
- Data matches expected time ranges
- No authentication failures

---

### Task 6: Create Production Validation Script

**Objective**: Automated testing script for production readiness

**Script**: `scripts/validate_production_tools.py`

**Features**:
- Test all MCP tools with hub-ca-auth
- Check response format (text/json)
- Validate data integrity
- Report pass/fail for each tool
- Generate test report

**Output**:
```
=== LogAI MCP Tools Production Validation ===
✅ search_logs: PASS (found 47 matches in 1.2s)
✅ query_sentry_issues: PASS (found 3 issues in 0.8s)
✅ query_datadog_apm: PASS (found 12 traces in 1.5s)
✅ query_datadog_logs: PASS (found 89 logs in 1.1s)
⚠️  query_datadog_metrics: PASS (no data for time range)

Overall: 5/5 tools functional
```

---

### Task 7: Update Documentation

**Files to Update**:
1. `docs/QUICKSTART.md`: Add production testing section
2. `README.md`: Update tool usage examples
3. Create `docs/PRODUCTION_VALIDATION.md`: Testing guide
4. Update `docs/INDEX.md`: Mark phase complete

**Content**:
- Working examples for each tool
- Common error messages and solutions
- Performance benchmarks
- Troubleshooting guide

---

## Testing Strategy

### Unit Tests
- Mock API responses with ACTUAL production response formats
- Update `tests/test_phase3_6_datadog_queries.py` with real structures
- Add `tests/test_sentry_production.py` for Sentry queries

### Integration Tests
- Deploy to syslog.awstst.pason.com
- Run validation script against production
- Verify with real hub-ca-auth data

### Regression Tests
- Ensure existing search_logs still works
- Verify service resolution unchanged
- Check backward compatibility

---

## Success Criteria

### Definition of Done
- [ ] All 8 MCP tools return valid data (no 400/403 errors)
- [ ] hub-ca-auth test case passes for all tools
- [ ] Production validation script runs successfully
- [ ] Documentation updated with working examples
- [ ] All tests passing (unit + integration)
- [ ] Code committed and deployed to production

### Performance Targets
- Response time < 5s for all queries
- No memory leaks (long-running server)
- Proper error handling for all edge cases

---

## Risk Assessment

### High Risk
- **Datadog API format changes**: SDK documentation may be outdated
  - Mitigation: Test with curl/Postman first to verify correct format

### Medium Risk
- **Sentry project mapping**: Services may not match projects 1:1
  - Mitigation: Create flexible mapping in services.yaml

### Low Risk
- **API key permissions**: May need org admin to update
  - Mitigation: Document required permissions clearly

---

## Rollback Plan

If issues persist:
1. Revert to previous working version (pre-Phase 3.6)
2. Disable Datadog/Sentry tools temporarily
3. Keep search_logs functional (critical tool)
4. Document known issues for future work

---

## Next Steps After Completion

1. Monitor production usage for 1 week
2. Gather user feedback on tool effectiveness
3. Optimize slow queries (caching, indexing)
4. Add alerting for tool failures
5. Begin Phase 4: Advanced Features (dashboards, correlations)

---

## Notes

- This is CRITICAL PRIORITY work
- Production Datadog instance - be careful with queries
- Start with minimal queries, expand incrementally
- Document every API response format discovered
- Update tests as we learn correct formats

