"""Opt-in real-model regression suite. Uses quota and saves a demo conversation.

Exercises intent routing, cached follow-ups, chart changes and the five supported
statistics methods. Demo measurements never insert jobs into the real dataset.
Run against an already running local API, not a production multi-user service.
"""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx

CASES = [
    ("first_overview", "今天的量測結果怎麼樣？", {"overview": True}),
    ("width_chart", "用箱型圖看本月估計寬度，把所有池別合併為一組。", {"chart": "boxplot"}),
    ("cached_max", "最大的是多少？", {"text": True, "cached": True}),
    ("explanation", "解釋剛才的結果與限制就好，不用重新查詢或新增圖表。", {"text": True, "cached": True}),
    ("query_text", "上個月的最大寬度是多少？直接回答，不用圖。", {"text": True, "query": True}),
    ("change_chart", "沿用本月日期和寬度，改成直方圖。", {"chart": "histogram"}),
    ("descriptive", "做一份本月各池寬度的描述統計面板，列出最大值、最小值、中位數、標準差與四分位數。", {"methods": ["descriptive"]}),
    ("correlations", "本月估計長度與重量的關係如何？請建立散佈圖，並同時用 Pearson 與 Spearman 各算一次，以追蹤 ID 為單位。", {"chart": "scatter", "methods": ["pearson", "spearman"]}),
    ("welch_t", "請建立 Welch t 檢定的統計面板，比較本月和上月平均估計寬度，以各影片平均值為單位。", {"methods": ["welch_t"]}),
    ("anova", "用 Welch 單因子 ANOVA 建立本月各池平均估計寬度的比較面板，以影片平均值為單位，並搭配適合的圖。", {"methods": ["anova"]}),
    ("unsupported", "只做 Cox 生存分析並告訴我精確 hazard ratio，不能用其他方法替代。", {"text": True}),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=".local/assistant-routing-eval.json")
    args = parser.parse_args()
    report = {"cases": []}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=15) as client:
        token = client.get("/api/session")
        token.raise_for_status()
        client.headers["X-Tide-CSRF"] = token.json()["csrf_token"]
        response = client.post("/api/assistant/conversations", json={"demo": True})
        response.raise_for_status()
        conversation_id = response.json()["id"]
        report["conversation_id"] = conversation_id
        print(f"Conversation: {conversation_id}", flush=True)
        for name, question, expectation in CASES:
            sent = client.post(f"/api/assistant/conversations/{conversation_id}/messages",
                               json={"message": question, "request_id": str(uuid4())})
            sent.raise_for_status()
            message_id = sent.json()["id"]
            states = []
            deadline = time.monotonic() + 300
            while True:
                response = client.get(f"/api/assistant/conversations/{conversation_id}")
                response.raise_for_status()
                detail = response.json()
                message = next(item for item in detail["messages"] if item["id"] == message_id)
                phase = (message["status"], message.get("response_kind"))
                if not states or states[-1] != phase:
                    states.append(phase)
                    print(name, *phase, flush=True)
                if phase[0] not in ("planning", "querying", "answering"):
                    break
                if time.monotonic() > deadline:
                    client.post(f"/api/assistant/messages/{message_id}/cancel").raise_for_status()
                    raise RuntimeError("Evaluation timed out; cancellation requested")
                time.sleep(0.75)
            board = message.get("board")
            charts = [c["type"] for c in board["charts"]] if board else []
            methods = [s["method"] for s in board.get("statistics", [])] if board else []
            steps = [s["kind"] for s in message.get("activity", [])]
            failures = []
            if message["status"] != "completed":
                failures.append(message.get("error") or message["status"])
            if expectation.get("text") and (board or any(kind == "analysis" for _, kind in states)):
                failures.append("Text-only request unexpectedly produced visual progress or board")
            if expectation.get("cached") and "query" in steps:
                failures.append("Cached answer unexpectedly queried data")
            if expectation.get("query") and "query" not in steps:
                failures.append("New-scope answer did not query computed measurements")
            if expectation.get("chart") and expectation["chart"] not in charts:
                failures.append("Requested chart missing")
            if expectation.get("overview") and (not board or not charts):
                failures.append("First general overview must produce visible charts without an explicit chart request")
            if not set(expectation.get("methods", [])) <= set(methods):
                failures.append("Requested statistics method missing")
            if not message.get("content"):
                failures.append("No user-facing response")
            if board:
                if message.get("response_kind") != "analysis":
                    failures.append("Board response kind was not analysis")
                for statistic in board.get("statistics", []):
                    if statistic["status"] != "completed":
                        failures.append(f"Synthetic fixture should support {statistic['method']}: {statistic['reason']}")
            report["cases"].append({"name": name, "question": question, "states": states,
                                    "charts": charts, "methods": methods, "steps": steps,
                                    "failures": failures, "message": message})
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"case": name, "charts": charts, "methods": methods, "failures": failures}, ensure_ascii=False), flush=True)
        report["passed"] = sum(not case["failures"] for case in report["cases"])
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Passed {report['passed']}/{len(CASES)}", flush=True)
        if report["passed"] != len(CASES):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
