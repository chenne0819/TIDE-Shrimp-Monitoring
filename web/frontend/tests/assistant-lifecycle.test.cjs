const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource, deferred, flush } = require("./helpers.cjs");

const { createAssistantSession } = loadSource("src/lib/assistant-session.ts");
const conversation = (id = "one") => ({
  id,
  title: id,
  demo: false,
  created_at: "2026-09-20T00:00:00Z",
  updated_at: "2026-09-20T00:00:00Z",
});
const message = (status = "planning", id = "answer") => ({
  id,
  role: "assistant",
  status,
  content: "",
  created_at: "2026-09-20T00:00:00Z",
  board: null,
  followups: [],
  error: null,
});
const detail = (id = "one", messages = []) => ({
  ...conversation(id),
  messages,
});
const capabilities = {
  enabled: true,
  today: "2026-09-20",
  timezone: "Asia/Taipei",
  available_ponds: [],
  templates: [],
};

function setup(overrides = {}, options = {}) {
  const changes = [],
    timers = new Map(),
    calls = [];
  let clockId = 0,
    uuidId = 0;
  const transport = {
    capabilities: async (demo) => {
      calls.push(["capabilities", demo]);
      return capabilities;
    },
    conversations: async (demo) => {
      calls.push(["conversations", demo]);
      return { items: [] };
    },
    create: async () => conversation(),
    detail: async (id) => detail(id),
    send: async () => message(),
    cancel: async () => message("cancelled"),
    ...overrides,
  };
  const session = createAssistantSession({
    demo: false,
    transport,
    onChange: (state) => changes.push(state),
    uuid: () => `request-${++uuidId}`,
    schedule: (callback, delay) => {
      assert.equal(delay, 1500);
      const id = ++clockId;
      timers.set(id, callback);
      return id;
    },
    unschedule: (id) => timers.delete(id),
    ...options,
  });
  return {
    session,
    changes,
    calls,
    timers,
    state: () => changes.at(-1),
    tick: async () => {
      const [id, callback] = timers.entries().next().value;
      timers.delete(id);
      callback();
      await flush();
    },
  };
}

test("disabled capabilities preserve history but never submit a model request", async () => {
  let sends = 0;
  const h = setup({
    capabilities: async () => ({
      ...capabilities,
      enabled: false,
      reason: "未設定",
    }),
    conversations: async () => ({ items: [conversation()] }),
    detail: async () => detail("one", [message("completed")]),
    send: async () => {
      sends++;
    },
  });
  await h.session.start();
  assert.equal(h.state().detail, null);
  assert.equal(h.state().conversations.length, 1);
  await h.session.select("one");
  assert.equal(h.state().detail.messages.length, 1);
  assert.equal(await h.session.send("今天的長度"), false);
  assert.equal(sends, 0);
  h.session.destroy();
});

test("demo catalog and history are requested explicitly, without a local fallback", async () => {
  const h = setup({}, { demo: true });
  await h.session.start();
  assert.deepEqual(h.calls, [
    ["capabilities", true],
    ["conversations", true],
  ]);
  h.session.destroy();
});

test("entering the workspace leaves the canvas blank until a history item is explicitly selected", async () => {
  let detailReads = 0,
    creates = 0;
  const h = setup({
    conversations: async () => ({ items: [conversation("old")] }),
    detail: async (id) => {
      detailReads++;
      return detail(id, [message("completed")]);
    },
    create: async () => {
      creates++;
      return conversation("new");
    },
  });
  await h.session.start();
  assert.equal(h.state().detail, null);
  assert.equal(h.state().conversations[0].id, "old");
  assert.equal(detailReads, 0);
  assert.equal(creates, 0);
  assert.equal(h.timers.size, 0);
  await h.session.select("old");
  assert.equal(detailReads, 1);
  assert.equal(h.state().detail.id, "old");
  await h.session.select(null);
  assert.equal(h.state().detail, null);
  assert.equal(creates, 0);
  h.session.destroy();
});

test("new conversation during bootstrap cannot abort capabilities and permanently disable the composer", async () => {
  const ready = deferred();
  let bootstrapSignal;
  const h = setup({
    capabilities: (_demo, signal) => {
      bootstrapSignal = signal;
      return ready.promise;
    },
  });
  const starting = h.session.start();
  await flush();
  await h.session.select(null);
  assert.equal(bootstrapSignal.aborted, false);
  assert.equal(h.state().loading, true);
  ready.resolve(capabilities);
  await starting;
  assert.equal(h.state().loading, false);
  assert.equal(h.state().capabilities.enabled, true);
  assert.equal(h.state().detail, null);
  h.session.destroy();
});

test("new conversation after a failed bootstrap preserves the error and initialization can be retried", async () => {
  let attempts = 0;
  const h = setup({
    capabilities: async () => {
      if (++attempts === 1) throw new Error("bootstrap offline");
      return capabilities;
    },
  });
  await h.session.start();
  assert.equal(h.state().capabilities, null);
  const error = h.state().error;
  await h.session.select(null);
  assert.equal(h.state().error, error);
  assert.match(error, /bootstrap offline/);
  await h.session.start();
  assert.equal(h.state().capabilities.enabled, true);
  assert.equal(h.state().error, null);
  assert.equal(h.state().loading, false);
  h.session.destroy();
});

test("switching conversation aborts stale detail and late responses cannot overwrite selection", async () => {
  const old = deferred();
  let oldSignal;
  const h = setup({
    detail: (id, signal) => {
      if (id === "old") {
        oldSignal = signal;
        return old.promise;
      }
      return Promise.resolve(detail(id));
    },
  });
  await h.session.start();
  const selectingOld = h.session.select("old");
  await h.session.select("new");
  assert.equal(oldSignal.aborted, true);
  old.resolve(detail("old"));
  await selectingOld;
  assert.equal(h.state().detail.id, "new");
  h.session.destroy();
});

