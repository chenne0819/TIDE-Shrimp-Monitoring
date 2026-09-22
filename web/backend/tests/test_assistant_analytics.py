from datetime import date, datetime, timezone
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select

from app.assistant import analytics
from app.assistant.analytics import build_board, get_catalog
from app.assistant.schemas import AnalysisPlan
from app.database import Base, Job, Track, make_engine, make_session_factory


@pytest.fixture
def db():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        yield session
    engine.dispose()


def add_job(db, when="2026-09-20T10:00:00+08:00", values=None, *, pond="A-01", status="completed", water="clear", details=None):
    job = Job(id=str(uuid4()), filename="test.mp4", pond=pond, status=status,
              recorded_at=datetime.fromisoformat(when).astimezone(timezone.utc), source_path="unused.mp4",
              water_label=water, details=details or {})
    # Deliberately wrong cached averages: analysis must use the per-ID values instead.
    job.avg_length_mm = job.avg_width_mm = job.avg_weight_g = 999
    job.tracks = [Track(track_id=str(i + 1), label=row.get("label", "Male"), observations=row.get("observations", 10),
                        length_mm=row.get("length_mm"), width_mm=row.get("width_mm"), weight_g=row.get("weight_g"))
                  for i, row in enumerate(values if values is not None else [{"length_mm": 80, "width_mm": 12, "weight_g": 4}])]
    db.add(job)
    db.commit()
    return job


def make_plan(kind="bar", metric="length_mm", group="period", *, secondary=None, periods=None, ponds=None):
    return AnalysisPlan.model_validate({
        "title": "測試分析", "ponds": ponds or [],
        "periods": periods or [{"id": "now", "label": "目前", "start_date": "2026-09-20", "end_date": "2026-09-20"}],
        "charts": [{"type": kind, "title": "測試圖表", "metric": metric, "secondary_metric": secondary, "group_by": group}],
    })


TWO_PERIODS = [
    {"id": "current", "label": "本期", "start_date": "2026-09-20", "end_date": "2026-09-20"},
    {"id": "previous", "label": "前期", "start_date": "2026-09-19", "end_date": "2026-09-19"},
]


def test_kpis_use_valid_individuals_not_cached_job_means_or_frame_weights(db):
    add_job(db, values=[{"length_mm": 100, "width_mm": 0, "weight_g": 8, "observations": 1000}])
    add_job(db, values=[{"length_mm": 10, "width_mm": 10, "weight_g": 2},
                        {"length_mm": 10, "width_mm": 20, "weight_g": None},
                        {"length_mm": None, "width_mm": 30, "weight_g": -1}])
    add_job(db, "2026-09-19T10:00:00+08:00", values=[{"length_mm": 20, "width_mm": 8, "weight_g": 4}])
    board = build_board(db, make_plan(periods=TWO_PERIODS))
    length, width, weight, tracks, videos = board["kpis"]
    assert length["value"] == 40
    assert length["previous_value"] == 20
    assert length["delta_pct"] == 100
    assert width["value"] == 20 and weight["value"] == 5
    assert tracks["value"] == 4 and videos["value"] == 2
    assert board["total_tracks"] == 5  # ID 1 in different videos is not deduplicated.
    assert board["period_summaries"][0]["valid_length"] == 3
    assert board["period_summaries"][0]["valid_width"] == 3
    assert board["period_summaries"][0]["valid_weight"] == 2


def test_invalid_values_are_excluded_independently_and_json_is_finite(db):
    add_job(db, values=[{"length_mm": float("nan"), "width_mm": float("inf"), "weight_g": -1},
                        {"length_mm": float("inf"), "width_mm": float("-inf"), "weight_g": 0},
                        {"length_mm": 0, "width_mm": 12, "weight_g": 2},
                        {"length_mm": 10, "width_mm": -1, "weight_g": None}])
    board = build_board(db, make_plan())
    assert [k["value"] for k in board["kpis"]] == [10, 12, 2, 4, 1]
    assert [board["period_summaries"][0][key] for key in ("valid_length", "valid_width", "valid_weight")] == [1, 1, 1]
    json.dumps(board, allow_nan=False)


