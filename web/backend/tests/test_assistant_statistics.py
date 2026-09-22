"""Known-value and independent-formula checks, not SciPy compared to itself."""
from datetime import date, datetime, timezone
import json
import math
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.assistant.statistics import calculate_statistics, descriptive_summary, summarize
from app.assistant.statistics_schemas import StatisticsRequest


def request(method="descriptive", *, metric="length_mm", secondary=None, unit="track", group="period", **extra):
    return StatisticsRequest(method=method, metric=metric, secondary_metric=secondary, unit=unit, group_by=group, **extra)


def plan(*requests, periods=None, ponds=None):
    return SimpleNamespace(statistics=list(requests), ponds=ponds or [], periods=periods or [
        SimpleNamespace(id="now", label="本期", start_date=date(2026, 9, 1), end_date=date(2026, 9, 30))])


def job(values, *, pond="A", day=date(2026, 9, 20)):
    return {"id": str(uuid4()), "pond": pond, "day": day, "tracks": [
        value if isinstance(value, dict) else {"length_mm": value} for value in values]}


def values_by_label(result):
    return {row["label"]: row["value"] for row in result["values"]}


def test_full_descriptive_values_linear_quartiles_sample_denominator():
    result = summarize([1, 2, 3, 4, None, 0, -1, float("nan"), float("inf")])
    assert result == {"count": 4, "min": 1, "max": 4, "mean": 2.5, "median": 2.5,
                      "std_dev": math.sqrt(5 / 3), "q1": 1.75, "q3": 3.25}


def test_missing_empty_and_singleton_are_not_fake_zero_or_sd():
    assert summarize([]) == {"count": 0, "min": None, "max": None, "mean": None, "median": None, "std_dev": None, "q1": None, "q3": None}
    assert summarize([7])["std_dev"] is None
    assert summarize([7, 7])["std_dev"] == 0
    data = calculate_statistics([job([None, 0])], plan(request()))[0]
    assert data["status"] == "not_applicable"
    assert data["groups"][0]["n"] == 0


def test_summary_retains_full_precision_and_handles_large_finite_values():
    original = 1.1234567890123
    assert summarize([original])["max"] == original
    result = summarize([1e308, 1.1e308, 1.2e308])
    assert result["mean"] == pytest.approx(1.1e308)
    assert result["std_dev"] == pytest.approx(1e307)
    json.dumps(result, allow_nan=False)


def test_period_descriptive_summary_is_independent_for_all_three_dimensions():
    p = plan()
    result = descriptive_summary(p.periods, [[job([
        {"length_mm": 100, "width_mm": None, "weight_g": 2},
        {"length_mm": 20, "width_mm": 8, "weight_g": 4}])]])[0]
    assert result["period_id"] == "now"
    assert result["metrics"]["length_mm"]["max"] == 100
    assert result["metrics"]["width_mm"]["count"] == 1
    assert result["metrics"]["weight_g"]["median"] == 3


def test_video_mean_equal_weight_differs_from_track_mean():
    jobs = [job([100]), job([10, 10, 10])]
    track, video = calculate_statistics(jobs, plan(request(), request(unit="video_mean")))
    assert track["groups"][0]["mean"] == pytest.approx(32.5)
    assert video["groups"][0]["mean"] == pytest.approx(55)
    assert video["groups"][0]["n"] == 2
    assert video["sample_unit"] == "video_mean"
    assert any("獨立性仍未驗證" in warning for warning in video["warnings"])


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_correlation_uses_complete_pairs_not_independent_missing_filters(method):
    rows = [{"length_mm": 1, "weight_g": 1}, {"length_mm": 2, "weight_g": 2},
            {"length_mm": 3, "weight_g": 3}, {"length_mm": 1000, "weight_g": None},
            {"length_mm": None, "weight_g": 0.1}, {"length_mm": float("nan"), "weight_g": 5}]
    result = calculate_statistics([job(rows)], plan(request(method, secondary="weight_g")))[0]
    assert result["groups"][0]["n"] == 3
    assert result["values"][0]["value"] == pytest.approx(1)
    assert result["values"][1]["value"] is None


