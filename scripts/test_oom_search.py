#!/usr/bin/env python3
"""
Search hub-ca-edr-proxy-service for OOM errors on Dec 14, 2025
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

async def test_search():
    # Start the server process
    proc = await asyncio.create_subprocess_exec(
        "ssh", "srt@syslog.awstst.pason.com",
        "~/.local/bin/uv run --directory /home/srt/log-ai src/server.py",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
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
        
        # 3. Call search_logs tool for specific date
        # Dec 14, 2025 - need to search 4 days back to include it
        # days_back counts: 0=today(17), 1=yesterday(16), 2=(15), 3=(14)
        search_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_logs",
                "arguments": {
                    "service_name": "hub-ca-edr-proxy-service",
                    "query": "oom|OutOfMemory",
                    "days_back": 4,  # Need 4 to include Dec 14
                    "format": "json"
                }
            }
        }
        
        print(f"\nSearching hub-ca-edr-proxy-service for OOM errors on Dec 14, 2025...\n", file=sys.stderr)
        
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
                    print(f"Total matches: {data['metadata']['total_matches']}")
                    print(f"Files searched: {data['metadata']['files_searched']}")
                    print(f"Duration: {data['metadata']['duration_seconds']:.2f}s")
                    print(f"Cached: {data['metadata']['cached']}")
                    
                    if data['metadata'].get('overflow'):
                        print(f"\n⚠️  Large result set - saved to: {data['metadata']['saved_to']}")
                        print(f"Showing first {len(data['matches'])} matches:\n")
                    
                    if data['metadata']['total_matches'] == 0:
                        print("\n✓ No OOM errors found on Dec 14, 2025")
                    else:
                        # Show all matches (or first 20 if many)
                        for i, match in enumerate(data['matches'][:20], 1):
                            print(f"\n{i}. [{match['service']}] {match['file']}:{match['line']}")
                            print(f"   {match['content']}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        
    finally:
        proc.terminate()
        await proc.wait()

if __name__ == "__main__":
    asyncio.run(test_search())
