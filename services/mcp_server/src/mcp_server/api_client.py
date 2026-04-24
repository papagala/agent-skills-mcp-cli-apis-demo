from typing import Any

import httpx


class TasksApiClient:
    """Thin HTTP client around the Tasks API.

    Kept separate from the MCP tool surface so the tool layer can stay
    intent-focused while this module owns transport concerns.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {"status": status} if status else None
        response = await self._client.get("/tasks", params=params)
        response.raise_for_status()
        return response.json()

    async def create_task(
        self, title: str, assignee: str, priority: str
    ) -> dict[str, Any]:
        response = await self._client.post(
            "/tasks",
            json={"title": title, "assignee": assignee, "priority": priority},
        )
        response.raise_for_status()
        return response.json()

    async def update_task(self, task_id: int, **changes: Any) -> dict[str, Any]:
        response = await self._client.patch(f"/tasks/{task_id}", json=changes)
        response.raise_for_status()
        return response.json()
