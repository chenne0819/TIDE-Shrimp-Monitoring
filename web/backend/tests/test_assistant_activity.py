"""Execution activity is persisted observation, not generated model reasoning."""
import asyncio
from copy import deepcopy
from datetime import datetime
import json
import threading
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.assistant.models import Activity, Conversation, Message
from app.assistant.providers import ProviderError
from app.assistant.service import AssistantService
from app.database import utcnow
from app.main import create_app


PLAN = {"action": "analyze", "clarification": "", "plan": {
    "title": "兩期比較", "periods": [
        {"id": "current", "label": "本月", "start_date": "2026-09-01", "end_date": "2026-09-20"},
        {"id": "previous", "label": "上月", "start_date": "2026-08-01", "end_date": "2026-08-20"},
    ], "ponds": ["A01"], "charts": [
        {"type": "histogram", "title": "長度分布", "metric": "length_mm", "secondary_metric": None, "group_by": "period"},
        {"type": "scatter", "title": "長寬關係", "metric": "length_mm", "secondary_metric": "width_mm", "group_by": "pond"},
    ],
}}
BOARD = {"id": "board-fixture", "title": "兩期比較", "demo": False,
         "query": {"periods": PLAN["plan"]["periods"], "ponds": ["A01"]},
         "total_jobs": 2, "total_tracks": 12, "period_summaries": [],
         "charts": [
             {"type": "histogram", "title": "長度分布", "sample_count": 11, "data": []},
             {"type": "scatter", "title": "長寬關係", "sample_count": 9, "data": []},
         ], "sources": [], "warnings": []}


class Provider:
    def __init__(self):
        self.block = None
        self.failure = None
        self.clarify = False
        self.bad_plan = False
        self.release = threading.Event()
        self.started = set()
        self.cancelled = set()

    async def generate(self, prompt, schema):
        stage = "plan" if schema["title"] == "AgentDecision" else "answer"
        self.started.add(stage)
        if stage == self.block:
            try:
                while not self.release.is_set():
                    await asyncio.sleep(.005)
            except asyncio.CancelledError:
                self.cancelled.add(stage)
                raise
        if stage == self.failure:
            raise ProviderError("測試模型未完成回覆")
        if stage == "plan":
            if self.clarify:
                return {"action": "clarify", "clarification": "請選擇要比較的日期。", "plan": None}
            plan = deepcopy(PLAN)
            if self.bad_plan:
                plan["plan"]["sql"] = "NEVER_EXECUTE_PRIVATE_TEXT"
            return plan
        return {"answer": "模型回覆內容", "followups": ["再看重量"]}


@pytest.fixture
def activity_provider(monkeypatch):
    from app.assistant import providers
    provider = Provider()
    monkeypatch.setattr(providers, "provider_status", lambda: {
        "enabled": True, "provider": "test", "model": "fixture", "reason": ""})
    monkeypatch.setattr(providers, "make_provider", lambda: provider)
    monkeypatch.setattr(AssistantService, "_context", lambda self, mid: {
        "catalog": {"today": "2026-09-20", "timezone": "Asia/Taipei", "available_ponds": ["A01", "B02"],
                    "earliest_date": "2026-07-23", "latest_date": "2026-09-20"},
        "demo": False, "history": [{"role": "user", "content": "PRIVATE_HISTORY_TEXT"}], "previous_query": None})
    monkeypatch.setattr(AssistantService, "_analyze", lambda self, plan, demo: deepcopy(BOARD))
    return provider


