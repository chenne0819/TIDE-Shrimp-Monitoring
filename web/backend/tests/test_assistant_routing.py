"""Intent routing must not replace boards or lose computed follow-up facts."""
import asyncio
from copy import deepcopy
from time import monotonic, sleep
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.assistant import analytics, providers
from app.assistant.models import AssistantResult, Conversation, Message
from app.assistant.schemas import AgentDecision, AnalysisPlan
from app.assistant.service import AssistantService, computed_facts, context_facts, maximum_followup


PERIOD = {"id": "current", "label": "本月", "start_date": "2026-09-01", "end_date": "2026-09-20"}
STAT = {"method": "descriptive", "metric": "width_mm", "secondary_metric": None,
        "group_by": "period", "unit": "track"}
PLAN = {"title": "寬度摘要", "periods": [PERIOD], "ponds": ["A01"],
        "charts": [], "statistics": [STAT], "presentation": "answer"}
SUMMARY = {"period_id": "current", "label": "本月", "metrics": {
    "length_mm": {"count": 8, "min": 60, "max": 110.123456789, "mean": 80},
    "width_mm": {"count": 7, "min": 10, "max": 22.123456789, "mean": 18},
    "weight_g": {"count": 6, "min": 5, "max": 20.123456789, "mean": 12},
}}
BOARD = {"id": "computed-board", "title": "寬度摘要", "demo": False,
         "query": {"periods": [PERIOD], "ponds": ["A01"]},
         "charts": [], "statistics": [{"id": "stat-1", "method": "descriptive", "status": "completed"}],
         "descriptive_summary": [SUMMARY], "total_jobs": 2, "total_tracks": 8,
         "sources": [{"private_path": "NEVER_INCLUDE_PRIVATE_PATH"}], "warnings": [], "kpis": []}


class Provider:
    def __init__(self):
        self.decision = {"action": "analyze", "clarification": "", "plan": deepcopy(PLAN)}
        self.calls = []
        self.answer_failure = False
        self.block = None

    async def generate(self, prompt, schema):
        stage = "plan" if schema["title"] == "AgentDecision" else "answer"
        self.calls.append((stage, prompt))
        if self.block == stage:
            await asyncio.Event().wait()
        if stage == "plan":
            return deepcopy(self.decision)
        if self.answer_failure:
            raise providers.ProviderError("測試文字回覆失敗")
        return {"answer": "寬度最大值已依有效量測計算。", "followups": []}


@pytest.fixture
def routing(monkeypatch):
    provider = Provider()
    monkeypatch.setattr(providers, "provider_status", lambda: {"enabled": True, "provider": "test", "model": "fixture"})
    monkeypatch.setattr(providers, "make_provider", lambda: provider)
    monkeypatch.setattr(analytics, "get_catalog", lambda db, demo=False: {
        "today": "2026-09-20", "timezone": "Asia/Taipei", "available_ponds": ["A01"],
        "statistical_methods": ["descriptive", "pearson", "spearman", "welch_t", "anova"]})
    calls = []

    def analyze(self, plan, demo):
        # These values must already be committed before query execution begins.
        with self.sessions() as db:
            row = db.scalar(select(Message).where(Message.status == "querying"))
            stored = db.get(AssistantResult, row.id)
            assert stored.presentation == plan.presentation and stored.plan["statistics"]
            assert stored.facts == {}
        calls.append(plan)
        return deepcopy(BOARD)

    monkeypatch.setattr(AssistantService, "_analyze", analyze)
    return provider, calls


def create(client):
    return client.post("/api/assistant/conversations", json={}).json()["id"]


def submit(client, cid, question="請計算寬度摘要", key=None):
    response = client.post(f"/api/assistant/conversations/{cid}/messages", json={
        "message": question, "request_id": key or str(uuid4())})
    assert response.status_code == 202, response.text
    return response.json()


def wait(client, cid, predicate=lambda value: value["status"] not in {"planning", "querying", "answering"}):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        value = client.get(f"/api/assistant/conversations/{cid}").json()["messages"][-1]
        if predicate(value):
            return value
        sleep(.01)
    pytest.fail("routing did not reach expected state")


