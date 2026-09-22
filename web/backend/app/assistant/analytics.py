"""Bounded, deterministic analysis over completed jobs; the LLM never runs SQL.

Each (job ID, track ID) is one individual observation, regardless of frame count.
The first requested period is the KPI primary period; the second is its comparison.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import math
from statistics import mean
from uuid import uuid4

from sqlalchemy import func, or_, select

from ..database import Job, Track
from ..storage import TAIPEI, aware
from .demo_data import DEMO_TODAY, make_demo_jobs
from .schemas import AnalysisPlan
from .statistics import METHODS as STATISTICAL_METHODS, calculate_statistics, descriptive_summary

MAX_JOBS = 2_000
MAX_TRACKS = 50_000
MAX_SCATTER_POINTS = 500
MAX_SOURCES = 30
MAX_OBSERVED_POND_LABELS = 30
MAX_HEATMAP_CELLS = 10_000
DIMENSIONS = ("length_mm", "width_mm", "weight_g")
METRICS = {
    "length_mm": ("平均估計長度", "mm"),
    "width_mm": ("平均估計寬度", "mm"),
    "weight_g": ("平均估計重量", "g"),
    "shrimp_count": ("追蹤個體數", "隻"),
    "video_count": ("分析影片數", "段"),
}
SEX_LABELS = {"male": "公蝦", "female": "母蝦", "unknown": "未判定"}
WATER_LABELS = {"clear": "清澈", "turbid": "混濁", "unknown": "未判定"}
TEMPLATES = [
    {"type": "line", "label": "折線圖", "description": "比較每日或分組的單一平均尺寸、重量或數量；缺測保留空值。"},
    {"type": "area", "label": "面積圖", "description": "顯示單一指標趨勢，各期間獨立，不堆疊平均尺寸。"},
    {"type": "bar", "label": "比較柱狀圖", "description": "按日期、池別、期間、性別或首幀水質比較單一指標。"},
    {"type": "stacked_bar", "label": "組成堆疊圖", "description": "只用個體數或影片數；個體按性別、影片按首幀水質組成，各期間分列。"},
    {"type": "histogram", "label": "尺寸重量直方圖", "description": "只用長度、寬度或重量；所有期間共用區間，Y 軸是有效個體數。"},
    {"type": "scatter", "label": "配對散布圖", "description": "X、Y 為兩個不同的長度、寬度或重量指標；只取同一 ID 的有效配對，最多顯示 500 點。"},
    {"type": "boxplot", "label": "五數摘要箱形圖", "description": "只用長度、寬度或重量；顯示實際最小值、Q1、中位數、Q3、最大值。"},
    {"type": "heatmap", "label": "分組熱圖", "description": "日期分組以每日×池別呈現，其他分組與期間交叉顯示單一指標；缺測保留空值。"},
    {"type": "donut", "label": "數量組成環圖", "description": "只用個體數或影片數；對期間聯集去重。期間分組不得重疊，影片數不可按性別切環圖。"},
    {"type": "table", "label": "彙整表格", "description": "顯示每日、期間或其他分組的單一指標彙整，不輸出無界原始資料。"},
]


def _day(value):
    return aware(value).astimezone(TAIPEI).date()


def _positive(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _number(value):
    return round(value, 4) if value is not None and math.isfinite(value) else None


def _average(values):
    values = [value for value in values if value is not None]
    return _number(mean(values)) if values else None


def _sex(value):
    return {"m": "male", "male": "male", "f": "female", "female": "female"}.get(str(value).strip().lower(), "unknown")


def _water(value):
    return value if value in ("clear", "turbid") else "unknown"


def _utc_bounds(period):
    return (
        datetime.combine(period.start_date, time.min, TAIPEI).astimezone(timezone.utc),
        datetime.combine(period.end_date + timedelta(days=1), time.min, TAIPEI).astimezone(timezone.utc),
    )


def get_catalog(db, demo=False):
    """Metadata uses aggregate SQL, never ORM eager-loading every job's tracks."""
    if demo:
        jobs = make_demo_jobs()
        earliest, latest = min(_day(j["recorded_at"]) for j in jobs), DEMO_TODAY
        ponds = sorted({j["pond"] for j in jobs})
    else:
        earliest_time, latest_time = db.execute(
            select(func.min(Job.recorded_at), func.max(Job.recorded_at)).where(Job.status == "completed")
        ).one()
        earliest = _day(earliest_time) if earliest_time is not None else None
        latest = _day(latest_time) if latest_time is not None else None
        ponds = list(db.scalars(select(Job.pond).where(Job.status == "completed").distinct().order_by(Job.pond)).all())
    return {
        "today": (DEMO_TODAY if demo else datetime.now(TAIPEI).date()).isoformat(),
        "timezone": "Asia/Taipei", "available_ponds": ponds,
        "earliest_date": earliest.isoformat() if earliest else None,
        "latest_date": latest.isoformat() if latest else None,
        "templates": [dict(template) for template in TEMPLATES],
        "statistical_methods": [dict(method) for method in STATISTICAL_METHODS],
    }