def test_pearson_known_centered_dot_product_with_full_input_over_500_points():
    pairs = [(i + 1, (i % 7) + 1) for i in range(731)]
    x_mean = sum(x for x, _ in pairs) / len(pairs)
    y_mean = sum(y for _, y in pairs) / len(pairs)
    expected = sum((x-x_mean)*(y-y_mean) for x, y in pairs) / math.sqrt(
        sum((x-x_mean)**2 for x, _ in pairs) * sum((y-y_mean)**2 for _, y in pairs))
    result = calculate_statistics([job([{"length_mm": x, "weight_g": y} for x, y in pairs])],
                                  plan(request("pearson", secondary="weight_g")))[0]
    assert result["groups"][0]["n"] == 731
    assert result["values"][0]["value"] == pytest.approx(expected, abs=1e-14)


def test_spearman_tied_ranks_known_value():
    # Average ranks: x=[1,2.5,2.5,4], y=[1,2,3,4]. Dot product=4.5;
    # squared centered norms=4.5 and 5, so rho=sqrt(0.9).
    result = calculate_statistics([job([{"length_mm": x, "weight_g": y} for x, y in zip([1, 2, 2, 4], [1, 2, 3, 4])])],
                                  plan(request("spearman", secondary="weight_g")))[0]
    assert result["values"][0]["value"] == pytest.approx(math.sqrt(0.9))


def test_video_pair_means_use_same_complete_pair_subset_and_hide_small_spearman_p():
    jobs = [job([{"length_mm": i, "weight_g": i * 2}, {"length_mm": 10000, "weight_g": None},
                 {"length_mm": None, "weight_g": 1000}]) for i in [1, 2, 3, 4]]
    result = calculate_statistics(jobs, plan(request("spearman", secondary="weight_g", unit="video_mean")))[0]
    assert result["groups"][0]["mean"] == 2.5
    assert result["values"][0]["value"] == pytest.approx(1)
    assert result["values"][1]["value"] is None
    assert any("500" in warning for warning in result["warnings"])


def test_video_pearson_known_r_and_conditional_p_for_n4():
    # r=0.8 for these centered sequences; for n=4 Pearson's null r is uniform,
    # so the exact two-sided p value is 1-|r| = 0.2.
    jobs = [job([{"length_mm": x, "weight_g": y}]) for x, y in zip([1, 2, 3, 4], [1, 3, 2, 4])]
    result = calculate_statistics(jobs, plan(request("pearson", secondary="weight_g", unit="video_mean")))[0]
    assert result["values"][0]["value"] == pytest.approx(0.8)
    assert result["values"][1]["value"] == pytest.approx(0.2)
    assert any("前提" in warning for warning in result["warnings"])


@pytest.mark.parametrize("rows", [
    [{"length_mm": 2, "weight_g": i} for i in [1, 2, 3]],
    [{"length_mm": i, "weight_g": 3} for i in [1, 2, 3]],
    [{"length_mm": i, "weight_g": i} for i in [1, 2]],
])
@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_correlation_constant_and_insufficient_are_not_applicable(rows, method):
    result = calculate_statistics([job(rows)], plan(request(method, secondary="weight_g")))[0]
    assert result["status"] == "not_applicable"
    assert result["reason"] and not result["values"]


