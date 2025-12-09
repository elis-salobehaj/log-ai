import asyncio
import os
import sys
import uuid
import datetime
import shutil
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configuration for artifacts
# In non-Windows enviroments, we'd use /tmp directly.
# For cross-platform safety in this agent:
TEMP_ROOT = Path("/tmp") if os.name != "nt" else Path(os.environ.get("TEMP", "C:\\Temp"))

class LogAIAgent:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = TEMP_ROOT / "logai" / self.session_id
        self.logs_dir = self.session_dir / "logs"
        self.insights_dir = self.session_dir / "insights"
        self.history = [] # List of {role, content}
        
        # Initialize directories
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.insights_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"LogAI Session Initialized: {self.session_id}")
        print(f"Artifacts stored in: {self.session_dir}")

    def save_log_artifact(self, content: str, query: str) -> str:
        timestamp = datetime.datetime.now().strftime("%H-%M-%S")
        filename = f"log-search-{timestamp}.txt"
        path = self.logs_dir / filename
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Query: {query}\n")
            f.write("-" * 40 + "\n")
            f.write(content)
            
        return str(path)

    def save_insight_artifact(self, content: str) -> str:
        timestamp = datetime.datetime.now().strftime("%H-%M-%S")
        filename = f"insight-{timestamp}.txt"
        path = self.insights_dir / filename
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return str(path)

    async def run_query(self, mcp_session: ClientSession, user_input: str):
        self.history.append({"role": "user", "content": user_input})
        
        # --- NLP Router (Heuristic) ---
        # NOTE: Since we removed list_resources functionality for Scale, 
        # we can't discover services via resources anymore.
        # We must rely on user input or hardcoded knowledge of 'what services exist' 
        # or maybe we add a 'list_services' tool?
        # For POC/Agent simplicity, we check known config? 
        # Or let's just grep the input for known keys in services.yaml (if agent has access? No agent shouldn't know backend config).
        # Let's fallback to: "Service name is required".
        
        # Hardcoded known services for the client CLI POC to work
        known_services = ["aws-ecs-web", "pylons-app", "aws-ses"]
        target_services = [s for s in known_services if s in user_input]
        
        if not target_services:
            print("LogAI: I couldn't identify a specific service in your query.")
            print(f"Known services: {', '.join(known_services)}")
            return

        # 2. Extract Intent (Search Query)
        keywords = ["error", "fail", "warn", "exception", "timeout", "down", "oom", "crash"]
        search_term = next((k for k in keywords if k in user_input.lower()), None)
        if not search_term: search_term = "error" 
        
        # --- Execution ---
        for service in target_services:
            print(f"LogAI: Searching logs for '{service}' with term '{search_term}'...")
            
            # Call Search Tool
            result = await mcp_session.call_tool(
                "search_logs",
                arguments={"service_name": service, "query": search_term, "days_back": 1}
            )
            
            content = result.content[0].text
            
            if "No matches" in content:
                print(f"LogAI: No relevant logs found for {service}.")
                continue
                
            # --- Save Artifacts ---
            log_file = self.save_log_artifact(content, user_input)
            print(f"LogAI: [Saved Logs] {log_file}")
            
            # --- Insights (Via Tool) ---
            print("LogAI: Analyzing for insights...")
            insight_result = await mcp_session.call_tool(
                "get_insights",
                arguments={"service_name": service, "log_content": content}
            )
            insight_text = insight_result.content[0].text
            
            insight_file = self.save_insight_artifact(insight_text)
            
            print(f"LogAI: [Insight] {insight_text}")
            print(f"LogAI: [Saved Insight] {insight_file}")
            
            self.history.append({
                "role": "assistant", 
                "content": f"Found logs. Insight: {insight_text}"
            })

async def main():
    # Setup Server Parameters
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_script = os.path.join(project_root, "src", "server.py")
    
    # We must ensure we are using the sub-process correctly
    # 'python' or 'uv run'
    server_params = StdioServerParameters(
        command="python", 
        args=[server_script],
        env=os.environ.copy()
    )

    # Session ID
    sid = str(uuid.uuid4())[:8]
    agent = LogAIAgent(sid)
    
    print("----------------------------------------------------------------")
    print("Welcome to LogAI. I can help you investigate system logs.")
    print("Try: 'find errors in aws-ecs-web' or 'check pylons-app status'")
    print("Type 'exit' to quit.")
    print("----------------------------------------------------------------")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            while True:
                user_input = input("\nUser> ").strip()
                if user_input.lower() in ["exit", "quit"]:
                    break
                
                if not user_input:
                    continue
                    
                await agent.run_query(session, user_input)

    # Cleanup is handled by start.sh or we can prompt here
    # print("Session ended.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
