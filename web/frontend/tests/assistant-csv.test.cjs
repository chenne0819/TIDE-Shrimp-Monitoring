const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource } = require("./helpers.cjs");
const { csvCell, chartCsv } = loadSource("src/lib/assistant-utils.ts");

test("CSV neutralizes spreadsheet formulas even after whitespace and control characters", () => {
  for (const value of [
    '=HYPERLINK("https://example.invalid")',
    "+cmd",
    "-cmd",
    "@SUM(1)",
    "  =1+1",
    "\t=1+1",
    "\r=1+1",
    "\n=1+1",
    "\uFEFF=1+1",
  ]) {
    assert.ok(csvCell(value).startsWith("\"'"), value);
  }
  assert.equal(csvCell(-12.5), '"-12.5"');
  assert.equal(csvCell(0), '"0"');
  assert.equal(csvCell(null), '""');
  assert.equal(csvCell(Infinity), '""');
});

test("CSV keeps commas, quotes, and newlines inside quoted cells and protects headers", () => {
  const chart = {
    x_key: "label",
    series: [{ key: "p0", label: "=bad heading", unit: "mm" }],
    data: [
      { label: '池,一"\n第二行', p0: 12.25 },
      { label: "@formula", p0: null },
    ],
  };
  const output = chartCsv(chart);
  assert.equal(
    output,
    '\uFEFF"分類","\'=bad heading (mm)"\r\n"池,一""\n第二行","12.25"\r\n"\'@formula",""',
  );
});

test("CSV exports all returned rows and preserves paired scatter values", () => {
  const chart = {
    x_key: "x",
    series: [{ key: "y", label: "寬度", unit: "mm" }],
    data: Array.from({ length: 240 }, (_, i) => ({
      x: i + 1,
      y: i / 10,
      label: `個體 ${i}`,
    })),
  };
  const output = chartCsv(chart);
  assert.equal(output.split("\r\n").length, 241);
  assert.ok(output.endsWith('"240","23.9","個體 239"'));
});

function downloadSetup(failure) {
  const events = [],
    timers = [],
    revoked = [];
  let attached = false,
    blob;
  const problem = new Error("download DOM failure");
  const anchor = {
    click() {
      assert.equal(
        attached,
        true,
        "download anchor must be in document.body when clicked",
      );
      assert.equal(this.hidden, true);
      events.push("click");
      if (failure === "click") throw problem;
    },
    remove() {
      attached = false;
      events.push("remove");
      if (failure === "remove") throw problem;
    },
  };
  const { downloadChartCsv } = loadSource(
    "src/lib/assistant-utils.ts",
    {},
    {
      document: {
        createElement(tag) {
          assert.equal(tag, "a");
          return anchor;
        },
        body: {
          appendChild(node) {
            assert.equal(node, anchor);
            events.push("append");
            if (failure === "append") throw problem;
            attached = true;
          },
        },
      },
      URL: {
        createObjectURL(value) {
          blob = value;
          return "blob:test-csv";
        },
        revokeObjectURL(url) {
          revoked.push(url);
        },
      },
      setTimeout(callback, delay) {
        timers.push({ callback, delay });
      },
    },
  );
  return {
    downloadChartCsv,
    anchor,
    events,
    timers,
    revoked,
    problem,
    attached: () => attached,
    blob: () => blob,
  };
}

const downloadChart = {
  id: "unsafe/../圖表-id",
  type: "table",
  x_key: "label",
  series: [{ key: "p0", label: "寬度", unit: "mm" }],
  data: [{ label: "=1+1", p0: 12.25 }],
};

test("CSV download attaches a hidden anchor, clicks synchronously, then removes it and revokes after one second", async () => {
  const setup = downloadSetup();
  setup.downloadChartCsv(downloadChart);
  assert.deepEqual(setup.events, ["append", "click", "remove"]);
  assert.equal(setup.attached(), false);
  assert.equal(setup.anchor.href, "blob:test-csv");
  assert.match(setup.anchor.download, /^tide-[a-zA-Z0-9_-]+\.csv$/);
  assert.equal(setup.blob().type, "text/csv;charset=utf-8");
  assert.match(
    await setup.blob().text(),
    /"寬度 \(mm\)".*\r\n"'=1\+1","12.25"/s,
  );
  assert.deepEqual(setup.revoked, []);
  assert.equal(setup.timers.length, 1);
  assert.equal(setup.timers[0].delay, 1000);
  setup.timers[0].callback();
  assert.deepEqual(setup.revoked, ["blob:test-csv"]);
});

for (const failure of ["append", "click", "remove"]) {
  test(`CSV download cleans up the anchor and blob URL when ${failure} fails`, () => {
    const setup = downloadSetup(failure);
    assert.throws(
      () => setup.downloadChartCsv(downloadChart),
      (error) => error === setup.problem,
    );
    assert.equal(setup.attached(), false);
    assert.ok(setup.events.includes("remove"));
    assert.deepEqual(setup.revoked, []);
    assert.equal(setup.timers.length, 1);
    assert.equal(setup.timers[0].delay, 1000);
    setup.timers[0].callback();
    assert.deepEqual(setup.revoked, ["blob:test-csv"]);
  });
}
