from copy import deepcopy

import pytest

from app.assistant import analytics
from app.assistant.models import AssistantResult
from app.assistant.presentation import overview_presentation, prefers_text_only, wants_overview
from app.assistant.schemas import AgentDecision
from app.assistant.service import AssistantService
from test_assistant_routing import PLAN, create, routing, submit, wait


QUESTION = "今天的量測結果怎麼樣？"


def overview_plan():
    plan = deepcopy(PLAN)
    plan.update(title="今天量測結果", ponds=[], periods=[{
        "id": "today", "label": "今天", "start_date": "2026-09-20", "end_date": "2026-09-20"}],
        statistics=[{**plan["statistics"][0], "metric": metric} for metric in ("length_mm", "width_mm", "weight_g")])
    return plan


@pytest.mark.parametrize("question", [QUESTION, "今天的測量結果如何", "這幾天的分析怎麼樣", "整理這個月的量測概況", "這個月跟上個月的成長狀況", "比較兩池的量測結果", "本月的整體結果"])
def test_general_measurement_questions_request_a_visible_overview(question):
    assert wants_overview(question)


@pytest.mark.parametrize("question", ["最大的是多少", "今天最大寬度是多少？", "今天寬度的中位數", "解釋剛才的量測結果", "這個結果代表什麼？", "為什麼今天量測結果變這樣", QUESTION + "只要文字", QUESTION + "不要畫圖", QUESTION + "不用新增圖表", "今天分析概況僅用文字回答"])
def test_single_numbers_explanations_and_explicit_text_requests_are_not_overviews(question):
    assert not wants_overview(question)


@pytest.mark.parametrize("question", [
    "請用文字回答今天的量測結果怎麼樣？",
    "請以文字說明今天的量測結果怎麼樣？",
    "今天的量測結果怎麼樣？請用純文字回答。",
    "分析報告的寬度單位是什麼？",
    "今天量測結果的平均寬度如何？",
])
def test_text_phrasing_unit_explanations_and_scalar_wording_do_not_trigger_replanning(question):
    assert not wants_overview(question)
    decision = AgentDecision(action="analyze", plan=overview_plan())
    assert overview_presentation(decision, question) is decision
    assert decision.plan.presentation == "answer" and not decision.plan.charts


def test_descriptive_only_overview_gets_three_charts_without_changing_dates_or_ponds():
    original = AgentDecision(action="analyze", plan=overview_plan())
    result = overview_presentation(original, QUESTION)
    assert original.plan.presentation == "answer" and not original.plan.charts
    assert result.plan.presentation == "board"
    assert result.plan.periods == original.plan.periods and result.plan.ponds == original.plan.ponds
    assert [(c.type, c.metric, c.group_by) for c in result.plan.charts] == [
        ("histogram", metric, "period") for metric in ("length_mm", "width_mm", "weight_g")]
    assert result.plan.statistics == original.plan.statistics


def test_period_overviews_use_trends_or_period_comparisons():
    plan = overview_plan()
    plan["periods"][0]["start_date"] = "2026-09-01"
    decision = AgentDecision(action="analyze", plan=plan)
    assert all(c.type == "line" and c.group_by == "day" for c in overview_presentation(decision, "本月量測結果如何").plan.charts)
    plan["periods"].append({"id":"previous", "label":"上月", "start_date":"2026-08-01", "end_date":"2026-08-31"})
    decision = AgentDecision(action="analyze", plan=plan)
    assert all(c.type == "bar" and c.group_by == "period" for c in overview_presentation(decision, "本月與上月成長狀況").plan.charts)


@pytest.mark.parametrize("start_date", ["2026-09-20", "2026-09-01"])
def test_single_period_pond_overview_preserves_validated_grouping_and_scope(start_date):
    plan = overview_plan()
    plan["ponds"] = ["A01", "B02"]
    plan["periods"][0]["start_date"] = start_date
    for request in plan["statistics"]:
        request["group_by"] = "pond"
    decision = AgentDecision(action="analyze", plan=plan)
    result = overview_presentation(decision, "今天各池的量測結果如何？")
    assert result.plan.presentation == "board" and result.plan.charts
    assert all(chart.type == "bar" and chart.group_by == "pond" for chart in result.plan.charts)
    assert result.plan.periods == decision.plan.periods
    assert result.plan.ponds == ["A01", "B02"]
    assert result.plan.statistics == decision.plan.statistics
    assert decision.plan.presentation == "answer" and not decision.plan.charts


