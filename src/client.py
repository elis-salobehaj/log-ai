import asyncio
import sys
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # We assume this client is run from the project root or we know where server.py is
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_script = os.path.join(project_root, "src", "server.py")

    # Command to run the server
    # Using 'uv run' or 'python' depending on env. 
    # Let's assume 'python' for simplicity in this script, user can alias it.
    server_params = StdioServerParameters(
        command="python", # or "uv"
        args=[server_script],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print("Connected to LogAI Server!")
            
            # List resources
            resources = await session.list_resources()
            print(f"\nFound {len(resources.resources)} resources:")
            for res in resources.resources:
                print(f" - {res.name} ({res.uri})")
                
            # Optionally read the first one
            if resources.resources:
                first = resources.resources[0]
                print(f"\nReading content of first resource: {first.name}...")
                content = await session.read_resource(first.uri)
                # Content is returned as ReadResourceResult, which has 'contents' list
                print("--- Content Start ---")
                for item in content.contents:
                    print(item.text[:200] + "... (truncated)") # Print first 200 chars
                print("--- Content End ---")

if __name__ == "__main__":
    asyncio.run(main())
