"""Presentation safeguards for broad measurement overviews, not date/SQL parsing."""
import re

from .schemas import AgentDecision, AnalysisPlan


def prefers_text_only(question: str) -> bool:
    """Recognize an explicit output preference without negating the opposite request."""
    text = re.sub(r"\s+", "", question)
    negative = r"(?:不用|不要|不需(?:要)?|無需|不必|別|先不)"
    text_only = r"(?:(?:只要|只需|僅要|僅需|只用|僅用|只有)文字|純文字|(?:用|以)文字(?:回答|說明|描述|呈現))"
    if re.search(negative + r"[^，。；！？,;!?]{0,5}(?:圖|畫|視覺)", text):
        return True
    # "不要只用文字，請給我總覽圖" asks for visuals, not a text-only reply.
    text = re.sub(negative + text_only, "", text)
    return bool(re.search(text_only, text))


def wants_overview(question: str) -> bool:
    text = re.sub(r"\s+", "", question)
    # Explicit text-only instructions win, including on the first turn.
    if prefers_text_only(question):
        return False
    if re.search(r"什麼意思|代表什麼|為什麼|解釋|解說|單位|定義|怎麼算|如何計算", text):
        return False
    return bool(re.search(
        r"(?:量測|測量|分析|數據|成長|生長)(?:結果)?(?:怎麼樣|怎樣|如何|狀況|情況|概況|總覽|報告|比較)"
        r"|(?:比較|整理|查看).*(?:量測|測量|分析|數據).*(?:結果|概況)"
        r"|(?:總覽|概況|整體結果|成長狀況|生長狀況)", text
    ))


def overview_presentation(decision: AgentDecision, question: str) -> AgentDecision:
    """Keep the model's validated scope; a broad overview must have a visible result.

    Reclassify an analysis accidentally marked text-only, and add suitable
    default dimension charts when it only requested descriptive statistics.
    Explanations, scalar lookups, explicit text-only requests and specialized
    statistics remain untouched. No dates or ponds are guessed here.
    """
    if decision.action != "analyze":
        return decision
    if prefers_text_only(question):
        if decision.plan.presentation == "answer":
            return decision
        # Chart aggregates may still be needed to answer composition questions;
        # preserve their computation, but never replace the visible board.
        return decision.model_copy(update={"plan": decision.plan.model_copy(update={"presentation": "answer"})})
    if not wants_overview(question):
        return decision
    payload = decision.plan.model_dump(mode="json")
    payload["presentation"] = "board"
    if not payload["charts"] and all(item["method"] == "descriptive" and item["unit"] == "track" for item in payload["statistics"]):
        # Current chart templates aggregate tracks, not per-video means. Keep
        # video-mean summaries as visible statistics cards instead of silently
        # changing their observation unit when adding default charts.
        dimensions = [("length_mm", "長度"), ("width_mm", "寬度"), ("weight_g", "重量")]
        named = [(metric, label) for metric, label in dimensions if label in question]
        dimensions = named or dimensions
        if any(item["group_by"] == "pond" for item in payload["statistics"]):
            # Bar charts already use one series per period, so preserve ponds
            # as categories even when the comparison contains two periods.
            kind, group, suffix = "bar", "pond", "池別比較"
        elif len(decision.plan.periods) > 1:
            kind, group, suffix = "bar", "period", "期間比較"
        elif any(p.start_date != p.end_date for p in decision.plan.periods):
            kind, group, suffix = "line", "day", "每日變化"
        else:
            kind, group, suffix = "histogram", "period", "分布"
        payload["charts"] = [{"type": kind, "title": f"估計{label}{suffix}", "metric": metric,
                              "secondary_metric": None, "group_by": group} for metric, label in dimensions]
    return decision.model_copy(update={"plan": AnalysisPlan.model_validate(payload)})
