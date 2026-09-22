const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource, elements } = require("./helpers.cjs");

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
const { AnalysisVisualization } = loadSource(
  "src/components/assistant-charts.tsx",
  {
    recharts,
    "@/lib/api": { formatNumber: (value) => String(value) },
    "@/lib/assistant-utils": { chartColumns: () => [] },
  },
);
const scatter = {
  id: "scatter",
  type: "scatter",
  title: "長度與重量",
  x_key: "x",
  description: "",
  series: [
    { key: "x", label: "估計長度", unit: "mm" },
    { key: "y", label: "估計重量", unit: "g" },
  ],
  data: [{ x: 55, y: 4.5, label: "池 A · ID 1" }],
  note: "",
  sample_count: 1,
};

test("scatter axes and tooltip use each metric's own label and unit", () => {
  const tree = AnalysisVisualization({ chart: scatter });
  const x = elements(tree, (node) => node.type === recharts.XAxis)[0];
  const y = elements(tree, (node) => node.type === recharts.YAxis)[0];
  const tooltip = elements(tree, (node) => node.type === recharts.Tooltip)[0];
  assert.equal(x.props.name, "估計長度");
  assert.equal(x.props.unit, "mm");
  assert.equal(y.props.name, "估計重量");
  assert.equal(y.props.unit, "g");
  assert.equal(
    tooltip.props.formatter(4.5, "估計重量", { unit: "g" })[0],
    "4.5 g",
  );
});

test("scatter only displays complete finite pairs and never turns missing values into zero", () => {
  const tree = AnalysisVisualization({
    chart: {
      ...scatter,
      data: [
        ...scatter.data,
        { x: 20, y: null },
        { x: Infinity, y: 3 },
        { x: 0, y: 0 },
      ],
    },
  });
  const points = elements(tree, (node) => node.type === recharts.Scatter)[0]
    .props.data;
  assert.equal(points.length, 2);
  assert.equal(points[0].x, 55);
  assert.equal(points[0].y, 4.5);
  assert.equal(points[1].x, 0);
  assert.equal(points[1].y, 0);
});

test("box plot keeps period and pond labels distinct on separate lines and identifies its unit", () => {
  const labels = ["本月（尚未完整） · A-01", "本月（尚未完整） · B-02"];
  const component = AnalysisVisualization({
    chart: {
      ...scatter,
      type: "boxplot",
      title: "各池長度分布",
      x_key: "label",
      series: [{ key: "median", label: "中位估計長度", unit: "mm" }],
      data: labels.map((label) => ({
        label,
        min: 30,
        q1: 42,
        median: 50,
        q3: 58,
        max: 70,
        count: 30,
      })),
    },
  });
  const tree = component.type(component.props);
  const lines = elements(tree, (node) => node.type === "tspan");
  assert.deepEqual(
    lines.map((node) => node.props.children),
    ["本月（尚未完整）", "A-01", "本月（尚未完整）", "B-02"],
  );
  assert.equal(lines[1].props.dy, 19);
  const titles = elements(tree, (node) => node.type === "title");
  labels.forEach((label, index) =>
    assert.ok(titles[index].props.children.startsWith(label)),
  );
  assert.ok(
    elements(tree, (node) => node.type === "text").some(
      (node) => node.props.children === "mm",
    ),
  );
});
