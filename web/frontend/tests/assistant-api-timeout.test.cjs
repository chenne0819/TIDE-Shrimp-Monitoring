const test = require("node:test");
const assert = require("node:assert/strict");
const { getEventListeners } = require("node:events");
const { loadSource, deferred, flush } = require("./helpers.cjs");

const response = (body) => new Response(JSON.stringify(body));
const token = { csrf_token: "test-token", max_upload_bytes: 1024 };
const isTimeout = (error) =>
  error instanceof Error && error.message.includes("等待分析服務回應逾時");

function setup(fetch) {
  let now = 0,
    nextId = 0;
  const timers = new Map();
  const shared = loadSource("src/lib/api.ts", {}, { fetch });
  const { assistantApi } = loadSource(
    "src/lib/assistant-api.ts",
    { "./api": shared },
    {
      setTimeout: (callback, delay) => {
        const id = ++nextId;
        timers.set(id, { at: now + delay, callback });
        return id;
      },
      clearTimeout: (id) => timers.delete(id),
    },
  );
  return {
    api: assistantApi,
    timers,
    advance(ms) {
      now += ms;
      for (const [id, timer] of timers) {
        if (timer.at <= now) {
          timers.delete(id);
          timer.callback();
        }
      }
    },
  };
}

const endpoints = {
  capabilities: (api, signal) => api.capabilities(false, signal),
  conversations: (api, signal) => api.conversations(false, signal),
  create: (api, signal) => api.create(false, signal),
  detail: (api, signal) => api.detail("one", signal),
  send: (api, signal) => api.send("one", "比較寬度", "request-one", signal),
  cancel: (api, signal) => api.cancel("answer-one", signal),
};

for (const [name, invoke] of Object.entries(endpoints)) {
  test(`${name} aborts only its HTTP request after 30 seconds`, async () => {
    let requestSignal;
    const fixture = setup((_url, options) => {
      requestSignal = options.signal;
      // A transport that never settles must not trap the caller indefinitely.
      return new Promise(() => {});
    });
    const scope = new AbortController();
    const operation = invoke(fixture.api, scope.signal);
    const rejection = assert.rejects(operation, isTimeout);
    fixture.advance(29_999);
    assert.equal(requestSignal.aborted, false);
    fixture.advance(1);
    await rejection;
    assert.equal(requestSignal.aborted, true);
    assert.equal(scope.signal.aborted, false);
    assert.equal(fixture.timers.size, 0);
    assert.equal(getEventListeners(scope.signal, "abort").length, 0);
  });
}

test("a timed out CSRF bootstrap cannot send a POST if it finishes late", async () => {
  const bootstrap = deferred();
  const calls = [];
  const fixture = setup((url, options) => {
    calls.push({ url, options });
    return bootstrap.promise;
  });
  const scope = new AbortController();
  const operation = fixture.api.send(
    "one",
    "比較長度",
    "same-id",
    scope.signal,
  );
  const rejection = assert.rejects(operation, isTimeout);
  fixture.advance(30_000);
  await rejection;
  bootstrap.resolve(response(token));
  await flush();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url.endsWith("/session"), true);
  assert.equal(scope.signal.aborted, false);
});

test("bootstrap and complete response body share a single deadline", async () => {
  const bootstrap = deferred();
  const body = deferred();
  const calls = [];
  const fixture = setup((url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/session")) return bootstrap.promise;
    return Promise.resolve({ ok: true, json: () => body.promise });
  });
  const scope = new AbortController();
  const operation = fixture.api.send(
    "one",
    "比較長度",
    "same-id",
    scope.signal,
  );
  const rejection = assert.rejects(operation, isTimeout);
  fixture.advance(20_000);
  bootstrap.resolve(response(token));
  await flush();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].options.headers.get("X-Tide-CSRF"), "test-token");
  assert.equal(calls[0].options.signal, calls[1].options.signal);
  fixture.advance(9_999);
  assert.equal(calls[1].options.signal.aborted, false);
  fixture.advance(1);
  await rejection;
  assert.equal(calls[1].options.signal.aborted, true);
  assert.equal(scope.signal.aborted, false);
  // A late body is consumed by the raced promise without a second completion.
  body.resolve({ id: "late-answer" });
  await flush();
});

test("successful and rejected responses release their timer and scope listener", async () => {
  for (const value of [
    response({ items: [] }),
    new Response("bad", { status: 500 }),
  ]) {
    let requestSignal;
    const fixture = setup(async (_url, options) => {
      requestSignal = options.signal;
      return value;
    });
    const scope = new AbortController();
    const operation = fixture.api.conversations(false, scope.signal);
    if (value.ok) assert.deepEqual((await operation).items, []);
    else await assert.rejects(operation, /服務回應 500/);
    assert.equal(fixture.timers.size, 0);
    assert.equal(getEventListeners(scope.signal, "abort").length, 0);
    fixture.advance(30_000);
    scope.abort();
    assert.equal(requestSignal.aborted, false);
  }
});

test("conversation cancellation retains its reason and pre-aborted scopes never fetch", async () => {
  let calls = 0,
    requestSignal;
  const fixture = setup((_url, options) => {
    calls += 1;
    requestSignal = options.signal;
    return new Promise(() => {});
  });
  const scope = new AbortController();
  const reason = new DOMException("Conversation changed", "AbortError");
  const operation = fixture.api.detail("one", scope.signal);
  const rejection = assert.rejects(operation, (error) => error === reason);
  scope.abort(reason);
  await rejection;
  assert.equal(requestSignal.aborted, true);
  assert.equal(fixture.timers.size, 0);
  await assert.rejects(
    fixture.api.detail("two", scope.signal),
    (error) => error === reason,
  );
  assert.equal(calls, 1);
  assert.equal(fixture.timers.size, 0);
});

test("session can retry a timed out send with the original request id", async () => {
  const sentIds = [];
  const conversation = {
    id: "one",
    title: "寬度比較",
    demo: false,
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
  };
  const answer = {
    id: "answer",
    role: "assistant",
    status: "completed",
    content: "完成",
    followups: [],
    board: null,
  };
  const fixture = setup(async (url, options) => {
    if (url.endsWith("/session")) return response(token);
    if (url.endsWith("/capabilities")) return response({ enabled: true });
    if (url.endsWith("/conversations") && options.method !== "POST")
      return response({ items: [] });
    if (url.endsWith("/conversations")) return response(conversation);
    if (url.endsWith("/messages")) {
      sentIds.push(JSON.parse(options.body).request_id);
      if (sentIds.length === 1) return new Promise(() => {});
      return response(answer);
    }
    return response({ ...conversation, messages: [answer] });
  });
  const { createAssistantSession } = loadSource("src/lib/assistant-session.ts");
  let state;
  const session = createAssistantSession({
    demo: false,
    transport: fixture.api,
    uuid: () => "stable-id",
    onChange: (next) => {
      state = next;
    },
  });
  await session.start();
  const first = session.send("比較寬度");
  await flush();
  assert.equal(state.sending, true);
  fixture.advance(30_000);
  assert.equal(await first, false);
  assert.equal(state.sending, false);
  assert.equal(state.retryable, true);
  assert.match(state.error, /等待分析服務回應逾時/);
  assert.equal(await session.retry(), true);
  assert.deepEqual(sentIds, ["stable-id", "stable-id"]);
  assert.equal(state.retryable, false);
  assert.equal(state.detail.messages[0].id, "answer");
  session.destroy();
  assert.equal(fixture.timers.size, 0);
});
