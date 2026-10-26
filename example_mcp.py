"""Custom MCP server for a one-hour workshop.

One process, seven demos. Connect this file once, then ask the model to use
each tool. Or skip the host and open the Inspector:

    pip install -r requirements.txt
    mcp dev example_mcp.py

Cursor mcp.json, with the path to this file:

    {
      "mcpServers": {
        "workshop": {
          "command": "python",
          "args": ["<path-to>/example_mcp.py"]
        }
      }
    }

Run of show:

    1. echo                  A tool is a typed function.             ~5 min
    2. plan_session          Schemas, defaults, structured results.  ~8 min
       minutes_per_topic     Schema rejection versus ToolError.
    3. system://stats        Resources versus tools.                 ~8 min
       disk_free, system_snapshot
    4. glossary://{term}     Resource templates.                     ~7 min
    5. explain_tool          Prompts the user picks from a menu.     ~7 min
       debug_server
    6. countdown             Progress while a tool is still running. ~8 min
    7. save_note             Tools, resources, and memory.           ~12 min
       Your turn             Attendees add a tool at the bottom.     ~5 min

The server class is MCPServer from mcp.server. That is SDK v2, which is
what `pip install mcp` installs. stdout is the protocol, so this file
never prints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Annotated, Literal

import psutil
from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.prompts.base import AssistantMessage, Message, UserMessage
from mcp.types import ToolAnnotations

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
log = logging.getLogger("workshop")

# psutil accepts "/" on Windows (the current drive). Prefer the drive root
# so a no-argument call shows the disk people expect, on either OS.
DEFAULT_DISK = os.path.abspath(os.sep)

mcp = MCPServer("Workshop")


# =============================================================================
# Demo 1 — A tool is a function (~5 min)
# Ask: "Use echo to say hello workshop."
# The function name is the tool name. The docstring is the description the
# model reads. The type hints are the input schema. Nothing else is required.
# =============================================================================


@mcp.tool(title="Echo")
def echo(message: str) -> str:
    """Repeat a message back. The smallest possible tool."""
    return message


# =============================================================================
# Demo 2 — Schemas, defaults, and structured results (~8 min)
# Ask: "Plan a 15 minute live-code slice about tools."
# Then: "Split 60 minutes across 0 topics." The schema allows 0. The
# function raises ToolError, and the model receives that text as a failed
# tool result it can retry from. The server log will also say the tool
# failed. Pass topics=-1 and the SDK rejects it first, before this
# function runs, because of Field(ge=0).
# =============================================================================


class SessionPlan(BaseModel):
    """One slice of the workshop. The return type is the output schema."""

    topic: str
    minutes: int
    style: str
    cue: str = Field(description="One sentence the instructor can say out loud.")


@mcp.tool(title="Plan a session")
def plan_session(
    topic: Annotated[str, Field(description="What this slice of the workshop covers.")],
    minutes: Annotated[int, Field(ge=5, le=60, description="How long the slice is.")] = 10,
    style: Literal["live-code", "demo", "exercise"] = "demo",
) -> SessionPlan:
    """Sketch one slice of the workshop."""
    return SessionPlan(
        topic=topic,
        minutes=minutes,
        style=style,
        cue=f"{style} for {minutes} minutes: {topic}.",
    )


@mcp.tool(title="Minutes per topic")
def minutes_per_topic(
    total_minutes: Annotated[int, Field(ge=1, le=180)],
    topics: Annotated[
        int,
        Field(ge=0, description="Zero is allowed by the schema and rejected by the function."),
    ],
) -> str:
    """Split a block of time evenly across a number of topics."""
    if topics == 0:
        raise ToolError("topics must be at least 1. Ask again with a positive count.")
    each = total_minutes / topics
    return f"About {each:.1f} minutes per topic ({total_minutes} minutes, {topics} topics)."


# =============================================================================
# Demo 3 — Resources versus tools (~8 min)
# A tool is something the model decides to call. A resource is data the
# application reads by URI and puts in front of the model.
# Ask: "How much disk is free?" (tool) and "Read system://stats" (resource).
# system_snapshot is the same facts as the resource, returned as a model
# so the client gets structured_content as well as text.
# =============================================================================


@mcp.resource("system://stats", title="System stats")
def get_stats() -> str:
    """CPU and memory right now."""
    # interval blocks briefly so the first read is a real sample.
    # With no interval, the first call returns 0.0.
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    return f"CPU: {cpu}% | RAM: {ram}%"


@mcp.tool(
    title="Free disk space",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def disk_free(path: str = DEFAULT_DISK) -> str:
    """Free space on a drive, in whole gigabytes.

    On Windows pass a drive root such as C:\\. Omit path to use this machine's default.
    """
    try:
        usage = psutil.disk_usage(path)
    except OSError as exc:
        raise ToolError(f"Cannot read disk space for {path!r}: {exc}") from exc
    free_gb = usage.free // (2**30)
    return f"Free disk space on {path}: {free_gb} GB"


class SystemSnapshot(BaseModel):
    """CPU and memory as fields a client can parse."""

    cpu_percent: float = Field(description="CPU usage over a short sample.")
    ram_percent: float = Field(description="Percent of RAM in use.")
    ram_used_gb: float = Field(description="RAM in use, in gigabytes.")


@mcp.tool(
    title="System snapshot",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def system_snapshot() -> SystemSnapshot:
    """Current CPU and memory, as structured data."""
    memory = psutil.virtual_memory()
    return SystemSnapshot(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        ram_percent=memory.percent,
        ram_used_gb=round(memory.used / (1024**3), 2),
    )


# =============================================================================
# Demo 4 — Resource templates (~7 min)
# A placeholder in the URI plus a matching parameter makes one function
# answer many addresses. glossary://index is a normal resource. glossary://tool
# is the template with term="tool".
# Ask: "What is a resource? Look it up in the glossary."
# The names have to match. {term} in the URI and term: str on the function.
# =============================================================================

GLOSSARY: dict[str, str] = {
    "tool": "A function the model chooses to call. Its name, docstring, and type hints are the schema.",
    "resource": "Data the application reads by URI and places in front of the model. The model does not call it.",
    "template": "A resource URI with a placeholder, such as glossary://{term}. One function answers every match.",
    "prompt": "A message template the user picks from a menu. It is rendered into the conversation.",
    "host": "The application the person is using, such as Cursor, Claude Desktop, or the MCP Inspector.",
    "transport": "How the bytes move. stdio means the host launched this process and talks on stdin and stdout.",
    "structured-output": "The return type of a tool. The model sees text. The client also receives the typed value.",
}


@mcp.resource("glossary://index", title="Glossary index")
def glossary_index() -> str:
    """Every term the glossary template can answer."""
    return "\n".join(f"{term}: {text}" for term, text in sorted(GLOSSARY.items()))


@mcp.resource("glossary://{term}", title="Glossary entry")
def glossary_entry(term: str) -> str:
    """One glossary entry. The {term} placeholder becomes the term argument."""
    key = term.strip().lower()
    if key not in GLOSSARY:
        known = ", ".join(sorted(GLOSSARY))
        return f"No entry for {term!r}. Try one of: {known}."
    return f"{key}: {GLOSSARY[key]}"


# =============================================================================
# Demo 5 — Prompts (~7 min)
# A prompt is the opposite of a tool: the user picks it, fills in a form,
# and the returned text is dropped into the chat. Return a str for one user
# message, or a list of UserMessage / AssistantMessage to seed a conversation.
# Open the Prompts tab in the Inspector, or the client's prompt menu.
# Arguments are strings. There is no JSON schema.
# =============================================================================


@mcp.prompt(title="Explain this tool")
def explain_tool(
    code: Annotated[str, Field(description="A Python function you might expose from an MCP server.")],
) -> str:
    """Decide whether a function should be a tool, a resource, or a prompt."""
    return (
        "Look at this function. Say whether it should be an MCP tool, a resource, "
        "or a prompt, and what the client will see: the name, the description, and "
        f"the arguments.\n\n{code}"
    )


@mcp.prompt(title="Debug my server")
def debug_server(
    error: Annotated[str, Field(description="The traceback or the error the client showed.")],
) -> list[Message]:
    """Start a debugging conversation from an error message."""
    return [
        UserMessage("My MCP server failed with this error:"),
        UserMessage(error),
        AssistantMessage(
            "I'll trace that. Which demo were you running, and did the Inspector or the host show the error?"
        ),
    ]


# =============================================================================
# Demo 6 — Progress (~8 min)
# Ask: "Run a countdown of 3 steps."
# ctx is injected because of its type hint, and it is omitted from the schema.
# It is the first parameter so `steps` can keep a default: Python requires
# parameters with defaults to come after parameters without them.
# report_progress is what a client can draw while the tool is still running.
# Call it on every step. If the client did not request progress, the SDK
# skips the notification. Log lines use the logging module and land on
# stderr, which the host captures.
# =============================================================================


@mcp.tool(
    title="Countdown",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
async def countdown(
    ctx: Context,
    steps: Annotated[int, Field(ge=1, le=10, description="How many one-second steps to report.")] = 3,
) -> str:
    """Count up once per second and report progress after each step."""
    for done in range(1, steps + 1):
        await asyncio.sleep(1)
        log.info("countdown %s/%s", done, steps)
        await ctx.report_progress(done, total=steps, message=f"Step {done} of {steps}")
    return f"Counted to {steps}."


# =============================================================================
# Demo 7 — A tiny app: tools + resources + a prompt (~12 min)
# Ask: "Save a note titled agenda that says start with echo, then list the notes."
# Then render the "Summarize the scratchpad" prompt from the menu.
# NOTES lives in this process. Saving the file often restarts the server
# and empties the pad. Say that out loud when it happens.
# Titles work best as a single word: the URI is note://agenda.
# Annotations are hints a client may use to ask before running delete_note.
# A client is free to ignore them.
# =============================================================================

NOTES: dict[str, str] = {}


@mcp.tool(
    title="Save note",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def save_note(
    title: Annotated[str, Field(description="Single-word title. It becomes the URI note://{title}.")],
    body: Annotated[str, Field(description="The text to remember.")],
) -> str:
    """Remember a note for the rest of this server process. Same title overwrites."""
    NOTES[title] = body
    return f"Saved {title!r} ({len(body)} characters)."


@mcp.tool(
    title="List notes",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def list_notes() -> list[str]:
    """Titles of notes saved in this process."""
    return sorted(NOTES)


@mcp.tool(
    title="Delete note",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def delete_note(title: str) -> str:
    """Delete one saved note."""
    if title not in NOTES:
        return f"No note named {title!r}."
    del NOTES[title]
    return f"Deleted {title!r}."


@mcp.resource("notes://all", title="All notes", mime_type="application/json")
def notes_catalog() -> str:
    """Every note saved during this server process, as JSON."""
    return json.dumps(NOTES, indent=2)


@mcp.resource("note://{title}", title="One note")
def read_note(title: str) -> str:
    """One saved note, addressed by its title."""
    if title not in NOTES:
        known = ", ".join(sorted(NOTES)) or "(none)"
        return f"No note named {title!r}. Saved titles: {known}."
    return NOTES[title]


@mcp.prompt(title="Summarize the scratchpad")
def summarize_notes() -> str:
    """Ask the model to summarize notes saved in this server."""
    titles = ", ".join(sorted(NOTES)) or "(none yet)"
    return (
        "Summarize the workshop scratchpad. Call list_notes, then read each note "
        "from note://{title}, or read notes://all. "
        f"Titles when this prompt was rendered: {titles}."
    )


# =============================================================================
# Your turn (~5 min)
# Uncomment this, save, and reconnect the server. Ask the model to call it.
# Then replace the body with a tool of your own.
# =============================================================================
#
# @mcp.tool(title="Shout")
# def shout(text: str) -> str:
#     """Return text in uppercase."""
#     return text.upper()


if __name__ == "__main__":
    # stdio is the local transport: the host launches this file and speaks
    # on stdin and stdout. With no host connected, this waits.
    mcp.run(transport="stdio")