def test_two_period_pond_statistics_keep_pond_categories_and_period_series():
    plan = overview_plan()
    plan["ponds"] = ["A01", "B02"]
    plan["periods"].append({"id": "previous", "label": "上期", "start_date": "2026-09-19", "end_date": "2026-09-19"})
    for request in plan["statistics"]:
        request["group_by"] = "pond"
    decision = AgentDecision(action="analyze", plan=plan)
    result = overview_presentation(decision, "比較兩期各池的量測結果")
    assert result.plan.charts and all(chart.type == "bar" and chart.group_by == "pond" for chart in result.plan.charts)
    assert result.plan.periods == decision.plan.periods and result.plan.ponds == decision.plan.ponds
    assert result.plan.statistics == decision.plan.statistics


def test_two_period_pond_fallback_renders_both_ponds_and_both_periods(client):
    from test_assistant_analytics import add_job

    plan = overview_plan()
    plan["ponds"] = ["A01", "B02"]
    plan["periods"].append({"id": "previous", "label": "上期", "start_date": "2026-09-19", "end_date": "2026-09-19"})
    for request in plan["statistics"]:
        request["group_by"] = "pond"
    result = overview_presentation(AgentDecision(action="analyze", plan=plan), "比較兩期各池的量測結果")
    with client.app.state.sessions() as db:
        for day, pond, length in [(20, "A01", 100), (20, "B02", 200), (19, "A01", 80), (19, "B02", 160)]:
            add_job(db, f"2026-09-{day}T10:00:00+08:00", [{"length_mm": length}], pond=pond)
        board = analytics.build_board(db, result.plan)
    length = next(chart for chart in board["charts"] if "長度" in chart["title"])
    assert length["data"] == [{"label": "A01", "p0": 100, "p1": 80}, {"label": "B02", "p0": 200, "p1": 160}]


@pytest.mark.parametrize("question", [
    "今天量測結果如何？只要文字不用圖。", "請用文字回答今天量測結果。", "清澈的影片有幾段？不要新增圖表。",
])
def test_explicit_text_preference_overrides_a_model_board_misroute(question):
    plan = overview_plan()
    plan["presentation"] = "board"
    plan["charts"] = [{"type": "donut", "title": "水色", "metric": "video_count", "secondary_metric": None, "group_by": "water"}]
    decision = AgentDecision(action="analyze", plan=plan)
    result = overview_presentation(decision, question)
    assert result.plan.presentation == "answer"
    assert decision.plan.presentation == "board"
    assert result.plan.charts == decision.plan.charts
    assert result.plan.periods == decision.plan.periods


@pytest.mark.parametrize("question", [
    "不要只用文字，請給我量測總覽圖。", "不要用文字回答，請給總覽圖。", "不需要純文字，請呈現量測概況。",
])
def test_negated_text_only_preference_still_allows_a_visual_overview(question):
    assert not prefers_text_only(question)
    assert wants_overview(question)
    result = overview_presentation(AgentDecision(action="analyze", plan=overview_plan()), question)
    assert result.plan.presentation == "board" and result.plan.charts


def test_specific_width_scope_and_explicit_text_preference_are_preserved():
    decision = AgentDecision(action="analyze", plan=overview_plan())
    assert [c.metric for c in overview_presentation(decision, "今天寬度量測結果怎麼樣").plan.charts] == ["width_mm"]
    assert overview_presentation(decision, QUESTION + "只要文字不用圖") is decision
    clarify = AgentDecision(action="clarify", clarification="缺少指定池別")
    assert overview_presentation(clarify, QUESTION) is clarify


