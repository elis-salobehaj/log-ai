---
title: "Datadog Observability - Dashboard & Alerts (Remaining from Phase 3)"
status: backlog
priority: medium
date_created: 2026-02-05
origin: mcp-observability-completion.md (Phase 3.7-3.9)
completion:
  - [ ] Phase 3.7 - Dashboard Setup
  - [ ] Phase 3.8 - Alert Configuration
  - [ ] Phase 3.9 - Documentation Update
related_files:
  - src/datadog_integration.py
  - src/metrics_collector.py
  - docs/IMPLEMENTATION.md
---

# Datadog Observability - Dashboard & Alerts

Remaining items from the original MCP Observability Phase 3 plan, moved to backlog for future implementation.

---

## Phase 3.7 - Dashboard Setup

Create Datadog dashboards for MCP server monitoring.

### Dashboard: LogAI MCP Server Overview

**Widgets to include**:

1. **Search Performance**
   - `avg:log_ai.search.duration_ms{*}` - Average search latency
   - `count:log_ai.search.count{*}` - Search volume
   - `avg:log_ai.search.matches{*}` - Average matches per search

2. **Cache Metrics**
   - `avg:log_ai.cache.hit_rate{*}` - Cache hit rate %
   - `sum:log_ai.cache.evictions{*}` - Cache evictions
   - `avg:log_ai.cache.size_mb{*}` - Cache size

3. **Service Usage**
   - Top 10 services by search volume
   - Error rate by service
   - Search latency by service (heatmap)

4. **Redis Health**
   - Connection status
   - Command latency
   - Memory usage

5. **System Resources**
   - Host CPU/Memory for syslog server
   - Disk I/O for log directories

### Implementation

```python
# Use Datadog Dashboard API to create programmatically
# Or document manual setup steps
```

---

## Phase 3.8 - Alert Configuration

Configure Datadog monitors for proactive alerting.

### Monitors to Create

| Monitor | Query | Threshold | Severity |
|---------|-------|-----------|----------|
| High Search Latency | `avg:log_ai.search.duration_ms{*}` | > 5000ms for 5min | Warning |
| Search Error Rate | `sum:log_ai.search.errors{*}.as_rate()` | > 5% for 5min | Critical |
| Cache Hit Rate Drop | `avg:log_ai.cache.hit_rate{*}` | < 50% for 10min | Warning |
| Redis Connection Failure | `sum:log_ai.redis.connection_errors{*}` | > 0 for 1min | Critical |
| Disk Space Low | `avg:system.disk.in_use{host:syslog*}` | > 90% | Warning |

### Alert Channels

- Slack: #log-ai-alerts
- PagerDuty: For critical alerts
- Email: Team distribution list

---

## Phase 3.9 - Documentation Update

Update documentation with observability details.

### Updates Required

1. **IMPLEMENTATION.md**
   - Add Datadog integration section
   - Document metrics naming conventions
   - Add dashboard links

2. **QUICKSTART.md**
   - Add Datadog configuration steps
   - Document required environment variables

3. **README.md**
   - Update features list with observability
   - Add troubleshooting section for Datadog

4. **QUICK_REFERENCE.md**
   - Add Datadog metric queries
   - Add common dashboard links

### Metrics Reference Doc

Create `docs/METRICS_REFERENCE.md`:

```markdown
# LogAI Metrics Reference

## Search Metrics
- `log_ai.search.duration_ms` - Search duration in milliseconds
- `log_ai.search.count` - Number of searches
- `log_ai.search.matches` - Matches found per search
- `log_ai.search.errors` - Search errors

## Cache Metrics
- `log_ai.cache.hit_rate` - Cache hit percentage
- `log_ai.cache.size_mb` - Current cache size
- `log_ai.cache.evictions` - Cache eviction count

## Redis Metrics
- `log_ai.redis.latency_ms` - Redis operation latency
- `log_ai.redis.connection_errors` - Connection failures
```

---

## Dependencies

- Datadog API key with dashboard write permissions
- Slack webhook for alert notifications
- Team agreement on alert thresholds
