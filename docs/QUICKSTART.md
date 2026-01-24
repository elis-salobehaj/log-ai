# Quick Start Guide

This guide shows you how to deploy and use the LogAI MCP server with AI assistants like GitHub Copilot, Claude Desktop, or IntelliJ Junie.

## Prerequisites

- SSH access to the remote syslog server
- Python 3.12+ on the remote server
- [uv](https://docs.astral.sh/uv/) package manager on remote server
- AI assistant that supports MCP protocol (GitHub Copilot, Claude Desktop, IntelliJ with Junie)

## 1. Configure the Application

Before deploying, you need to configure the server:

```bash
cd /home/ubuntu/elis_temp/github_projects/log-ai

# Copy environment configuration template
cp .env.example config/.env

# Edit config/.env and set your values:
# - SYSLOG_SERVER: Your syslog server hostname
# - SYSLOG_USER: SSH user for deployment
# - REDIS_HOST, REDIS_PORT: Redis settings (if using)
# - LOG_LEVEL: DEBUG for development, INFO for production
nano config/.env

# Copy service configuration template
cp config/services.yaml.example config/services.yaml

# Edit config/services.yaml with your log file patterns:
# Each service needs:
# - name: Service identifier
# - type: "json" or "syslog"
# - description: Human-readable description
# - path_pattern: Log file path with placeholders {YYYY}, {MM}, {DD}, {HH}
nano config/services.yaml
```

**Important Configuration Files:**
- `config/.env`: Environment variables (server, user, Redis, limits, logging)
- `config/services.yaml`: Service definitions with log file patterns
- Both files are gitignored - use the `.example` templates

## 2. Deploy to Remote Server

From your local machine:

```bash
cd /home/ubuntu/elis_temp/github_projects/log-ai
bash scripts/deploy.sh
```

This will:
- ✅ Load configuration from `config/.env`
- ✅ Validate Python syntax locally
- ✅ Copy files to remote server via SCP
- ✅ Install dependencies with `uv sync`
- ✅ Run tests on remote server

## 3. Configure AI Assistant

### Option A: GitHub Copilot in VS Code

See [VSCODE_SETUP.md](VSCODE_SETUP.md) for detailed instructions.

**Quick summary:**

1. Create workspace config (`.vscode/mcp-settings.json`):
```json
{
  "mcp": {
    "inputs": [],
    "servers": {
      "log-ai": {
        "command": "ssh",
        "args": [
          "user@syslog.example.com",
          "~/.local/bin/uv run --directory /home/user/log-ai src/server.py"
        ]
      }
    }
  }
}
```

2. Add to user settings (`.vscode/settings.json`):
```json
{
  "github.copilot.chat.codeGeneration.instructions": [
    {
      "text": "When analyzing logs, use @log-ai MCP server"
    }
  ]
}
```

3. Reload VS Code window

4. Chat with Copilot:
```
@log-ai search for timeout errors in dev-ca-api from the past 2 hours
```

### Option B: Claude Desktop

1. Edit Claude config (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):
```json
{
  "mcpServers": {
    "log-ai": {
      "command": "ssh",
      "args": [
        "user@syslog.example.com",
        "~/.local/bin/uv run --directory /home/user/log-ai src/server.py"
      ]
    }
  }
}
```

2. Restart Claude Desktop

3. Use the log-ai tool in conversation

### Option C: IntelliJ with Junie

See [VSCODE_SETUP.md](VSCODE_SETUP.md) for IntelliJ configuration details.

## 4. Test the Integration

### Test in GitHub Copilot Chat

Open Copilot Chat in VS Code and try:

```
@log-ai what services are available?
```

Expected response:
```
I found 90+ services including:
- dev-ca-api
- dev-ca-rock-service
- awesome
- aws-ecs-auth
...
```

### Search for Errors

```
@log-ai search for errors in dev-ca-api from the past hour
```

Copilot will:
1. Call the `search_logs` MCP tool
2. Parse the structured JSON results
3. Summarize findings in natural language
4. Provide actionable insights

### Example Conversation

```
You: @log-ai check if there are any timeout errors in hub services today

Copilot: I'll search for timeout errors in hub-related services.

[Copilot calls search_logs with services=["dev-ca-api", "dev-ca-rock-service"], 
 query="timeout", date="today"]

Found 47 timeout errors across hub services:
- dev-ca-api: 32 errors
  - Most common: "Connection timeout to database" (18 occurrences)
  - Peak time: 14:30-15:00 UTC
- dev-ca-rock-service: 15 errors
  - "API timeout exceeded 30s" (15 occurrences)

Would you like me to investigate the database connection issues?
```

## 5. Understanding the Tools

LogAI provides 2 MCP tools:

### `search_logs`

Search log files with datetime filtering and multi-service support.

**Parameters:**
- `service_name`: String or array of service names
- `query`: Search keyword or pattern
- `date`: Optional date (e.g., "today", "yesterday", "Dec 29")
- `hours_back`: Optional number of hours to search back
- `minutes_back`: Optional number of minutes to search back (for surgical precision)
- `time_range`: Optional time range (e.g., "2pm to 4pm")
- `timezone`: Optional timezone (e.g., "America/Denver")
- `format`: "text" (human-readable) or "json" (structured)

**Returns:**
- Structured results with file paths, line numbers, parsed content
- Metadata: services searched, total matches, duration
- If >50 matches: saves to file and returns preview + file path

### `read_search_file`

Read full results from saved search files (when search returns >50 matches).

**Parameters:**
- `file_path`: Path to saved search file
- `format`: "text" or "json"

**Returns:**
- Full search results from the file

## 6. Advanced Usage

### Multi-Service Search

```
@log-ai search for "authentication failed" in aws-ecs-auth and dev-ca-api 
from yesterday between 2pm and 4pm
```

### Large Result Sets

When search finds >50 matches, LogAI automatically:
1. Saves complete results to `/tmp/log-ai/logai-search-{timestamp}-...json`
2. Returns preview of first 50 matches
3. Provides file path for full results

Copilot can then ask:
```
Show me the full results from that search
```

And it will call `read_search_file` with the path.

### JSON Format for Parsing

```
@log-ai search for errors in dev-ca-api, return JSON format
```

Returns structured data that Copilot can analyze programmatically.

## 7. Session Management

Each MCP connection creates a unique session:
- Session ID format: `abc123-2025-12-31`
- Session logs: `/tmp/log-ai/{session-id}/mcp-server.log`
- Search results: `/tmp/log-ai/logai-search-*.json`

Files are automatically cleaned up after 24 hours.

## 8. Runtime Configuration

Edit `config/.env` on the remote server to adjust:

```bash
# Global Limits
MAX_GLOBAL_SEARCHES=20
MAX_PARALLEL_SEARCHES_PER_CALL=5

# Cache Configuration
CACHE_MAX_SIZE_MB=500
CACHE_TTL_MINUTES=10

# Search Limits
AUTO_CANCEL_TIMEOUT_SECONDS=300
PREVIEW_MATCHES_LIMIT=50

# Logging
LOG_LEVEL=DEBUG  # Set to INFO for production
```

After changing config, restart the MCP server (close and reopen AI assistant connection).

## Troubleshooting

### "Cannot connect to server"
- ✅ Verify SSH connection: `ssh view-user@syslog.example.com`
- ✅ Check uv is installed: `ssh view-user@syslog.example.com "which uv"`
- ✅ Verify deployment: `ssh view-user@syslog.example.com "ls -la ~/log-ai"`

### "Tool not available"
- ✅ Reload VS Code window (Cmd/Ctrl + Shift + P → "Reload Window")
- ✅ Check MCP settings file syntax (valid JSON)
- ✅ Restart Claude Desktop or IntelliJ

### "Configuration error"
- ✅ Ensure `config/.env` exists on remote server
- ✅ Check all required values are set in `.env`
- ✅ Review session logs: `tail -f /tmp/log-ai/{session-id}/mcp-server.log`

### Slow searches
- ✅ Enable Redis coordination (see README.md)
- ✅ Reduce search scope (specific services, shorter time ranges)
- ✅ Check `CACHE_MAX_SIZE_MB` in config/.env

## Next Steps

- **GitHub Copilot**: See [VSCODE_SETUP.md](VSCODE_SETUP.md) for detailed integration
- **Architecture**: See [README.md](README.md) for system design and Redis coordination
- **Development**: See [IMPLEMENTATION.md](IMPLEMENTATION.md) for technical details

## Example Use Cases

### 1. Service Health Check
```
@log-ai check for errors in awesome services in the last 2 hours
```

### 2. Surgical Precision Search (Production)
```
@log-ai search for errors in dev-ca-api from the last 10 minutes
```

### 3. Authentication Investigation
```
@log-ai search for "missing privilege" in aws-ecs-auth today
```

### 3. Performance Analysis
```
@log-ai find timeout and latency warnings in hub services from 2pm to 4pm yesterday
```

### 4. Multi-Service Correlation
```
@log-ai search for errors in dev-ca-api and dev-ca-rock-service 
with trace ID "69529ef00000000012db3f8badb09b21"
```

The AI assistant will intelligently:
- Parse your natural language request
- Extract relevant parameters (services, query, datetime)
- Call the appropriate MCP tools
- Synthesize findings into actionable insights
- Suggest follow-up investigations
