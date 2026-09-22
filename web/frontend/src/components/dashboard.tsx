"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  CrosshairIcon,
  RulerIcon,
  ArrowsHorizontalIcon,
  ScalesIcon,
  VideoCameraIcon,
  UploadSimpleIcon,
  DropIcon,
  CheckCircleIcon,
} from "@phosphor-icons/react";
import { getOverview, errorMessage, formatNumber } from "@/lib/api";
import { demoOverview } from "@/lib/demo";
import type { Filters, Overview } from "@/lib/types";
import { AppShell } from "./app-shell";
import { FilterBar } from "./filters";
import { TrendChart, DistributionChart, SexChart } from "./charts";
import { JobTable } from "./job-table";
import { EmptyState, ErrorState, LoadingState } from "./ui";

export function initialFilters(demo: boolean): Filters {
  const end = demo
    ? "2026-09-20"
    : new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Taipei",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date());
  const start = new Date(`${end}T12:00:00+08:00`);
  start.setUTCDate(start.getUTCDate() - 6);
  return { start_date: start.toISOString().slice(0, 10), end_date: end };
}
export function Dashboard({ demo }: { demo: boolean }) {
  const [filters, setFilters] = useState<Filters>(() => initialFilters(demo));
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [ponds, setPonds] = useState<string[]>([]);
  const reload = useCallback(() => setRevision((r) => r + 1), []);
  const demoData = useMemo(
    () => (demo ? demoOverview(filters) : null),
    [demo, filters],
  );
  useEffect(() => {
    if (demo) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const next = await getOverview(filters, controller.signal);
        setData(next);
        setPonds((p) => [...new Set([...p, ...next.available_ponds])].sort());
        setError("");
        // Inbox uploads may arrive while this dashboard is already open.
        timer = setTimeout(
          () => load(true),
          next.summary.processing > 0 ? 4000 : 15000,
        );
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [demo, filters, revision]);
  const overview = demo ? demoData : data;
  const availablePonds = demo ? ["A-01", "B-02"] : ponds;
  return (
    <AppShell demo={demo}>
      <div className="page-heading">
        <div>
          <p className="page-kicker">蝦隻影像分析</p>
          <h1>分析總覽</h1>
          <p>查看各日期與池別的個體數、體型估計和水色分類。</p>
        </div>
        <Link
          href={`/upload${demo ? "?demo=1" : ""}`}
          className="button button-dark"
        >
          <UploadSimpleIcon size={19} />
          新增分析
        </Link>
      </div>
      <FilterBar
        filters={filters}
        onChange={setFilters}
        ponds={availablePonds}
        demo={demo}
      />
      {!demo && loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} retry={reload} />
      ) : overview && overview.summary.jobs_total === 0 ? (
        <EmptyState filtered={Object.values(filters).some(Boolean)} />
      ) : (
        overview && (
          <>
            <div className="stats-grid stats-grid-measurements">
              {[
                {
                  title: "追蹤個體",
                  value: overview.summary.shrimp_count,
                  unit: "隻",
                  icon: CrosshairIcon,
                  hint: "各影片追蹤 ID 加總",
                  digits: 0,
                },
                {
                  title: "平均估計長度",
                  value: overview.summary.avg_length_mm,
                  unit: "mm",
                  icon: RulerIcon,
                  hint: "依有效個體資料計算",
                  digits: 1,
                },
                {
                  title: "平均估計寬度",
                  value: overview.summary.avg_width_mm,
                  unit: "mm",
                  icon: ArrowsHorizontalIcon,
                  hint: "以偵測框短邊換算",
                  digits: 1,
                },
                {
                  title: "平均估計重量",
                  value: overview.summary.avg_weight_g,
                  unit: "g",
                  icon: ScalesIcon,
                  hint: "依有效個體資料計算",
                  digits: 1,
                },
                {
                  title: "已完成影片",
                  value: overview.summary.completed,
                  unit: "段",
                  icon: VideoCameraIcon,
                  hint: overview.summary.processing
                    ? `${overview.summary.processing} 段正在分析`
                    : "影片分析記錄",
                  digits: 0,
                },
              ].map(({ title, value, unit, icon: Icon, hint, digits }, i) => (
                <section
                  className={`stat-card ${i === 0 ? "stat-featured" : ""}`}
                  key={title}
                >
                  <div className="stat-title">
                    {title}
                    <Icon size={21} />
                  </div>
                  <div
                    className={`stat-value ${value == null ? "stat-value-empty" : ""}`}
                  >
                    {formatNumber(value, digits)}
                    {value != null && <span>{unit}</span>}
                  </div>
                  <p>
                    {i === 0 ? (
                      <CrosshairIcon size={13} />
                    ) : title === "已完成影片" ? (
                      <CheckCircleIcon size={13} />
                    ) : null}
                    {hint}
                  </p>
                </section>
              ))}
            </div>
            <div className="dashboard-charts">
              <TrendChart data={overview.daily} />
              <section className="water-panel">
                <div className="water-panel-top">
                  <DropIcon size={26} />
                  <span>水色分類</span>
                </div>
                <h2>
                  影片中的水色
                  <br />
                  清澈還是混濁？
                </h2>
                <div className="water-numbers">
                  <div>
                    <strong>{overview.summary.clear_count}</strong>
                    <span>清澈影片</span>
                  </div>
                  <div>
                    <strong>{overview.summary.turbid_count}</strong>
                    <span>混濁影片</span>
                  </div>
                </div>
                <p>
                  由影像分類清澈與混濁，
                  <br />
                  不等同溶氧、酸鹼值等實測水質。
                </p>
                <Link href={`/recordings${demo ? "?demo=1" : ""}`}>
                  查看分析影片
                  <ArrowUpRightIcon size={18} />
                </Link>
              </section>
            </div>
            <div className="distribution-grid">
              <DistributionChart data={overview.distributions} />
              <SexChart data={overview.sex} />
            </div>
            <section className="recordings-panel">
              <div className="panel-heading">
                <div>
                  <h2>最近分析影片</h2>
                  <p>查看處理狀態、個體數與水色分類。</p>
                </div>
                <Link
                  href={`/recordings${demo ? "?demo=1" : ""}`}
                  className="text-link"
                >
                  全部記錄
                  <ArrowRightIcon size={17} />
                </Link>
              </div>
              <JobTable jobs={overview.recent_jobs} demo={demo} />
            </section>
            <p className="measurement-note">
              長度與重量依模型與拍攝尺度估計，OBB
              短邊用作寬度代理；更換相機或拍攝距離後，請先完成尺度校正。
            </p>
          </>
        )
      )}
    </AppShell>
  );
}
