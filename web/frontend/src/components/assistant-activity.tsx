"use client";

import { useEffect, useState } from "react";
import {
  CaretDownIcon,
  CheckIcon,
  ClockIcon,
  ListChecksIcon,
  StopIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import type {
  AssistantActivity,
  AssistantMessage,
} from "@/lib/assistant-types";
import { formatNumber } from "@/lib/api";

export const assistantStageNames = {
  planning: "正在整理問題",
  querying: "正在查詢資料",
  answering: "正在整理分析結果",
  completed: "完成",
  failed: "分析未完成",
  cancelled: "已停止",
};
const activityStatusNames = {
  running: "進行中",
  completed: "完成",
  failed: "未完成",
  cancelled: "已停止",
};
const metricNames: Record<string, string> = {
  avg_length_mm: "估計長度",
  avg_width_mm: "估計寬度",
  avg_weight_g: "估計重量",
  length_mm: "估計長度",
  width_mm: "估計寬度",
  weight_g: "估計重量",
  shrimp_count: "追蹤個體數",
  video_count: "影片數",
};
const chartNames: Record<string, string> = {
  line: "折線圖",
  area: "面積圖",
  bar: "分組長條圖",
  stacked_bar: "堆疊長條圖",
  histogram: "直方圖",
  scatter: "散佈圖",
  boxplot: "箱型圖",
  heatmap: "熱圖",
  donut: "環圈圖",
  table: "資料表",
};
const record = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);
const strings = (value: unknown) =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

/** Only expose known, computed execution metadata; never dump arbitrary provider fields. */
export function activityMetadata(
  activity: AssistantActivity,
): { label: string; value: string }[] {
  const data = activity.metadata;
  const rows: { label: string; value: string }[] = [];
  const add = (label: string, value: unknown) => {
    if (typeof value === "string" && value) rows.push({ label, value });
    else if (typeof value === "number" && Number.isFinite(value))
      rows.push({ label, value: formatNumber(value, 0) });
  };
  if (typeof data.demo === "boolean")
    add("資料", data.demo ? "合成示範量測" : "已完成的影片量測");
  add("查詢基準日", data.today);
  add("時區", data.timezone);
  if (
    typeof data.earliest_date === "string" &&
    typeof data.latest_date === "string"
  )
    add("可查日期", `${data.earliest_date} — ${data.latest_date}`);
  add("可查池別數", data.pond_count);
  if (Array.isArray(data.periods)) {
    data.periods.filter(record).forEach((period) => {
      if (
        typeof period.start_date === "string" &&
        typeof period.end_date === "string"
      )
        add(
          typeof period.label === "string" ? period.label : "日期範圍",
          `${period.start_date} — ${period.end_date}`,
        );
    });
  }
  if (Array.isArray(data.ponds))
    add("池別", strings(data.ponds).join("、") || "所有池別");
  add(
    "指標",
    strings(data.metrics)
      .map((key) => metricNames[key] ?? key)
      .join("、"),
  );
  add(
    "圖表",
    strings(data.chart_types)
      .map((key) => chartNames[key] ?? key)
      .join("、"),
  );
  add("影片數", data.total_jobs);
  add("影片內追蹤 ID 數", data.total_tracks);
  add("產生圖表數", data.chart_count);
  add("統計結果數", data.statistics_count);
  if (data.presentation === "answer") add("結果呈現", "僅文字回答，不更新圖表");
  if (data.presentation === "board") add("結果呈現", "更新中央分析結果");
  add("統計方法", strings(data.statistics_methods).join("、"));
  if (Array.isArray(data.chart_samples)) {
    data.chart_samples.filter(record).forEach((chart) => {
      if (
        typeof chart.title === "string" &&
        typeof chart.sample_count === "number" &&
        Number.isFinite(chart.sample_count)
      )
        add(chart.title, `${formatNumber(chart.sample_count, 0)} 筆圖表樣本`);
    });
  }
  return rows;
}

export function ActivityDetails({ message }: { message: AssistantMessage }) {
  const activity = message.activity ?? [];
  if (!activity.length) return null;
  const running = activity.find((step) => step.status === "running");
  const completedCount = activity.filter(
    (step) => step.status === "completed",
  ).length;
  const preview = activity.filter((step) => step.kind !== "complete").slice(-2);
  const state = running
    ? running.label
    : message.status === "failed"
      ? "分析未完成"
      : message.status === "cancelled"
        ? "已停止"
        : `${completedCount} 個步驟完成`;
  return (
    <div className="ai-activity">
      <details>
        <summary>
          <ListChecksIcon size={17} aria-hidden="true" />
          <span>
            執行紀錄
            <small>{state}</small>
          </span>
          <CaretDownIcon size={15} aria-hidden="true" />
        </summary>
        <ol className="ai-activity-list">
          {activity.map((step) => (
            <li className={`ai-activity-${step.status}`} key={step.id}>
              <div className="ai-activity-step">
                <span className="ai-activity-icon">
                  {step.status === "completed" ? (
                    <CheckIcon size={14} />
                  ) : step.status === "failed" ? (
                    <WarningCircleIcon size={15} />
                  ) : step.status === "cancelled" ? (
                    <StopIcon size={13} />
                  ) : (
                    <ClockIcon size={14} />
                  )}
                </span>
                <strong>{step.label}</strong>
                <span>{activityStatusNames[step.status]}</span>
              </div>
              {step.detail && <p>{step.detail}</p>}
              <dl>
                {activityMetadata(step).map((item, index) => (
                  <div key={`${item.label}-${index}`}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ol>
      </details>
      <ul
        className="ai-activity-preview"
        aria-label="最近執行步驟"
        role={running ? "status" : undefined}
      >
        {preview.map((step) => (
          <li key={step.id}>
            {step.status === "running" ? (
              <ClockIcon size={15} aria-hidden="true" />
            ) : step.status === "failed" ? (
              <WarningCircleIcon size={15} aria-hidden="true" />
            ) : step.status === "cancelled" ? (
              <StopIcon size={15} aria-hidden="true" />
            ) : (
              <CheckIcon size={15} aria-hidden="true" />
            )}
            <span>{step.label}</span>
            <small>{activityStatusNames[step.status]}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CompletionSummary({ message }: { message: AssistantMessage }) {
  const complete = message.activity?.find(
    (step) => step.kind === "complete" && step.status === "completed",
  );
  if (!complete?.detail) return null;
  return (
    <p className="ai-completion-summary">
      <CheckIcon size={16} aria-hidden="true" />
      <span>{complete.detail}</span>
    </p>
  );
}

export function AnalysisProgress({
  message,
  sendingStartedAt,
  cancelling = false,
}: {
  message?: AssistantMessage;
  sendingStartedAt: number | null;
  cancelling?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const startedAt = message ? Date.parse(message.created_at) : sendingStartedAt;
  const seconds =
    startedAt != null && Number.isFinite(startedAt)
      ? Math.max(0, Math.floor((now - startedAt) / 1000))
      : 0;
  const running = message?.activity?.find((step) => step.status === "running");
  const stage = cancelling
    ? "正在停止分析"
    : (running?.label ??
      (message ? assistantStageNames[message.status] : "正在送出問題"));
  return (
    <div className="ai-analysis-progress" data-state="processing">
      <span className="ai-progress-spinner" aria-hidden="true" />
      <h2 role="status" aria-live="polite">
        {stage}
      </h2>
      <p>完成後，圖表與分析結果會顯示在這裡。</p>
      <span className="ai-progress-time" aria-hidden="true">
        已經過{" "}
        {seconds >= 60
          ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
          : `${seconds} 秒`}
      </span>
    </div>
  );
}