def _load_jobs(db, plan, demo):
    if demo:
        jobs = [job for job in make_demo_jobs()
                if (not plan.ponds or job["pond"] in plan.ponds)
                and any(p.start_date <= _day(job["recorded_at"]) <= p.end_date for p in plan.periods)]
    else:
        periods = [((Job.recorded_at >= start) & (Job.recorded_at < end))
                   for start, end in (_utc_bounds(p) for p in plan.periods)]
        query = select(Job.id, Job.filename, Job.pond, Job.recorded_at, Job.water_label, Job.details).where(
            Job.status == "completed", or_(*periods))
        if plan.ponds:
            query = query.where(Job.pond.in_(plan.ponds))
        jobs = [dict(row) for row in db.execute(query.order_by(Job.recorded_at, Job.id).limit(MAX_JOBS + 1)).mappings()]
    if len(jobs) > MAX_JOBS:
        raise ValueError(f"查詢超過 {MAX_JOBS:,} 部影片，請縮短日期或指定池別；未產生截斷統計。")
    if not demo and jobs:
        by_id = {job["id"]: job for job in jobs}
        for job in jobs:
            job["tracks"] = []
        rows = list(db.execute(select(Track.job_id, Track.track_id, Track.label, Track.observations,
                                     Track.length_mm, Track.width_mm, Track.weight_g)
                               .where(Track.job_id.in_(list(by_id)))
                               .order_by(Track.job_id, Track.id).limit(MAX_TRACKS + 1)).mappings())
        if len(rows) > MAX_TRACKS:
            raise ValueError(f"查詢超過 {MAX_TRACKS:,} 個追蹤 ID，請縮短日期或指定池別；未產生截斷統計。")
        for row in rows:
            by_id[row["job_id"]]["tracks"].append(dict(row))
    if sum(len(job["tracks"]) for job in jobs) > MAX_TRACKS:
        raise ValueError(f"查詢超過 {MAX_TRACKS:,} 個追蹤 ID，請縮短日期或指定池別；未產生截斷統計。")
    for job in jobs:
        job["day"] = _day(job["recorded_at"])
        job["water"] = _water(job["water_label"])
        for track in job["tracks"]:
            track["sex"] = _sex(track["label"])
            for field in DIMENSIONS:
                track[field] = _positive(track[field])
    return jobs


def _tracks(jobs):
    return [track for job in jobs for track in job["tracks"]]


def _observed_ponds(jobs):
    """Coverage counts come from matching completed videos, never selected filters."""
    labels = sorted({job["pond"] for job in jobs})
    return {"count": len(labels), "labels": labels[:MAX_OBSERVED_POND_LABELS],
            "labels_truncated": len(labels) > MAX_OBSERVED_POND_LABELS}


def _new_bucket():
    return {"jobs": {}, "tracks": []}


