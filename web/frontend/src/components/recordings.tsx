"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  UploadSimpleIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
} from "@phosphor-icons/react";
import { errorMessage, getJobs, getOverview } from "@/lib/api";
import { filteredDemoJobs } from "@/lib/demo";
import type { Filters, Job } from "@/lib/types";
import { AppShell } from "./app-shell";
import { FilterBar } from "./filters";
import { initialFilters } from "./dashboard";
import { JobTable } from "./job-table";
import { EmptyState, ErrorState, LoadingState } from "./ui";
export function Recordings({ demo }: { demo: boolean }) {
  const [filters, setFilters] = useState<Filters>(() => initialFilters(demo));
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [ponds, setPonds] = useState<string[]>([]);
  const [pondsError, setPondsError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const samples = useMemo(() => filteredDemoJobs(filters), [filters]);
  useEffect(() => {
    if (demo) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let active = true;
    let inFlight = false;
    let refreshQueued = false;
    const load = async (silent = false) => {
      if (!active) return;
      if (inFlight) {
        refreshQueued = true;
        return;
      }
      inFlight = true;
      clearTimeout(timer);
      if (!silent) setLoading(true);
      let busy = false;
      try {
        const [jobs, overview] = await Promise.allSettled([
          getJobs(filters, offset, controller.signal),
          getOverview({}, controller.signal),
        ]);
        if (!active || controller.signal.aborted) return;
        if (jobs.status === "fulfilled") {
          setItems(jobs.value.items);
          setTotal(jobs.value.total);
          setError("");
          busy = jobs.value.items.some(
            (job) => job.status === "processing" || job.status === "queued",
          );
        } else {
          setError(errorMessage(jobs.reason));
        }
        if (overview.status === "fulfilled") {
          setPonds([...overview.value.available_ponds].sort());
          setPondsError(false);
          busy ||= overview.value.summary.processing > 0;
        } else {
          setPondsError(true);
        }
      } finally {
        inFlight = false;
        if (active && !controller.signal.aborted) {
          setLoading(false);
          // Idle/empty lists must still discover videos arriving through the inbox.
          timer = setTimeout(
            () => load(true),
            refreshQueued ? 0 : busy ? 4000 : 15000,
          );
          refreshQueued = false;
        }
      }
    };
    const refreshOnFocus = () => {
      void load(true);
    };
    window.addEventListener("focus", refreshOnFocus);
    void load();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, [demo, filters, offset, revision]);
  const count = demo ? samples.length : total;
  const jobs = demo ? samples.slice(offset, offset + 12) : items;
  return (
    <AppShell demo={demo}>
      <div className="page-heading">
        <div>
          <p className="page-kicker">每次觀察，都值得回看</p>
          <h1>影像記錄</h1>
          <p>找到影片，從畫面回到每一筆分析結果。</p>
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
        onChange={(next) => {
          setFilters(next);
          setOffset(0);
        }}
        ponds={demo ? ["A-01", "B-02"] : ponds}
        demo={demo}
      />
      {pondsError && !error && (
        <div className="notice" role="status">
          <p>池別選單暫時無法更新，系統會自動重試。</p>
          <button
            type="button"
            className="button button-small"
            onClick={() => setRevision((r) => r + 1)}
          >
            重新讀取
          </button>
        </div>
      )}
      {!demo && loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} retry={() => setRevision((r) => r + 1)} />
      ) : jobs.length === 0 ? (
        <EmptyState filtered={Object.values(filters).some(Boolean)} />
      ) : (
        <section className="recordings-panel">
          <div className="panel-heading">
            <h2>
              觀察清單<span className="count-label">{count} 段影片</span>
            </h2>
          </div>
          <JobTable jobs={jobs} demo={demo} />
          <div className="pagination">
            <span>
              第 {offset + 1} – {Math.min(offset + 12, count)} 筆，共 {count} 筆
            </span>
            <div>
              <button
                className="button button-small"
                disabled={offset === 0}
                onClick={() => setOffset(offset - 12)}
              >
                <ArrowLeftIcon size={16} />
                上一頁
              </button>
              <button
                className="button button-small"
                disabled={offset + 12 >= count}
                onClick={() => setOffset(offset + 12)}
              >
                下一頁
                <ArrowRightIcon size={16} />
              </button>
            </div>
          </div>
        </section>
      )}
    </AppShell>
  );
}