def test_welch_t_known_statistic_df_and_independent_cdf_integration():
    jobs = [job([x], pond="A") for x in [1, 2, 3]] + [job([x], pond="B") for x in [2, 4, 6]]
    result = calculate_statistics(jobs, plan(request("welch_t", group="pond", unit="video_mean")))[0]
    values = values_by_label(result)
    t, df = -2 / math.sqrt(5 / 3), 50 / 17
    # Independent numerical integration of Student t density using Simpson's rule.
    limit, steps = abs(t), 10000
    def density(x):
        return math.gamma((df + 1) / 2) / (math.sqrt(df * math.pi) * math.gamma(df / 2)) * (1 + x*x / df) ** (-(df + 1) / 2)
    h = limit / steps
    area = h / 3 * (density(0) + density(limit) + sum((4 if i % 2 else 2) * density(i*h) for i in range(1, steps)))
    assert values["Welch t"] == pytest.approx(t)
    assert values["Welch 自由度"] == pytest.approx(df)
    assert values["p 值（雙尾）"] == pytest.approx(1 - 2*area, abs=1e-11)
    assert values["平均差（第一組 − 第二組）"] == -2
    assert values["平均差 95% CI 下限"] < -2 < values["平均差 95% CI 上限"]
    assert [group["n"] for group in result["groups"]] == [3, 3]


def test_welch_anova_independent_closed_form_three_groups():
    jobs = [job([x], pond=pond) for pond, seq in {"A": [1, 2, 3], "B": [2, 3, 4], "C": [3, 4, 5]}.items() for x in seq]
    result = calculate_statistics(jobs, plan(request("anova", group="pond", unit="video_mean")))[0]
    values = values_by_label(result)
    # k=3, n=3, variance=1, weights=3. Welch correction 1+1/6;
    # F=3/(7/6)=18/7, df1=2 and df2=4. For F(2,v), survival is
    # (v/(v+2F))**(v/2), avoiding a second call to scipy.stats.f_oneway.
    expected_f = 18 / 7
    expected_p = (4 / (4 + 2 * expected_f)) ** 2
    assert result["status"] == "completed"
    assert values["Welch F"] == pytest.approx(expected_f)
    assert values["p 值"] == pytest.approx(expected_p)
    assert "Welch" in result["title"]


@pytest.mark.parametrize("method", ["welch_t", "anova"])
@pytest.mark.parametrize("seq_a,seq_b", [([1], [2, 3]), ([1, 1], [2, 3]), ([1, 2], []), ([1, 1], [2, 2])])
def test_inference_rejects_insufficient_or_constant_video_samples(method, seq_a, seq_b):
    jobs = [job([x], pond="A") for x in seq_a] + [job([x], pond="B") for x in seq_b]
    result = calculate_statistics(jobs, plan(request(method, group="pond", unit="video_mean"), ponds=["A", "B"]))[0]
    assert result["status"] == "not_applicable"
    assert result["reason"] and result["values"] == []
    json.dumps(result, allow_nan=False)


def test_more_tracks_in_single_video_does_not_satisfy_inference_minimum():
    result = calculate_statistics([job([1, 2, 3, 4], pond="A"), job([3, 4, 5, 6], pond="B")],
                                  plan(request("welch_t", group="pond", unit="video_mean")))[0]
    assert result["status"] == "not_applicable"
    assert [group["n"] for group in result["groups"]] == [1, 1]


@pytest.mark.parametrize("method", ["welch_t", "anova"])
def test_overlapping_periods_never_treated_as_independent(method):
    periods = [SimpleNamespace(id=key, label=key, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30)) for key in ["a", "b"]]
    result = calculate_statistics([job([x]) for x in [1, 2, 3]], plan(request(method, unit="video_mean"), periods=periods))[0]
    assert result["status"] == "not_applicable" and "重疊" in result["reason"]


def test_nonoverlapping_period_comparison_uses_each_period_not_union_twice():
    periods = [SimpleNamespace(id=key, label=key, start_date=date(2026, month, 1), end_date=date(2026, month, 28)) for key, month in [("a", 9), ("b", 8)]]
    jobs = [job([x], day=date(2026, 9, 20)) for x in [1, 2, 3]] + [job([x], day=date(2026, 8, 20)) for x in [3, 4, 5]]
    result = calculate_statistics(jobs, plan(request("welch_t", unit="video_mean"), periods=periods))[0]
    assert result["status"] == "completed"
    assert [group["mean"] for group in result["groups"]] == pytest.approx([2, 4])


