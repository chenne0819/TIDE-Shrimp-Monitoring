"""Exercise the configured model through the real API; consumes model quota.

Creates a saved conversation. --demo uses synthetic measurements, never inserts
video jobs. Omit --demo to ask about the application's actual completed jobs.
"""
import argparse
import json
import time
from uuid import uuid4

import httpx


def verify_activity(message):
    """Check saved application events, not model-written claims of completion."""
    steps = message.get("activity", [])
    board = message.get("board")
    kinds = [step["kind"] for step in steps]
    assert kinds[:2] == ["context", "plan"] and kinds[-1] == "complete"
    assert len(kinds) == len(set(kinds)), "Duplicate execution steps"
    order = ["context", "plan", "query", "charts", "answer", "complete"]
    assert kinds == sorted(kinds, key=order.index), "Out-of-order execution steps"
    if board:
        assert kinds == order, "Visual analysis must record query, charts and narrative"
    else:
        assert "charts" not in kinds, "Text answers must not claim to have redrawn charts"
    assert all(step["status"] == "completed" and step["finished_at"] for step in steps)
    summary = steps[-1]["metadata"]
    if board:
        assert summary["total_jobs"] == board["total_jobs"]
        assert summary["total_tracks"] == board["total_tracks"]
    assert summary["chart_count"] == (len(board["charts"]) if board else 0)
    print(steps[-1]["detail"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--question", action="append", required=True)
    parser.add_argument("--output", help="Optional local JSON result path")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=15) as client:
        session = client.get("/api/session")
        session.raise_for_status()
        client.headers["X-Tide-CSRF"] = session.json()["csrf_token"]
        response = client.post("/api/assistant/conversations", json={"demo": args.demo})
        response.raise_for_status()
        conversation = response.json()
        for question in args.question:
            response = client.post(f"/api/assistant/conversations/{conversation['id']}/messages",
                                   json={"message": question, "request_id": str(uuid4())})
            response.raise_for_status()
            message_id = response.json()["id"]
            deadline = time.monotonic() + 300
            previous_status = None
            while True:
                response = client.get(f"/api/assistant/conversations/{conversation['id']}")
                response.raise_for_status()
                conversation = response.json()
                message = next(item for item in conversation["messages"] if item["id"] == message_id)
                if message["status"] != previous_status:
                    print(message["status"], flush=True)
                    previous_status = message["status"]
                if message["status"] not in {"planning", "querying", "answering"}:
                    break
                if time.monotonic() > deadline:
                    client.post(f"/api/assistant/messages/{message_id}/cancel").raise_for_status()
                    raise RuntimeError("Smoke test deadline reached; cancellation requested")
                time.sleep(1)
            if message["status"] != "completed":
                raise RuntimeError(message.get("error") or message["status"])
            verify_activity(message)
            board = message.get("board")
            if board:
                print(json.dumps({"title": board["title"], "query": board["query"],
                    "charts": [chart["type"] for chart in board["charts"]],
                    "jobs": board["total_jobs"], "tracks": board["total_tracks"],
                    "kpis": board["kpis"]}, ensure_ascii=False), flush=True)
            print(message["content"], flush=True)
        if args.output:
            from pathlib import Path
            Path(args.output).write_text(json.dumps(conversation, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Conversation: {conversation['id']}", flush=True)


if __name__ == "__main__":
    main()
