#!/usr/bin/env python3
"""
Test Sentry and Datadog MCP tools on the deployed server
"""
import json
import subprocess
import sys

def test_mcp_tool(tool_name, params):
    """Test an MCP tool by invoking the server directly"""
    
    # Create MCP request
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": params
        }
    }
    
    # Convert to JSON
    request_json = json.dumps(request)
    
    # Call the MCP server
    cmd = [
        "ssh",
        "srt@syslog.awstst.pason.com",
        "cd /home/srt/log-ai && ~/.local/bin/uv run python -c \"import sys; sys.path.insert(0, '.'); from src.server import handle_call_tool; import json; import asyncio; req = json.loads(sys.stdin.read()); result = asyncio.run(handle_call_tool(req['params']['name'], req['params']['arguments'])); print(json.dumps({'result': [{'type': 'text', 'text': str(r.text if hasattr(r, 'text') else r)} for r in result]}))\""
    ]
    
    print(f"\n{'='*80}")
    print(f"Testing: {tool_name}")
    print(f"Parameters: {json.dumps(params, indent=2)}")
    print(f"{'='*80}\n")
    
    try:
        # Run the command
        result = subprocess.run(
            cmd,
            input=request_json,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                print("✅ SUCCESS")
                print(f"\nResponse:\n{json.dumps(response, indent=2)}")
            except json.JSONDecodeError:
                print("✅ Got response but not JSON:")
                print(result.stdout)
        else:
            print(f"❌ FAILED (exit code {result.returncode})")
            if result.stderr:
                print(f"Error: {result.stderr}")
            if result.stdout:
                print(f"Output: {result.stdout}")
                
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT (30s)")
    except Exception as e:
        print(f"❌ ERROR: {e}")

def main():
    print("\n" + "="*80)
    print("Testing Sentry and Datadog MCP Tools on Deployed Server")
    print("="*80)
    
    # Test 1: Sentry Issues Query
    print("\n### TEST 1: Query Sentry Issues ###")
    test_mcp_tool("query_sentry_issues", {
        "service_name": "auth",
        "query": "is:unresolved",
        "limit": 3,
        "statsPeriod": "24h"
    })
    
    # Test 2: Datadog APM Query
    print("\n### TEST 2: Query Datadog APM Traces ###")
    test_mcp_tool("query_datadog_apm", {
        "service": "log-ai-mcp",
        "hours_back": 2,
        "format": "text"
    })
    
    # Test 3: Datadog Metrics Query
    print("\n### TEST 3: Query Datadog Metrics ###")
    test_mcp_tool("query_datadog_metrics", {
        "metric_query": "avg:system.cpu.user{*}",
        "hours_back": 1,
        "format": "text"
    })
    
    # Test 4: Datadog Logs Query
    print("\n### TEST 4: Query Datadog Logs ###")
    test_mcp_tool("query_datadog_logs", {
        "query": "service:log-ai-mcp",
        "hours_back": 1,
        "limit": 10,
        "format": "text"
    })
    
    print("\n" + "="*80)
    print("Testing Complete")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
