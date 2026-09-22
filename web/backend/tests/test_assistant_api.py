import asyncio
from copy import deepcopy
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.assistant.models import Conversation, Message
from app.assistant.service import AssistantService
from app.database import Job
from app.main import create_app
from test_request_security import raw_request, request_chunk


PLAN = {"action": "analyze", "clarification": "", "plan": {
    "title": "今日量測", "periods": [{"id": "current", "label": "今天", "start_date": "2026-09-20", "end_date": "2026-09-20"}],
    "ponds": [], "charts": [{"type": "histogram", "title": "長度分布", "metric": "length_mm", "secondary_metric": None, "group_by": "period"}],
}}
BOARD = {"id": "board-1", "title": "今日量測", "demo": False, "timezone": "Asia/Taipei",
         "generated_at": "2026-09-20T00:00:00Z", "query": {"periods": PLAN["plan"]["periods"], "ponds": [], "aggregation": "有效個體平均"},
         "kpis": [{"label": "估計長度", "value": 82.5, "unit": "mm", "previous_value": None, "delta_pct": None}],
         "charts": [], "warnings": ["估計值"], "sources": [], "total_jobs": 1, "total_tracks": 2, "period_summaries": []}


class FakeProvider:
    def __init__(self, *, wait=False, bad_plan=False, answer_error=False):
        self.calls = []
        self.wait = wait
        self.bad_plan = bad_plan
        self.answer_error = answer_error
        self.cancelled = False

    async def generate(self, prompt, schema):
        self.calls.append(prompt)
        if self.wait:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if schema["title"] == "AgentDecision":
            decision = deepcopy(PLAN)
            if self.bad_plan:
                decision["plan"]["sql"] = "DROP TABLE jobs"
            return decision
        if self.answer_error:
            from app.assistant.providers import ProviderError
            raise ProviderError("模型暫時無法回覆")
        assert '82.5' in prompt
        return {"answer": "今天平均估計長度為 82.5 mm，共 2 個有效樣本。", "followups": ["改看寬度分布"]}


@pytest.fixture
def provider(monkeypatch):
    import app.assistant.providers as module
    fake = FakeProvider()
    monkeypatch.setattr(module, "provider_status", lambda: {"enabled": True, "provider": "test", "model": "fixture", "reason": None})
    monkeypatch.setattr(module, "make_provider", lambda: fake)
    monkeypatch.setattr(AssistantService, "_context", lambda self, mid: {
        "catalog": {"today": "2026-09-20", "timezone": "Asia/Taipei", "available_ponds": []},
        "demo": False, "history": [], "previous_query": None})
    monkeypatch.setattr(AssistantService, "_analyze", lambda self, plan, demo: deepcopy(BOARD))
    return fake


def create(client, demo=False):
    response = client.post("/api/assistant/conversations", json={"demo": demo})
    assert response.status_code == 201
    return response.json()["id"]


def submit(client, cid, question="今天測量結果如何？", request_id=None):
    return client.post(f"/api/assistant/conversations/{cid}/messages", json={"message": question, "request_id": request_id or str(uuid4())})


def wait_result(client, cid, expected="completed"):
    end = monotonic() + 5
    while monotonic() < end:
        result = client.get(f"/api/assistant/conversations/{cid}").json()["messages"][-1]
        if result["status"] not in {"planning", "querying", "answering"}:
            assert result["status"] == expected, result
            return result
        sleep(0.01)
    pytest.fail("analysis did not settle")


