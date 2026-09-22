"""Bounded statistics on cleaned observations; never executes model-supplied code.

Chart sampling is deliberately not used here. Correlations use complete pairs,
and inferential comparisons use one mean per video to reduce within-video
pseudoreplication. This does not establish independence between videos.
"""
import math
import warnings

import numpy as np
from scipy import stats

from .statistics_schemas import StatisticsRequest

MAX_GROUPS = 10
DIMENSIONS = ("length_mm", "width_mm", "weight_g")
LABELS = {"length_mm": ("估計長度", "mm"), "width_mm": ("估計寬度", "mm"), "weight_g": ("估計重量", "g")}
METHODS = [
    {"method": "descriptive", "label": "描述統計", "description": "有效數、最小／最大值、平均、中位數、樣本標準差與四分位數。"},
    {"method": "pearson", "label": "Pearson 相關", "description": "以全部有效配對計算線性相關；追蹤 ID 模式不提供 p 值。"},
    {"method": "spearman", "label": "Spearman 等級相關", "description": "以全部有效配對計算單調相關並處理同名次；小樣本不提供漸近 p 值。"},
    {"method": "welch_t", "label": "Welch t 檢定", "description": "兩組影片平均值的雙尾比較，不假設等變異。"},
    {"method": "anova", "label": "Welch 單因子 ANOVA", "description": "兩組以上影片平均值的整體平均比較，不假設等變異；不含事後檢定。"},
]
COMMON_WARNINGS = [
    "量測尺度與回歸校正尚未驗證一致；長寬重量是估計值，寬度是 OBB 短邊代理值。",
    "統計屬探索性比較；不能推論因果，也不能視為同一個體的成長。",
]
VIDEO_WARNING = "先算各影片內有效個體平均，再讓每段影片等權；這只能降低片內偽重複，跨影片、池別與日期的獨立性仍未驗證。"
TRACK_WARNING = "不同影片可能拍到相同個體，同片追蹤 ID 也有群聚性；追蹤 ID 不視為獨立實驗重複。"


