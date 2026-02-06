# LogAI Documentation Index

**For AI Agents**: Start here to understand current work and context.

**🤖 Agent Maintenance Instructions**: 
- When completing a task from a plan, check off the item in the plan's frontmatter `completion` list
- Update `date_updated` in the plan frontmatter
- Update this INDEX.md file to reflect current status
- When a plan is fully complete, move it from `plans/active/` to `plans/implemented/` and update status in this index

---

## 🔥 Active Plans (Priority Reading)

**No active plans currently.** All core functionality is implemented and production-ready.

**Recently Completed**:
- ✅ [Datadog Environment Context](plans/implemented/datadog-environment-context.md) - Completed 2026-02-06
- ✅ [MCP Observability Completion](plans/implemented/mcp-observability-completion.md) - Completed 2026-02-06

**Current Focus**: 
- Phase 3.1: Datadog SDK Integration ✅ **COMPLETE**
- Phase 3.2: APM Tracing Implementation ✅ **COMPLETE**
- Phase 3.3: Metrics Collection ✅ **COMPLETE**
- Phase 3.4: Infrastructure Monitoring ✅ **COMPLETE**
- Phase 3.5: Log Aggregation ✅ **COMPLETE**
- Phase 3.6: MCP Tools for Datadog Queries ✅ **COMPLETE** (3 core tools production-ready)
  - ✅ query_datadog_apm - APM traces with service name mapping
  - ✅ query_datadog_logs - Log aggregation queries
  - ⚠️ query_datadog_metrics - Limited by org permissions
- Phase 3.6+: Additional Datadog Tools ✅ **COMPLETE** (3 high-priority tools)
  - ✅ list_datadog_monitors - Active alerts & monitor status (15 tests)
  - ✅ search_datadog_events - Deployment correlation (15 tests)
  - ✅ get_service_dependencies - Service topology (15 tests)
  - 🔄 Remaining medium-priority: list_datadog_incidents, list_datadog_hosts
- Next up: Phase 3.7 - Dashboard Setup
- **Service Name Mapping**: ✅ Implemented `datadog_service_name` field in services.yaml
- Phases 1-2 COMPLETE ✅: Redis coordination + Sentry integration
- 156/156 tests passing (31 existing + 10 SDK + 15 APM + 26 metrics + 26 infra + 21 logs + 17 queries + 15 monitors/events/deps)

---

## 📊 Current Reports

- [Datadog Environment Context Implementation](reports/current/datadog-env-context-implementation-complete.md) - ✅ **COMPLETE** - Environment filtering for 6 Datadog tools (2026-02-06)
- [Datadog Service Name Mapping](reports/current/datadog-service-name-mapping.md) - ✅ **RESOLVED** - APM now finds traces with proper mapping (2026-01-25)
- [Production Validation Final](reports/current/production-validation-final.md) - ✅ **4/5 tools working** - Phase 3.6 production ready (2026-01-25)
- [Phase 3 Datadog API Fix](reports/current/phase3-datadog-api-fix.md) - ✅ **COMPLETE** - Fixed Datadog APM/Logs with GET methods (2026-01-24)

---

## 📚 Implementation Guides (Always Relevant)

**Quick Access:**
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - ⚡ Fast command lookup and patterns
- [INDEX.md](INDEX.md) - This file - documentation navigation hub

**Getting Started:**
- [QUICKSTART.md](QUICKSTART.md) - Quick setup guide
- [README.md](../README.md) - Full project documentation
- [VS Code MCP Setup](guides/VSCODE_SETUP.md) - VS Code/Cursor configuration
- [WSL Setup Guide](guides/HOWTO_WSL.md) - Windows Subsystem for Linux setup

**Development:**
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - Architecture and implementation details
- [SERVICE_RESOLUTION_FIX.md](SERVICE_RESOLUTION_FIX.md) - Service name resolution documentation
- [Fetch Sentry DSNs Guide](guides/FETCH_SENTRY_DSNS_GUIDE.md) - Sentry DSN configuration

**Reference:**
- [ELEVATOR_PITCH.md](ELEVATOR_PITCH.md) - Project overview and capabilities
- [Sentry Per-Service DSN](SENTRY_PER_SERVICE_DSN.md) - Per-service Sentry configuration
- [Log Search Result Example](log-search-result-example.json) - Example output format

---

## ✅ Recently Completed

| Plan | Completed | Summary |
|------|-----------|---------|
| [MCP Server Enhancement - Phases 1-2](plans/implemented/mcp-server-enhancement-plan-phases-1-2-COMPLETED.md) | 2025-12-31 | ✅ Redis coordination, global limits, ✅ Sentry integration (Phase 3 moved to active plans) |
| [Service Name Resolution & Sentry](plans/implemented/service-name-resolution-sentry.md) | 2025-12-31 | Flexible service matching, locale filtering, Sentry query integration |

---

## 🗂️ Archive Reference

<details>
<summary>Future Plans (Backlog) - Expand if needed</summary>

**Datadog Expansion:**
- [Datadog Observability Remaining](plans/backlog/datadog-observability-remaining.md) - Dashboard, Alerts, Docs from Phase 3
- [Datadog CI Visibility Tools](plans/backlog/datadog-ci-visibility-tools.md) - Pipeline & test monitoring
- [Datadog Security Tools](plans/backlog/datadog-security-tools.md) - SIEM, vulnerabilities, CSM, AppSec
- [Datadog Infrastructure Tools](plans/backlog/datadog-infrastructure-tools.md) - Hosts, containers, processes, ECS

</details>

<details>
<summary>Historical Reports - Expand if needed</summary>

**2025:**
- [Phase 2 Sentry Integration Progress](reports/archive/2025/phase2-sentry-integration-progress.md) - Sentry API integration and tool implementation

</details>

---

## 🎯 For AI Coding Agents

**When asked to implement a feature:**
1. Check `docs/plans/active/` for relevant plan
2. Read linked files in frontmatter `related_files`
3. Check `docs/reports/current/` for context on recent changes
4. Reference root docs for coding standards

**When generating reports:**
- Save to `docs/reports/current/` while work is ongoing
- Include frontmatter with status and related_files
- Link back to the original plan

**When a plan is complete:**
- Move from `plans/active/` to `plans/implemented/`
- Update status in frontmatter to `implemented`
- Archive related reports to `reports/archive/{year}/`

---

## Project Architecture

```
log-ai/
├── src/                    # MCP Server source code
│   ├── server.py          # Main MCP server implementation
│   ├── config.py          # Configuration and service resolution
│   ├── config_loader.py   # Environment configuration loader
│   ├── redis_coordinator.py # Redis caching and coordination
│   └── sentry_integration.py # Sentry error tracking
├── config/                 # Configuration files
│   ├── services.yaml      # Service definitions (90+ services)
│   └── .env               # Environment variables
├── scripts/               # Utility scripts
│   └── tools/             # Sentry DSN management tools
├── tests/                 # Test suite
└── docs/                  # Documentation
    ├── plans/             # Feature plans
    │   ├── active/        # Currently in progress
    │   ├── backlog/       # Future work
    │   └── implemented/   # Completed plans
    └── reports/           # Implementation reports
        ├── current/       # Active work
        └── archive/       # Historical
```
