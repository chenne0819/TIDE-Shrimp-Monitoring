const test = require("node:test");
const assert = require("node:assert/strict");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { loadSource } = require("./helpers.cjs");

const demo = loadSource("src/lib/demo.ts");
const api = loadSource("src/lib/api.ts");

test("synthetic demo records expose no private video, thumbnail, or artifact URLs", () => {
  assert.ok(demo.demoJobs.length > 0);
  for (const job of demo.demoJobs) {
    assert.equal(job.source_video_url, null);
    assert.equal(job.result_video_url, null);
    assert.equal(job.thumbnail_url, null);
    assert.equal(job.artifacts.length, 0);
    assert.equal(job.metadata.sample, true);
    assert.ok(job.tracks.length > 0, "synthetic measurements remain available");
  }
  assert.equal(api.mediaUrl(null), undefined);
});

test("synthetic recording details show an honest empty media state without a video request", () => {
  const { RecordingDetail } = loadSource(
    "src/components/recording-detail.tsx",
    {
      "next/link": {
        default: ({ children, ...props }) =>
          React.createElement("a", props, children),
      },
      "@/lib/api": api,
      "@/lib/demo": demo,
      "./app-shell": { AppShell: ({ children }) => children },
      "./ui": {
        ErrorState: () => null,
        LoadingState: () => null,
        StatusBadge: () => null,
        WaterBadge: () => null,
      },
    },
  );
  const markup = renderToStaticMarkup(
    React.createElement(RecordingDetail, {
      id: demo.demoJobs[0].id,
      demo: true,
    }),
  );
  assert.match(markup, /這是合成示範資料，未附實際影片或縮圖/);
  assert.match(markup, /下載示範 CSV/);
  assert.doesNotMatch(markup, /<video\b|<img\b|\/demo\//);
  assert.doesNotMatch(markup, /影片準備完成後/);
});
