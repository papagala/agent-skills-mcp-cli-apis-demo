from fastapi.testclient import TestClient
from tasks_api.main import app

client = TestClient(app)


def test_healthcheck_returns_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_then_complete_task():
    create = client.post(
        "/tasks",
        json={"title": "Write demo", "assignee": "dan", "priority": "high"},
    )
    assert create.status_code == 201
    task_id = create.json()["id"]

    complete = client.patch(
        f"/tasks/{task_id}", json={"status": "done", "note": "shipped"}
    )
    assert complete.status_code == 200
    body = complete.json()
    assert body["status"] == "done"
    assert body["note"] == "shipped"
