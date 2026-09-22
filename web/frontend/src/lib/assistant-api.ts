import { api } from "./api";
import type {
  AssistantCapabilities,
  AssistantConversation,
  AssistantDetail,
  AssistantMessage,
} from "./assistant-types";

// One deadline covers CSRF bootstrap, response headers and the complete JSON body.
// Abort only this request: the conversation scope must remain usable for retries.
async function request<T>(
  path: string,
  init: RequestInit & { signal: AbortSignal },
) {
  const scope = init.signal;
  scope.throwIfAborted();
  const controller = new AbortController();
  const forwardAbort = () => controller.abort(scope.reason);
  scope.addEventListener("abort", forwardAbort, { once: true });
  const timer = setTimeout(
    () =>
      controller.abort(
        new Error(
          "等待分析服務回應逾時，請重試或重新整理對話。伺服器上的分析可能仍在進行。",
        ),
      ),
    30_000,
  );
  let rejectAbort: () => void = () => {};
  const aborted = new Promise<never>((_, reject) => {
    rejectAbort = () => reject(controller.signal.reason);
    controller.signal.addEventListener("abort", rejectAbort, { once: true });
  });
  try {
    return await Promise.race([
      api<T>(path, { ...init, signal: controller.signal }),
      aborted,
    ]);
  } finally {
    clearTimeout(timer);
    scope.removeEventListener("abort", forwardAbort);
    controller.signal.removeEventListener("abort", rejectAbort);
  }
}

export const assistantApi = {
  capabilities: (demo: boolean, signal: AbortSignal) =>
    request<AssistantCapabilities>(
      `/assistant/capabilities${demo ? "?demo=1" : ""}`,
      { signal },
    ),
  conversations: (demo: boolean, signal: AbortSignal) =>
    request<{ items: AssistantConversation[] }>(
      `/assistant/conversations${demo ? "?demo=1" : ""}`,
      { signal },
    ),
  create: (demo: boolean, signal: AbortSignal) =>
    request<AssistantConversation>("/assistant/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demo }),
      signal,
    }),
  detail: (id: string, signal: AbortSignal) =>
    request<AssistantDetail>(
      `/assistant/conversations/${encodeURIComponent(id)}`,
      {
        signal,
      },
    ),
  send: (id: string, message: string, requestId: string, signal: AbortSignal) =>
    request<AssistantMessage>(
      `/assistant/conversations/${encodeURIComponent(id)}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, request_id: requestId }),
        signal,
      },
    ),
  cancel: (id: string, signal: AbortSignal) =>
    request<AssistantMessage>(
      `/assistant/messages/${encodeURIComponent(id)}/cancel`,
      { method: "POST", signal },
    ),
};
export type AssistantTransport = typeof assistantApi;
