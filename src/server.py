import asyncio
import logging
import os
import sys
import subprocess
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from config import load_config, find_log_files

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("log-ai")

async def main():
    config = load_config()
    server = Server("log-ai")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        return [] # For Scale, we don't list all 300GB files. Too expensive.

    @server.read_resource()
    async def handle_read_resource(uri: types.AnyUrl) -> str | bytes:
        # We might not support direct file reading of non-listed resources 
        # or implement it via a direct path check if needed.
        # But for 'Search' heavy flow, read_resource is less used.
        return "Direct file reading disabled for scale performance."

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_logs",
                description="Search for log entries. Uses optimized GREP.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string", "description": "Name of the service"},
                        "query": {"type": "string", "description": "Keyword to search"},
                        "days_back": {"type": "integer", "description": "Last N days (Default 1)"},
                    },
                    "required": ["service_name", "query"]
                }
            ),
             types.Tool(
                name="get_insights",
                description="Get expert insights and recommendations based on log content.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string"},
                        "log_content": {"type": "string", "description": "The raw logs to analyze"},
                    },
                    "required": ["service_name", "log_content"]
                }
            )
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if not arguments:
            raise ValueError("Missing arguments")

        if name == "search_logs":
            return await search_logs(arguments)
        elif name == "get_insights":
            return await get_insights(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def search_logs(args: dict) -> list[types.TextContent]:
        service_name = args.get("service_name")
        query = args.get("query")
        days_back = int(args.get("days_back", 1))

        target_service = next((s for s in config.services if s.name == service_name), None)
        if not target_service:
            return [types.TextContent(type="text", text=f"Error: Service {service_name} not found.")]

        # 1. Efficient File Discovery (Date Partitioned)
        files = find_log_files(target_service, days_back=days_back)
        
        if not files:
            return [types.TextContent(type="text", text=f"No log files found for {service_name} in last {days_back} days.")]

        # 2. Grep Execution
        # We start a subprocess to grep keywords in found files.
        # This is much faster than Python loop.
        
        # Windows fallback (since user is on Windows dev env but targeting Ubuntu)
        if os.name == 'nt':
            # Use Python implementation on Windows for testing
            results = []
            hit_count = 0
            MAX_HITS = 200
            for file_path in files:
                if hit_count >= MAX_HITS: break
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if query.lower() in line.lower():
                                results.append(f"[{Path(file_path).name}:{i}] {line.strip()}")
                                hit_count += 1
                                if hit_count >= MAX_HITS: break
                except: pass
            return [types.TextContent(type="text", text="\n".join(results) if results else "No matches.")]
        
        else:
            # Linux/Ubuntu Grep
            # grep -n "query" file1 file2 ...
            # Limit results to avoided blowing up stdout (head -n 200?)
            cmd = ["grep", "-i", "-n", query] + files
            
            try:
                # We cap output at 100KB or some lines.
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                stdout, stderr = process.communicate(timeout=10) # 10s regex timeout
                
                # Format: filename:line:content
                # We might want to truncate if huge.
                lines = stdout.splitlines()[:200]
                return [types.TextContent(type="text", text="\n".join(lines) if lines else "No matches found (grep).")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"Grep failed: {str(e)}")]

    async def get_insights(args: dict) -> list[types.TextContent]:
        service_name = args.get("service_name")
        content = args.get("log_content", "")
        
        target_service = next((s for s in config.services if s.name == service_name), None)
        if not target_service or not target_service.insight_rules:
            sys.stderr.write(f"DEBUG: No rules for {service_name}. Rules: {getattr(target_service, 'insight_rules', 'None')}\n")
            return [types.TextContent(type="text", text="No specific insight rules configured for this service.")]

        insights = []
        lower_content = content.lower()
        sys.stderr.write(f"DEBUG: Checking {len(target_service.insight_rules)} rules against content len {len(content)}\n")
        
        for rule in target_service.insight_rules:
            # Check if ANY pattern in the rule matches
            match = False
            for pattern in rule.patterns:
                if pattern.lower() in lower_content:
                    match = True
                    break
            
            if match:
                insights.append(f"[{rule.severity.upper()}] Recommendation: {rule.recommendation}")

        if not insights:
            return [types.TextContent(type="text", text="No issues matched known patterns.")]

        return [types.TextContent(type="text", text="\n".join(insights))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