def _buckets(jobs, group_by, period):
    buckets = defaultdict(_new_bucket)
    for job in jobs:
        if group_by == "sex":
            per_sex = defaultdict(list)
            for track in job["tracks"]:
                per_sex[track["sex"]].append(track)
            if not per_sex:
                per_sex["unknown"] = []
            for key, tracks in per_sex.items():
                buckets[key]["jobs"][job["id"]] = job
                buckets[key]["tracks"].extend(tracks)
        else:
            key = {"day": job["day"].isoformat(), "pond": job["pond"], "period": period.id,
                   "water": job["water"]}[group_by]
            buckets[key]["jobs"][job["id"]] = job
            buckets[key]["tracks"].extend(job["tracks"])
    return buckets


def _display(key, group_by, periods):
    if group_by == "sex":
        return SEX_LABELS[key]
    if group_by == "water":
        return WATER_LABELS[key]
    if group_by == "period":
        return next(period.label for period in periods if period.id == key)
    return key


def _value(bucket, metric):
    if bucket is None or not bucket["jobs"]:
        return None
    if metric == "video_count":
        return len(bucket["jobs"])
    if metric == "shrimp_count":
        return len(bucket["tracks"])
    return _average(track[metric] for track in bucket["tracks"])


def _metric_value(jobs, metric):
    return _value({"jobs": {job["id"]: job for job in jobs}, "tracks": _tracks(jobs)}, metric)


def _sample_count(jobs, metric):
    if metric == "video_count":
        return len(jobs)
    tracks = _tracks(jobs)
    return len(tracks) if metric == "shrimp_count" else sum(track[metric] is not None for track in tracks)


def _categories(period_buckets, request, plan):
    if request.group_by == "day":
        return sorted({(p.start_date + timedelta(days=i)).isoformat()
                       for p in plan.periods for i in range((p.end_date - p.start_date).days + 1)})
    present = {key for buckets in period_buckets for key in buckets}
    if request.group_by == "period":
        return [period.id for period in plan.periods]
    if request.group_by in ("sex", "water"):
        order = SEX_LABELS if request.group_by == "sex" else WATER_LABELS
        return [key for key in order if key in present]
    return sorted(present)


def _overlap(periods):
    return len(periods) == 2 and max(p.start_date for p in periods) <= min(p.end_date for p in periods)


def _validate_chart(request, periods):
    if request.type in ("stacked_bar", "donut") and request.metric in DIMENSIONS:
        raise ValueError("堆疊圖與環圖只接受個體數或影片數，不能把平均長寬重量相加成比例。")
    if request.type in ("histogram", "scatter", "boxplot") and request.metric not in DIMENSIONS:
        raise ValueError("直方圖、散布圖、箱形圖需選擇長度、寬度或重量指標。")
    if request.type == "scatter":
        if request.secondary_metric is None or request.secondary_metric == request.metric:
            raise ValueError("散布圖需選擇兩個不同的長度、寬度或重量指標。")
    elif request.secondary_metric is not None:
        raise ValueError("只有散布圖可以指定第二指標；其他圖表每張只呈現單一指標與單位。")
    if request.type == "donut":
        if request.group_by == "period" and _overlap(periods):
            raise ValueError("重疊期間不能作為環圖互斥分類，請改用比較柱狀圖。")
        if request.group_by == "sex" and request.metric == "video_count":
            raise ValueError("同一部影片可包含多種性別，不能用性別切分影片數環圖。")


def _quantile(values, fraction):
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return _number(values[low] + (values[high] - values[low]) * (position - low))