def test_taipei_inclusive_day_boundaries_and_completed_filter(db):
    add_job(db, "2026-09-19T15:59:59+00:00")  # Taipei previous day, excluded.
    included = add_job(db, "2026-09-19T16:00:00+00:00")
    add_job(db, "2026-09-20T15:59:59+00:00")
    add_job(db, "2026-09-20T16:00:00+00:00")  # Taipei next day, excluded.
    add_job(db, status="failed", pond="FAILED")
    board = build_board(db, make_plan())
    assert board["total_jobs"] == 2 and board["total_tracks"] == 2
    assert included.id in {source["id"] for source in board["sources"]}
    catalog = get_catalog(db)
    assert catalog["available_ponds"] == ["A-01"]
    assert (catalog["earliest_date"], catalog["latest_date"]) == ("2026-09-19", "2026-09-21")
    assert catalog["timezone"] == board["timezone"] == "Asia/Taipei"


def test_selected_four_ponds_today_reports_only_two_actually_observed_ponds(db):
    selected = ["A-01", "B-02", "C-03", "D-04"]
    add_job(db, pond="A-01", values=[{"length_mm": 80}] * 6)
    add_job(db, pond="C-03", values=[{"length_mm": 100}] * 6)
    add_job(db, "2026-09-19T10:00:00+08:00", pond="B-02")
    add_job(db, "2026-09-19T10:00:00+08:00", pond="D-04")
    add_job(db, pond="B-02", status="failed")
    board = build_board(db, make_plan(ponds=selected))
    expected = {"count": 2, "labels": ["A-01", "C-03"], "labels_truncated": False}
    assert board["query"]["ponds"] == selected
    assert (board["total_jobs"], board["total_tracks"]) == (2, 12)
    assert board["observed_ponds"] == expected
    assert board["period_summaries"][0]["observed_ponds"] == expected
    assert len(get_catalog(db)["available_ponds"]) == 4
    assert any("選定 4 個池別，其中只有 2 個池別" in warning for warning in board["warnings"])


def test_observed_ponds_are_per_period_and_union_deduplicated(db):
    for pond in ["A-01", "C-03"]:
        add_job(db, pond=pond)
    for pond in ["B-02", "C-03"]:
        add_job(db, "2026-09-19T10:00:00+08:00", pond=pond)
    board = build_board(db, make_plan(periods=TWO_PERIODS))
    assert board["observed_ponds"] == {"count": 3, "labels": ["A-01", "B-02", "C-03"], "labels_truncated": False}
    assert [item["observed_ponds"]["labels"] for item in board["period_summaries"]] == [["A-01", "C-03"], ["B-02", "C-03"]]
    assert [item["observed_ponds"]["count"] for item in board["period_summaries"]] == [2, 2]


def test_empty_observed_ponds_are_zero_without_filling_selected_ponds(db):
    board = build_board(db, make_plan(ponds=["A-01", "B-02"]))
    empty = {"count": 0, "labels": [], "labels_truncated": False}
    assert board["observed_ponds"] == empty
    assert board["period_summaries"][0]["observed_ponds"] == empty


def test_observed_pond_labels_are_bounded_without_truncating_the_count():
    observed = analytics._observed_ponds([{"pond": f"P{i:03d}"} for i in range(35)] + [{"pond": "P000"}])
    assert observed["count"] == 35 and len(observed["labels"]) == analytics.MAX_OBSERVED_POND_LABELS
    assert observed["labels_truncated"] and observed["labels"] == [f"P{i:03d}" for i in range(30)]


def test_catalog_uses_aggregate_queries_without_loading_tracks(db):
    add_job(db)
    queries = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement.lower())
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        catalog = get_catalog(db)
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert len(catalog["templates"]) == 10
    assert len(queries) == 2
    assert all("tracks" not in query for query in queries)


@pytest.mark.parametrize("kind,metric,secondary", [
    ("line", "length_mm", None), ("area", "width_mm", None), ("bar", "weight_g", None),
    ("stacked_bar", "shrimp_count", None), ("histogram", "length_mm", None),
    ("scatter", "length_mm", "weight_g"), ("boxplot", "width_mm", None),
    ("heatmap", "weight_g", None), ("donut", "shrimp_count", None), ("table", "video_count", None),
])
def test_all_ten_chart_templates_have_expected_shape(db, kind, metric, secondary):
    add_job(db)
    chart = build_board(db, make_plan(kind, metric, secondary=secondary))["charts"][0]
    assert chart["type"] == kind and chart["data"] and chart["note"] and chart["sample_count"] == 1
    assert chart["x_key"] in chart["data"][0]
    assert chart["series"]
    if kind == "scatter":
        assert {"x", "y", "label"} <= chart["data"][0].keys()
        assert [series["unit"] for series in chart["series"]] == ["mm", "g"]
    elif kind == "boxplot":
        assert {"label", "min", "q1", "median", "q3", "max", "count"} == chart["data"][0].keys()
    elif kind == "heatmap":
        assert set(chart["data"][0]) == {"x", "y", "value"}
    else:
        assert len({series["unit"] for series in chart["series"]}) == 1
        assert all(series["key"] in chart["data"][0] for series in chart["series"])
    json.dumps(chart, allow_nan=False)


