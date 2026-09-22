const test = require("node:test");
const assert = require("node:assert/strict");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { loadSource, elements } = require("./helpers.cjs");
const fixture = require("./fixtures/assistant-charts.json");

// Recharts needs browser layout/effects to produce SVG. These tests inspect the
// actual component's chart configuration; custom SVG and tables render in React.
const names = [
  "Area",
  "AreaChart",
  "Bar",
  "BarChart",
  "CartesianGrid",
  "Cell",
  "Legend",
  "Line",
  "LineChart",
  "Pie",
  "PieChart",
  "ResponsiveContainer",
  "Scatter",
  "ScatterChart",
  "Tooltip",
  "XAxis",
  "YAxis",
];
const recharts = Object.fromEntries(
  names.map((name) => [name, function ChartPart() {}]),
);
const utils = loadSource("src/lib/assistant-utils.ts");
const { formatNumber } = loadSource("src/lib/api.ts");
const { AnalysisVisualization, AnalysisDataTable } = loadSource(
  "src/components/assistant-charts.tsx",
  { recharts, "@/lib/api": { formatNumber }, "@/lib/assistant-utils": utils },
);
const charts = fixture.boards.flatMap((board) => board.charts);
const byType = Object.fromEntries(charts.map((chart) => [chart.type, chart]));
const kinds = [
  "line",
  "area",
  "bar",
  "stacked_bar",
  "histogram",
  "scatter",
  "boxplot",
  "heatmap",
  "donut",
  "table",
];
const plain = (value) => JSON.parse(JSON.stringify(value));
const render = (chart) => AnalysisVisualization({ chart });
const part = (tree, name) =>
  elements(tree, (node) => node.type === recharts[name]);
