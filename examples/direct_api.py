"""Path 1 from the article: Direct API calls.

Illustrates the M x N integration problem: every caller must learn the
endpoint shape, status semantics, and error handling on its own.

Run:
    uv run --with httpx python examples/direct_api.py
"""

import httpx

API_BASE_URL = "http://localhost:30080"


def main() -> None:
    with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
        created = (
            client.post(
                "/tasks",
                json={"title": "Review PR #42", "assignee": "erin", "priority": "high"},
            )
            .raise_for_status()
            .json()
        )

        completed = (
            client.patch(
                f"/tasks/{created['id']}",
                json={"status": "done", "note": "approved and merged"},
            )
            .raise_for_status()
            .json()
        )

    print(f"Created task {created['id']}: {created['title']}")
    print(f"Completed task {completed['id']} with note: {completed['note']}")


if __name__ == "__main__":
    main()
