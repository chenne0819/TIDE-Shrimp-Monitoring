"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type HealthState = "checking" | "online" | "worker-offline" | "unavailable";

export function ServiceStatus({
  demo,
  variant,
}: {
  demo: boolean;
  variant?: "assistant";
}) {
  const [state, setState] = useState<HealthState>("checking");
  const requiresBackend = !demo || variant === "assistant";
  useEffect(() => {
    if (!requiresBackend) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const health = await api<{ status: string; worker: string }>(
          "/health",
          { signal: controller.signal },
        );
        if (!controller.signal.aborted)
          setState(
            variant === "assistant" || health.worker === "online"
              ? "online"
              : "worker-offline",
          );
      } catch {
        if (!controller.signal.aborted) setState("unavailable");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(check, 15000);
      }
    };
    void check();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [requiresBackend, variant]);

  const labels = {
    checking: "正在連線",
    online: "分析服務就緒",
    "worker-offline": "分析程序離線",
    unavailable: "分析服務未連線",
  };
  const description =
    state === "worker-offline"
      ? "API 已連線，請啟動背景 worker，排隊影片才會開始分析。"
      : state === "unavailable"
        ? "請啟動 FastAPI 並確認資料庫連線。"
        : "本機 API 與背景分析程序的即時狀態";
  const assistantDescription =
    "使用合成量測資料；AI 問答仍會使用已設定模型的額度。需要啟動 FastAPI 並連線資料庫。";
  const assistantLabels = {
    checking: "正在連線",
    online: "資料服務已連線",
    "worker-offline": "資料服務已連線",
    unavailable: "資料服務未連線",
  };
  return (
    <div
      className="workspace-badge"
      role="status"
      title={
        variant === "assistant"
          ? demo
            ? assistantDescription
            : "AI 分析需要已連線的 FastAPI 與資料庫；模型是否可用請查看 AI 功能狀態。"
          : demo
            ? "展示資料不需要後端服務"
            : description
      }
    >
      <span
        className={demo && !requiresBackend ? "sample-dot" : "local-dot"}
        style={
          requiresBackend && state !== "online"
            ? { background: state === "checking" ? "#7c8c85" : "#b37b36" }
            : undefined
        }
      />
      {variant === "assistant"
        ? `${demo ? "AI 示範 · " : ""}${assistantLabels[state]}`
        : demo
          ? "示範工作區"
          : labels[state]}
    </div>
  );
}
