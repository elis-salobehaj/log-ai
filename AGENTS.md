# AI Agent Instructions for LogAI

## Documentation Structure

**Always start with**: [`docs/INDEX.md`](./docs/INDEX.md) for current work context.

**When implementing features**:
1. Check `docs/plans/active/` for the implementation plan.
2. Read YAML frontmatter for related files.
3. Follow patterns in existing code.
4. **REQUIRED**: Update plan progress as you work (see maintenance rules below).

**When creating reports**:
- Use frontmatter with status, date, related_files.
- Save to `docs/reports/current/` during work.
- Move to `docs/reports/archive/{year}/` when complete.

---

## 🧬 Tech Stack & Architecture

### Backend (Python 3.12+)
- **Package Manager**: `uv`
- **Framework**: MCP SDK (Model Context Protocol)
- **Async Runtime**: asyncio with subprocess streaming
- **Configuration**: Pydantic Settings v2
- **Caching**: Redis (distributed) + LRU fallback (local)
- **Monitoring**: Sentry for error tracking

### MCP Server Architecture
```
┌─────────────────────────────────────────────────────────────┐
│  AI Agent (Copilot/Claude/Junie)                            │
└─────────────────┬───────────────────────────────────────────┘
                  │ SSH + MCP (STDIO transport)
┌─────────────────▼───────────────────────────────────────────┐
│  LogAI MCP Server                                           │
│  ├── Tools: search_logs, get_services, get_sentry_issues    │
│  ├── Redis Cache (500MB, 10min TTL)                         │
│  └── Async ripgrep execution with streaming                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│  Log Files (300GB+/day) + services.yaml (90+ services)      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 MCP Server Best Practices (Anthropic Guidelines)

### Tool Design Principles

1. **Single Responsibility**: Each tool performs ONE well-defined operation
   ```python
   # ✅ Good: Single purpose
   @mcp.tool()
   async def search_logs(service: str, pattern: str) -> str:
       """Search logs for a specific service and pattern."""
   
   # ❌ Bad: Multiple responsibilities
   @mcp.tool()  
   async def search_and_analyze_and_export_logs(...) -> str:
       """Does too many things."""
   ```

2. **Clear Descriptions**: Tool descriptions guide the LLM on when to use them
   ```python
   @mcp.tool()
   async def search_logs(
       services: list[str],
       pattern: str,
       hours_back: int = 24
   ) -> str:
       """
       Search system logs for specific patterns.
       
       Use this tool when investigating:
       - Error messages or exceptions
       - Service behavior over time
       - Specific transaction IDs or request patterns
       
       Args:
           services: List of service names (e.g., ["hub-ca-auth", "edr-proxy"])
           pattern: Regex pattern to search for
           hours_back: How many hours of logs to search (default: 24)
       
       Returns:
           Matching log entries with timestamps and context.
       """
   ```

3. **Typed Parameters with JSON Schema**: Use Pydantic models or explicit types
   ```python
   # Use clear, typed parameters
   async def search_logs(
       services: list[str],           # Required
       pattern: str,                  # Required
       hours_back: int = 24,          # Optional with default
       format: Literal["text", "json"] = "text"
   ) -> str:
   ```

4. **Structured Error Responses**: Return errors in a consistent format
   ```python
   # ✅ Good: Structured error handling
   if not services:
       return json.dumps({
           "error": "No services specified",
           "suggestion": "Use get_services tool to list available services"
       })
   
   # ❌ Bad: Generic errors
   raise Exception("Something went wrong")
   ```

### STDIO Transport Rules (Critical)

**NEVER write to stdout except MCP messages**:
```python
# ❌ FORBIDDEN - Corrupts JSON-RPC protocol
print("Debug message")
print(f"Processing {service}")

# ✅ CORRECT - Use stderr or logging
import sys
sys.stderr.write(f"[DEBUG] Processing {service}\n")

# ✅ BEST - Use logging library
import logging
logger = logging.getLogger("log-ai")
logger.info(f"Processing {service}")  # Goes to stderr
```

### Security Considerations

1. **Validate All Inputs**
   ```python
   def validate_service_name(service: str) -> bool:
       """Prevent path traversal and injection attacks."""
       if ".." in service or "/" in service:
           return False
       if not re.match(r'^[a-zA-Z0-9_-]+$', service):
           return False
       return True
   ```

2. **Rate Limit Tool Invocations**
   ```python
   # Use semaphores to limit concurrent operations
   MAX_CONCURRENT_SEARCHES = 10
   search_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
   
   async def search_logs(...):
       async with search_semaphore:
           # Perform search
   ```

3. **Sanitize Outputs**: Don't expose sensitive data
   ```python
   # Mask potential secrets in log output
   def sanitize_output(text: str) -> str:
       text = re.sub(r'password["\s:=]+\S+', 'password=***', text, flags=re.I)
       text = re.sub(r'api[_-]?key["\s:=]+\S+', 'api_key=***', text, flags=re.I)
       return text
   ```

4. **Implement Timeouts**: Prevent runaway operations
   ```python
   async def search_logs(...):
       try:
           result = await asyncio.wait_for(
               perform_search(...),
               timeout=300.0  # 5 minute max
           )
       except asyncio.TimeoutError:
           return "Search timed out after 300 seconds. Try narrowing your search."
   ```

### Progress Reporting

For long-running operations, report progress via stderr:
```python
async def search_logs(...):
    sys.stderr.write(f"[PROGRESS] Starting search across {len(services)} services\n")
    
    for i, service in enumerate(services):
        sys.stderr.write(f"[PROGRESS] Searching {service} ({i+1}/{len(services)})\n")
        # ... search logic
    
    sys.stderr.write(f"[PROGRESS] Complete: Found {match_count} matches\n")