def _finite(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _valid(value):
    try:
        number = _finite(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number is not None and number > 0 else None


def summarize(values):
    """Full precision; linear quartiles and sample SD (ddof=1), never zero-fill."""
    data = np.asarray([number for value in values if (number := _valid(value)) is not None], dtype=float)
    empty = {"count": len(data), **{key: None for key in ("min", "max", "mean", "median", "std_dev", "q1", "q3")}}
    if not len(data):
        return empty
    # Scaling avoids overflow when finite source values are unusually large.
    scale = float(np.max(data))
    scaled = data / scale
    q1, median, q3 = np.quantile(scaled, [0.25, 0.5, 0.75], method="linear")
    return {"count": len(data), "min": float(np.min(data)), "max": scale,
            "mean": _finite(float(np.mean(scaled)) * scale), "median": _finite(float(median) * scale),
            "std_dev": _finite(float(np.std(scaled, ddof=1)) * scale) if len(data) > 1 else None,
            "q1": _finite(float(q1) * scale), "q3": _finite(float(q3) * scale)}


def descriptive_summary(periods, by_period):
    return [{"period_id": period.id, "label": period.label,
             "metrics": {metric: summarize(track.get(metric) for job in jobs for track in job["tracks"])
                         for metric in DIMENSIONS}}
            for period, jobs in zip(periods, by_period)]


def _groups(jobs, plan, group_by):
    if group_by == "period":
        return [(p.label, [job for job in jobs if p.start_date <= job["day"] <= p.end_date]) for p in plan.periods]
    ponds = sorted(set(plan.ponds) | {job["pond"] for job in jobs})
    if len(ponds) > MAX_GROUPS:
        raise ValueError(f"統計分組超過 {MAX_GROUPS} 個池別，請指定池別縮小範圍；未截斷統計。")
    return [(pond, [job for job in jobs if job["pond"] == pond]) for pond in ponds]


def _observations(jobs, request):
    pairs = request.secondary_metric is not None
    values = []
    for job in jobs:
        current = []
        for track in job["tracks"]:
            x = _valid(track.get(request.metric))
            y = _valid(track.get(request.secondary_metric)) if pairs else None
            if x is not None and (not pairs or y is not None):
                current.append((x, y) if pairs else x)
        if request.unit == "track":
            values.extend(current)
        elif current:
            if pairs:
                # Both means use the SAME complete-pair subset within each video.
                values.append((summarize(row[0] for row in current)["mean"], summarize(row[1] for row in current)["mean"]))
            else:
                values.append(summarize(current)["mean"])
    return values


def _base(request, index, groups, suffix=""):
    label, unit = LABELS[request.metric]
    method = next(item["label"] for item in METHODS if item["method"] == request.method)
    title = f"{label}{'與' + LABELS[request.secondary_metric][0] if request.secondary_metric else ''} · {method}{suffix}"
    return {"id": f"stat-{index + 1}{suffix}", "method": request.method, "title": title,
            "status": "completed", "metric": request.metric, "secondary_metric": request.secondary_metric,
            "unit": unit, "sample_unit": request.unit, "groups": groups, "values": [],
            "warnings": [*COMMON_WARNINGS, VIDEO_WARNING if request.unit == "video_mean" else TRACK_WARNING], "reason": None}


def _summary_group(label, values, pairs=False):
    summary = summarize(row[0] for row in values) if pairs else summarize(values)
    return {"label": label, "n": summary.pop("count"), **summary}


def _na(result, reason):
    result["status"] = "not_applicable"
    result["reason"] = reason
    result["values"] = []
    return result


def _value(label, value, unit=""):
    return {"label": label, "value": _finite(value), "unit": unit}


def _pvalue(result, value):
    p = _finite(value)
    if p == 0:
        result["warnings"].append("p 值達數值邊界或小於浮點可表示範圍；不以 0 報告，亦不解讀為零機率。")
        return None
    return p


def _overlap(periods):
    return len(periods) > 1 and max(p.start_date for p in periods) <= min(p.end_date for p in periods)


def _correlation(request, index, label, observations, group_index):
    result = _base(request, index, [_summary_group(label, observations, True)], f" · {label}")
    result["id"] = f"stat-{index + 1}-{group_index + 1}"
    if len(observations) < 3:
        return _na(result, "相關分析至少需要 3 個有效配對；沒有以缺值補零或交錯配對。")
    x, y = np.asarray(observations, dtype=float).T
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return _na(result, "至少一個指標為常數，相關係數無法定義。")
    try:
        with warnings.catch_warnings():
            for category in (RuntimeWarning, stats.ConstantInputWarning, stats.NearConstantInputWarning):
                warnings.simplefilter("error", category)
            coefficient, p = (stats.pearsonr(x, y) if request.method == "pearson" else stats.spearmanr(x, y))
    except (ValueError, FloatingPointError, RuntimeWarning, stats.ConstantInputWarning, stats.NearConstantInputWarning):
        return _na(result, "數值精度不足或資料接近常數，無法可靠計算相關。")
    if _finite(coefficient) is None:
        return _na(result, "相關計算產生非有限值，未回報無效結果。")
    pvalue = None
    if request.unit == "track":
        result["warnings"].append("追蹤 ID 可能群聚或重複觀測，僅呈現描述性相關係數，不提供 p 值。")
    elif request.method == "spearman" and len(observations) <= 500:
        result["warnings"].append("有效影片配對不超過 500；Spearman 漸近 p 值不夠可靠，本版不做置換檢定，因此只報係數。")
    else:
        pvalue = _pvalue(result, p)
        result["warnings"].append("p 值以影片配對獨立及相應分布假設成立為前提；本系統未驗證這些假設，不自動判定顯著。")
    result["values"] = [_value("Pearson r" if request.method == "pearson" else "Spearman ρ", coefficient), _value("p 值（雙尾）", pvalue)]
    result["warnings"].append("使用全部有效配對；散布圖的 500 點顯示上限不影響相關計算。")
    return result


def calculate_statistics(jobs, plan):
    results = []
    requests = getattr(plan, "statistics", [])
    for index, raw in enumerate(requests):
        request = StatisticsRequest.model_validate(raw.model_dump() if isinstance(raw, StatisticsRequest) else raw)
        grouped = [(label, _observations(items, request)) for label, items in _groups(jobs, plan, request.group_by)]
        pairs = request.method in ("pearson", "spearman")
        if pairs and grouped:
            results.extend(_correlation(request, index, label, observations, i) for i, (label, observations) in enumerate(grouped))
            continue
        result = _base(request, index, [_summary_group(label, values, pairs) for label, values in grouped])
        results.append(result)
        if request.method == "descriptive":
            if not any(values for _, values in grouped):
                _na(result, "選定範圍沒有有效量測，未以零代替缺值。")
            else:
                result["warnings"].append("標準差採樣本標準差（n−1）；只有 1 筆時為空值。四分位數採線性插值。")
            continue
        if pairs:
            _na(result, "選定範圍沒有有效量測配對。")
            continue
        result["warnings"].extend([
            "Welch 方法不要求各組變異數相同，但仍需獨立觀測及適當的常態／大樣本近似；本系統未驗證假設。",
            "p 值未作多重比較校正；不自動宣告顯著。ANOVA 只檢查整體差異，不指出哪兩組不同。",
        ])
        if _overlap(plan.periods):
            _na(result, "查詢期間重疊，可能重用同一影片；不執行獨立樣本檢定，請使用互不重疊的期間。")
            continue
        arrays = [np.asarray(values, dtype=float) for _, values in grouped]
        if (request.method == "welch_t" and len(arrays) != 2) or (request.method == "anova" and len(arrays) < 2):
            _na(result, "Welch t 檢定需要恰好 2 組；Welch ANOVA 需要至少 2 組有效分組。")
            continue
        if any(len(values) < 2 for values in arrays):
            _na(result, "每組至少需要 2 段有有效量測的影片；同片更多追蹤 ID 不會增加影片樣本數。")
            continue
        if any(np.ptp(values) == 0 for values in arrays):
            _na(result, "至少一組影片平均值沒有變異；本版不對常數組執行 Welch 檢定。")
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", RuntimeWarning)
                if request.method == "welch_t":
                    tested = stats.ttest_ind(*arrays, equal_var=False, alternative="two-sided", nan_policy="raise")
                    ci = tested.confidence_interval(confidence_level=0.95)
                    result["values"] = [_value("Welch t", tested.statistic), _value("p 值（雙尾）", _pvalue(result, tested.pvalue)),
                                        _value("Welch 自由度", tested.df),
                                        _value("平均差（第一組 − 第二組）", np.mean(arrays[0]) - np.mean(arrays[1]), result["unit"]),
                                        _value("平均差 95% CI 下限", ci.low, result["unit"]), _value("平均差 95% CI 上限", ci.high, result["unit"])]
                else:
                    tested = stats.f_oneway(*arrays, equal_var=False, nan_policy="raise")
                    result["values"] = [_value("Welch F", tested.statistic), _value("p 值", _pvalue(result, tested.pvalue))]
                if _finite(tested.statistic) is None or _finite(tested.pvalue) is None:
                    _na(result, "計算產生非有限值，未回報無效統計量或 p 值。")
        except (ValueError, FloatingPointError, RuntimeWarning):
            _na(result, "數值尺度或精度使檢定無法可靠計算，請檢查量測與校正。")
    return results
