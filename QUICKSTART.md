# Quick Start Guide

## 1. Deploy to Remote Server

From your local machine:

```bash
cd /home/ubuntu/elis_temp/github_projects/log-ai
bash scripts/deploy.sh
```

This will:
- ✅ Validate Python syntax
- ✅ Copy files to remote server via SCP
- ✅ Install dependencies with `uv sync`
- ✅ Run tests on remote server

## 2. Start WebSocket Server

SSH into the remote server:

```bash
ssh srt@syslog.awstst.pason.com
cd /home/srt/log-ai
```

**(Optional) Enable LLM features:**
```bash
export OPENAI_API_KEY='sk-proj-...'
```

**Start the server:**
```bash
bash scripts/start_websocket.sh
```

You'll see output like:
```
============================================================
LogAI WebSocket Server
============================================================
Authentication Token: abc123xyz789...
WebSocket URL: ws://localhost:8765/ws/search?token=abc123xyz789...
Health Check: http://localhost:8765/health
Services: 90
LLM Available: True
============================================================
```

**Copy the authentication token** - you'll need it!

## 3. Create SSH Tunnel

From your **local machine** (where VSCode runs), open a new terminal:

```bash
ssh -L 8765:localhost:8765 srt@syslog.awstst.pason.com
```

Keep this terminal open. The tunnel forwards `localhost:8765` on your machine to the remote server.

## 4. Test with WebSocket Client

### Option A: Python Test Script

```python
import asyncio
import websockets
import json

async def test_search():
    token = "abc123xyz789..."  # Your token from step 2
    uri = f"ws://localhost:8765/ws/search?token={token}"
    
    async with websockets.connect(uri) as ws:
        # Send search request
        await ws.send(json.dumps({
            "type": "search",
            "query": "find errors in hub-ca-api in the past hour"
        }))
        
        # Receive responses
        async for message in ws:
            msg = json.loads(message)
            print(f"{msg['type'].upper()}: {msg}")
            
            if msg['type'] == 'complete':
                break

asyncio.run(test_search())
```

### Option B: wscat (Command Line)

Install wscat:
```bash
npm install -g wscat
```

Connect and query:
```bash
wscat -c "ws://localhost:8765/ws/search?token=abc123xyz789..."

# After connecting, type:
{"type":"search","query":"find errors in hub-ca-api"}
```

### Option C: Browser Console

Open browser console (F12) and paste:

```javascript
const ws = new WebSocket('ws://localhost:8765/ws/search?token=abc123xyz789...');

ws.onopen = () => {
    console.log('Connected!');
    ws.send(JSON.stringify({
        type: 'search',
        query: 'find timeout errors in hub-ca-api in the past hour'
    }));
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    console.log(msg.type + ':', msg);
};
```

## 5. Expected Output

You'll receive messages in this order:

### 1. Plan Message
```json
{
  "type": "plan",
  "llm_explanation": "Searching hub-ca-api for timeout and error patterns...",
  "services": ["hub-ca-api"],
  "ripgrep_command": "rg -i -n -e timeout -e error <156 files>",
  "files_count": 156
}
```

### 2. Batch Messages (every 10 matches)
```json
{
  "type": "batch",
  "matches": [
    {
      "file": "/syslog/.../hub-ca-api-kinesis-xyz.log",
      "line_number": 1234,
      "content": "ERROR: Connection timeout",
      "service": "hub-ca-api"
    }
  ],
  "total_so_far": 10
}
```

### 3. Complete Message
```json
{
  "type": "complete",
  "total_matches": 234,
  "duration_seconds": 4.52
}
```

## 6. Health Check

Test if server is running:

```bash
curl http://localhost:8765/health
```

Response:
```json
{
  "status": "healthy",
  "connections": 0,
  "services": 90,
  "llm_available": true,
  "cache_size": 0
}
```

## Troubleshooting

### "Connection refused"
- ✅ Is the WebSocket server running? Check SSH session
- ✅ Is the SSH tunnel active? Check local terminal
- ✅ Correct port? Should be 8765

### "Invalid authentication token"
- ✅ Copy token from server startup output
- ✅ Include in URL: `?token=...`
- ✅ Token changes on server restart

### "Rate limit exceeded"
- ⏱️ Wait 60 seconds
- 📊 Limit: 10 queries per minute per connection

### "Search already in progress"
- ⏳ Wait for current search to complete
- ❌ Or send `{"type": "cancel"}` first

### "LLM available: False"
- ⚠️ OPENAI_API_KEY not set
- 🔄 Server falls back to rule-based parsing
- ✅ Still works, just less intelligent

## Next Steps

### Build VSCode Extension

Now that the backend works, create a VSCode extension that:
1. Spawns SSH tunnel automatically
2. Connects to WebSocket with token from settings
3. Shows results in TreeView
4. Provides cancel/progress UI

### Advanced Usage

See [WEBSOCKET_PROTOCOL.md](WEBSOCKET_PROTOCOL.md) for:
- Complete message protocol
- Cancellation
- Caching behavior
- Rate limiting details
- Connection lifecycle

### More Examples

See [README.md](README.md) for:
- WebSocket API examples
- MCP server usage (legacy)
- Configuration options

---

**Questions?** Check the documentation:
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - What was built and why
- [WEBSOCKET_PROTOCOL.md](WEBSOCKET_PROTOCOL.md) - API reference
- [README.md](README.md) - User guide