```

---

## ⚙️ Backend Configuration (Pydantic v2)

### Configuration Pattern
All backend configuration MUST use `pydantic-settings`:

```python
# src/config_loader.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="config/.env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Cache settings
    cache_max_size_mb: int = 500
    cache_max_entries: int = 100
    cache_ttl_minutes: int = 10
    
    # Redis (optional)
    redis_url: str | None = None
    
    # Sentry (optional)
    sentry_dsn: str | None = None
    sentry_org: str | None = None
    sentry_auth_token: str | None = None

settings = Settings()
```

### Usage Rules
1. **NEVER use `os.getenv()` directly** - always use `settings.attribute`
2. **Graceful Fallbacks**: Missing optional keys should have sensible defaults
3. **Feature Flags**: Check configuration before enabling features
   ```python
   if settings.redis_url:
       redis_client = Redis.from_url(settings.redis_url)
   else:
       # Use local LRU cache fallback
       cache = LRUCache(max_size=settings.cache_max_entries)
   ```

---

## 🛠️ Essential Commands

### Environment Setup
```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy configuration
cp config/.env.example config/.env
cp config/services.yaml.example config/services.yaml
```

### Development
```bash
# Run MCP server directly (for testing)
uv run python -m src.server

# Test with MCP Inspector
npx @anthropic/mcp-inspector uv run python -m src.server
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_service_resolution.py -v

# Run integration tests (requires syslog server)
uv run pytest -m integration
```

### Linting
```bash
uv run ruff check .
uv run ruff format .
```

---

## 🔄 Documentation Maintenance Rules

**CRITICAL: After completing ANY task from a plan, you MUST**:

1. **Update the plan file** (`docs/plans/active/*.md`):
   ```yaml
   # In frontmatter completion list:
   - [x] Phase 1 - Service Resolution Fix ✅
   date_updated: 2026-01-24
   ```

2. **Update `docs/INDEX.md`**:
   ```markdown
   | Plan | Status | Progress | Last Updated |
   |------|--------|----------|--------------|
   | Service Resolution | In Progress | 1/3 phases ✅ | 2026-01-24 |
   ```

3. **When plan is 100% complete**:
   ```bash
   git mv docs/plans/active/plan-name.md docs/plans/implemented/
   ```

---

## Code Conventions

### Python Backend
- Type hints required for all functions
- Docstrings for public methods (Google style)
- Use `logger` not `print()` - **Critical for MCP servers**
- Async-first for I/O operations
- Use `settings` object for configuration

### Error Handling
```python
# Always return structured errors, don't raise exceptions
try:
    result = await search_logs(...)
except ServiceNotFoundError as e:
    return json.dumps({
        "error": f"Service not found: {e.service}",
        "available_services": get_similar_services(e.service),
        "suggestion": "Use get_services tool to list all available services"
    })
except Exception as e:
    logger.exception("Unexpected error in search_logs")
    return json.dumps({
        "error": "Internal error occurred",
        "details": str(e) if settings.debug else "Contact administrator"
    })
```

### Testing
- Unit tests in `tests/`
- Use `pytest-asyncio` for async tests
- Mock external services (Redis, Sentry) in unit tests

---

## MCP-Specific Guidelines

### Tool Response Formats

1. **Text Format (Default)**: Human-readable output
   ```
   === Search Results: hub-ca-auth ===
   Time Range: 2026-01-24 10:00 - 11:00 UTC
   Matches: 47 entries
   
   [2026-01-24T10:15:32Z] ERROR: Connection timeout...
   [2026-01-24T10:15:33Z] WARN: Retrying connection...
   ```

2. **JSON Format**: For agent parsing
   ```json
   {
     "service": "hub-ca-auth",
     "time_range": {"start": "...", "end": "..."},
     "match_count": 47,
     "matches": [...]
   }
   ```

### Large Result Handling

For results exceeding preview limits:
```python
if len(matches) > PREVIEW_LIMIT:
    # Save full results to file
    file_path = save_results_to_file(matches)
    return {
        "preview": matches[:PREVIEW_LIMIT],
        "total_count": len(matches),
        "full_results_file": str(file_path),
        "message": f"Showing first {PREVIEW_LIMIT} of {len(matches)} matches. Full results saved to {file_path}"
    }
```

### Service Name Resolution

The server supports flexible service name matching:
```python
# All these resolve to the same service:
"hub-ca-auth"      # Exact match
"auth"             # Base name match  
"hub_ca_auth"      # Underscore variant
"HUB-CA-AUTH"      # Case insensitive
```

---

## Active Work Context

**Current Focus**: MCP Server maintenance and stability
**Key Files**:
- `src/server.py` - Main MCP server implementation
- `src/config.py` - Service configuration and resolution
- `config/services.yaml` - Service definitions

## Ignore for Code Suggestions

- `docs/plans/backlog/` - Future work, not current
- `docs/reports/archive/` - Historical reference only
- `*.prompt.md` files - Prompt templates for other agents

## When Confused

1. Read [`docs/INDEX.md`](./docs/INDEX.md)
2. Check plan frontmatter for `related_files`
3. Look at recent commits: `git log --oneline -10`
4. Review [README.md](./README.md) for project overview
