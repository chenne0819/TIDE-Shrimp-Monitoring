"""The model selects a validated query; only application code creates chart data."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .statistics_schemas import StatisticsRequest

Metric = Literal["length_mm", "width_mm", "weight_g", "shrimp_count", "video_count"]
ChartKind = Literal["line", "area", "bar", "stacked_bar", "histogram", "scatter", "boxplot", "heatmap", "donut", "table"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Period(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    label: str = Field(min_length=1, max_length=60)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 365:
            raise ValueError("每個期間需為 1 至 366 天，開始日不能晚於結束日")
        if self.start_date.year < 2000 or self.end_date.year > 2100:
            raise ValueError("日期需介於 2000 至 2100 年")
        return self


class ChartRequest(StrictModel):
    type: ChartKind
    title: str = Field(min_length=1, max_length=100)
    metric: Metric
    secondary_metric: Literal["length_mm", "width_mm", "weight_g"] | None
    group_by: Literal["day", "pond", "period", "sex", "water"] = Field(
        description="For a daily-by-pond heatmap choose day (the application automatically adds ponds as rows); pond means period-by-pond totals. For stacked_bar choose pond for per-pond composition, day for daily composition, or period for whole-period composition."
    )


class AnalysisPlan(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    periods: list[Period] = Field(min_length=1, max_length=2)
    ponds: list[str] = Field(max_length=10)
    charts: list[ChartRequest] = Field(default_factory=list, max_length=8)
    statistics: list[StatisticsRequest] = Field(default_factory=list, max_length=6)
    presentation: Literal["answer", "board"] = "board"

    @model_validator(mode="after")
    def valid_plan(self):
        if not self.charts and not self.statistics:
            raise ValueError("分析計畫至少需要一個圖表或統計請求")
        if len({p.id for p in self.periods}) != len(self.periods):
            raise ValueError("期間 ID 不可重複")
        if any(not p.strip() or len(p) > 80 or any(ord(c) < 32 for c in p) for p in self.ponds):
            raise ValueError("池別格式無效")
        return self


class AgentDecision(StrictModel):
    action: Literal["answer", "analyze", "clarify"]
    clarification: str = Field(default="", max_length=8000, description="Traditional Chinese reply for answer or clarify; answer must use only supplied trusted computed facts. Empty for analyze.")
    plan: AnalysisPlan | None = None

    @model_validator(mode="after")
    def valid_decision(self):
        if self.action == "analyze" and self.plan is None:
            raise ValueError("分析必須包含查詢計畫")
        if self.action in {"answer", "clarify"}:
            if not self.clarification.strip():
                raise ValueError("直接回答或釐清問題必須包含回覆文字")
            if self.plan is not None:
                raise ValueError("直接回答與釐清不能附帶查詢計畫")
        return self


class AgentAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=8000)
    followups: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(max_length=3)