def test_chat_persists_grounded_board_and_does_not_modify_analysis_jobs(client, provider):
    cid = create(client)
    response = submit(client, cid)
    assert response.status_code == 202
    result = wait_result(client, cid)
    assert result["board"] == BOARD
    assert "82.5" in result["content"]
    assert result["followups"] == ["改看寬度分布"]
    assert len(provider.calls) == 2
    with client.app.state.sessions() as db:
        assert db.get(Conversation, cid).active_message_id is None
        assert db.scalar(select(func.count()).select_from(Job)) == 0
    detail = client.get(f"/api/assistant/conversations/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


def test_idempotent_requests_do_not_launch_a_second_model_run(client, provider):
    cid = create(client)
    key = str(uuid4())
    first = submit(client, cid, request_id=key)
    wait_result(client, cid)
    again = submit(client, cid, request_id=key)
    assert first.json()["id"] == again.json()["id"]
    assert len(provider.calls) == 2
    assert submit(client, cid, question="different question", request_id=key).status_code == 409


def test_cancel_interrupts_provider_and_releases_conversation(client, provider):
    provider.wait = True
    cid = create(client)
    message = submit(client, cid).json()
    assert submit(client, cid).status_code == 409
    end = monotonic() + 5
    while not provider.calls and monotonic() < end:
        sleep(0.01)
    response = client.post(f"/api/assistant/messages/{message['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert provider.cancelled
    provider.wait = False
    assert submit(client, cid).status_code == 202
    wait_result(client, cid)


def test_disabled_provider_never_invents_an_answer(client, provider, monkeypatch):
    import app.assistant.providers as module
    monkeypatch.setattr(module, "provider_status", lambda: {"enabled": False, "reason": "請設定 AI provider"})
    cid = create(client)
    assert submit(client, cid).status_code == 503
    assert client.get(f"/api/assistant/conversations/{cid}").json()["messages"] == []
    assert provider.calls == []


def test_invalid_model_plan_is_rejected_before_data_query(client, provider, monkeypatch):
    provider.bad_plan = True
    monkeypatch.setattr(AssistantService, "_analyze", lambda *_: pytest.fail("unvalidated query ran"))
    cid = create(client)
    assert submit(client, cid).status_code == 202
    result = wait_result(client, cid, "failed")
    assert result["board"] is None
    assert len(provider.calls) == 1


def test_narrative_failure_preserves_successful_chart_results(client, provider):
    provider.answer_error = True
    cid = create(client)
    submit(client, cid)
    result = wait_result(client, cid, "failed")
    assert result["board"] == BOARD
    assert "已完成" in result["error"]
    assert result["response_kind"] == "analysis"


def test_restart_marks_old_active_messages_failed(settings):
    app = create_app(settings)
    with TestClient(app):
        with app.state.sessions() as db:
            cid, mid = str(uuid4()), str(uuid4())
            db.add(Conversation(id=cid, title="interrupted", demo=False, active_message_id=mid))
            db.flush()
            db.add(Message(id=mid, conversation_id=cid, request_id=str(uuid4()), position=0, role="assistant", content="", status="answering", board=BOARD))
            db.commit()
    second = create_app(settings)
    with TestClient(second) as client:
        result = client.get(f"/api/assistant/conversations/{cid}").json()["messages"][0]
        assert result["status"] == "failed"
        assert result["board"] == BOARD
        assert "重新啟動" in result["error"]


def test_real_and_demo_conversation_lists_are_separate(client):
    real, demo = create(client), create(client, True)
    assert [x["id"] for x in client.get("/api/assistant/conversations").json()["items"]] == [real]
    assert [x["id"] for x in client.get("/api/assistant/conversations?demo=true").json()["items"]] == [demo]


def test_assistant_rejects_csrf_origin_extra_fields_and_oversize_before_work(client, provider):
    cid = create(client)
    token = client.headers["X-Tide-CSRF"]
    path = f"/api/assistant/conversations/{cid}/messages"
    for headers in [[("X-Tide-CSRF", "wrong")], [("X-Tide-CSRF", token), ("Origin", "https://evil.example")]]:
        code, reads, _ = raw_request(client.app, path=path, headers=headers, messages=[AssertionError("must not read")])
        assert code == 403 and reads == 0
    code, reads, _ = raw_request(client.app, path=path,
        headers=[("X-Tide-CSRF", token), ("Content-Length", "20000")], messages=[AssertionError("must not read")])
    assert code == 413 and reads == 0
    code, _, _ = raw_request(client.app, path=path, headers=[("X-Tide-CSRF", token), ("Content-Type", "application/json")],
        messages=[request_chunk(b'{"message":"' + b'a' * 17000, False)])
    assert code == 413
    assert client.post(path, json={"message": "x", "request_id": str(uuid4()), "sql": "select *"}).status_code == 422
    assert submit(client, cid, question=" ").status_code == 422
    assert submit(client, cid, question="x" * 2001).status_code == 422
    assert provider.calls == []


def test_concurrency_limit_and_timeout_release_slots(client, provider):
    provider.wait = True
    service = client.app.state.assistant
    service.max_concurrent = 1
    service.timeout = 2
    first, second = create(client), create(client)
    assert submit(client, first).status_code == 202
    assert submit(client, second).status_code == 429
    result = wait_result(client, first, "failed")
    assert "時間限制" in result["error"]
    assert provider.cancelled
    provider.wait = False
    # The next run verifies released capacity, not another short deadline.
    service.timeout = 30
    assert submit(client, second).status_code == 202
    wait_result(client, second)


def test_messages_remain_ordered_when_clock_timestamps_are_identical(client, provider):
    from app.database import utcnow
    cid = create(client)
    submit(client, cid)
    wait_result(client, cid)
    submit(client, cid, question="改看上個月")
    wait_result(client, cid)
    with client.app.state.sessions() as db:
        timestamp = utcnow()
        for message in db.scalars(select(Message).where(Message.conversation_id == cid)):
            message.created_at = timestamp
        db.commit()
    response = client.get(f"/api/assistant/conversations/{cid}")
    assert response.headers["Cache-Control"] == "no-store"
    messages = response.json()["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"] == "改看上個月"