def test_existing_charts_and_specialized_statistics_are_not_replaced_with_defaults():
    plan = overview_plan()
    plan["charts"] = [{"type":"boxplot", "title":"寬度", "metric":"width_mm", "secondary_metric":None, "group_by":"pond"}]
    result = overview_presentation(AgentDecision(action="analyze", plan=plan), QUESTION)
    assert [c.type for c in result.plan.charts] == ["boxplot"]
    plan["charts"] = []
    plan["statistics"] = [{"method":"pearson", "metric":"length_mm", "secondary_metric":"weight_g", "group_by":"period", "unit":"track"}]
    result = overview_presentation(AgentDecision(action="analyze", plan=plan), "分析結果如何，用 Pearson")
    assert result.plan.presentation == "board" and not result.plan.charts


def test_video_mean_overview_keeps_statistical_unit_instead_of_adding_track_charts():
    plan = overview_plan()
    for request in plan["statistics"]:
        request["unit"] = "video_mean"
    original = AgentDecision(action="analyze", plan=plan)
    result = overview_presentation(original, "請給我各影片平均量測結果總覽")
    assert result.plan.presentation == "board" and result.plan.statistics == original.plan.statistics
    assert not result.plan.charts


def test_fresh_overview_with_planner_text_misroute_persists_first_board_even_without_data(client, routing, monkeypatch):
    provider, _ = routing
    provider.decision = {"action":"analyze", "plan":overview_plan()}
    catalog = analytics.get_catalog
    monkeypatch.setattr(analytics, "get_catalog", lambda db, demo=False: {
        **catalog(db, demo), "earliest_date": None, "latest_date": None})
    cid = create(client)
    observed = []
    def analyze(runner, plan, demo):
        with runner.sessions() as db:
            from sqlalchemy import select
            from app.assistant.models import Message
            message = db.scalar(select(Message).where(Message.conversation_id == cid, Message.role == "assistant"))
            assert message.status == "querying"
            assert db.get(AssistantResult, message.id).presentation == "board"
            observed.append(plan)
            return analytics.build_board(db, plan, demo=False)
    monkeypatch.setattr(AssistantService, "_analyze", analyze)
    submit(client, cid, QUESTION)
    result = wait(client, cid)
    assert result["status"] == "completed" and result["response_kind"] == "analysis"
    assert len(result["board"]["charts"]) == 3
    assert result["board"]["total_jobs"] == 0 and all(not chart["data"] for chart in result["board"]["charts"])
    assert len(observed) == 1
    assert [step["kind"] for step in result["activity"]] == ["context","plan","query","charts","answer","complete"]


def test_overview_replans_a_bare_answer_instead_of_guessing_the_new_scope(client, routing, monkeypatch):
    provider, queries = routing
    original = provider.generate
    attempts = []
    async def generate(prompt, schema):
        if schema["title"] == "AgentDecision":
            attempts.append(prompt)
            if len(attempts) == 1:
                return {"action":"answer", "clarification":"只有文字的總覽", "plan":None}
            provider.decision = {"action":"analyze", "plan":overview_plan()}
        return await original(prompt, schema)
    monkeypatch.setattr(provider, "generate", generate)
    cid = create(client)
    submit(client, cid, QUESTION)
    result = wait(client, cid)
    assert result["status"] == "completed" and result["board"] is not None
    assert len(attempts) == 2 and "APPLICATION_VALIDATION" in attempts[-1]
    assert queries[0].presentation == "board" and len(queries[0].charts) == 3


def test_first_text_only_overview_does_not_claim_an_existing_board(client, routing):
    provider, queries = routing
    provider.decision = {"action":"analyze", "plan":overview_plan()}
    cid = create(client)
    submit(client, cid, QUESTION + "只要文字不用圖")
    result = wait(client, cid)
    assert result["status"] == "completed" and result["board"] is None and result["response_kind"] == "answer"
    assert queries[0].presentation == "answer" and not queries[0].charts
    assert "原有圖表" not in result["activity"][-1]["detail"]


def test_text_only_model_board_misroute_never_publishes_a_new_board(client, routing):
    provider, queries = routing
    requested = overview_plan()
    requested["presentation"] = "board"
    provider.decision = {"action": "analyze", "plan": requested}
    cid = create(client)
    submit(client, cid, QUESTION + "只要文字不用圖")
    result = wait(client, cid)
    assert result["status"] == "completed" and result["board"] is None
    assert result["response_kind"] == "answer" and queries[0].presentation == "answer"
    assert "charts" not in [step["kind"] for step in result["activity"]]
