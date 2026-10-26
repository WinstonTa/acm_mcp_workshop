# ACM MCP Workshop

A one-hour workshop on building a custom [Model Context Protocol](https://modelcontextprotocol.io) server. The whole session is one Python process, [`example_mcp.py`](example_mcp.py). Connect it once, then walk the demos in order.

You leave able to answer three questions:

- A **tool** is a function the model chooses to call. The name, docstring, and type hints are the schema.
- A **resource** is data the host reads by URI and puts in front of the model.
- A **prompt** is a message template a person picks from a menu.

## Prerequisites

- Python 3.10 or newer
- [Cursor](https://cursor.com), which is the host for the live demos
- Node.js (`npx`) and [`uv`](https://docs.astral.sh/uv/) only if you also open the MCP Inspector

The server class is `MCPServer` from `mcp.server`. That is the v2 SDK, which is what `pip install mcp` installs.

## Setup

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS or Linux, the interpreter is `.venv/bin/python` and the activate path differs, but the pip command is the same idea.

[`requirements.txt`](requirements.txt) installs `mcp[cli]` (the SDK plus the `mcp` command) and `psutil` (CPU, memory, and disk for the system demo).

## Connect it in Cursor

Create `.cursor/mcp.json` in this repo.

Windows:

```json
{
  "mcpServers": {
    "workshop": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["${workspaceFolder}/example_mcp.py"]
    }
  }
}
```

macOS or Linux:

```json
{
  "mcpServers": {
    "workshop": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["${workspaceFolder}/example_mcp.py"]
    }
  }
}
```

Reload the window. Open **Customize** in the sidebar, find **workshop**, and turn it on. The tool list should be `echo`, `plan_session`, `minutes_per_topic`, `disk_free`, `system_snapshot`, `countdown`, `save_note`, `list_notes`, and `delete_note`.

Open `example_mcp.py` on one side of the screen and an **Agent** chat on the other. Cursor starts the server. Running `python example_mcp.py` yourself only waits on stdin, because stdout is the protocol and the file never prints.

When a tool call appears, expand it so the room can see the arguments. Leave approval on for the first call, then allow the server so later demos keep moving. If the model answers without calling a tool, add: "Use the workshop tool. Do not answer from memory."