@pytest.mark.parametrize("group", ["day", "pond", "period", "sex", "water"])
def test_all_grouping_modes_use_track_weighted_values(db, group):
    add_job(db, values=[{"length_mm": 10, "label": "Male"}, {"length_mm": 30, "label": "Female"}])
    chart = build_board(db, make_plan(group=group))["charts"][0]
    if group == "sex":
        assert {row["label"]: row["p0"] for row in chart["data"]} == {"公蝦": 10, "母蝦": 30}
    else:
        assert chart["data"][0]["p0"] == 20


@pytest.mark.parametrize("kind,metric,secondary", [
    ("line", "length_mm", None), ("area", "width_mm", None), ("bar", "weight_g", None),
    ("stacked_bar", "shrimp_count", None), ("histogram", "length_mm", None),
    ("scatter", "length_mm", "weight_g"), ("boxplot", "width_mm", None),
    ("heatmap", "weight_g", None), ("donut", "shrimp_count", None), ("table", "video_count", None),
])
def test_empty_query_never_fabricates_zero_measurements(db, kind, metric, secondary):
    board = build_board(db, make_plan(kind, metric, secondary=secondary))
    assert all(kpi["value"] is None and kpi["previous_value"] is None and kpi["delta_pct"] is None for kpi in board["kpis"])
    assert board["charts"][0]["data"] == []
    assert board["total_jobs"] == board["total_tracks"] == 0
    assert board["metadata"]["earliest_date"] is None
    assert any("沒有已完成" in text for text in board["warnings"])


def test_missing_day_is_null_but_observed_zero_tracks_is_zero(db):
    add_job(db, "2026-09-19T10:00:00+08:00", values=[])
    period = [{"id": "a", "label": "測試", "start_date": "2026-09-19", "end_date": "2026-09-20"}]
    chart = build_board(db, make_plan("line", "shrimp_count", "day", periods=period))["charts"][0]
    assert chart["data"] == [{"label": "2026-09-19", "date": "2026-09-19", "p0": 0},
                              {"label": "2026-09-20", "date": "2026-09-20", "p0": None}]


def test_overlap_sources_totals_and_donut_use_union_once(db):
    add_job(db, values=[{"length_mm": 10, "label": "Male"}, {"length_mm": 30, "label": "Female"}])
    periods = [TWO_PERIODS[0], {**TWO_PERIODS[0], "id": "overlap", "label": "另一期間"}]
    board = build_board(db, make_plan("donut", "shrimp_count", "sex", periods=periods))
    assert board["total_jobs"] == len(board["sources"]) == 1
    assert board["total_tracks"] == 2
    assert [p["tracks"] for p in board["period_summaries"]] == [2, 2]
    assert sum(row["value"] for row in board["charts"][0]["data"]) == 2
    assert any("重疊" in text for text in board["warnings"])


def test_histogram_common_bins_totals_and_empty_period_is_null(db):
    add_job(db, values=[{"length_mm": 10}, {"length_mm": 20}, {"length_mm": 30}])
    add_job(db, "2026-09-19T10:00:00+08:00", values=[{"length_mm": 100}, {"length_mm": 110}])
    chart = build_board(db, make_plan("histogram", periods=TWO_PERIODS))["charts"][0]
    assert sum(row["p0"] for row in chart["data"]) == 3
    assert sum(row["p1"] for row in chart["data"]) == 2
    assert chart["data"][0]["lower"] == 10 and chart["data"][-1]["upper"] == 110
    empty_previous = [TWO_PERIODS[0], {**TWO_PERIODS[1], "start_date": "2026-09-18", "end_date": "2026-09-18"}]
    empty_chart = build_board(db, make_plan("histogram", periods=empty_previous))["charts"][0]
    assert all(row["p1"] is None for row in empty_chart["data"])


