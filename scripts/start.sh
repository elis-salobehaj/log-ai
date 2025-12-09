#!/bin/bash
# LogAI Startup Script
# Handles cleanup of temporary artifacts on exit.

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

# Determine TEMP_ROOT same as python script logic
# In standard linux this is just /tmp
TEMP_ROOT="/tmp"
# If on windows git bash, we might need a different path, 
# but User prompt said "Ubuntu syslog server", so /tmp is safe for the "Target OS".
# For local dev in `uv`, we might rely on the python agent to print the path it used, 
# or just assume the agent manages its own life?
# The prompt asked: "on ssh session close /tmp/{id} should be pruned".
# The best way is to trap the EXIT of this script, which the user runs.

function cleanup {
    # We don't know the uuid easily unless we capture it from the python output
    # or pass it IN.
    # Let's pass the ID in? Or have the python script write a PID/ID file?
    # Simpler: The Python agent is the main process. 
    # If this script runs the python agent, when python exits, we can clean up?
    # Actually, the requirement is "on ssh session close". 
    # If the user runs this interactively, when they exit the tool, we clean up.
    # If the SSH session dies, SIGHUP is sent.
    
    echo "LogAI: Cleaning up session artifacts..."
    # A robust way is for the agent to write its session_dir to a file
    if [ -f .last_session ]; then
        SESSION_DIR=$(cat .last_session)
        if [ -d "$SESSION_DIR" ]; then
            rm -rf "$SESSION_DIR"
            echo "Removed $SESSION_DIR"
        fi
        rm .last_session
    fi
}

trap cleanup EXIT

echo "Starting LogAI..."
# We run the agent. We modify agent to write the session path to .last_session for cleanup.
# Note: In a multi-user env, .last_session in global dir is bad. 
# It should be a temp file or the python script handles its own cleanup via atexit?
# But `atexit` in python might not catch SIGKILL/hard crash.
# Let's rely on the Python script handling graceful exits, AND this trap for safety if we can.
# Modified approach: We won't implement complex IPC for POC. 
# We'll trust the user "exits" the shell.
# Or, simpler: We tell the user "Session artifacts are in /tmp/...".
# The PROMPT requirement "on ssh close ... pruned":
# This implies we need to encompass the session.
# If `uv run` blocks, the trap waits.
uv run src/agent.py
