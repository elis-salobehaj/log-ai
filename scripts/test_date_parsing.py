#!/usr/bin/env python3
"""
Test date parsing and timezone conversion features
"""
import asyncio
import json
import sys
from datetime import datetime

async def print_stderr(stream):
    """Print stderr output as it comes"""
    while True:
        line = await stream.readline()
        if not line:
            break
        sys.stderr.write(line.decode())
        sys.stderr.flush()

async def test_date_search():
    # Start the server process
    proc = await asyncio.create_subprocess_exec(
        "ssh", "srt@syslog.awstst.pason.com",
        "~/.local/bin/uv run --directory /home/srt/log-ai src/server.py",
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
        print(f"Init response received", file=sys.stderr)
        
        # 2. Send initialized notification
        initialized = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        proc.stdin.write((json.dumps(initialized) + "\n").encode())
        await proc.stdin.drain()
        
        # 3. Test date parsing with time range
        # Search for logs on Sunday (Dec 15, 2025) from 2pm to 4pm MST
        # MST is UTC-7, so 2pm MST = 21:00 UTC (Dec 15)
        search_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_logs",
                "arguments": {
                    "service_name": "hub-ca-edr-proxy-service",
                    "query": "error",
                    "date": "Sunday",  # Dec 15, 2025
                    "time_range": "2 to 4pm",
                    "timezone": "America/Denver",  # MST
                    "format": "json"
                }
            }
        }
        
        print(f"\n=== Test: Search Sunday 2-4pm MST (should convert to UTC 21:00-23:00) ===\n", file=sys.stderr)
        
        proc.stdin.write((json.dumps(search_request) + "\n").encode())
        await proc.stdin.drain()
        
        # Read search response
        response = await proc.stdout.readline()
        result = json.loads(response.decode())
        
        if "result" in result:
            for content in result["result"]["content"]:
                if content["type"] == "text":
                    data = json.loads(content["text"])
                    print(f"\n✓ Search completed:")
                    print(f"  Total matches: {data['metadata']['total_matches']}")
                    print(f"  Files searched: {data['metadata']['files_searched']}")
                    print(f"  Duration: {data['metadata']['duration_seconds']:.2f}s")
                    print(f"  Services: {data['metadata'].get('services', 'N/A')}")
                    
        # 4. Test specific date
        search_request2 = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_logs",
                "arguments": {
                    "service_name": "hub-ca-edr-proxy-service",
                    "query": "error",
                    "date": "Dec 14 2025",
                    "format": "json"
                }
            }
        }
        
        print(f"\n=== Test: Search specific date Dec 14, 2025 (all hours) ===\n", file=sys.stderr)
        
        proc.stdin.write((json.dumps(search_request2) + "\n").encode())
        await proc.stdin.drain()
        
        response = await proc.stdout.readline()
        result = json.loads(response.decode())
        
        if "result" in result:
            for content in result["result"]["content"]:
                if content["type"] == "text":
                    data = json.loads(content["text"])
                    print(f"\n✓ Search completed:")
                    print(f"  Total matches: {data['metadata']['total_matches']}")
                    print(f"  Files searched: {data['metadata']['files_searched']}")
                    print(f"  Duration: {data['metadata']['duration_seconds']:.2f}s")
        
        print("\n✓ All tests passed!\n")
        
    finally:
        proc.terminate()
        await proc.wait()
        stderr_task.cancel()

if __name__ == "__main__":
    asyncio.run(test_date_search())
