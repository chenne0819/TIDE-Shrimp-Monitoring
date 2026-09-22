"""Allow-listed statistics requests; independent of the analysis-plan module."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Dimension = Literal["length_mm", "width_mm", "weight_g"]


class StatisticsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["descriptive", "pearson", "spearman", "welch_t", "anova"]
    metric: Dimension
    secondary_metric: Dimension | None = None
    group_by: Literal["period", "pond"]
    unit: Literal["track", "video_mean"] = Field(
        description="welch_t and anova require video_mean: average within each video first; videos are not proven independent."
    )

    @model_validator(mode="after")
    def validate_method(self):
        if self.method in ("pearson", "spearman"):
            if self.secondary_metric is None or self.secondary_metric == self.metric:
                raise ValueError("相關分析需要兩個不同的長度、寬度或重量指標")
        elif self.secondary_metric is not None:
            raise ValueError("只有相關分析可以指定第二指標")
        if self.method in ("welch_t", "anova") and self.unit != "video_mean":
            raise ValueError("t 檢定與 ANOVA 必須先以影片平均值為單位，不能把同片追蹤 ID 當獨立重複")
        return self