def _chart(request, index, plan, jobs, by_period):
    label, unit = METRICS[request.metric]
    buckets = [_buckets(items, request.group_by, period) for period, items in zip(plan.periods, by_period)]
    categories = _categories(buckets, request, plan)
    chart = {
        "id": f"chart-{index + 1}", "type": request.type, "title": request.title,
        "description": f"{label}；" + ("每段已完成影片為一筆觀測。" if request.metric == "video_count"
                                        else "各影片內每個追蹤 ID 為一筆觀測。"),
        "x_key": "date" if request.group_by == "day" else "label",
        "series": [{"key": f"p{i}", "label": p.label, "unit": unit} for i, p in enumerate(plan.periods)],
        "data": [], "sample_count": _sample_count(jobs, request.metric),
        "note": "平均值按有效個體等權計算，不按影片平均再平均；缺值、非有限值及非正尺寸不進分母。" if request.metric in DIMENSIONS
                else ("按已完成影片計數，不按影格或追蹤個體計數。" if request.metric == "video_count"
                      else "同一影片內的 ID 只計一次；不同影片的同號 ID 分別計數，不能當成池內去重總數。"),
    }
    if request.group_by == "water" or (request.type == "stacked_bar" and request.metric == "video_count"):
        chart["note"] += " 水質是影片首幀分類，不代表整段影片的連續水質量測。"
    if request.group_by == "sex" and request.metric == "video_count":
        chart["note"] += " 同一影片可出現在多個性別組，組間影片數不能相加。"
    if not jobs or (request.metric in DIMENSIONS and not chart["sample_count"]):
        chart["note"] += " 沒有可用觀測，保留空圖。"
        return chart
    if request.type in ("line", "area", "bar", "table"):
        chart["data"] = [
            {"label": _display(key, request.group_by, plan.periods),
             **({"date": key} if request.group_by == "day" else {}),
             **{f"p{i}": _value(items.get(key), request.metric) for i, items in enumerate(buckets)}}
            for key in categories
        ]
    elif request.type == "stacked_bar":
        composition = SEX_LABELS if request.metric == "shrimp_count" else WATER_LABELS
        chart["x_key"] = "label"
        chart["series"] = [{"key": key, "label": title, "unit": unit} for key, title in composition.items()]
        for period, items in zip(plan.periods, buckets):
            for key in categories:
                bucket = items.get(key)
                if bucket is None:
                    continue
                values = bucket["tracks"] if request.metric == "shrimp_count" else bucket["jobs"].values()
                field = "sex" if request.metric == "shrimp_count" else "water"
                counts = {category: 0 for category in composition}
                for value in values:
                    counts[value[field]] += 1
                display = _display(key, request.group_by, plan.periods)
                chart["data"].append({"label": display if request.group_by == "period" else f"{period.label} · {display}", **counts})
        chart["note"] += " 每一根柱為一個期間內的組成，各期間不相加。"
    elif request.type == "donut":
        chart["x_key"] = "label"
        chart["series"] = [{"key": "value", "label": label, "unit": unit}]
        union_buckets = _buckets(jobs, request.group_by, plan.periods[0]) if request.group_by != "period" else None
        if union_buckets is not None:
            chart["data"] = [{"label": _display(key, request.group_by, plan.periods), "value": _value(bucket, request.metric)}
                             for key, bucket in sorted(union_buckets.items())]
        else:
            chart["data"] = [{"label": period.label, "value": _metric_value(items, request.metric)}
                             for period, items in zip(plan.periods, by_period) if items]
        chart["note"] += " 環圖使用所選期間的資料聯集，來源影片已去重，不把重疊期間重複加總。"
    elif request.type == "histogram":
        union_values = [t[request.metric] for t in _tracks(jobs) if t[request.metric] is not None]
        low, high = min(union_values), max(union_values)
        bin_count = min(10, max(1, math.ceil(math.sqrt(len(union_values))))) if low != high else 1
        edges = [low + (high - low) * (i / bin_count) for i in range(bin_count + 1)]
        edges[-1] = high
        chart["x_key"] = "label"
        chart["series"] = [{"key": f"p{i}", "label": p.label, "unit": "隻"} for i, p in enumerate(plan.periods)]
        histogram_groups = [None] if request.group_by == "period" else [
            key for key in categories if any(any(track[request.metric] is not None for track in items.get(key, {"tracks": []})["tracks"]) for items in buckets)
        ]
        if len(histogram_groups) * bin_count > 10_000:
            raise ValueError("直方圖分組區間超過 10,000 列，請縮短日期或指定池別。")
        for group in histogram_groups:
            counts = []
            for period_index, items in enumerate(by_period):
                group_tracks = _tracks(items) if group is None else buckets[period_index].get(group, {"tracks": []})["tracks"]
                values = [t[request.metric] for t in group_tracks if t[request.metric] is not None]
                bins = [0] * bin_count if values else [None] * bin_count
                for value in values:
                    bins[min(bin_count - 1, max(0, bisect_right(edges, value) - 1))] += 1
                counts.append(bins)
            prefix = "" if group is None else _display(group, request.group_by, plan.periods) + " · "
            chart["data"].extend({"label": f"{prefix}{edges[i]:.6g}–{edges[i + 1]:.6g}", "lower": edges[i], "upper": edges[i + 1],
                                  **{f"p{p}": bins[i] for p, bins in enumerate(counts)}} for i in range(bin_count))
        chart["description"] = f"{label.replace('平均', '')}（{unit}）的共同區間分布；Y 軸為有效個體數。"
        chart["note"] += " 各期間共用區間，左閉右開、最後區間包含最大值；不同樣本數會影響柱高。"
    elif request.type == "scatter":
        second = request.secondary_metric
        points = [(job, track) for job in jobs for track in job["tracks"]
                  if track[request.metric] is not None and track[second] is not None]
        total_pairs = len(points)
        if total_pairs > MAX_SCATTER_POINTS:
            points = [points[round(i * (total_pairs - 1) / (MAX_SCATTER_POINTS - 1))] for i in range(MAX_SCATTER_POINTS)]
        chart["x_key"] = "x"
        chart["series"] = [{"key": "x", "label": label.replace("平均", ""), "unit": unit},
                           {"key": "y", "label": METRICS[second][0].replace("平均", ""), "unit": METRICS[second][1]}]
        for job, track in points:
            group = {"day": job["day"].isoformat(), "pond": job["pond"], "sex": SEX_LABELS[track["sex"]],
                     "water": WATER_LABELS[job["water"]],
                     "period": "／".join(p.label for p in plan.periods if p.start_date <= job["day"] <= p.end_date)}[request.group_by]
            chart["data"].append({"x": track[request.metric], "y": track[second],
                                  "label": f"{group} · {job['pond']} · {job['day'].isoformat()} · ID {track['track_id']}"})
        chart["sample_count"] = len(points)
        chart["description"] = f"X：{label.replace('平均', '')}（{unit}）；Y：{METRICS[second][0].replace('平均', '')}（{METRICS[second][1]}）。"
        chart["note"] += f" 有效配對 {total_pairs:,} 筆，圖中 {len(points):,} 筆；超過 {MAX_SCATTER_POINTS} 筆時依查詢順序等距抽樣，僅用於展示，不是隨機推論樣本。每點必須是同一影片同一 ID 的兩個有效值。"
    elif request.type == "boxplot":
        chart["x_key"] = "label"
        chart["series"] = [{"key": "median", "label": label.replace("平均", "中位數"), "unit": unit}]
        for period, items in zip(plan.periods, buckets):
            for key in categories:
                bucket = items.get(key)
                values = sorted(t[request.metric] for t in bucket["tracks"] if t[request.metric] is not None) if bucket else []
                if not values:
                    continue
                display = _display(key, request.group_by, plan.periods)
                chart["data"].append({"label": display if request.group_by == "period" else f"{period.label} · {display}",
                                      "min": values[0], "q1": _quantile(values, .25), "median": _quantile(values, .5),
                                      "q3": _quantile(values, .75), "max": values[-1], "count": len(values)})
        chart["note"] += " Q1／中位數／Q3 採排序後線性插值；上下端點是實際最小／最大值，不是 1.5 IQR 鬚線，也不另外判定離群值。"
    elif request.type == "heatmap":
        chart["x_key"] = "x"
        chart["series"] = [{"key": "value", "label": label, "unit": unit}]
        if request.group_by == "day":
            ponds = sorted({job["pond"] for job in jobs})
            cells = sum((p.end_date - p.start_date).days + 1 for p in plan.periods) * len(ponds)
            if cells > MAX_HEATMAP_CELLS:
                raise ValueError(f"每日×池別熱圖超過 {MAX_HEATMAP_CELLS:,} 格，請縮短期間或指定池別。")
            for period, items in zip(plan.periods, by_period):
                dates = [(period.start_date + timedelta(days=i)).isoformat()
                         for i in range((period.end_date - period.start_date).days + 1)]
                for pond in ponds:
                    per_day = _buckets([job for job in items if job["pond"] == pond], "day", period)
                    chart["data"].extend({"x": day, "y": f"{period.label} · {pond}" if len(plan.periods) > 1 else pond,
                                          "value": _value(per_day.get(day), request.metric)} for day in dates)
            chart["description"] = f"X：拍攝日期；Y：池別{'與期間' if len(plan.periods) > 1 else ''}；色階：{label}（{unit}）。"
        else:
            if len(categories) * len(plan.periods) > MAX_HEATMAP_CELLS:
                raise ValueError(f"熱圖超過 {MAX_HEATMAP_CELLS:,} 格，請縮小查詢範圍。")
            for period, items in zip(plan.periods, buckets):
                keys = [period.id] if request.group_by == "period" else categories
                chart["data"].extend({"x": label if request.group_by == "period" else _display(key, request.group_by, plan.periods),
                                      "y": period.label, "value": _value(items.get(key), request.metric)} for key in keys)
            chart["description"] = f"X：查詢分組；Y：期間；色階：{label}（{unit}）。"
        chart["note"] += " 沒有觀測的格子是空值，不補成零。"
    return chart


