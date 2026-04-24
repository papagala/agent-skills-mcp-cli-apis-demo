"""Path 3 from the article: MCP.

The agent connects to a remote MCP server and discovers intent-grouped
tools. Same backend, but the server speaks the agent's language.

Run:
    uv run --with mcp python examples/mcp_client.py
"""

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_SERVER_URL = "http://localhost:30090/mcp"


async def main() -> None:
    async with streamable_http_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Discovered intent-grouped tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description.splitlines()[0]}")

            created = await session.call_tool(
                "triage_new_task",
                arguments={
                    "title": "Investigate latency spike",
                    "assignee": "grace",
                    "priority": "high",
                },
            )
            new_task = json.loads(created.content[0].text)
            print(f"\nTriage result: id={new_task['id']} title={new_task['title']!r}")

            completed = await session.call_tool(
                "complete_task_with_note",
                arguments={
                    "task_id": new_task["id"],
                    "note": "rolled back the bad release",
                },
            )
            done_task = json.loads(completed.content[0].text)
            print(
                f"Completion result: status={done_task['status']} note={done_task['note']!r}"
            )


if __name__ == "__main__":
    asyncio.run(main())
