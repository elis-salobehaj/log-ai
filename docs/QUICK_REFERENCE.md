# LogAI Quick Reference

**For AI Agents**: Fast lookup of common commands, patterns, and file locations.

---

## 📂 File Locations

| What | Where |
|------|-------|
| MCP Server | [src/server.py](../src/server.py) |
| Configuration | [src/config.py](../src/config.py), [src/config_loader.py](../src/config_loader.py) |
| Service Definitions | [config/services.yaml](../config/services.yaml) |
| Environment Config | [config/.env](../config/.env) |
| Redis Coordinator | [src/redis_coordinator.py](../src/redis_coordinator.py) |
| Sentry Integration | [src/sentry_integration.py](../src/sentry_integration.py) |
| Tests | [tests/](../tests/) |

---

## 🚀 Common Commands

```bash
# Setup
uv sync                                    # Install dependencies
cp config/.env.example config/.env         # Copy environment config
cp config/services.yaml.example config/services.yaml  # Copy service config

# Development
uv run python -m src.server                # Run MCP server
npx @anthropic/mcp-inspector uv run python -m src.server  # Test with inspector

# Testing
uv run pytest                              # Run all tests
uv run pytest tests/test_service_resolution.py -v  # Specific test
uv run pytest -m integration              # Integration tests only

# Deployment
./scripts/deploy.sh                        # Deploy to syslog server
./scripts/start.sh                         # Start server (production)

# Utilities
uv run python scripts/validate_resolution.py  # Test service name matching
uv run python scripts/validate_sentry_mapping.py  # Verify Sentry mappings
```

---

## 🔧 MCP Tools Overview

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `search_logs` | Search logs by time range | `service_name`, `query`, `start_time_utc`, `end_time_utc` |
| `read_search_file` | Retrieve saved results | `file_path`, `format` |
| `query_sentry_issues` | Get Sentry errors | `service_name`, `query`, `statsPeriod` |
| `get_sentry_issue_details` | Issue details | `issue_id` |
| `search_sentry_traces` | Performance traces | `service_name`, `query` |

---

## 🎯 Service Name Patterns

LogAI supports flexible service name matching:

```python
# All these resolve to "hub-ca-auth":
"hub-ca-auth"      # Exact match
"auth"             # Base name (finds hub-ca-auth, hub-us-auth, hub-na-auth)
"hub_ca_auth"      # Underscore variant
"HUB-CA-AUTH"      # Case insensitive

# Locale filtering:
search_logs(service_name="auth", locale="ca")  # Only hub-ca-auth
search_logs(service_name="auth", locale="us")  # Only hub-us-auth
```

**Locale Prefixes:**
- `hub-ca-` - Canadian services
- `hub-us-` - US services
- `hub-na-` - North American services
- `edr-na-` - EDR North American services
- `edrtier3-na-` - EDR Tier 3 services

---

## ⏰ Time Handling

**Always use UTC timestamps in ISO 8601 format:**

```python
# Correct format
start_time_utc = "2026-01-24T15:20:00Z"
end_time_utc = "2026-01-24T16:30:00Z"

# Time conversion (agent responsibility)
# User says: "2-4pm MST"
# Agent converts: "2026-01-24T21:00:00Z" to "2026-01-24T23:00:00Z"
```

---

## 💾 Cache Behavior

**Redis Cache (Global):**
- Shared across all SSH sessions
- 500MB total size limit
- 10-minute TTL
- Auto-invalidates when `services.yaml` changes

**Local LRU Fallback:**
- Used when Redis unavailable
- 100 entries max
- 500MB size limit
- Per-session (not shared)

---

## 📊 Result File Paths

All search results saved to:
```
/tmp/log-ai/{session-id}/logai-search-{timestamp}-{service}-{hash}.json
```

Example:
```
/tmp/log-ai/abc123-2026-01-24/logai-search-20260124-143015-hub-ca-auth-a3f9b2.json
```

Files automatically cleaned up after 24 hours.

---

## 🐛 Common Debugging

```bash
# Check logs
tail -f /tmp/log-ai/{session-id}/mcp-server.log

# Test Redis connection
redis-cli ping

# Verify service resolution
uv run python scripts/validate_resolution.py auth

# Check Sentry mapping
uv run python scripts/validate_sentry_mapping.py

# List all services
grep "^  - name:" config/services.yaml | wc -l
```

---

## 📖 Documentation Map

| Document | Purpose |
|----------|---------|
| [INDEX.md](INDEX.md) | Documentation navigation hub |
| [QUICKSTART.md](QUICKSTART.md) | Fast setup guide |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Architecture deep dive |
| [ELEVATOR_PITCH.md](ELEVATOR_PITCH.md) | Project overview |
| [SERVICE_RESOLUTION_FIX.md](SERVICE_RESOLUTION_FIX.md) | Service matching logic |

**Guides:**
- [VS Code Setup](guides/VSCODE_SETUP.md) - Configure VS Code/Cursor
- [Sentry DSN Guide](guides/FETCH_SENTRY_DSNS_GUIDE.md) - Configure Sentry integration
- [WSL How-To](guides/HOWTO_WSL.md) - Windows development setup

**Plans:**
- [Active Plans](plans/active/README.md) - Current work
- [Implemented Plans](plans/implemented/README.md) - Completed features

---

## 🎓 Best Practices

### For AI Agents

1. **Always convert user timezone to UTC** before calling `search_logs`
2. **Use base names** for multi-region queries: `"auth"` instead of `"hub-ca-auth"`
3. **Add locale filter** when user specifies region
4. **Check preview count** - if `match_count > 50`, use `read_search_file` for full results
5. **Cite log file paths** when showing results to users

### For Developers

1. **Never use `print()`** in MCP server code - use `logger.info()` or `sys.stderr.write()`
2. **Always validate service names** before executing searches
3. **Use Pydantic Settings** for all configuration
4. **Test with MCP Inspector** before deploying
5. **Update docs** after implementing features
