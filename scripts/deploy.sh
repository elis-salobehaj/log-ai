#!/bin/bash
#
# Deploy LogAI MCP Server to remote syslog server
#
# Usage: bash scripts/deploy.sh
#

set -e

REMOTE_USER="srt"
REMOTE_HOST="syslog.awstst.pason.com"
REMOTE_DIR="/home/srt/log-ai"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "========================================"
echo "Deploying LogAI to $REMOTE_HOST"
echo "========================================"
echo ""

# Check if remote is accessible
if ! ssh -o ConnectTimeout=5 "$REMOTE_USER@$REMOTE_HOST" "echo 'Connection successful'" 2>/dev/null; then
    echo "❌ Cannot connect to $REMOTE_HOST"
    echo "   Make sure SSH is configured and the host is reachable"
    exit 1
fi

echo "✓ SSH connection verified"
echo ""

# Compile Python files locally first
echo "Checking Python syntax..."
cd "$LOCAL_DIR"
python3 -m py_compile src/server.py src/config.py || {
    echo "❌ Syntax errors found. Fix them before deploying."
    exit 1
}
echo "✓ All Python files compile successfully"
echo ""

# Create remote output directory
echo "Creating /tmp/log-ai directory on remote..."
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p /tmp/log-ai && chmod 755 /tmp/log-ai" || {
    echo "❌ Failed to create output directory"
    exit 1
}
echo "✓ Output directory created"
echo ""

# Sync entire project to remote (excludes .git, .venv, __pycache__)
echo "Syncing project files to remote server..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='uv.lock' \
    "$LOCAL_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo ""
echo "✓ Files synced successfully"
echo ""

# Install dependencies on remote
echo "Installing dependencies on remote server..."
ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_DIR && ~/.local/bin/uv sync" || {
    echo "❌ Failed to install dependencies"
    exit 1
}
echo "✓ Dependencies installed"
echo ""

# Test server loads correctly
echo "Testing server imports..."
ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_DIR && ~/.local/bin/uv run python -c 'import sys; sys.path.insert(0, \"src\"); from server import SearchCache, ensure_output_dir; print(\"✓ Server module loads correctly\")'" || {
    echo "❌ Server module failed to load"
    exit 1
}
echo "✓ Server imports successful"
echo ""

echo "========================================"
echo "✅ Deployment successful!"
echo "========================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your AI agent (Copilot/Claude) with MCP:"
echo "   {"
echo "     \"mcpServers\": {"
echo "       \"log-ai\": {"
echo "         \"command\": \"ssh\","
echo "         \"args\": ["
echo "           \"$REMOTE_USER@$REMOTE_HOST\","
echo "           \"~/.local/bin/uv run --directory $REMOTE_DIR src/server.py\""
echo "         ]"
echo "       }"
echo "     }"
echo "   }"
echo ""
echo "2. Available MCP tools:"
echo "   - search_logs: Search log entries (supports multi-service)"
echo "   - get_insights: Get expert recommendations"
echo "   - read_search_file: Read saved overflow results"
echo ""
echo "3. Monitor logs:"
echo "   - Progress: [PROGRESS] N matches"
echo "   - Cache: [CACHE] HIT/PUT/Evicted"
echo "   - Files: [FILE] Saved to /tmp/log-ai/..."
echo ""
echo "4. Server features:"
echo "   - Streaming search (no timeouts)"
echo "   - Smart caching (500MB, 10min TTL)"
echo "   - Multi-service support"
echo "   - JSON/text format options"
echo "   - Auto file overflow for large results"
echo ""
echo "========================================"