def seed(client, cid, *, legacy=False, all_dimensions=False):
    mid = str(uuid4())
    plan, board = deepcopy(PLAN), deepcopy(BOARD)
    plan["presentation"] = "board"
    if all_dimensions:
        plan["statistics"] = [{**STAT, "metric": metric} for metric in SUMMARY["metrics"]]
    if legacy:
        board.pop("descriptive_summary")
        board["charts"] = [{"description": "估計寬度", "series": []}]
    with client.app.state.sessions() as db:
        db.add(Message(id=mid, conversation_id=cid, request_id=str(uuid4()), position=0,
                       role="assistant", status="completed", content="不可信舊敘述最大99999", board=board))
        db.flush()
        if not legacy:
            db.add(AssistantResult(message_id=mid, presentation="board", plan=plan, facts=board))
        db.commit()
    return mid


def test_cached_width_maximum_never_queries_or_calls_model(client, routing):
    provider, queries = routing
    cid = create(client)
    previous_id = seed(client, cid)
    key = str(uuid4())
    assert submit(client, cid, "那最大呢？", key)["response_kind"] == "pending"
    result = wait(client, cid)
    assert result["status"] == "completed" and result["response_kind"] == "answer"
    assert result["board"] is None
    assert "22.123456789 mm" in result["content"] and "寬度" in result["content"]
    assert "99999" not in result["content"] and "長度" not in result["content"]
    assert not queries and not provider.calls
    assert [item["kind"] for item in result["activity"]] == ["context", "plan", "complete"]
    assert result["activity"][-1]["metadata"]["outcome"] == "cached_answer"
    assert submit(client, cid, "那最大呢？", key)["response_kind"] == "answer"
    with client.app.state.sessions() as db:
        assert db.get(Message, previous_id).board["id"] == BOARD["id"]
        assert db.get(Conversation, cid).active_message_id is None


def test_previous_three_dimensions_maxima_do_not_need_clarification(client, routing):
    cid = create(client)
    seed(client, cid, all_dimensions=True)
    submit(client, cid, "最大值是多少")
    result = wait(client, cid)
    assert all(label in result["content"] for label in ("長度", "寬度", "重量"))
    assert all(str(values["max"]) in result["content"] for values in SUMMARY["metrics"].values())
    assert routing[0].calls == [] and routing[1] == []


def test_cached_explicit_width_narrows_following_vague_maximum(client, routing):
    cid = create(client)
    seed(client, cid, all_dimensions=True)
    submit(client, cid, "寬度最大多少？")
    assert "估計寬度" in wait(client, cid)["content"]
    submit(client, cid, "那最大的呢？")
    content = wait(client, cid)["content"]
    assert "估計寬度" in content and "估計長度" not in content and "估計重量" not in content
    assert routing[0].calls == [] and routing[1] == []


def test_old_history_without_exact_summary_queries_only_and_retains_facts(client, routing):
    provider, queries = routing
    cid = create(client)
    seed(client, cid, legacy=True)
    submit(client, cid, "那最大呢")
    result = wait(client, cid)
    assert result["status"] == "completed" and result["board"] is None and result["response_kind"] == "answer"
    assert len(queries) == 1 and queries[0].presentation == "answer"
    assert queries[0].statistics[0].metric == "width_mm" and not queries[0].charts
    assert [stage for stage, _ in provider.calls] == ["answer"]
    assert [item["kind"] for item in result["activity"]] == ["context", "plan", "query", "answer", "complete"]
    assert result["activity"][-1]["metadata"]["outcome"] == "statistics_answer"
    with client.app.state.sessions() as db:
        saved = db.get(AssistantResult, result["id"])
        assert saved.facts["descriptive_summary"] == [SUMMARY]
        assert "sources" not in saved.facts and saved.plan["statistics"][0]["metric"] == "width_mm"
    # A following maximum uses the saved answer-only computation.
    submit(client, cid, "最大呢")
    assert "22.123456789" in wait(client, cid)["content"]
    assert len(queries) == len(provider.calls) == 1


