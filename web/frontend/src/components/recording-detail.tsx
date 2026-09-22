"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  DownloadSimpleIcon,
  FilmStripIcon,
  ArrowClockwiseIcon,
  ClockIcon,
  InfoIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import {
  errorMessage,
  formatDate,
  formatNumber,
  getJob,
  mediaUrl,
  retryJob,
} from "@/lib/api";
import { demoJobs } from "@/lib/demo";
import type { JobDetail } from "@/lib/types";
import { AppShell } from "./app-shell";
import { ErrorState, LoadingState, StatusBadge, WaterBadge } from "./ui";

function VideoPlayer({ job, demo }: { job: JobDetail; demo: boolean }) {
  const [kind, setKind] = useState<"source" | "result">(
    job.result_video_url ? "result" : "source",
  );
  const [videoError, setVideoError] = useState(false);
  const source =
    kind === "result" ? job.result_video_url : job.source_video_url;
  return (
    <section className="video-panel">
      <div className="panel-heading">
        <div>
          <h2>{demo ? "合成資料示範" : "觀察畫面"}</h2>
          <p>
            {demo
              ? "示範數值不對應實際拍攝影片"
              : "原始影像與標記結果，隨時對照"}
          </p>
        </div>
        <div className="segmented" role="group" aria-label="影片版本">
          <button
            disabled={!job.source_video_url}
            className={kind === "source" ? "selected" : ""}
            aria-pressed={kind === "source"}
            onClick={() => {
              setKind("source");
              setVideoError(false);
            }}
          >
            原始影片
          </button>
          <button
            disabled={!job.result_video_url}
            className={kind === "result" ? "selected" : ""}
            aria-pressed={kind === "result"}
            onClick={() => {
              setKind("result");
              setVideoError(false);
            }}
          >
            標記結果
          </button>
        </div>
      </div>
      <div className="video-stage">
        {source && !videoError ? (
          <video
            key={source}
            controls
            playsInline
            preload="metadata"
            poster={mediaUrl(job.thumbnail_url)}
            src={mediaUrl(source)}
            onError={() => setVideoError(true)}
            aria-label={kind === "result" ? "標記結果影片" : "原始觀察影片"}
          />
        ) : (
          <div className="video-placeholder">
            <FilmStripIcon size={45} weight="light" />
            <p>
              {videoError
                ? "瀏覽器暫時無法播放這段影片"
                : demo
                  ? "這是合成示範資料，未附實際影片或縮圖"
                  : "影片準備完成後，會顯示在這裡"}
            </p>
            {videoError && source && (
              <a
                href={mediaUrl(source)}
                target="_blank"
                rel="noreferrer"
                className="button button-small"
              >
                開啟影片檔
                <ArrowRightIcon size={16} />
              </a>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
export function RecordingDetail({ id, demo }: { id: string; demo: boolean }) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const [page, setPage] = useState(0);
  const reload = useCallback(() => setRevision((r) => r + 1), []);
  useEffect(() => {
    if (demo) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const next = await getJob(id, controller.signal);
        setJob(next);
        setError("");
        if (next.status === "processing" || next.status === "queued")
          timer = setTimeout(load, 2500);
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
  }, [id, demo, revision]);
  const current = demo ? demoJobs.find((j) => j.id === id) : job;
  const csvArtifact =
    current?.artifacts.find((artifact) => artifact.kind === "tracks") ??
    current?.artifacts.find(
      (artifact) =>
        artifact.kind === "detections" ||
        artifact.kind.includes("csv") ||
        artifact.url.endsWith(".csv"),
    );
  const retry = async () => {
    setRetrying(true);
    try {
      await retryJob(id);
      reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRetrying(false);
    }
  };
  const demoCsv = () => {
    if (!current) return;
    const csv =
      "\uFEFF示範資料（非實際推論結果）\ntrack_id,sex,length_mm,width_mm,weight_g\n" +
      current.tracks
        .map(
          (t) =>
            `${t.track_id},${t.label},${t.length_mm},${t.width_mm},${t.weight_g}`,
        )
        .join("\n");
    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "TIDE-demo-tracks.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <AppShell demo={demo}>
      <Link href={`/recordings${demo ? "?demo=1" : ""}`} className="back-link">
        <ArrowLeftIcon size={17} />
        返回影像記錄
      </Link>
      {!demo && loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} retry={reload} />
      ) : !current ? (
        <div className="state-panel">
          <h1>找不到這筆觀察</h1>
          <Link
            href={`/recordings${demo ? "?demo=1" : ""}`}
            className="button button-dark"
          >
            返回影像記錄
          </Link>
        </div>
      ) : (
        <>
          <div className="page-heading detail-heading">
            <div>
              <p className="page-kicker">
                {current.pond} 養殖池 / {formatDate(current.recorded_at, true)}
              </p>
              <h1>{current.filename}</h1>
              <div className="detail-status">
                <StatusBadge status={current.status} />
                <span>
                  {current.mode === "head_tail"
                    ? "頭尾追蹤"
                    : current.mode === "predict"
                      ? "單幀分析"
                      : "一般個體追蹤"}
                </span>
              </div>
            </div>
            {demo ? (
              <button className="button" onClick={demoCsv}>
                <DownloadSimpleIcon size={19} />
                下載示範 CSV
              </button>
            ) : csvArtifact ? (
              <a href={mediaUrl(csvArtifact.url)} className="button">
                <DownloadSimpleIcon size={19} />
                匯出 CSV
              </a>
            ) : null}
          </div>
          {(current.status === "queued" || current.status === "processing") && (
            <div className="processing-notice" role="status">
              <ClockIcon size={25} />
              <div>
                <strong>
                  {current.status === "queued"
                    ? "影片已收到，等待背景分析"
                    : "正在分析你的觀察影片"}
                </strong>
                <p>畫面會自動更新，你可以先回到工作台。</p>
              </div>
              <span>{current.progress}%</span>
              <progress
                value={current.progress}
                max={100}
                aria-label="分析進度"
              />
            </div>
          )}
          {(current.status === "failed" || current.status === "stopped") && (
            <div className="notice warning">
              <WarningCircleIcon size={25} />
              <div>
                <strong>
                  {current.status === "stopped"
                    ? "這次分析已停止"
                    : "這次分析未能完成"}
                </strong>
                <p>{current.error || "水質政策或分析程序停止了這項工作。"}</p>
              </div>
              {!demo && (
                <button
                  className="button button-small"
                  disabled={retrying}
                  onClick={retry}
                >
                  <ArrowClockwiseIcon size={16} />
                  {retrying ? "正在建立…" : "重新分析"}
                </button>
              )}
            </div>
          )}
          <div className="detail-layout">
            <VideoPlayer
              key={`${current.id}-${Boolean(current.result_video_url)}`}
              job={current}
              demo={demo}
            />
            <aside className="observation-summary">
              <div className="panel-heading">
                <h2>這次觀察</h2>
              </div>
              <div className="observation-count">
                <strong>{formatNumber(current.shrimp_count, 0)}</strong>
                <span>追蹤個體</span>
              </div>
              <dl>
                <div>
                  <dt>平均估計長度</dt>
                  <dd>
                    {formatNumber(current.avg_length_mm)}
                    <span>{current.avg_length_mm == null ? "" : "mm"}</span>
                  </dd>
                </div>
                <div>
                  <dt>平均估計寬度</dt>
                  <dd>
                    {formatNumber(current.avg_width_mm)}
                    <span>{current.avg_width_mm == null ? "" : "mm"}</span>
                  </dd>
                </div>
                <div>
                  <dt>平均估計重量</dt>
                  <dd>
                    {formatNumber(current.avg_weight_g)}
                    <span>{current.avg_weight_g == null ? "" : "g"}</span>
                  </dd>
                </div>
                <div>
                  <dt>水質判讀</dt>
                  <dd>
                    <WaterBadge label={current.water_label} />
                  </dd>
                </div>
                <div>
                  <dt>分類信心值</dt>
                  <dd>
                    {current.water_confidence == null
                      ? "尚無資料"
                      : `${formatNumber(current.water_confidence * 100)}%`}
                  </dd>
                </div>
                <div>
                  <dt>已處理影格</dt>
                  <dd>{formatNumber(current.processed_frames, 0)}</dd>
                </div>
              </dl>
              <p>
                <InfoIcon size={17} />
                水質僅表示影像分類，尺寸依既有拍攝尺度估計。
              </p>
            </aside>
          </div>
          <section className="recordings-panel track-panel">
            <div className="panel-heading">
              <div>
                <h2>
                  個體觀察記錄
                  <span className="count-label">
                    {current.tracks.length} 個 ID
                  </span>
                </h2>
                <p>同一影片內，依追蹤 ID 整理觀測與體型估計</p>
              </div>
            </div>
            {current.tracks.length ? (
              <>
                <div className="table-scroll">
                  <table className="track-table">
                    <thead>
                      <tr>
                        <th>追蹤 ID</th>
                        <th>性別判定</th>
                        <th>觀測次數</th>
                        <th>估計長度 (mm)</th>
                        <th>寬度代理 (mm)</th>
                        <th>估計重量 (g)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {current.tracks
                        .slice(page * 15, (page + 1) * 15)
                        .map((track) => (
                          <tr key={track.track_id}>
                            <td className="mono">#{track.track_id}</td>
                            <td>
                              {track.label === "Male"
                                ? "公蝦"
                                : track.label === "Female"
                                  ? "母蝦"
                                  : "未判定"}
                            </td>
                            <td>{track.observations}</td>
                            <td>{formatNumber(track.length_mm)}</td>
                            <td>{formatNumber(track.width_mm)}</td>
                            <td>{formatNumber(track.weight_g)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <div className="pagination">
                  <span>
                    第 {page * 15 + 1} –{" "}
                    {Math.min((page + 1) * 15, current.tracks.length)} 筆
                  </span>
                  <div>
                    <button
                      className="button button-small"
                      disabled={!page}
                      onClick={() => setPage(page - 1)}
                    >
                      <ArrowLeftIcon size={15} />
                      上一頁
                    </button>
                    <button
                      className="button button-small"
                      disabled={(page + 1) * 15 >= current.tracks.length}
                      onClick={() => setPage(page + 1)}
                    >
                      下一頁
                      <ArrowRightIcon size={15} />
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="no-tracks">
                <FilmStripIcon size={28} />
                <p>
                  {current.status === "completed"
                    ? "這次分析沒有偵測到可追蹤的個體。"
                    : "分析完成後，個體記錄會顯示在這裡。"}
                </p>
              </div>
            )}
          </section>
          <details className="metadata-details">
            <summary>分析來源與完整輸出</summary>
            <p>
              工作 ID：<code>{current.id}</code>
            </p>
            {current.artifacts.length > 0 && (
              <div className="artifact-links">
                {current.artifacts.map((artifact) => (
                  <a
                    key={artifact.kind}
                    href={mediaUrl(artifact.url)}
                    className="button button-small"
                  >
                    <DownloadSimpleIcon size={15} />
                    {artifact.label}
                  </a>
                ))}
              </div>
            )}
            <pre>{JSON.stringify(current.metadata, null, 2)}</pre>
          </details>
        </>
      )}
    </AppShell>
  );
}
