"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRightIcon,
  CloudArrowUpIcon,
  FilmStripIcon,
  InfoIcon,
  XIcon,
} from "@phosphor-icons/react";
import {
  errorMessage,
  uploadJob,
  UploadError,
  type UploadPhase,
} from "@/lib/api";
import { AppShell } from "./app-shell";
import { DateField } from "./date-field";
const videoExtensions = /\.(mp4|mov|avi|mkv|m4v|webm)$/i;
function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export function Upload({ demo }: { demo: boolean }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const cancelRef = useRef<(() => boolean) | null>(null);
  const mounted = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState("");
  const [pond, setPond] = useState("A-01");
  const [recorded, setRecorded] = useState(localDateTime);
  const [mode, setMode] = useState("general");
  const [policy, setPolicy] = useState("report");
  const [limit, setLimit] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("preparing");
  const [uncertainOutcome, setUncertainOutcome] = useState(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancelRef.current?.();
    };
  }, []);
  const choose = (candidate?: File) => {
    if (!candidate) return;
    if (!videoExtensions.test(candidate.name)) {
      setError("請選擇 MP4、MOV、AVI、MKV、M4V 或 WebM 影片。");
      return;
    }
    if (!candidate.size) {
      setError("這個檔案是空的，請選擇其他影片。");
      return;
    }
    setFile(candidate);
    setError("");
  };
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (demo || uploading || uncertainOutcome) return;
    if (!file) {
      setError("請先選擇一段影片。");
      input.current?.focus();
      return;
    }
    const recordedAt = new Date(recorded);
    if (!Number.isFinite(recordedAt.getTime())) {
      setError("請填寫有效的拍攝日期與時間。");
      return;
    }
    setUploading(true);
    setError("");
    setProgress(0);
    setUploadPhase("preparing");
    const data = new FormData();
    data.append("file", file);
    data.append("pond", pond.trim());
    data.append("recorded_at", recordedAt.toISOString());
    data.append("mode", mode);
    data.append("water_policy", policy);
    if (limit) data.append("max_frames", limit);
    const upload = uploadJob(
      data,
      (value) => {
        if (mounted.current) setProgress(value);
      },
      (phase) => {
        if (mounted.current) setUploadPhase(phase);
      },
    );
    cancelRef.current = upload.cancel;
    try {
      const job = await upload.promise;
      cancelRef.current = null;
      if (mounted.current)
        router.push(`/recordings/${encodeURIComponent(job.id)}`);
    } catch (e) {
      if (mounted.current) {
        setError(errorMessage(e));
        setUncertainOutcome(
          e instanceof UploadError && e.outcome === "unknown",
        );
      }
    } finally {
      if (mounted.current) setUploading(false);
      cancelRef.current = null;
    }
  };
  return (
    <AppShell demo={demo}>
      <div className="page-heading">
        <div>
          <p className="page-kicker">新的觀察，從一段影片開始</p>
          <h1>新增分析</h1>
          <p>保留拍攝脈絡，讓後續比較更有意義。</p>
        </div>
      </div>
      {demo && (
        <div className="notice">
          <InfoIcon size={22} />
          <div>
            <strong>示範模式不會接收影片</strong>
            <p>切換到真實工作區，即可上傳並建立分析工作。</p>
          </div>
          <Link href="/upload" className="button button-small">
            前往上傳
            <ArrowRightIcon size={16} />
          </Link>
        </div>
      )}
      <form className="upload-layout" onSubmit={submit}>
        <section
          className="upload-card upload-media"
          aria-labelledby="upload-video-heading"
        >
          <fieldset disabled={demo || uploading}>
            <div className="form-section-heading">
              <h2 id="upload-video-heading">觀察影片</h2>
              <span>在本機背景處理</span>
            </div>
            <div
              className={`dropzone ${drag ? "dragging" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                if (!demo && !uploading) setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                if (!demo && !uploading) choose(e.dataTransfer.files[0]);
              }}
            >
              <input
                ref={input}
                id="video-file"
                type="file"
                accept=".mp4,.mov,.avi,.mkv,.m4v,.webm,video/*"
                onChange={(e) => choose(e.target.files?.[0])}
                className="sr-only"
              />
              {file ? (
                <>
                  <FilmStripIcon size={42} />
                  <strong>{file.name}</strong>
                  <p>{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                  <button
                    type="button"
                    className="button button-small"
                    onClick={() => input.current?.click()}
                  >
                    選擇其他影片
                  </button>
                </>
              ) : (
                <>
                  <CloudArrowUpIcon size={48} weight="light" />
                  <h3>把觀察影片拖曳到這裡</h3>
                  <p>或從電腦選擇檔案</p>
                  <label
                    htmlFor="video-file"
                    className={`button button-dark ${demo ? "disabled" : ""}`}
                  >
                    選擇影片
                  </label>
                  <span>支援 MP4、MOV、AVI、MKV、M4V、WebM</span>
                </>
              )}
            </div>
          </fieldset>
        </section>
        <section
          className="upload-card upload-settings"
          aria-labelledby="upload-settings-heading"
        >
          <fieldset disabled={demo || uploading}>
            <div className="form-section-heading">
              <h2 id="upload-settings-heading">拍攝資訊</h2>
            </div>
            <div className="form-grid">
              <label className="form-field form-field-wide">
                養殖池名稱
                <input
                  value={pond}
                  onChange={(e) => setPond(e.target.value)}
                  required
                  maxLength={80}
                  placeholder="例如 A-01"
                />
              </label>
              <div className="form-field">
                <span>拍攝日期</span>
                <DateField
                  label="拍攝日期"
                  required
                  value={recorded.split("T")[0]}
                  onChange={(date) =>
                    setRecorded(`${date}T${recorded.split("T")[1] || "00:00"}`)
                  }
                  disabled={demo || uploading}
                />
                <small>依你瀏覽器的本地時區儲存</small>
              </div>
              <label className="form-field">
                拍攝時間（24 小時制）
                <input
                  type="text"
                  placeholder="HH:mm"
                  pattern="([01][0-9]|2[0-3]):[0-5][0-9]"
                  title="請輸入 24 小時制時間，例如 08:30"
                  maxLength={5}
                  required
                  value={recorded.split("T")[1] || ""}
                  onChange={(e) =>
                    setRecorded(`${recorded.split("T")[0]}T${e.target.value}`)
                  }
                />
              </label>
              <label className="form-field form-field-wide">
                分析模式
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="general">一般追蹤（OBB + HBB）</option>
                  <option value="head_tail">頭尾追蹤（OBB + 分類）</option>
                  <option value="predict">單幀分析</option>
                </select>
              </label>
              <label className="form-field form-field-wide">
                發現混濁時
                <select
                  value={policy}
                  onChange={(e) => setPolicy(e.target.value)}
                >
                  <option value="report">記錄水質並繼續分析</option>
                  <option value="stop">停止分析，保留判讀結果</option>
                </select>
              </label>
            </div>
            <details className="advanced-options">
              <summary>進階設定</summary>
              <label className="form-field">
                測試用影格上限
                <input
                  type="number"
                  min={1}
                  step={1}
                  placeholder="留空分析整段影片"
                  value={limit}
                  onChange={(e) => setLimit(e.target.value)}
                />
                <small>只有測試時才需要限制影格；正式分析請留空。</small>
              </label>
            </details>
          </fieldset>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {uncertainOutcome && (
            <div className="notice warning" role="status">
              <InfoIcon size={22} />
              <div>
                <strong>請先確認是否已有分析工作</strong>
                <p>
                  停止傳送或連線中斷，無法保證伺服器取消了工作。先查看影像記錄，避免同一影片重複分析。
                </p>
                <Link href="/recordings" className="text-link">
                  查看影像記錄
                  <ArrowRightIcon size={15} />
                </Link>
              </div>
              <button
                type="button"
                className="button button-small"
                onClick={() => {
                  setUncertainOutcome(false);
                  setError("");
                }}
              >
                已確認無記錄，允許重傳
              </button>
            </div>
          )}
          {uploading && (
            <div className="upload-progress" role="status">
              <div>
                <strong>
                  {uploadPhase === "preparing"
                    ? "正在確認分析服務，影片尚未送出"
                    : uploadPhase === "awaiting-response"
                      ? "影片已送出，正在確認分析工作"
                      : "影片傳送中"}
                </strong>
                <span>{progress}%</span>
              </div>
              <progress max={100} value={progress} aria-label="影片上傳進度" />
              {(uploadPhase === "preparing" ||
                uploadPhase === "transferring") && (
                <button
                  type="button"
                  className="text-link"
                  onClick={() => cancelRef.current?.()}
                >
                  <XIcon size={14} />
                  {uploadPhase === "preparing" ? "取消準備" : "停止傳送"}
                </button>
              )}
            </div>
          )}
          <div className="form-submit">
            <p>分析完成後，結果會保存在工作台。</p>
            <button
              type="submit"
              className="button button-dark"
              disabled={demo || uploading || uncertainOutcome}
            >
              {uploading ? "正在上傳…" : "開始分析"}
              <ArrowRightIcon size={19} />
            </button>
          </div>
        </section>
      </form>
    </AppShell>
  );
}
