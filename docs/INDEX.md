# LogAI Documentation Index

**For AI Agents**: Start here to understand current work and context.

**🤖 Agent Maintenance Instructions**: 
- When completing a task from a plan, check off the item in the plan's frontmatter `completion` list
- Update `date_updated` in the plan frontmatter
- Update this INDEX.md file to reflect current status
- When a plan is fully complete, move it from `plans/active/` to `plans/implemented/` and update status in this index

---

## 🔥 Active Plans (Priority Reading)

| Plan | Status | Priority | Last Updated | Progress | Related Files |
|------|--------|----------|--------------|----------|---------------|
| [MCP Observability Completion](plans/active/mcp-observability-completion.md) | **Active** | 🔴 High | 2026-01-24 | 22% (2/9 tasks) | server.py, config_loader.py, datadog_integration.py |

**Current Focus**: 
- Phase 3.1: Datadog SDK Integration ✅ **COMPLETE**
- Phase 3.2: APM Tracing Implementation ✅ **COMPLETE**
- Next up: Phase 3.3 - Metrics Collection
- Phases 1-2 COMPLETE ✅: Redis coordination + Sentry integration
- 46/46 tests passing (31 existing + 10 Datadog SDK + 5 APM tracing)

---

## 📊 Current Reports

*No active implementation reports. Add reports to `docs/reports/current/` as work progresses.*

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

*No backlog plans. Add future ideas to `docs/plans/backlog/`.*

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
