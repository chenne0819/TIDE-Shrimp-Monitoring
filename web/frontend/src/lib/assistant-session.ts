import type { AssistantTransport } from "./assistant-api";
import type {
  AssistantCapabilities,
  AssistantConversation,
  AssistantDetail,
  AssistantMessage,
} from "./assistant-types";

export function isPending(message: AssistantMessage) {
  return (
    message.role === "assistant" &&
    ["planning", "querying", "answering"].includes(message.status)
  );
}
export type AssistantState = {
  capabilities: AssistantCapabilities | null;
  conversations: AssistantConversation[];
  detail: AssistantDetail | null;
  loading: boolean;
  sending: boolean;
  sendingStartedAt: number | null;
  cancelling: boolean;
  error: string | null;
  retryable: boolean;
};
export const initialAssistantState: AssistantState = {
  capabilities: null,
  conversations: [],
  detail: null,
  loading: true,
  sending: false,
  sendingStartedAt: null,
  cancelling: false,
  error: null,
  retryable: false,
};

/** One request scope per selected conversation. Stale promises cannot replace a newer view. */
export function createAssistantSession(options: {
  demo: boolean;
  transport: AssistantTransport;
  onChange: (state: AssistantState) => void;
  uuid?: () => string;
  schedule?: (
    callback: () => void,
    delay: number,
  ) => ReturnType<typeof setTimeout>;
  unschedule?: (id: ReturnType<typeof setTimeout>) => void;
}) {
  const { transport } = options;
  const schedule = options.schedule ?? setTimeout;
  const unschedule = options.unschedule ?? clearTimeout;
  let state = { ...initialAssistantState };
  let alive = true;
  let scope = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let retryRequest: { message: string; requestId: string } | null = null;
  let polling = false;
  let detailRevision = 0;
  const emit = (patch: Partial<AssistantState>) => {
    if (!alive) return;
    state = { ...state, ...patch };
    options.onChange(state);
  };
  const valid = (signal: AbortSignal) =>
    alive && !signal.aborted && signal === scope.signal;
  const resetScope = () => {
    scope.abort();
    scope = new AbortController();
    if (timer !== undefined) unschedule(timer);
    timer = undefined;
    polling = false;
    detailRevision += 1;
    retryRequest = null;
    return scope.signal;
  };
  const describe = (error: unknown) =>
    error instanceof Error ? error.message : "讀取失敗，請稍後重試。";
  const accept = (detail: AssistantDetail) => {
    const conversation = {
      id: detail.id,
      title: detail.title,
      demo: detail.demo,
      created_at: detail.created_at,
      updated_at: detail.updated_at,
    };
    emit({
      detail,
      conversations: [
        conversation,
        ...state.conversations.filter((item) => item.id !== detail.id),
      ],
    });
  };
  const queuePoll = (signal: AbortSignal) => {
    if (
      !valid(signal) ||
      state.cancelling ||
      timer !== undefined ||
      !state.detail?.messages.some(isPending)
    )
      return;
    timer = schedule(() => {
      timer = undefined;
      if (state.cancelling || !state.detail?.messages.some(isPending)) return;
      void refresh(signal);
    }, 1500);
  };
  const refresh = async (signal = scope.signal) => {
    if (!valid(signal) || !state.detail || polling || state.cancelling) return;
    if (timer !== undefined) unschedule(timer);
    timer = undefined;
    polling = true;
    const id = state.detail.id;
    const revision = detailRevision;
    try {
      const detail = await transport.detail(id, signal);
      if (!valid(signal) || revision !== detailRevision) return;
      accept(detail);
      if (!retryRequest) emit({ error: null });
    } catch (error) {
      if (valid(signal) && revision === detailRevision)
        emit({
          error: `狀態更新中斷：${describe(error)} 可重新整理對話；伺服器上的分析可能仍在進行。`,
        });
    } finally {
      if (valid(signal)) {
        polling = false;
        queuePoll(signal);
      }
    }
  };
  const select = async (id: string | null) => {
    // A new-view action must not abort the capabilities request that enables the composer.
    if (!alive || !state.capabilities) return;
    const signal = resetScope();
    emit({
      detail: null,
      loading: Boolean(id),
      sending: false,
      sendingStartedAt: null,
      cancelling: false,
      error: null,
      retryable: false,
    });
    if (!id) return;
    try {
      const detail = await transport.detail(id, signal);
      if (!valid(signal)) return;
      accept(detail);
      emit({ loading: false });
      queuePoll(signal);
    } catch (error) {
      if (valid(signal)) emit({ loading: false, error: describe(error) });
    }
  };
  const start = async () => {
    const signal = resetScope();
    emit({ ...initialAssistantState, conversations: state.conversations });
    try {
      const [capabilities, list] = await Promise.all([
        transport.capabilities(options.demo, signal),
        transport.conversations(options.demo, signal),
      ]);
      if (!valid(signal)) return;
      emit({ capabilities, conversations: list.items, loading: false });
    } catch (error) {
      if (valid(signal)) emit({ loading: false, error: describe(error) });
    }
  };
  const send = async (text: string, repeat = false) => {
    const message = text.trim();
    if (
      !alive ||
      state.loading ||
      state.sending ||
      state.cancelling ||
      state.detail?.messages.some(isPending) ||
      !state.capabilities?.enabled ||
      !message ||
      message.length > 2000 ||
      (retryRequest && !repeat)
    )
      return false;
    const request =
      repeat && retryRequest
        ? retryRequest
        : {
            message,
            requestId: (options.uuid ?? (() => crypto.randomUUID()))(),
          };
    const signal = scope.signal;
    detailRevision += 1;
    emit({
      sending: true,
      sendingStartedAt: Date.now(),
      error: null,
      retryable: false,
    });
    try {
      let detail = state.detail;
      if (!detail) {
        const conversation = await transport.create(options.demo, signal);
        if (!valid(signal)) return false;
        detail = { ...conversation, messages: [] };
        accept(detail);
      }
      // Retain this id until an acknowledgement arrives. Retrying a dropped response is idempotent.
      retryRequest = request;
      const reply = await transport.send(
        detail.id,
        request.message,
        request.requestId,
        signal,
      );
      if (!valid(signal)) return false;
      retryRequest = null;
      const messages = detail.messages.some((item) => item.id === reply.id)
        ? detail.messages
        : [...detail.messages, reply];
      accept({ ...detail, messages });
      emit({ sending: false, retryable: false });
      await refresh(signal);
      return valid(signal);
    } catch (error) {
      if (valid(signal)) {
        // No invented user/assistant history: the next refresh reads the persisted records.
        emit({
          sending: false,
          error: `${describe(error)}${retryRequest ? " 尚未確認送出結果；重試會沿用同一請求編號，避免重複分析。" : ""}`,
          retryable: Boolean(retryRequest),
        });
      }
      return false;
    }
  };
  const cancel = async () => {
    const pending = state.detail?.messages.find(isPending);
    if (!pending || state.cancelling || state.sending) return;
    const signal = scope.signal;
    detailRevision += 1;
    if (timer !== undefined) unschedule(timer);
    timer = undefined;
    emit({ cancelling: true, error: null });
    try {
      const cancelled = await transport.cancel(pending.id, signal);
      if (!valid(signal) || !state.detail) return;
      detailRevision += 1;
      accept({
        ...state.detail,
        messages: state.detail.messages.map((item) =>
          item.id === cancelled.id ? cancelled : item,
        ),
      });
      if (timer !== undefined) unschedule(timer);
      timer = undefined;
      emit({ cancelling: false });
      await refresh(signal);
    } catch (error) {
      if (valid(signal)) emit({ error: `尚未確認停止：${describe(error)}` });
    } finally {
      if (valid(signal)) {
        emit({ cancelling: false });
        queuePoll(signal);
      }
    }
  };
  return {
    start,
    select,
    send,
    cancel,
    refresh: () => refresh(),
    retry: () =>
      retryRequest ? send(retryRequest.message, true) : Promise.resolve(false),
    destroy: () => {
      alive = false;
      resetScope();
    },
  };
}
export type AssistantSession = ReturnType<typeof createAssistantSession>;
