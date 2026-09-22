const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource, createHooks, elements } = require("./helpers.cjs");

const stubs = { "@/lib/api": { formatNumber: (value) => String(value) } };
const { ActivityDetails, CompletionSummary, activityMetadata } = loadSource(
  "src/components/assistant-activity.tsx",
  stubs,
);
const activity = (overrides = {}) => ({
  id: "query",
  kind: "query",
  label: "查詢影片量測",
  status: "completed",
  started_at: "2026-09-20T00:00:00Z",
  finished_at: "2026-09-20T00:00:02Z",
  detail: "已取得完成影片的追蹤 ID。",
  metadata: {},
  ...overrides,
});

test("legacy messages have no invented execution steps or completion summary", () => {
  assert.equal(ActivityDetails({ message: { activity: [] } }), null);
  assert.equal(ActivityDetails({ message: {} }), null);
  assert.equal(CompletionSummary({ message: {} }), null);
});

test("execution metadata exposes actual filters and counts while ignoring arbitrary provider fields", () => {
  const rows = activityMetadata(
    activity({
      metadata: {
        periods: [
          { label: "本月", start_date: "2026-09-01", end_date: "2026-09-20" },
        ],
        ponds: ["A-01"],
        total_jobs: 8,
        total_tracks: 93,
        chart_samples: [{ title: "有效長度", sample_count: 80 }],
        raw_thoughts: "PRIVATE_THOUGHTS",
        sql: "SELECT PRIVATE",
        prompt: "PRIVATE_PROMPT",
        irrelevant: 123,
      },
    }),
  );
  const serialized = JSON.stringify(rows);
  assert.match(serialized, /2026-09-01 — 2026-09-20/);
  assert.match(serialized, /A-01/);
  assert.match(serialized, /影片內追蹤 ID 數/);
  assert.match(serialized, /80 筆圖表樣本/);
  assert.doesNotMatch(serialized, /PRIVATE|irrelevant|sql|prompt/);
});

test("text-only activity does not claim a previous board existed", () => {
  const rows = activityMetadata(
    activity({ metadata: { presentation: "answer" } }),
  );
  assert.deepEqual(JSON.parse(JSON.stringify(rows)), [
    { label: "結果呈現", value: "僅文字回答，不更新圖表" },
  ]);
});

test("the collapsed record lists only the backend steps and completion uses backend detail", () => {
  const steps = [
    activity(),
    activity({
      id: "complete",
      kind: "complete",
      label: "完成",
      detail: "已整理 8 部影片，產生 2 張圖表。",
    }),
  ];
  const tree = ActivityDetails({ message: { activity: steps } });
  assert.equal(
    elements(tree, (node) => node.type === "details")[0].props.open,
    undefined,
  );
  const fullRecord = elements(tree, (node) => node.type === "ol")[0];
  assert.equal(elements(fullRecord, (node) => node.type === "li").length, 2);
  assert.equal(
    elements(tree, (node) => node.props?.className === "ai-completion-summary")
      .length,
    0,
  );
  const summary = elements(
    CompletionSummary({ message: { activity: steps } }),
    (node) => node.props?.className === "ai-completion-summary",
  )[0];
  assert.ok(
    elements(summary, (node) => node.type === "span").some(
      (node) => node.props.children === steps[1].detail,
    ),
  );
});

test("compact execution preview shows only two actual recent steps and exposes a running stage", () => {
  const steps = [
    activity({ id: "context" }),
    activity({ id: "plan" }),
    activity({ id: "query", status: "running", label: "正在計算量測" }),
  ];
  const tree = ActivityDetails({
    message: { status: "querying", activity: steps },
  });
  const preview = elements(
    tree,
    (node) => node.props?.className === "ai-activity-preview",
  )[0];
  assert.equal(preview.props.role, "status");
  const items = elements(preview, (node) => node.type === "li");
  assert.equal(items.length, 2);
  assert.ok(
    elements(items[1], (node) => node.type === "span").some(
      (node) => node.props.children === "正在計算量測",
    ),
  );
  assert.equal(CompletionSummary({ message: { activity: steps } }), null);
});

test("progress shows the real running stage and removes its elapsed timer on unmount", () => {
  const hooks = createHooks();
  const timers = new Map();
  let next = 0;
  const { AnalysisProgress } = loadSource(
    "src/components/assistant-activity.tsx",
    { ...stubs, react: hooks.react },
    {
      setInterval: (callback, delay) => {
        assert.equal(delay, 1000);
        timers.set(++next, callback);
        return next;
      },
      clearInterval: (id) => timers.delete(id),
    },
  );
  const tree = hooks.render(AnalysisProgress, {
    message: {
      created_at: new Date(Date.now() - 7000).toISOString(),
      status: "querying",
      activity: [activity({ status: "running", label: "產生長寬比較圖" })],
    },
    sendingStartedAt: null,
  });
  assert.equal(
    elements(tree, (node) => node.type === "h2")[0].props.children,
    "產生長寬比較圖",
  );
  assert.equal(timers.size, 1);
  hooks.cleanup();
  assert.equal(timers.size, 0);
});