test("one pending request at a time, persisted history is polled serially until terminal", async () => {
  const sending = deferred();
  let sends = 0,
    detailCalls = 0;
  const h = setup({
    send: async () => {
      sends++;
      return sending.promise;
    },
    detail: async () => {
      detailCalls++;
      return detail("one", [
        message(detailCalls > 1 ? "completed" : "querying"),
      ]);
    },
  });
  await h.session.start();
  const first = h.session.send("比較各池");
  await flush();
  assert.equal(await h.session.send("另一個問題"), false);
  assert.equal(sends, 1);
  sending.resolve(message());
  assert.equal(await first, true);
  assert.equal(h.timers.size, 1);
  assert.equal(await h.session.send("另一個問題"), false);
  await h.tick();
  assert.equal(h.state().detail.messages[0].status, "completed");
  assert.equal(h.timers.size, 0);
  assert.equal(detailCalls, 2);
  h.session.destroy();
});

test("cancel calls the backend and an older in-flight poll cannot revive the cancelled job", async () => {
  const oldPoll = deferred();
  let reads = 0,
    cancelledId;
  const h = setup({
    conversations: async () => ({ items: [conversation()] }),
    detail: async () =>
      ++reads === 1 ? detail("one", [message()]) : oldPoll.promise,
    cancel: async (id) => {
      cancelledId = id;
      return message("cancelled");
    },
  });
  await h.session.start();
  await h.session.select("one");
  await h.tick();
  const stop = h.session.cancel();
  await stop;
  assert.equal(cancelledId, "answer");
  assert.equal(h.state().detail.messages[0].status, "cancelled");
  oldPoll.resolve(detail("one", [message("querying")]));
  await flush();
  assert.equal(h.state().detail.messages[0].status, "cancelled");
  assert.equal(h.timers.size, 0);
  h.session.destroy();
});

test("a queued poll cannot start during cancellation or revive the answer after the acknowledgement", async () => {
  const acknowledgement = deferred();
  let reads = 0;
  const h = setup({
    detail: async () =>
      detail("one", [message(++reads === 1 ? "planning" : "cancelled")]),
    cancel: () => acknowledgement.promise,
  });
  await h.session.start();
  await h.session.select("one");
  const queued = h.timers.values().next().value;
  const stopping = h.session.cancel();
  assert.equal(h.timers.size, 0);
  assert.equal(h.state().cancelling, true);
  queued();
  await h.session.refresh();
  await flush();
  assert.equal(reads, 1);
  acknowledgement.resolve(message("cancelled"));
  await stopping;
  assert.equal(h.state().detail.messages[0].status, "cancelled");
  assert.equal(h.state().cancelling, false);
  const readsAfterAcknowledgement = reads;
  queued();
  await flush();
  assert.equal(reads, readsAfterAcknowledgement);
  assert.equal(h.timers.size, 0);
  h.session.destroy();
});

test("a lost POST response retries with the same UUID and blocks unrelated submissions", async () => {
  const ids = [];
  let attempts = 0;
  const h = setup({
    send: async (_id, _text, requestId) => {
      ids.push(requestId);
      if (++attempts === 1) throw new Error("connection lost");
      return message("completed");
    },
    detail: async () => detail("one", [message("completed")]),
  });
  await h.session.start();
  assert.equal(await h.session.send("平均長度"), false);
  assert.equal(h.state().retryable, true);
  assert.equal(await h.session.send("不同問題"), false);
  assert.equal(await h.session.retry(), true);
  assert.deepEqual(ids, ["request-1", "request-1"]);
  assert.equal(h.state().retryable, false);
  h.session.destroy();
});

test("unmount aborts transport, clears polling, and ignores late writes", async () => {
  const response = deferred();
  let signal;
  const h = setup({
    conversations: async () => ({ items: [conversation()] }),
    detail: async (_id, requestSignal) => {
      signal = requestSignal;
      return response.promise;
    },
  });
  await h.session.start();
  const starting = h.session.select("one");
  await flush();
  h.session.destroy();
  const count = h.changes.length;
  assert.equal(signal.aborted, true);
  response.resolve(detail("one", [message()]));
  await starting;
  assert.equal(h.changes.length, count);
  assert.equal(h.timers.size, 0);
});

test("a pending view keeps its last data during a transient poll failure and can recover", async () => {
  let reads = 0;
  const h = setup({
    conversations: async () => ({ items: [conversation()] }),
    detail: async () => {
      reads++;
      if (reads === 2) throw new Error("network down");
      return detail("one", [message(reads > 2 ? "completed" : "planning")]);
    },
  });
  await h.session.start();
  await h.session.select("one");
  await h.tick();
  assert.match(h.state().error, /狀態更新中斷/);
  assert.equal(h.state().detail.messages[0].status, "planning");
  assert.equal(h.timers.size, 1);
  await h.tick();
  assert.equal(h.state().error, null);
  assert.equal(h.state().detail.messages[0].status, "completed");
  assert.equal(h.timers.size, 0);
  h.session.destroy();
});

test("late completion after switching view does not acknowledge the old submit to the UI", async () => {
  const old = deferred();
  const h = setup({
    send: async () => message(),
    detail: async (id) => (id === "one" ? old.promise : detail(id)),
  });
  await h.session.start();
  const sending = h.session.send("今天的數據");
  await flush();
  await h.session.select("two");
  old.resolve(detail("one", [message("completed")]));
  assert.equal(await sending, false);
  assert.equal(h.state().detail.id, "two");
  h.session.destroy();
});
