"""MCP server exposing intent-grouped tools over the Tasks API.

Design lesson (from "Building agents that reach production systems with MCP"):
group tools around intent, not endpoints. We expose three intent tools
instead of mirroring the five HTTP endpoints of the underlying API.
"""

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp_server.api_client import TasksApiClient

TaskPriority = Literal["low", "medium", "high"]


def _build_api_client() -> TasksApiClient:
    base_url = os.environ.get("TASKS_API_BASE_URL", "http://localhost:8000")
    return TasksApiClient(base_url=base_url)


mcp = FastMCP(
    "tasks-mcp",
    instructions=(
        "Tools for triaging and resolving tasks in the Tasks production system."
    ),
    stateless_http=True,
    json_response=True,
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8000")),
)

_api_client = _build_api_client()


@mcp.tool()
async def list_open_tasks() -> list[dict]:
    """Return every task that is not yet done, ordered by API insertion order."""
    return await _api_client.list_tasks(status="open")


@mcp.tool()
async def triage_new_task(
    title: str, assignee: str, priority: TaskPriority = "medium"
) -> dict:
    """Create a task and return it ready for work.

    Intent-grouped: callers describe a triage outcome; the server handles
    the create-and-return round trip.
    """
    return await _api_client.create_task(
        title=title, assignee=assignee, priority=priority
    )


@mcp.tool()
async def complete_task_with_note(task_id: int, note: str) -> dict:
    """Mark a task as done and attach a closing note in a single call.

    Intent-grouped: replaces what would otherwise be two endpoint calls
    (set status, set note) with one tool that captures the user's goal.
    """
    return await _api_client.update_task(task_id, status="done", note=note)


def run() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run()