def create(client):
    response = client.post("/api/assistant/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


def submit(client, cid, request_id=None):
    response = client.post(f"/api/assistant/conversations/{cid}/messages", json={
        "message": "PRIVATE_USER_QUESTION 比較這兩期", "request_id": request_id or str(uuid4())})
    assert response.status_code == 202
    return response.json()


def wait_message(client, cid, predicate):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        result = client.get(f"/api/assistant/conversations/{cid}").json()["messages"][-1]
        if predicate(result):
            return result
        sleep(.01)
    pytest.fail("activity did not reach the expected state")


def finish(client, cid, status="completed"):
    return wait_message(client, cid, lambda result: result["status"] == status)


def test_six_actual_steps_are_ordered_persisted_and_have_computed_summary(client, activity_provider):
    cid = create(client)
    key = str(uuid4())
    response = submit(client, cid, key)
    assert response["activity"] == []  # Queued is not a fabricated started phase.
    result = finish(client, cid)
    activity = result["activity"]
    assert [step["kind"] for step in activity] == ["context", "plan", "query", "charts", "answer", "complete"]
    assert all(step["status"] == "completed" for step in activity)
    for step in activity:
        started, finished = datetime.fromisoformat(step["started_at"]), datetime.fromisoformat(step["finished_at"])
        assert started.tzinfo is not None and started <= finished
        assert set(step) == {"id", "kind", "label", "status", "started_at", "finished_at", "detail", "metadata"}
    assert activity[1]["metadata"]["periods"] == PLAN["plan"]["periods"]
    assert activity[1]["metadata"]["ponds"] == ["A01"]
    assert activity[1]["metadata"]["metrics"] == ["length_mm", "width_mm"]
    assert activity[1]["metadata"]["chart_types"] == ["histogram", "scatter"]
    assert activity[3]["metadata"]["chart_samples"][1]["sample_count"] == 9
    assert activity[-1]["metadata"]["total_jobs"] == 2
    assert activity[-1]["metadata"]["total_tracks"] == 12
    assert activity[-1]["metadata"]["chart_count"] == 2
    assert "2 段影片" in activity[-1]["detail"] and "12 個追蹤 ID" in activity[-1]["detail"]
    assert "PRIVATE_" not in json.dumps(activity)
    assert result["content"] == "模型回覆內容"  # Summary came from code, not this text.
    again = submit(client, cid, key)
    assert again["activity"] == activity
    with client.app.state.sessions() as db:
        rows = list(db.scalars(select(Activity).where(Activity.message_id == result["id"]).order_by(Activity.position)))
        assert [row.id for row in rows] == [step["id"] for step in activity]


@pytest.mark.parametrize("phase,expected_kinds", [
    ("plan", ["context", "plan"]),
    ("answer", ["context", "plan", "query", "charts", "answer"]),
])
def test_running_steps_are_visible_and_cancel_only_marks_started_work(client, activity_provider, phase, expected_kinds):
    activity_provider.block = phase
    cid = create(client)
    mid = submit(client, cid)["id"]
    result = wait_message(client, cid, lambda value: value["activity"] and value["activity"][-1]["kind"] == phase)
    assert [step["kind"] for step in result["activity"]] == expected_kinds
    assert result["activity"][-1]["status"] == "running"
    assert result["activity"][-1]["finished_at"] is None
    response = client.post(f"/api/assistant/messages/{mid}/cancel")
    assert response.status_code == 200
    stopped = response.json()
    assert stopped["status"] == "cancelled"
    assert [step["kind"] for step in stopped["activity"]] == expected_kinds
    assert stopped["activity"][-1]["status"] == "cancelled"
    assert stopped["activity"][-1]["finished_at"] is not None
    assert all(step["status"] == "completed" for step in stopped["activity"][:-1])
    assert (stopped["board"] is not None) == (phase == "answer")


def test_real_query_thread_publishes_running_before_results(client, activity_provider, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def analyze(self, plan, demo):
        started.set()
        assert release.wait(timeout=4)
        return deepcopy(BOARD)

    monkeypatch.setattr(AssistantService, "_analyze", analyze)
    cid = create(client)
    submit(client, cid)
    try:
        result = wait_message(client, cid, lambda value: value["status"] == "querying")
        assert started.wait(timeout=1)
        assert result["board"] is None
        assert result["response_kind"] == "analysis"
        assert [step["kind"] for step in result["activity"]] == ["context", "plan", "query"]
        assert result["activity"][-1]["status"] == "running"
    finally:
        release.set()
    assert finish(client, cid)["activity"][-1]["kind"] == "complete"


@pytest.mark.parametrize("failure", ["plan", "bad_plan", "query", "answer", "timeout"])
def test_failure_marks_only_unfinished_step_and_preserves_prior_results(client, activity_provider, monkeypatch, failure):
    if failure == "bad_plan":
        activity_provider.bad_plan = True
    elif failure == "query":
        def reject_query(*args):
            raise ValueError("bounded query rejected")
        monkeypatch.setattr(AssistantService, "_analyze", reject_query)
    elif failure == "timeout":
        activity_provider.block = "plan"
        client.app.state.assistant.timeout = 1
    else:
        activity_provider.failure = failure
    cid = create(client)
    submit(client, cid)
    result = finish(client, cid, "failed")
    failed = result["activity"][-1]
    if failure == "timeout":
        # Slow storage can consume the deadline before the model begins. Assert
        # the observed step ends honestly, not a particular fsync speed.
        assert failed["kind"] in {"context", "plan"}
        if "plan" in activity_provider.started:
            assert "plan" in activity_provider.cancelled
        assert client.app.state.assistant.has_capacity()
    else:
        assert failed["kind"] == ("query" if failure == "query" else "answer" if failure == "answer" else "plan")
    assert failed["status"] == "failed" and failed["finished_at"] is not None
    assert all(step["status"] == "completed" for step in result["activity"][:-1])
    assert not any(step["kind"] == "complete" for step in result["activity"])
    assert (result["board"] is not None) == (failure == "answer")
    assert "NEVER_EXECUTE" not in json.dumps(result["activity"])


def test_clarification_does_not_claim_data_was_queried(client, activity_provider, monkeypatch):
    activity_provider.clarify = True
    monkeypatch.setattr(AssistantService, "_analyze", lambda *_: pytest.fail("clarification must not query"))
    cid = create(client)
    submit(client, cid)
    result = finish(client, cid)
    assert [step["kind"] for step in result["activity"]] == ["context", "plan", "complete"]
    summary = result["activity"][-1]
    assert summary["metadata"]["outcome"] == "clarification"
    assert summary["metadata"]["total_jobs"] == summary["metadata"]["chart_count"] == 0
    assert "尚未查詢" in summary["detail"]
    assert result["board"] is None


def test_context_failure_does_not_invent_planning_or_query_work(client, activity_provider, monkeypatch):
    def unavailable(*args):
        raise ValueError("private data catalog error")
    monkeypatch.setattr(AssistantService, "_context", unavailable)
    cid = create(client)
    submit(client, cid)
    result = finish(client, cid, "failed")
    assert [step["kind"] for step in result["activity"]] == ["context"]
    assert result["activity"][0]["status"] == "failed"
    assert "private data" not in json.dumps(result["activity"])


@pytest.mark.parametrize("demo", [False, True])
def test_zero_result_summary_uses_actual_counts_and_identifies_demo(client, activity_provider, monkeypatch, demo):
    monkeypatch.setattr(AssistantService, "_context", lambda *_: {
        "catalog": {}, "demo": demo, "history": [], "previous_query": None})
    empty = deepcopy(BOARD)
    empty.update(total_jobs=0, total_tracks=0, demo=demo)
    for chart in empty["charts"]:
        chart["sample_count"] = 0
    monkeypatch.setattr(AssistantService, "_analyze", lambda *_: empty)
    cid = create(client)
    submit(client, cid)
    result = finish(client, cid)
    summary = result["activity"][-1]
    assert summary["metadata"]["total_jobs"] == summary["metadata"]["total_tracks"] == 0
    assert summary["metadata"]["demo"] is demo
    assert "0 段影片" in summary["detail"]
    assert summary["detail"].startswith("示範分析：") is demo


def test_restart_closes_only_real_running_activity_and_old_messages_stay_empty(settings):
    app = create_app(settings)
    cid, mid, old_mid = str(uuid4()), str(uuid4()), str(uuid4())
    with TestClient(app):
        with app.state.sessions() as db:
            db.add(Conversation(id=cid, active_message_id=mid))
            db.flush()
            db.add_all([
                Message(id=old_mid, conversation_id=cid, request_id=str(uuid4()), position=0,
                        role="assistant", status="completed", content="舊訊息", board=BOARD),
                Message(id=mid, conversation_id=cid, request_id=str(uuid4()), position=1,
                        role="assistant", status="querying", content=""),
            ])
            db.flush()
            stamp = utcnow()
            db.add_all([
                Activity(id=str(uuid4()), message_id=mid, position=0, kind="context", label="讀取資料範圍",
                         status="completed", started_at=stamp, finished_at=stamp, detail="已讀取"),
                Activity(id=str(uuid4()), message_id=mid, position=2, kind="query", label="查詢資料並計算統計",
                         status="running", started_at=stamp, detail="正在查詢"),
            ])
            db.commit()
    # A second app lifespan exercises additive create_all + interrupted recovery.
    second = create_app(settings)
    with TestClient(second) as client:
        messages = client.get(f"/api/assistant/conversations/{cid}").json()["messages"]
        assert messages[0]["activity"] == []
        assert messages[0]["content"] == "舊訊息" and messages[0]["board"] == BOARD
        assert messages[1]["status"] == "failed"
        assert [step["status"] for step in messages[1]["activity"]] == ["completed", "failed"]
        assert messages[1]["activity"][0]["detail"] == "已讀取"
        assert "重新啟動" in messages[1]["activity"][1]["detail"]
        assert messages[1]["activity"][1]["finished_at"] is not None


def test_conversation_activity_uses_one_batch_query(client, activity_provider):
    cid = create(client)
    submit(client, cid)
    finish(client, cid)
    submit(client, cid)
    finish(client, cid)
    statements = []
    with client.app.state.sessions() as db:
        engine = db.get_bind()

    def record(connection, cursor, statement, parameters, context, executemany):
        if "assistant_activity" in statement and statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        messages = client.get(f"/api/assistant/conversations/{cid}").json()["messages"]
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 1
    assert [len(message["activity"]) for message in messages] == [0, 6, 0, 6]
