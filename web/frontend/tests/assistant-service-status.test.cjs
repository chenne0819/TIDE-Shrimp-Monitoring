const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource, createHooks, flush } = require("./helpers.cjs");

test("AI demo checks its backend and explains model usage even though the video worker is offline", async () => {
  const hooks = createHooks();
  const requests = [];
  const { ServiceStatus } = loadSource("src/components/service-status.tsx", {
    react: hooks.react,
    "@/lib/api": {
      api: async (path, options) => {
        requests.push({ path, signal: options.signal });
        return { status: "ok", worker: "offline" };
      },
    },
  });
  const props = { demo: true, variant: "assistant" };
  hooks.render(ServiceStatus, props);
  await flush();
  const tree = hooks.render(ServiceStatus, props);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].path, "/health");
  assert.match(tree.props.title, /FastAPI/);
  assert.match(tree.props.title, /模型的額度/);
  assert.equal(tree.props.children.at(-1), "AI 示範 · 資料服務已連線");
  hooks.cleanup();
  assert.equal(requests[0].signal.aborted, true);
});

test("ordinary demo pages still work without backend health requests", async () => {
  const hooks = createHooks();
  let requests = 0;
  const { ServiceStatus } = loadSource("src/components/service-status.tsx", {
    react: hooks.react,
    "@/lib/api": {
      api: async () => {
        requests++;
        return {};
      },
    },
  });
  const tree = hooks.render(ServiceStatus, { demo: true });
  await flush();
  assert.equal(requests, 0);
  assert.equal(tree.props.title, "展示資料不需要後端服務");
  assert.equal(tree.props.children.at(-1), "示範工作區");
  hooks.cleanup();
});