@pytest.mark.parametrize("action", ["answer", "clarify"])
def test_model_direct_answers_and_clarifications_do_not_query(client, routing, action):
    provider, queries = routing
    provider.decision = {"action": action, "clarification": "寬度是偵測框短邊換算的估計值。", "plan": None}
    cid = create(client)
    submit(client, cid, "寬度代表什麼？")
    result = wait(client, cid)
    assert result["status"] == "completed" and result["response_kind"] == "answer" and result["board"] is None
    assert not queries and len(provider.calls) == 1
    assert "query" not in [item["kind"] for item in result["activity"]]
    assert result["activity"][-1]["metadata"]["outcome"] == ("clarification" if action == "clarify" else "cached_answer")


def test_statistics_only_board_is_an_analysis_and_has_no_invented_charts(client, routing):
    provider, queries = routing
    provider.decision["plan"]["presentation"] = "board"
    cid = create(client)
    submit(client, cid, "分析寬度基本統計")
    result = wait(client, cid)
    assert result["status"] == "completed" and result["response_kind"] == "analysis"
    assert result["board"]["charts"] == [] and result["board"]["statistics"]
    assert len(queries) == 1
    metadata = result["activity"][-1]["metadata"]
    assert metadata["chart_count"] == 0 and metadata["statistics_count"] == 1 and metadata["presentation"] == "board"
    assert "NEVER_INCLUDE_PRIVATE_PATH" not in provider.calls[-1][1]


@pytest.mark.parametrize("presentation,kind", [("answer", "answer"), ("board", "analysis")])
def test_confirmed_kind_is_visible_while_answer_running_and_cancel_preserves_facts(client, routing, presentation, kind):
    provider, _ = routing
    provider.decision["plan"]["presentation"] = presentation
    provider.block = "answer"
    cid = create(client)
    initial = submit(client, cid)
    assert initial["response_kind"] == "pending"
    running = wait(client, cid, lambda value: value["status"] == "answering")
    assert running["response_kind"] == kind
    stopped = client.post(f"/api/assistant/messages/{initial['id']}/cancel").json()
    assert stopped["status"] == "cancelled" and stopped["response_kind"] == kind
    assert (stopped["board"] is not None) == (presentation == "board")
    assert stopped["activity"][-1]["kind"] == "answer" and stopped["activity"][-1]["status"] == "cancelled"
    with client.app.state.sessions() as db:
        assert db.get(AssistantResult, initial["id"]).facts["descriptive_summary"] == [SUMMARY]


@pytest.mark.parametrize("presentation", ["answer", "board"])
def test_narrative_failure_keeps_computation_and_next_followup_uses_it(client, routing, presentation):
    provider, queries = routing
    provider.decision["plan"]["presentation"] = presentation
    provider.answer_failure = True
    cid = create(client)
    submit(client, cid)
    result = wait(client, cid)
    assert result["status"] == "failed"
    assert (result["board"] is not None) == (presentation == "board")
    provider.answer_failure = False
    submit(client, cid, "那最大呢")
    assert "22.123456789" in wait(client, cid)["content"]
    assert len(queries) == 1 and len(provider.calls) == 2


def test_timeout_before_classification_never_confirms_analysis_or_creates_result(client, routing):
    provider, queries = routing
    provider.block = "plan"
    client.app.state.assistant.timeout = .2
    cid = create(client)
    initial = submit(client, cid)
    result = wait(client, cid)
    assert initial["response_kind"] == "pending" and result["status"] == "failed"
    assert result["board"] is None and not queries
    with client.app.state.sessions() as db:
        assert db.get(AssistantResult, result["id"]) is None


def test_scope_changing_maximum_goes_to_planner():
    context = {"previous_plan": PLAN, "previous_dimensions": ["width_mm"],
               "trusted_results": [{"facts": BOARD}]}
    for question in ("今天最大呢", "B 池最大呢", "用圖表看最大", "各池的最大呢", "最大值做 t 檢定"):
        assert maximum_followup(question, context) is None


def test_context_bounds_statistics_without_losing_exact_descriptive_values():
    facts = deepcopy(BOARD)
    facts["statistics"] = [{"id": str(index)} for index in range(60)]
    trimmed = context_facts(facts)
    assert len(trimmed["statistics"]) == 12 and trimmed["statistics_total"] == 60 and trimmed["statistics_truncated"]
    assert trimmed["descriptive_summary"] == [SUMMARY] and "sources" not in trimmed


