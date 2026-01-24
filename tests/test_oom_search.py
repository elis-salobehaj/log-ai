#!/usr/bin/env python3
"""
Search dev-ca-awesome-service for OOM errors on Dec 14, 2025
"""
import asyncio
import json
import os
import sys
from datetime import datetime
import pytest

async def print_stderr(stream):
    """Print stderr output as it comes"""
    while True:
        line = await stream.readline()
        if not line:
            break
        sys.stderr.write(line.decode())
        sys.stderr.flush()

@pytest.mark.asyncio
@pytest.mark.integration
async def test_search():
    # Configuration from environment (required)
    syslog_user = os.environ.get("SYSLOG_USER")
    syslog_server = os.environ.get("SYSLOG_SERVER")
    
    if not syslog_user or not syslog_server:
        raise ValueError(
            "Required environment variables SYSLOG_USER and SYSLOG_SERVER must be set.\n"
            "Source config/.env or set them manually: export SYSLOG_USER=your-user SYSLOG_SERVER=your-server"
        )
    
    # Start the server process
    proc = await asyncio.create_subprocess_exec(
        "ssh", f"{syslog_user}@{syslog_server}",
        f"~/.local/bin/uv run --directory /home/{syslog_user}/log-ai src/server.py",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=2**20  # Increase buffer to 1MB for large responses
    )
    
    # Start stderr printer in background
    stderr_task = asyncio.create_task(print_stderr(proc.stderr))
    
    try:
        # 1. Initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        proc.stdin.write((json.dumps(init_request) + "\n").encode())
        await proc.stdin.drain()
        
        # Read init response
        response = await proc.stdout.readline()
        print(f"Init response: {response.decode().strip()}", file=sys.stderr)
        
        # 2. Send initialized notification
        initialized = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        proc.stdin.write((json.dumps(initialized) + "\n").encode())
        await proc.stdin.drain()
        
        # 3. Call search_logs tool with UTC timestamps
        # Search for errors in the last 30 minutes (smaller window for testing)
        from datetime import datetime, timedelta
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=30)
        
        search_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_logs",
                "arguments": {
                    "service_name": "hub-ca-auth",
                    "query": "error|exception|failed",
                    "start_time_utc": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_time_utc": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "format": "json"
                }
            }
        }
        
        print(f"\nSearching hub-ca-auth for errors from {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')} UTC...\n", file=sys.stderr)
        
        proc.stdin.write((json.dumps(search_request) + "\n").encode())
        await proc.stdin.drain()
        
        # Read search response
        print("\n=== Search Results ===\n")
        response = await proc.stdout.readline()
        result = json.loads(response.decode())
        
        if "result" in result:
            for content in result["result"]["content"]:
                if content["type"] == "text":
                    data = json.loads(content["text"])
                    print(f"\nFound {len(data.get('matches', []))} matches", file=sys.stderr)
                    
                    # Verify the response structure
                    assert "matches" in data, "Response should contain matches"
                    assert "metadata" in data, "Response should contain metadata"
                    
                    metadata = data["metadata"]
                    print(f"Duration: {metadata.get('duration_seconds', 0):.2f}s", file=sys.stderr)
                    print(f"Total matches: {metadata.get('total_matches', 0)}", file=sys.stderr)
                    print(f"Files searched: {metadata.get('files_searched', 0)}", file=sys.stderr)
                    print("\n✓ Search completed successfully")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        
    finally:
        proc.terminate()
        await proc.wait()

if __name__ == "__main__":
    asyncio.run(test_search())
