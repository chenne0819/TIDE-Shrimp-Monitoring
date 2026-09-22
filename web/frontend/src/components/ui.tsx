"use client";
import Link from "next/link";
import {
  ArrowClockwiseIcon,
  WarningCircleIcon,
  FilmStripIcon,
  UploadSimpleIcon,
} from "@phosphor-icons/react";
import type { JobStatus } from "@/lib/types";
export function StatusBadge({ status }: { status: JobStatus }) {
  const labels: Record<JobStatus, string> = {
    queued: "等待分析",
    processing: "分析中",
    completed: "已完成",
    stopped: "已停止",
    failed: "分析失敗",
  };
  return (
    <span className={`status-badge status-${status}`}>
      <span />
      {labels[status]}
    </span>
  );
}
export function WaterBadge({ label }: { label: "clear" | "turbid" | null }) {
  return (
    <span className={`water-badge ${label || "pending"}`}>
      {label === "clear" ? "清澈" : label === "turbid" ? "混濁" : "待判讀"}
    </span>
  );
}
export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry: () => void;
}) {
  return (
    <div className="state-panel error-panel" role="alert">
      <WarningCircleIcon size={36} />
      <h2>暫時讀取不到資料</h2>
      <p>{message}</p>
      <button className="button button-dark" onClick={retry}>
        <ArrowClockwiseIcon size={18} />
        重新讀取
      </button>
      <Link href="/dashboard?demo=1" className="text-link">
        先看看示範工作台
      </Link>
    </div>
  );
}
export function EmptyState({ filtered = false }: { filtered?: boolean }) {
  return (
    <div className="state-panel">
      <FilmStripIcon size={40} weight="light" />
      <h2>{filtered ? "這個範圍還沒有記錄" : "從第一段觀察開始"}</h2>
      <p>
        {filtered
          ? "試著調整日期或池別，找到想查看的觀察。"
          : "上傳一段蝦隻影片，分析完成後就能在這裡查看每日分布與成長記錄。"}
      </p>
      {!filtered && (
        <Link className="button button-dark" href="/upload">
          <UploadSimpleIcon size={18} />
          上傳觀察影片
        </Link>
      )}
    </div>
  );
}
export function LoadingState() {
  return (
    <div className="loading-state" role="status" aria-label="正在讀取資料">
      <div className="skeleton skeleton-heading" />
      <div className="skeleton-row">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton skeleton-stat" />
        ))}
      </div>
      <div className="skeleton skeleton-chart" />
      <span className="sr-only">正在讀取觀察資料…</span>
    </div>
  );
}
