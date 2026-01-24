# VSCode GitHub Copilot Setup

Complete guide to integrating LogAI MCP server with GitHub Copilot in VSCode.

---

## Quick Start

### Method 1: Workspace Configuration (Recommended)

This method makes the MCP server available only in your current workspace.

**1. Create `.vscode/mcp.json` in your workspace root:**

```json
{
  "servers": {
    "log-ai": {
      "type": "stdio",
      "command": "ssh",
      "args": [
        "view-user@syslog.example.com",
        "cd /home/view-user/log-ai && ~/.local/bin/uv run src/server.py"
      ]
    }
  }
}
```

**2. Reload VSCode:**
- Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
- Type "Developer: Reload Window"
- Press Enter

**3. Test in Copilot Chat:**

Open GitHub Copilot Chat and try:

```
@workspace /tools log-ai search_logs dev-ca-api timeout 2 hours
```

---

### Method 2: User Settings (Global)

This method makes the MCP server available in all VSCode workspaces.

**1. Open User Settings:**

**Linux/Windows:**
- Press `Ctrl+Shift+P`
- Type "Preferences: Open User Settings (JSON)"
- Press Enter

**Mac:**
- Press `Cmd+Shift+P`
- Type "Preferences: Open User Settings (JSON)"
- Press Enter

**2. Add MCP Server Configuration:**

Add this to your `settings.json`:

```json
{
  "github.copilot.chat.mcpServers": {
    "log-ai": {
      "command": "ssh",
      "args": [
        "view-user@syslog.example.com",
        "~/.local/bin/uv run --directory /home/view-user/log-ai src/server.py"
      ]
    }
  }
}
```

**Note:** If you already have other settings, just add the `"github.copilot.chat.mcpServers"` section.

**3. Reload VSCode:**
- Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
- Type "Developer: Reload Window"
- Press Enter

**4. Test in Copilot Chat:**

```
Use log-ai to search for errors in dev-ca-api in the past hour
```

or

```
@workspace /tools log-ai search_logs dev-ca-api timeout 2 hours
```

## SSH Requirements

### SSH Key Setup

The MCP server connects via SSH, so you need passwordless SSH authentication:

1. **Generate SSH key** (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

2. **Copy to syslog server**:
   ```bash
   ssh-copy-id view-user@syslog.example.com
   ```

3. **Test connection**:
   ```bash
   ssh view-user@syslog.example.com "echo 'Connection OK'"
   ```
   
   Should connect without password prompt.

### Troubleshooting SSH

If VSCode MCP connection fails:

1. **Test SSH manually**:
   ```bash
   ssh view-user@syslog.example.com "~/.local/bin/uv run --directory /home/view-user/log-ai src/server.py"
   ```
   
   Should show: `{"jsonrpc": "2.0", ...}`

2. **Check SSH config** (`~/.ssh/config`):
   ```
   Host syslog.example.com
       User view-user
       IdentityFile ~/.ssh/id_ed25519
       ServerAliveInterval 60
   ```

3. **Check VSCode Output**:
   - View → Output
   - Select "GitHub Copilot Chat" from dropdown
   - Look for MCP connection errors

## Available MCP Tools

Once connected, Copilot can use these tools:

### search_logs
Search log entries across services:
- **Parameters**: service_name, query, hours_back/days_back, format
- **Example**: "Search dev-ca-api for timeout in past 2 hours"

### get_insights
Get recommendations based on log patterns:
- **Parameters**: service_name, log_content, format
- **Example**: "Analyze this error: OutOfMemoryError..."

### read_search_file
Read saved search results (for large result sets):
- **Parameters**: file_path, format
- **Example**: "Read the full results from /tmp/log-ai/..."

---

## IntelliJ IDEA Setup

If you use IntelliJ IDEA with Amazon Q or Junie, you can also connect to LogAI:

**1. Open Settings:**
- Windows/Linux: `Ctrl+Alt+S`
- Mac: `Cmd+,`

**2. Navigate to:**
- **Tools → Model Context Protocol**

**3. Add Server:**
- Click **+ Add Server**
- **Name**: `log-ai`
- **Connection Type**: `Stdio`
- **Command**: `ssh`
- **Arguments**: `view-user@syslog.example.com "~/.local/bin/uv run --directory /home/view-user/log-ai src/server.py"`

**4. Apply and Restart IntelliJ**

**5. Test:**
Ask your AI assistant: "Search dev-ca-api logs for errors in the past hour"

---

## Example Conversations

### Finding Recent Errors
```
You: Find errors in dev-ca-api from the past hour

Copilot: I'll search the logs...
[Uses search_logs tool]

Copilot: Found 23 error entries:
- Connection timeouts: 12 occurrences
- Null pointer exceptions: 8 occurrences
- Database deadlocks: 3 occurrences
```

### Multi-Service Investigation
```
You: Are there timeout issues across all hub services?

Copilot: I'll search dev-ca-api, dev-ca-rock-service, and dev-ca-auth...
[Uses search_logs with multiple services]

Copilot: Found 156 timeout entries across 3 services...
```

### Getting Insights
```
You: I see "OutOfMemoryError" in the logs. What should I do?

Copilot: Let me check the recommendations...
[Uses get_insights tool]

Copilot: This is a critical issue. Recommendations:
- Check JVM memory limits
- Analyze heap dumps
- Review service scaling settings
```

## Configuration Options

### Alternative SSH Setup (if needed)

If direct SSH doesn't work (firewall/VPN issues), create a wrapper script:

**~/bin/log-ai-mcp.sh:**
```bash
#!/bin/bash
ssh -T view-user@syslog.example.com "cd /home/view-user/log-ai && ~/.local/bin/uv run src/server.py"
```

Make executable:
```bash
chmod +x ~/bin/log-ai-mcp.sh
```

Update settings.json:
```json
{
  "github.copilot.chat.mcpServers": {
    "log-ai": {
      "command": "/home/your-username/bin/log-ai-mcp.sh",
      "args": []
    }
  }
}
```

### Output Format

By default, results are text format. For JSON (better for Copilot parsing):

```
You: Search dev-ca-api for errors (format: json)
```

Copilot will request JSON format which provides structured data.

## Monitoring

While Copilot searches, the MCP server logs activity on the remote server:

```bash
# SSH to syslog server and tail logs
ssh view-user@syslog.example.com
tail -f /tmp/log-ai-debug.log  # if debug logging enabled
```

Look for:
- `[SEARCH]` - Search started
- `[PROGRESS]` - Match count updates
- `[COMPLETE]` - Search finished
- `[CACHE]` - Cache hits/misses
- `[ERROR]` - Any failures

## Limits

- **In-memory results**: 1000 matches max
- **Overflow to file**: Larger result sets saved to `/tmp/log-ai/`
- **Cache TTL**: 10 minutes
- **Search timeout**: 5 minutes (returns partial results)
- **Concurrent searches**: 10 global, 5 per request

## Next Steps

1. ✅ Add MCP configuration to VSCode settings.json
2. ✅ Reload VSCode window
3. ✅ Test SSH connection manually
4. ✅ Try a simple search in Copilot Chat
5. ⏳ Explore multi-service searches
6. ⏳ Use get_insights for log analysis

## Support

For issues or questions:
- Check [README.md](README.md) for tool documentation
- Check [IMPLEMENTATION.md](IMPLEMENTATION.md) for architecture details
- Contact DevOps team for syslog server access issues