def build_board(db, plan: AnalysisPlan, demo=False):
    # Revalidate even model_construct-created plans before any SQL or sample access.
    plan = AnalysisPlan.model_validate(plan.model_dump() if isinstance(plan, AnalysisPlan) else plan)
    for request in plan.charts:
        _validate_chart(request, plan.periods)
    jobs = _load_jobs(db, plan, demo)
    by_period = [[job for job in jobs if period.start_date <= job["day"] <= period.end_date] for period in plan.periods]
    tracks = _tracks(jobs)
    warnings = ["本次比較尚未確認各影片拍攝尺度與回歸校正一致；長寬重量是估計值，寬度為 OBB 短邊代理值。",
                "不同影片的同號 ID 分別計數；跨期樣本沒有個體身分串接，不能視為同一隻蝦的成長曲線。"]
    if demo:
        warnings.insert(0, "目前使用合成示範量測，固定日期為 2026-09-20；不建立真實影片紀錄，示範對話與圖表會另外保存。")
    if not jobs:
        warnings.append("選定日期與池別沒有已完成的分析；保留空圖及空平均值，不填示範資料或零。")
    if _overlap(plan.periods):
        warnings.append("兩個期間有重疊，同一影片會參與各自期間統計；總數與來源清單採聯集去重，兩期數字不能直接相加。")
    days = [(period.end_date - period.start_date).days + 1 for period in plan.periods]
    if len(set(days)) > 1:
        warnings.append("兩期間天數不同；影片數與個體總數未按天正規化，不能直接當成等長期間變化率。")
    summaries = []
    coverage = {}
    for period, items, period_days in zip(plan.periods, by_period, days):
        current_tracks = _tracks(items)
        observed_ponds = _observed_ponds(items)
        covered_days = len({job["day"] for job in items})
        coverage[period.id] = covered_days
        if covered_days < period_days:
            warnings.append(f"「{period.label}」共 {period_days} 天，只有 {covered_days} 天有完成影片；未觀測日期不補成零，資料覆蓋可能影響比較。")
        selected_pond_count = len(set(plan.ponds))
        if selected_pond_count > observed_ponds["count"]:
            warnings.append(f"「{period.label}」選定 {selected_pond_count} 個池別，其中只有 {observed_ponds['count']} 個池別有已完成影片；選取範圍不代表實際觀測池數。")
        summaries.append({"id": period.id, "label": period.label, "days": period_days, "videos": len(items), "tracks": len(current_tracks),
                          "observed_ponds": observed_ponds,
                          **{f"valid_{name}": sum(track[field] is not None for track in current_tracks)
                             for name, field in zip(("length", "width", "weight"), DIMENSIONS)}})
    if any(any(track[field] is None for field in DIMENSIONS) for track in tracks):
        warnings.append("部分個體量測為缺值、非有限值或非正值；每個指標各自排除，長度、寬度、重量的有效樣本數可能不同。")
    signatures = {repr(tuple((job.get("details") or {}).get(key) for key in ("pixels_per_mm", "reference_size", "weight_mode", "width_source"))) for job in jobs}
    if len(signatures) > 1:
        warnings.append("查詢包含不同或缺少的量測設定；需先確認相機與校正條件一致，再比較尺寸與重量。")
    if len(jobs) > MAX_SOURCES:
        warnings.append(f"來源清單顯示最近 {MAX_SOURCES} 段影片；統計仍涵蓋查詢內全部 {len(jobs)} 段，沒有截斷計算。")
    kpis = []
    for metric, (label, unit) in METRICS.items():
        value = _metric_value(by_period[0], metric)
        previous = _metric_value(by_period[1], metric) if len(by_period) > 1 else None
        delta = _number((value - previous) / previous * 100) if value is not None and previous not in (None, 0) else None
        kpis.append({"label": label, "value": value, "unit": unit, "previous_value": previous, "delta_pct": delta})
    catalog = get_catalog(db, demo)
    sources = [{"id": job["id"], "filename": job["filename"], "pond": job["pond"], "recorded_at": aware(job["recorded_at"]).isoformat()}
               for job in sorted(jobs, key=lambda job: (aware(job["recorded_at"]), job["id"]), reverse=True)[:MAX_SOURCES]]
    return {
        "id": str(uuid4()), "title": plan.title, "generated_at": datetime.now(timezone.utc).isoformat(),
        "demo": bool(demo), "timezone": "Asia/Taipei",
        "query": {"periods": [period.model_dump(mode="json") for period in plan.periods], "ponds": plan.ponds,
                  "statistics": [request.model_dump(mode="json") for request in getattr(plan, "statistics", [])],
                  "aggregation": "圖表、KPI 與描述摘要以每影片每追蹤 ID 等權彙整；統計方法另依 sample_unit 指定的 ID 或影片平均值計算。只讀已完成分析；各指標排除缺值、非有限值及非正尺寸。第一期間為 KPI 主期間。"},
        "kpis": kpis, "charts": [_chart(request, i, plan, jobs, by_period) for i, request in enumerate(plan.charts)],
        "statistics": calculate_statistics(jobs, plan), "descriptive_summary": descriptive_summary(plan.periods, by_period),
        "warnings": warnings, "sources": sources, "total_jobs": len(jobs), "total_tracks": len(tracks), "period_summaries": summaries,
        "observed_ponds": _observed_ponds(jobs),
        "metadata": {"earliest_date": catalog["earliest_date"], "latest_date": catalog["latest_date"], "timezone": "Asia/Taipei",
                     "query_earliest_date": min(job["day"] for job in jobs).isoformat() if jobs else None,
                     "query_latest_date": max(job["day"] for job in jobs).isoformat() if jobs else None,
                     "covered_days": coverage, "source_count": len(jobs), "sources_shown": len(sources),
                     "sampling_limit": MAX_SCATTER_POINTS},
    }