function customTree(chart) {
  const node = render(chart);
  return typeof node.type === "function" ? node.type(node.props) : node;
}
function text(node) {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node !== "object") return String(node);
  return React.Children.toArray(node.props?.children).map(text).join("");
}
function parseCsv(csv) {
  const rows = [],
    row = [];
  let cell = "",
    quoted = false;
  csv = csv.replace(/^\uFEFF/, "");
  for (let i = 0; i < csv.length; i += 1) {
    const c = csv[i];
    if (c === '"') {
      if (quoted && csv[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else quoted = !quoted;
    } else if (!quoted && (c === "," || c === "\r")) {
      row.push(cell);
      cell = "";
      if (c === "\r") {
        rows.push([...row]);
        row.length = 0;
        i += 1;
      }
    } else cell += c;
  }
  row.push(cell);
  rows.push(row);
  return rows;
}

test("fixture contains all ten backend-generated types with bounded, isolated demo observations", () => {
  assert.deepEqual(
    charts.map((chart) => chart.type),
    kinds,
  );
  assert.equal(fixture.fixed_today, "2026-09-20");
  for (const board of fixture.boards) {
    assert.equal(board.demo, true);
    assert.equal(board.query.periods.length, 2);
    assert.equal(board.total_jobs, 6);
    assert.equal(board.total_tracks, 131);
    assert.ok(board.sources.every((source) => source.id.startsWith("demo-")));
    assert.ok(board.charts.length <= 8);
  }
  assert.ok(charts.every((chart) => chart.data.length <= 500));
  const request = fixture.requests.find((item) => item.type === "heatmap");
  assert.equal(request.group_by, "day");
  assert.match(byType.heatmap.description, /X：拍攝日期；Y：池別與期間/);
});

for (const kind of kinds) {
  test(`${kind}: empty result renders an explicit empty state without zero measurements`, () => {
    const tree = render({ ...byType[kind], data: [] });
    assert.equal(tree.props.className, "ai-chart-empty");
    assert.match(text(tree), /還沒有可顯示的資料/);
    assert.equal(part(tree, "ResponsiveContainer").length, 0);
  });
}

for (const [kind, container, mark] of [
  ["line", "LineChart", "Line"],
  ["area", "AreaChart", "Area"],
  ["bar", "BarChart", "Bar"],
  ["stacked_bar", "BarChart", "Bar"],
  ["histogram", "BarChart", "Bar"],
]) {
  test(`${kind}: preserves all periods, category order, units and independent/stacked series`, () => {
    const chart = byType[kind];
    const tree = render(chart);
    assert.deepEqual(plain(part(tree, container)[0].props.data), chart.data);
    assert.equal(part(tree, "XAxis")[0].props.dataKey, chart.x_key);
    const marks = part(tree, mark);
    assert.equal(marks.length, chart.series.length);
    marks.forEach((node, i) => {
      assert.equal(node.props.dataKey, chart.series[i].key);
      assert.equal(
        node.props.name,
        `${chart.series[i].label} (${chart.series[i].unit})`,
      );
      assert.equal(
        node.props.stackId,
        kind === "stacked_bar" ? "count" : undefined,
      );
      if (kind === "line" || kind === "area")
        assert.equal(node.props.connectNulls, false);
    });
    if (kind === "histogram") {
      assert.equal(part(tree, container)[0].props.barCategoryGap, "3%");
      assert.match(chart.description, /（g）.*Y 軸為有效個體數/);
      assert.ok(chart.series.every((series) => series.unit === "隻"));
    }
  });

  test(`${kind}: missing/non-finite values stay missing while observed zero is retained`, () => {
    const chart = byType[kind];
    const key = chart.series[0].key;
    const tree = render({
      ...chart,
      data: [
        { ...chart.data[0], [key]: null },
        { ...chart.data[0], [key]: 0 },
        { ...chart.data[0], [key]: Infinity },
        { ...chart.data[0], [key]: NaN },
      ],
    });
    assert.deepEqual(
      Array.from(part(tree, container)[0].props.data, (row) => row[key]),
      [null, 0, null, null],
    );
  });
}

test("histogram uses the same numeric bins for both periods, with sample counts on Y", () => {
  const chart = byType.histogram;
  assert.equal(
    chart.data.reduce((sum, row) => sum + row.p0, 0),
    43,
  );
  assert.equal(
    chart.data.reduce((sum, row) => sum + row.p1, 0),
    88,
  );
  chart.data.forEach((row, i) => {
    assert.ok(row.lower < row.upper);
    if (i) assert.equal(row.lower, chart.data[i - 1].upper);
  });
});

test("stacked count bars keep the periods separate and sum to the source individual count", () => {
  const chart = byType.stacked_bar;
  const totals = fixture.boards[0].query.periods.map((period) =>
    chart.data
      .filter((row) => row.label.startsWith(period.label))
      .reduce((sum, row) => sum + row.male + row.female + row.unknown, 0),
  );
  assert.deepEqual(totals, [43, 88]);
  assert.equal(new Set(chart.data.map((row) => row.label)).size, 4);
});

test("scatter forwards all paired observations without changing mm/g units or sample labels", () => {
  const tree = render(byType.scatter);
  assert.deepEqual(
    plain(part(tree, "Scatter")[0].props.data),
    byType.scatter.data,
  );
  assert.equal(part(tree, "XAxis")[0].props.unit, "mm");
  assert.equal(part(tree, "YAxis")[0].props.unit, "g");
  assert.equal(part(tree, "Scatter")[0].props.data.length, 131);
});

test("scatter without any complete finite pair explains why no points can be drawn", () => {
  const tree = render({
    ...byType.scatter,
    data: [
      { x: null, y: 2 },
      { x: 10, y: null },
    ],
  });
  assert.equal(tree.props.className, "ai-chart-empty");
  assert.match(text(tree), /沒有完整的有效配對/);
});

test("boxplot renders one five-number summary per period/pond with finite geometry and exact labels", () => {
  const chart = byType.boxplot;
  const tree = customTree(chart);
  const titles = elements(tree, (node) => node.type === "title");
  assert.equal(titles.length, 4);
  titles.forEach((node, i) => {
    assert.ok(text(node).startsWith(`${chart.data[i].label}:`));
    for (const key of ["min", "q1", "median", "q3", "max"])
      assert.ok(text(node).includes(formatNumber(chart.data[i][key], 2)));
    assert.ok(text(node).includes("mm"));
  });
  const labels = elements(tree, (node) => node.type === "tspan").map(text);
  assert.deepEqual(
    labels,
    chart.data.flatMap((row) => row.label.split(" · ")),
  );
  const html = renderToStaticMarkup(
    React.createElement(AnalysisVisualization, { chart }),
  );
  assert.ok(html.includes("<svg"));
  assert.doesNotMatch(html, /NaN|Infinity/);
  assert.match(chart.note, /實際最小／最大值，不是 1.5 IQR/);
});

test("boxplot handles identical observations and omits incomplete summaries without fabricated boxes", () => {
  const chart = {
    ...byType.boxplot,
    series: [{ key: "median", label: "中位估計重量", unit: "g" }],
    data: [
      { label: "同值樣本", min: 4, q1: 4, median: 4, q3: 4, max: 4, count: 3 },
      { label: "缺值", min: 1, q1: null, median: 3, q3: 4, max: 5, count: 4 },
    ],
  };
  const tree = customTree(chart);
  assert.equal(elements(tree, (node) => node.type === "rect").length, 1);
  assert.ok(text(tree).includes("g"));
  const html = renderToStaticMarkup(
    React.createElement(AnalysisVisualization, { chart }),
  );
  assert.doesNotMatch(html, /NaN|Infinity/);
  const empty = customTree({ ...chart, data: [chart.data[1]] });
  assert.match(text(empty), /沒有足夠的體型數據/);
});

test("daily heatmap displays actual date columns, period/pond rows, and every supplied value", () => {
  const chart = byType.heatmap;
  const tree = customTree(chart);
  const headings = elements(tree, (node) => node.type === "th");
  const dateLabels = headings
    .filter((node) => node.props.scope === "col")
    .slice(1)
    .map(text);
  assert.deepEqual(dateLabels, [...new Set(chart.data.map((row) => row.x))]);
  assert.ok(dateLabels.every((value) => /^2026-09-\d\d$/.test(value)));
  const rowLabels = headings
    .filter((node) => node.props.scope === "row")
    .map(text);
  assert.deepEqual(rowLabels, [...new Set(chart.data.map((row) => row.y))]);
  const cells = elements(
    tree,
    (node) =>
      typeof node.props?.className === "string" &&
      node.props.className.startsWith("ai-heat-cell"),
  );
  for (const row of chart.data) {
    const cell = cells.find((node) =>
      node.props.title.startsWith(`${row.y} / ${row.x}:`),
    );
    assert.ok(cell);
    assert.equal(
      text(cell),
      row.value === null ? "—" : formatNumber(row.value, 2),
    );
    assert.equal(
      cell.props.className.includes("ai-missing"),
      row.value === null,
    );
  }
});

test("heatmap distinguishes missing cells from observed zero and avoids invalid scales for all-null data", () => {
  const data = [
    { x: "09/20", y: "A-01", value: 0 },
    { x: "09/21", y: "A-01", value: null },
  ];
  const tree = customTree({ ...byType.heatmap, data });
  const cells = elements(
    tree,
    (node) => node.type === "span" && node.props.title,
  );
  assert.equal(text(cells[0]), "0");
  assert.equal(cells[0].props.className, "ai-heat-cell");
  assert.equal(text(cells[1]), "—");
  assert.equal(cells[1].props.style, undefined);
  const html = renderToStaticMarkup(
    React.createElement(AnalysisVisualization, {
      chart: {
        ...byType.heatmap,
        data: data.map((row) => ({ ...row, value: null })),
      },
    }),
  );
  assert.doesNotMatch(html, /NaN|Infinity/);
  assert.ok(html.includes("無資料"));
});

test("heatmap never relabels pond categories as dates based on a model-written daily title", () => {
  const chart = {
    ...byType.heatmap,
    title: "每日資料",
    description: "X：查詢分組；Y：期間。",
    data: [
      { x: "A-01", y: "本期", value: 6 },
      { x: "B-02", y: "本期", value: 4 },
    ],
  };
  const columns = elements(
    customTree(chart),
    (node) => node.type === "th" && node.props.scope === "col",
  ).map(text);
  assert.deepEqual(columns, ["分類", "A-01", "B-02"]);
});

test("donut shows video counts, not individual counts or invented percentages", () => {
  const chart = byType.donut;
  const tree = render(chart);
  const pie = part(tree, "Pie")[0];
  assert.deepEqual(plain(pie.props.data), chart.data);
  assert.equal(pie.props.dataKey, "value");
  assert.equal(pie.props.nameKey, "label");
  assert.equal(
    chart.data.reduce((sum, row) => sum + row.value, 0),
    6,
  );
  assert.equal(part(tree, "Cell").length, chart.data.length);
  const formatted = part(tree, "Tooltip")[0].props.formatter(4, "清澈");
  assert.equal(formatted[0], "4 段");
});

test("donut filters unusable values together with color cells and distinguishes all-zero from missing", () => {
  const chart = {
    ...byType.donut,
    data: [
      { label: "缺測", value: null },
      { label: "清澈", value: 4 },
      { label: "異常", value: -1 },
      { label: "混濁", value: 0 },
    ],
  };
  const tree = render(chart);
  assert.deepEqual(
    Array.from(part(tree, "Pie")[0].props.data, (row) => row.label),
    ["清澈", "混濁"],
  );
  assert.equal(part(tree, "Cell").length, 2);
  assert.match(
    text(render({ ...chart, data: [{ label: "清澈", value: 0 }] })),
    /數量均為 0/,
  );
  assert.match(
    text(render({ ...chart, data: [{ label: "清澈", value: null }] })),
    /沒有可計算比例/,
  );
});

for (const kind of kinds) {
  test(`${kind}: data table and CSV use matching columns, row order, nulls and units`, () => {
    const chart = byType[kind];
    const columns = utils.chartColumns(chart);
    const tree = AnalysisDataTable({ chart });
    const headers = elements(tree, (node) => node.type === "th").map(text);
    const tableRows = elements(tree, (node) => node.type === "tbody")[0].props
      .children;
    const csv = parseCsv(utils.chartCsv(chart));
    assert.deepEqual(csv[0], headers);
    assert.equal(csv.length, chart.data.length + 1);
    assert.equal(tableRows.length, Math.min(200, chart.data.length));
    chart.data.forEach((row, rowIndex) => {
      assert.equal(csv[rowIndex + 1].length, columns.length);
      columns.forEach((column, columnIndex) => {
        const value = row[column.key];
        assert.equal(
          csv[rowIndex + 1][columnIndex],
          value == null ? "" : String(value),
        );
      });
    });
    for (const series of chart.series) {
      const index = columns.findIndex((column) => column.key === series.key);
      assert.ok(headers[index].endsWith(` (${series.unit})`));
    }
  });
}

test("boxplot table/CSV mark all five measurements with their dimension unit, but never count", () => {
  for (const unit of ["mm", "g"]) {
    const chart = {
      ...byType.boxplot,
      series: [{ key: "median", label: "中位數", unit }],
    };
    const columns = utils.chartColumns(chart);
    for (const key of ["min", "q1", "median", "q3", "max"])
      assert.equal(columns.find((column) => column.key === key).unit, unit);
    assert.equal(columns.find((column) => column.key === "count").unit, "");
    const headers = parseCsv(utils.chartCsv(chart))[0];
    assert.equal(
      headers.filter((label) => label.endsWith(` (${unit})`)).length,
      5,
    );
  }
});

test("table limits visual rows explicitly while CSV preserves every precise numeric value", () => {
  const chart = {
    ...byType.table,
    data: Array.from({ length: 240 }, (_, index) => ({
      label: `池 ${index}`,
      p0: index + 0.1234,
      p1: null,
    })),
  };
  const tree = AnalysisDataTable({ chart });
  assert.equal(
    elements(tree, (node) => node.type === "tbody")[0].props.children.length,
    200,
  );
  assert.match(text(tree), /先顯示 200 列；CSV 包含本圖全部 240 列/);
  const csv = parseCsv(utils.chartCsv(chart));
  assert.equal(csv.length, 241);
  assert.deepEqual(csv.at(-1), ["池 239", "239.1234", ""]);
});

test("custom SVG/table text is escaped and CSV protects malicious labels and unit-bearing headers", () => {
  const payload = '<img src=x onerror="alert(1)">';
  const chart = {
    ...byType.table,
    title: payload,
    series: [{ key: "p0", label: "=FORMULA()", unit: "mm" }],
    data: [
      { label: payload, p0: 12.5 },
      { label: "\t=1+1", p0: null },
    ],
  };
  const html = renderToStaticMarkup(
    React.createElement(AnalysisDataTable, { chart }),
  );
  assert.doesNotMatch(html, /<img/);
  assert.ok(html.includes("&lt;img"));
  const csv = parseCsv(utils.chartCsv(chart));
  assert.equal(csv[0][1], "'=FORMULA() (mm)");
  assert.equal(csv[2][0], "'\t=1+1");
  const svg = renderToStaticMarkup(
    React.createElement(AnalysisVisualization, {
      chart: {
        ...byType.boxplot,
        data: [{ ...byType.boxplot.data[0], label: payload }],
      },
    }),
  );
  assert.doesNotMatch(svg, /<img/);
  assert.ok(svg.includes("&lt;img"));
});
