import type { Filters, Job, JobDetail, Overview } from "./types";

export const API_ORIGIN = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  return /^https?:\/\//.test(path) ? path : `${API_ORIGIN}${path}`;
}
export function query(filters: Filters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params.toString();
}
type LocalSession = { csrf_token: string; max_upload_bytes: number };

async function responseError(response: Response): Promise<string> {
  const data = await response.json().catch(() => null);
  return typeof data?.detail === "string"
    ? data.detail
    : `服務回應 ${response.status}，請稍後再試。`;
}

// Fetch a fresh token for each write; never persist it or expose it in env/config.
export async function getSession(signal?: AbortSignal): Promise<LocalSession> {
  const response = await fetch(`${API_ORIGIN}/api/session`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(await responseError(response));
  const session = (await response.json()) as Partial<LocalSession> | null;
  if (
    !session ||
    typeof session.csrf_token !== "string" ||
    !session.csrf_token ||
    !Number.isSafeInteger(session.max_upload_bytes) ||
    (session.max_upload_bytes ?? 0) <= 0
  ) {
    throw new Error("無法取得有效的分析服務工作階段，請稍後再試。");
  }
  return session as LocalSession;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const method = (init?.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const session = await getSession(init?.signal ?? undefined);
    init?.signal?.throwIfAborted();
    headers.set("X-Tide-CSRF", session.csrf_token);
  }
  const response = await fetch(`${API_ORIGIN}/api${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await responseError(response));
  return response.json() as Promise<T>;
}
export const getOverview = (filters: Filters, signal?: AbortSignal) =>
  api<Overview>(`/overview?${query(filters)}`, { signal });
export const getJobs = (filters: Filters, offset = 0, signal?: AbortSignal) =>
  api<{ items: Job[]; total: number }>(
    `/jobs?${query(filters)}&limit=12&offset=${offset}`,
    { signal },
  );
export const getJob = (id: string, signal?: AbortSignal) =>
  api<JobDetail>(`/jobs/${encodeURIComponent(id)}`, { signal });
export const retryJob = (id: string) =>
  api<Job>(`/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" });

export type UploadPhase =
  "preparing" | "transferring" | "awaiting-response" | "finished";
export class UploadError extends Error {
  constructor(
    message: string,
    public readonly outcome: "not-sent" | "rejected" | "unknown",
  ) {
    super(message);
    this.name = "UploadError";
  }
}

export function uploadJob(
  data: FormData,
  onProgress: (progress: number) => void,
  onPhaseChange?: (phase: UploadPhase) => void,
): { promise: Promise<Job>; cancel: () => boolean } {
  const bootstrap = new AbortController();
  let xhr: XMLHttpRequest | null = null;
  let phase: UploadPhase = "preparing";
  let settled = false;
  let cancelRequested = false;
  let rejectPromise: (error: UploadError) => void;
  const setPhase = (next: UploadPhase) => {
    phase = next;
    onPhaseChange?.(next);
  };
  const unknown = (message: string) =>
    new UploadError(
      `${message}無法確認伺服器是否已建立分析，請先查看影像記錄，避免重複上傳。`,
      "unknown",
    );
  const promise = new Promise<Job>((resolve, reject) => {
    const fail = (error: UploadError) => {
      if (settled) return;
      settled = true;
      setPhase("finished");
      reject(error);
    };
    rejectPromise = fail;
    const prepare = async () => {
      try {
        const session = await getSession(bootstrap.signal);
        // Some fetch implementations can resolve just as cancellation arrives.
        // Check after the await as well, so an aborted bootstrap never sends a POST.
        if (cancelRequested || settled || bootstrap.signal.aborted) return;
        const file = data.get("file");
        if (
          file &&
          typeof file !== "string" &&
          file.size > session.max_upload_bytes
        ) {
          fail(
            new UploadError(
              `影片超過服務限制（${formatNumber(session.max_upload_bytes / 1024 / 1024)} MB），尚未送出。`,
              "not-sent",
            ),
          );
          return;
        }
        const request = new XMLHttpRequest();
        xhr = request;
        request.open("POST", `${API_ORIGIN}/api/jobs`);
        request.setRequestHeader("X-Tide-CSRF", session.csrf_token);
        request.upload.onprogress = (event) => {
          if (
            !settled &&
            phase === "transferring" &&
            event.lengthComputable &&
            event.total > 0
          ) {
            onProgress(
              Math.min(99, Math.floor((event.loaded / event.total) * 100)),
            );
          }
        };
        request.upload.onload = () => {
          if (settled) return;
          // Only this event marks complete transport. Rounded progress does not.
          setPhase("awaiting-response");
          onProgress(100);
        };
        request.onload = () => {
          if (settled) return;
          let body: { id?: string; detail?: unknown } | null;
          try {
            body = JSON.parse(request.responseText);
          } catch {
            fail(unknown("無法讀取伺服器回應。"));
            return;
          }
          if (
            request.status >= 200 &&
            request.status < 300 &&
            typeof body?.id === "string"
          ) {
            settled = true;
            setPhase("finished");
            resolve(body as Job);
          } else if (request.status >= 400 && request.status < 500) {
            fail(
              new UploadError(
                typeof body?.detail === "string"
                  ? body.detail
                  : `上傳被拒絕（${request.status}）。`,
                "rejected",
              ),
            );
          } else {
            fail(unknown(`服務回應異常（${request.status}）。`));
          }
        };
        request.onerror = () => fail(unknown("傳輸連線中斷。"));
        request.ontimeout = () => fail(unknown("等待服務回應逾時。"));
        request.onabort = () => fail(unknown("已停止瀏覽器的影片傳送。"));
        setPhase("transferring");
        // Keep this guard even though the UI callback is normally synchronous.
        if (cancelRequested || settled) return;
        request.send(data);
      } catch (error) {
        if (!settled)
          fail(
            new UploadError(
              phase === "preparing"
                ? `${errorMessage(error)}影片尚未送出。`
                : "無法啟動影片傳送，請確認連線後重試。",
              "not-sent",
            ),
          );
      }
    };
    void prepare();
  });
  return {
    promise,
    cancel: () => {
      if (settled || phase === "awaiting-response") return false;
      cancelRequested = true;
      if (phase === "preparing") {
        bootstrap.abort();
        rejectPromise(
          new UploadError("已取消上傳準備，影片尚未送出。", "not-sent"),
        );
      } else {
        rejectPromise(unknown("已停止瀏覽器的影片傳送。"));
        xhr?.abort();
      }
      return true;
    },
  };
}
export function formatNumber(
  value: number | null | undefined,
  digits = 1,
): string {
  return value == null
    ? "尚無資料"
    : new Intl.NumberFormat("zh-TW", { maximumFractionDigits: digits }).format(
        value,
      );
}
export function formatDate(value: string, time = false): string {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    month: "2-digit",
    day: "2-digit",
    ...(time
      ? { hour: "2-digit", minute: "2-digit", hour12: false }
      : { year: "numeric" }),
  }).format(new Date(value));
}
export function errorMessage(error: unknown): string {
  return error instanceof TypeError
    ? "無法連線到分析服務，請確認 FastAPI 已啟動後再試一次。"
    : error instanceof Error
      ? error.message
      : "資料讀取失敗，請再試一次。";
}