def test_aggregate_facts_bound_rows_but_keep_water_sex_and_trends_exclude_raw_scatter():
    board = deepcopy(BOARD)
    board["charts"] = [
        {"type": "donut", "data": [{"label": "clear", "value": 12}]},
        {"type": "stacked_bar", "data": [{"label": "A01", "male": 123, "female": 456}]},
        {"type": "line", "data": [{"date": str(index), "p0": index} for index in range(100)]},
        {"type": "scatter", "data": [{"label": "PRIVATE_TRACK", "x": 8, "y": 9}]},
    ]
    facts = computed_facts(board)
    assert facts["charts"][0]["data"][0]["value"] == 12
    assert facts["charts"][1]["data"][0]["male"] == 123
    assert len(facts["charts"][2]["data"]) == 80 and facts["charts"][2]["rows_truncated"]
    assert facts["charts"][2]["total_chart_rows"] == 100
    assert "data" not in facts["charts"][3] and "sources" not in facts


def test_water_aggregates_reach_narrator_and_followup_context(client, routing, monkeypatch):
    provider, _ = routing
    board = deepcopy(BOARD)
    board["charts"] = [{"type": "donut", "title": "水色影片數", "sample_count": 19,
                        "data": [{"label": "clear", "value": 12}, {"label": "turbid", "value": 7}]}]
    monkeypatch.setattr(AssistantService, "_analyze", lambda *_: board)
    cid = create(client)
    submit(client, cid, "水色分布如何")
    result = wait(client, cid)
    assert result["status"] == "completed"
    assert '"label":"clear","value":12' in provider.calls[-1][1]
    provider.decision = {"action": "answer", "clarification": "先前查詢有 12 段清澈影片。", "plan": None}
    submit(client, cid, "清澈有幾段？")
    assert wait(client, cid)["status"] == "completed"
    assert '"label":"clear","value":12' in provider.calls[-1][1]


def test_observed_two_ponds_not_selected_four_reach_narrator_and_followup(client, routing, monkeypatch):
    provider, _ = routing
    observed = {"count": 2, "labels": ["A-01", "C-03"], "labels_truncated": False}
    board = deepcopy(BOARD)
    board.update(observed_ponds=observed, total_jobs=2, total_tracks=12,
                 period_summaries=[{"id": "today", "label": "今天", "videos": 2, "tracks": 12, "observed_ponds": observed}])
    board["query"]["ponds"] = ["A-01", "B-02", "C-03", "D-04"]
    monkeypatch.setattr(AssistantService, "_analyze", lambda *_: board)
    cid = create(client)
    submit(client, cid, "今天長度平均是多少？")
    assert wait(client, cid)["status"] == "completed"
    narration = provider.calls[-1][1]
    encoded_coverage = '"observed_ponds":{"count":2,"labels":["A-01","C-03"],"labels_truncated":false}'
    assert narration.count(encoded_coverage) == 2
    assert "query.ponds is selected scope" in narration
    assert "top-level observed_ponds only for the entire query union" in narration
    provider.decision = {"action": "answer", "clarification": "今天實際有 2 個池別的已完成影片。", "plan": None}
    submit(client, cid, "今天有幾個池別有資料？")
    assert wait(client, cid)["status"] == "completed"
    planner = provider.calls[-1][1]
    assert planner.count(encoded_coverage) == 2
    assert "catalog.available_ponds is not observed coverage" in planner


def test_new_schema_accepts_old_charts_and_statistics_only_rejects_empty_or_hidden_queries():
    old = {"title": "舊圖", "periods": [PERIOD], "ponds": [], "charts": [{
        "type": "bar", "title": "寬度", "metric": "width_mm", "secondary_metric": None, "group_by": "period"}]}
    assert AnalysisPlan.model_validate(old).presentation == "board"
    assert AnalysisPlan.model_validate(PLAN).charts == []
    with pytest.raises(ValidationError):
        AnalysisPlan.model_validate({**PLAN, "statistics": []})
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({"action": "answer", "clarification": "hello", "plan": PLAN})