def test_histogram_respects_sex_grouping_and_keeps_shared_bins(db):
    add_job(db, values=[{"length_mm": 10, "label": "Male"}, {"length_mm": 30, "label": "Female"}])
    chart = build_board(db, make_plan("histogram", group="sex"))["charts"][0]
    male = [row for row in chart["data"] if row["label"].startswith("公蝦")]
    female = [row for row in chart["data"] if row["label"].startswith("母蝦")]
    assert sum(row["p0"] for row in male) == sum(row["p0"] for row in female) == 1
    assert [(row["lower"], row["upper"]) for row in male] == [(row["lower"], row["upper"]) for row in female]


def test_heatmap_day_is_date_by_pond_with_period_labels_and_missing_cells(db):
    add_job(db, pond="A-01")
    add_job(db, "2026-09-19T10:00:00+08:00", pond="B-02")
    chart = build_board(db, make_plan("heatmap", group="day", periods=TWO_PERIODS))["charts"][0]
    assert chart["data"] == [{"x": "2026-09-20", "y": "本期 · A-01", "value": 80},
                              {"x": "2026-09-20", "y": "本期 · B-02", "value": None},
                              {"x": "2026-09-19", "y": "前期 · A-01", "value": None},
                              {"x": "2026-09-19", "y": "前期 · B-02", "value": 80}]
    assert "拍攝日期" in chart["description"] and "池別" in chart["description"]


def test_heatmap_cross_product_is_bounded_without_silent_truncation(db, monkeypatch):
    add_job(db, pond="A-01")
    add_job(db, pond="B-02")
    monkeypatch.setattr(analytics, "MAX_HEATMAP_CELLS", 1)
    with pytest.raises(ValueError, match="熱圖超過"):
        build_board(db, make_plan("heatmap", group="day"))


def test_boxplot_exact_linear_quantiles(db):
    add_job(db, values=[{"length_mm": value} for value in [10, 20, 30, 40]])
    chart = build_board(db, make_plan("boxplot"))["charts"][0]
    assert chart["data"] == [{"label": "目前", "min": 10, "q1": 17.5, "median": 25, "q3": 32.5, "max": 40, "count": 4}]
    assert "不是 1.5 IQR" in chart["note"]


def test_scatter_keeps_same_individual_pair_and_bounded_sample(db):
    values = [{"length_mm": n, "weight_g": n * 2, "width_mm": None} for n in range(1, 605)]
    values += [{"length_mm": 9999, "weight_g": None}, {"length_mm": None, "weight_g": 9999}]
    add_job(db, values=values)
    chart = build_board(db, make_plan("scatter", secondary="weight_g"))["charts"][0]
    assert len(chart["data"]) == chart["sample_count"] == 500
    assert all(row["y"] == row["x"] * 2 for row in chart["data"])
    assert "有效配對 604 筆" in chart["note"] and "等距抽樣" in chart["note"]


def test_stacked_composition_does_not_add_periods_together(db):
    add_job(db, values=[{"label": "M"}, {"label": "Female"}, {"label": "Unknown"}])
    add_job(db, "2026-09-19T10:00:00+08:00", values=[{"label": "Female"}])
    chart = build_board(db, make_plan("stacked_bar", "shrimp_count", periods=TWO_PERIODS))["charts"][0]
    assert chart["data"] == [{"label": "本期", "male": 1, "female": 1, "unknown": 1},
                              {"label": "前期", "male": 0, "female": 1, "unknown": 0}]


def test_coverage_days_calibration_and_growth_warnings(db):
    add_job(db, details={"pixels_per_mm": 2.5})
    add_job(db, "2026-09-18T10:00:00+08:00", details={"pixels_per_mm": 5.0})
    periods = [TWO_PERIODS[0], {**TWO_PERIODS[1], "start_date": "2026-09-17"}]
    warnings = " ".join(build_board(db, make_plan(periods=periods))["warnings"])
    for phrase in ("天數不同", "資料覆蓋", "不同或缺少的量測設定", "同一隻蝦的成長", "OBB"):
        assert phrase in warnings


def test_parameterized_pond_filter_does_not_interpret_sql(db):
    pond = "A' OR 1=1 --"
    add_job(db, pond=pond)
    add_job(db, pond="B-02")
    board = build_board(db, make_plan(ponds=[pond]))
    assert board["total_jobs"] == 1 and board["sources"][0]["pond"] == pond


