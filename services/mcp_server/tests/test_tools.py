import pytest
from mcp_server import server


class _StubApiClient:
    def __init__(self) -> None:
        self.update_calls: list[tuple[int, dict]] = []

    async def update_task(self, task_id: int, **changes):
        self.update_calls.append((task_id, changes))
        return {"id": task_id, "status": "done", "note": changes["note"]}


@pytest.mark.asyncio
async def test_complete_task_with_note_collapses_two_intents_into_one_call(monkeypatch):
    stub = _StubApiClient()
    monkeypatch.setattr(server, "_api_client", stub)

    result = await server.complete_task_with_note(task_id=42, note="shipped in v1.2")

    assert stub.update_calls == [(42, {"status": "done", "note": "shipped in v1.2"})]
    assert result["status"] == "done"
