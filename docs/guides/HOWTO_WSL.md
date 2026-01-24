# How to Run LogAI on WSL (Windows Subsystem for Linux)

This guide covers the initial setup and configuration for running LogAI in a WSL environment.

## 1. Initial Setup

### Prerequisites
- WSL 2 installed (Ubuntu recommended).
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

### 0. Enter the WSL Shell
From your PowerShell or Command Prompt in `D:\projects\logAI`, simply run:
```bash
wsl -u root
```
This will drop you into the Ubuntu terminal inside the current directory as the **root** user.
(Note: Since your initial user setup failed, using `-u root` is the easiest way to get in. You have full permissions.)

### Installation
Assuming you have copied the `logAI` folder to your Linux home directory (e.g., `~/logAI`):

```bash
cd ~/logAI

# 1. Sync dependencies (creates virtualenv)
# Note: We fixed the build error by adding [tool.hatch.build.targets.wheel] to pyproject.toml
uv sync

# 2. Verify the installation
uv run src/agent.py --help
# You should see the CLI help output or entry prompt.
```

### Generate Test Logs
Create the dummy log data for testing:
```bash
uv run scripts/create_dummy_logs.py
```

## 2. VSCode Integration (MCP over WSL)

To let your Windows VSCode Copilot talk to the LogAI Server running in WSL, you can use the `wsl.exe` bridge.

**Add to `claude_desktop_config.json` (or VSCode MCP Settings):**

```json
{
  "mcpServers": {
    "log-ai-wsl": {
      "command": "wsl.exe",
      "args": [
        "--cd",
        "~/logAI",
        "bash",
        "-c",
        "~/.cargo/bin/uv run src/server.py"
      ]
    }
  }
}
```
*Note 1: Adjust `~/logAI` if you placed the folder elsewhere.*
*Note 2: Ensure `uv` path is correct. `~/.cargo/bin/uv` is standard if installed via cargo/script, or just `uv` if it's in the global PATH.*

## 3. CLI Usage
You can always use the CLI directly inside the WSL terminal:

```bash
uv run src/agent.py
# User> find errors in pylons-app
```