def test_job_and_track_bounds_raise_instead_of_silently_truncating(db, monkeypatch):
    add_job(db)
    add_job(db)
    monkeypatch.setattr(analytics, "MAX_JOBS", 1)
    with pytest.raises(ValueError, match="影片.*未產生截斷統計"):
        build_board(db, make_plan())
    monkeypatch.setattr(analytics, "MAX_JOBS", 2000)
    monkeypatch.setattr(analytics, "MAX_TRACKS", 1)
    with pytest.raises(ValueError, match="追蹤 ID.*未產生截斷統計"):
        build_board(db, make_plan())


def test_job_bound_rejects_before_fetching_any_tracks(db, monkeypatch):
    add_job(db)
    add_job(db)
    monkeypatch.setattr(analytics, "MAX_JOBS", 1)
    queries = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement.lower())
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        with pytest.raises(ValueError):
            build_board(db, make_plan())
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert len(queries) == 1 and "tracks" not in queries[0]


def test_source_preview_is_capped_without_truncating_statistics(db, monkeypatch):
    for _ in range(4):
        add_job(db)
    monkeypatch.setattr(analytics, "MAX_SOURCES", 2)
    board = build_board(db, make_plan())
    assert board["total_jobs"] == board["total_tracks"] == 4
    assert len(board["sources"]) == 2
    assert board["metadata"]["sources_shown"] == 2


@pytest.mark.parametrize("kind,metric,secondary,group", [
    ("stacked_bar", "length_mm", None, "period"), ("donut", "weight_g", None, "period"),
    ("histogram", "video_count", None, "period"), ("boxplot", "shrimp_count", None, "period"),
    ("scatter", "length_mm", None, "period"), ("scatter", "length_mm", "length_mm", "period"),
    ("line", "length_mm", "weight_g", "day"), ("donut", "video_count", None, "sex"),
])
def test_semantically_invalid_chart_combinations_are_rejected_before_query(kind, metric, secondary, group):
    with pytest.raises(ValueError):
        build_board(None, make_plan(kind, metric, group, secondary=secondary))


def test_overlapping_period_donut_rejected(db):
    periods = [TWO_PERIODS[0], {**TWO_PERIODS[0], "id": "overlap"}]
    with pytest.raises(ValueError, match="重疊期間"):
        build_board(db, make_plan("donut", "shrimp_count", periods=periods))


def test_unvalidated_plan_cannot_bypass_date_bounds():
    plan = make_plan()
    plan.periods[0].end_date = date(2028, 9, 20)
    with pytest.raises(ValidationError):
        build_board(None, plan)


def test_two_leap_year_periods_allow_366_days_each_but_never_a_third(db):
    periods = [{"id": "a", "label": "甲", "start_date": "2024-01-01", "end_date": "2024-12-31"},
               {"id": "b", "label": "乙", "start_date": "2020-01-01", "end_date": "2020-12-31"}]
    board = build_board(db, make_plan(periods=periods))
    assert [summary["days"] for summary in board["period_summaries"]] == [366, 366]
    with pytest.raises(ValidationError):
        make_plan(periods=[*periods, {**periods[0], "id": "c"}])


def test_demo_isolated_memory_catalog_and_60_days(db):
    class RejectDatabaseAccess:
        def __getattr__(self, name):
            raise AssertionError("Demo must not touch a database")
    catalog = get_catalog(RejectDatabaseAccess(), demo=True)
    assert catalog["today"] == catalog["latest_date"] == "2026-09-20"
    assert catalog["earliest_date"] == "2026-07-23"
    assert catalog["available_ponds"] == ["A-01", "B-02"]
    periods = [{"id": "month", "label": "本月", "start_date": "2026-09-01", "end_date": "2026-09-20"},
               {"id": "previous", "label": "上月", "start_date": "2026-08-01", "end_date": "2026-08-31"}]
    board = build_board(RejectDatabaseAccess(), make_plan("line", group="day", periods=periods), demo=True)
    assert board["demo"] is True and board["total_jobs"] == 102
    assert len(board["sources"]) == 30 and all(source["id"].startswith("demo-") for source in board["sources"])
    assert board["kpis"][0]["previous_value"] is not None
    assert db.scalar(select(func.count()).select_from(Job)) == 0
    json.dumps(board, allow_nan=False)


def test_extreme_but_finite_measurements_do_not_create_invalid_json(db):
    add_job(db, values=[{"length_mm": 1e307}, {"length_mm": 1.7e308}])
    chart = build_board(db, make_plan("histogram"))["charts"][0]
    assert sum(row["p0"] for row in chart["data"]) == 2
    json.dumps(chart, allow_nan=False)