def test_group_bound_is_rejection_not_partial_statistics():
    jobs = [job([1, 2, 3], pond=f"P{i:02d}") for i in range(11)]
    with pytest.raises(ValueError, match="超過 10"):
        calculate_statistics(jobs, plan(request(group="pond")))


def test_pvalue_boundary_is_never_presented_as_zero_probability():
    jobs = [job([{"length_mm": i, "weight_g": i * 2}]) for i in range(1, 8)]
    result = calculate_statistics(jobs, plan(request("pearson", secondary="weight_g", unit="video_mean")))[0]
    assert result["status"] == "completed"
    assert result["values"][0]["value"] == pytest.approx(1)
    assert result["values"][1]["value"] is None
    assert any("數值邊界" in warning for warning in result["warnings"])


@pytest.mark.parametrize("method", ["welch_t", "anova"])
def test_extreme_finite_inference_never_returns_nan_or_infinity(method):
    jobs = [job([x], pond="A") for x in [1e307, 2e307, 3e307]] + [job([x], pond="B") for x in [4e307, 5e307, 6e307]]
    result = calculate_statistics(jobs, plan(request(method, group="pond", unit="video_mean")))[0]
    assert result["status"] == "not_applicable"
    json.dumps(result, allow_nan=False)


def test_empty_pond_correlation_returns_explicit_not_applicable_result():
    result = calculate_statistics([], plan(request("pearson", secondary="width_mm", group="pond")))[0]
    assert result["status"] == "not_applicable" and result["reason"]


def test_pond_groups_union_deduplicates_overlapping_periods():
    periods = [SimpleNamespace(id=key, label=key, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30)) for key in ["a", "b"]]
    result = calculate_statistics([job([1, 2, 3])], plan(request(group="pond"), periods=periods))[0]
    assert result["groups"][0]["n"] == 3


@pytest.mark.parametrize("kwargs", [
    {"method": "sql"}, {"metric": "shrimp_count"}, {"group": "sex"}, {"unit": "frame"}, {"sql": "select 1"},
    {"method": "pearson"}, {"method": "spearman", "secondary": "length_mm"},
    {"secondary": "weight_g"}, {"method": "welch_t"}, {"method": "anova"},
])
def test_strict_allowlist_rejects_unsupported_or_invalid_method_requests(kwargs):
    with pytest.raises(ValidationError):
        request(**kwargs)


def test_construct_bypass_request_is_revalidated_before_calculation():
    bypass = StatisticsRequest.model_construct(method="welch_t", metric="length_mm", secondary_metric=None, group_by="period", unit="track")
    with pytest.raises(ValidationError):
        calculate_statistics([], plan(bypass))


def test_board_integration_uses_one_job_load_and_supports_statistics_without_charts(monkeypatch):
    from app.assistant import analytics
    from app.assistant.schemas import AnalysisPlan

    real_plan = AnalysisPlan.model_validate({"title": "統計", "ponds": [], "periods": [
        {"id": "now", "label": "本期", "start_date": "2026-09-01", "end_date": "2026-09-30"}],
        "charts": [], "statistics": [request().model_dump()], "presentation": "answer"})
    jobs = [job([{"length_mm": 1, "width_mm": 2, "weight_g": 3}, {"length_mm": 99, "width_mm": 4, "weight_g": 5}])]
    for item in jobs:
        item.update(filename="test.mp4", recorded_at=datetime(2026, 9, 20, tzinfo=timezone.utc), details={}, water="unknown")
    calls = []
    def load(*_):
        calls.append("load")
        return jobs
    monkeypatch.setattr(analytics, "_load_jobs", load)
    monkeypatch.setattr(analytics, "get_catalog", lambda *_: {"earliest_date": "2026-09-20", "latest_date": "2026-09-20"})
    board = analytics.build_board(None, real_plan)
    assert calls == ["load"]
    assert board["charts"] == [] and len(board["statistics"]) == 1
    assert board["descriptive_summary"][0]["metrics"]["length_mm"]["max"] == 99
    json.dumps(board, allow_nan=False)
