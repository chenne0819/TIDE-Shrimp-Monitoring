const test = require("node:test");
const assert = require("node:assert/strict");
const { renderToStaticMarkup } = require("react-dom/server");
const React = require("react");
const { loadSource } = require("./helpers.cjs");
const { StatisticalCard, formatStatistic } = loadSource(
  "src/components/assistant-statistics.tsx",
);
const base = {
  id: "s",
  method: "descriptive",
  title: "寬度統計",
  status: "completed",
  metric: "width_mm",
  secondary_metric: null,
  unit: "mm",
  sample_unit: "track",
  groups: [
    {
      label: "A池",
      n: 3,
      min: 10,
      max: 30,
      mean: 20,
      median: 20,
      std_dev: 10,
      q1: 15,
      q3: 25,
    },
  ],
  values: [],
  warnings: ["估計值；不代表同一個體成長。"],
  reason: null,
};
test("statistics preserve nulls, signs, tiny probabilities and avoid exact-zero p claims", () => {
  assert.equal(formatStatistic(null), "—");
  assert.equal(formatStatistic(NaN), "—");
  assert.equal(formatStatistic(-0.8), "-0.8");
  assert.equal(formatStatistic(1.27e-12, true), "1.270e-12");
  assert.equal(formatStatistic(0, true), "低於數值精度");
  assert.equal(formatStatistic(0), "0");
});
for (const method of [
  "descriptive",
  "pearson",
  "spearman",
  "welch_t",
  "anova",
]) {
  test(`${method} renders values, sample unit, full group summary and limitations`, () => {
    const html = renderToStaticMarkup(
      React.createElement(StatisticalCard, {
        result: {
          ...base,
          method,
          sample_unit:
            method === "welch_t" || method === "anova" ? "video_mean" : "track",
          values: [{ label: "p 值（雙尾）", value: 1.27e-12, unit: "" }],
        },
      }),
    );
    assert.match(html, /1.270e-12/);
    assert.match(html, /樣本標準差 \(mm\)/);
    assert.match(html, /<td class="ai-number">3<\/td>/);
    assert.match(html, /計算方式與使用限制/);
    assert.match(
      html,
      method === "welch_t" || method === "anova" ? /影片等權/ : /追蹤 ID/,
    );
  });
}
test("insufficient data is explicit and missing values are not displayed as zero", () => {
  const html = renderToStaticMarkup(
    React.createElement(StatisticalCard, {
      result: {
        ...base,
        status: "not_applicable",
        reason: "至少需要兩部影片。",
        groups: [{ label: "A", n: 0 }],
        values: [{ label: "p 值", value: null, unit: "" }],
      },
    }),
  );
  assert.match(html, /無法計算/);
  assert.match(html, /至少需要兩部影片/);
  assert.match(html, /<dd>—<\/dd>/);
});
