"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalysisChart } from "@/lib/assistant-types";
import { chartColumns } from "@/lib/assistant-utils";
import { formatNumber } from "@/lib/api";

const colors = [
  "#277b65",
  "#b68539",
  "#508ca5",
  "#9475a7",
  "#689347",
  "#ba6964",
];
const tick = { fontSize: 13, fill: "var(--muted)" };
const tooltip = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 10,
  color: "var(--ink)",
  fontSize: 14,
  lineHeight: 1.6,
};
const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const display = (value: unknown) =>
  finite(value) ? formatNumber(value, 2) : value == null ? "—" : String(value);

export function AnalysisDataTable({ chart }: { chart: AnalysisChart }) {
  const columns = chartColumns(chart);
  return (
    <div
      className="ai-table-scroll"
      tabIndex={0}
      role="region"
      aria-label={`${chart.title}資料表`}
    >
      <table className="ai-data-table">
        <caption className="sr-only">
          {chart.title}；{chart.data.length} 列
        </caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.label}
                {column.unit ? ` (${column.unit})` : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {chart.data.slice(0, 200).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={
                    typeof row[column.key] === "number" ? "ai-number" : ""
                  }
                >
                  {display(row[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {chart.data.length > 200 && (
        <p className="ai-small">
          先顯示 200 列；CSV 包含本圖全部 {chart.data.length} 列。
        </p>
      )}
    </div>
  );
}

function BoxPlot({ chart }: { chart: AnalysisChart }) {
  const rows = chart.data.filter((row) =>
    [row.min, row.q1, row.median, row.q3, row.max].every(finite),
  );
  if (!rows.length)
    return <p className="ai-chart-empty">這個範圍沒有足夠的體型數據。</p>;
  const min = Math.min(...rows.map((row) => Number(row.min)));
  const max = Math.max(...rows.map((row) => Number(row.max)));
  const padding = (max - min || Math.abs(max) || 1) * 0.1;
  const lower = Math.max(0, min - padding);
  const upper = max + padding;
  const labels = rows.map((row, index) => {
    const [period, ...group] = String(row.label ?? index + 1).split(" · ");
    return [period, group.join(" · ")];
  });
  const labelWidth = Math.max(
    144,
    ...labels.flat().map((label) => Array.from(label).length * 13 + 24),
  );
  const width = Math.max(560, rows.length * labelWidth + 72);
  const left = 58,
    right = width - 18,
    top = 32,
    bottom = 252;
  const y = (value: number) =>
    bottom - ((value - lower) / (upper - lower || 1)) * (bottom - top);
  const step = (right - left) / rows.length;
  const unit = chart.series[0]?.unit ?? "";
  return (
    <div
      className="ai-custom-scroll"
      tabIndex={0}
      role="region"
      aria-label={`${chart.title}箱型圖`}
    >
      <svg
        viewBox={`0 0 ${width} 320`}
        style={{ minWidth: width }}
        role="img"
        aria-label={`${chart.title}。盒子表示第一至第三四分位數，中央線為中位數；完整數值可切換資料表。`}
      >
        <text
          x={left - 9}
          y={14}
          textAnchor="end"
          fill="var(--muted)"
          fontSize={13}
        >
          {unit}
        </text>
        {[0, 1, 2, 3, 4].map((i) => {
          const value = lower + ((upper - lower) * i) / 4;
          return (
            <g key={i}>
              <line
                x1={left}
                x2={right}
                y1={y(value)}
                y2={y(value)}
                stroke="var(--border)"
                strokeDasharray="3 4"
              />
              <text
                x={left - 9}
                y={y(value) + 4}
                textAnchor="end"
                fill="var(--muted)"
                fontSize={13}
              >
                {formatNumber(value, 1)}
              </text>
            </g>
          );
        })}
        {rows.map((row, index) => {
          const x = left + step * (index + 0.5),
            boxWidth = Math.min(step * 0.5, 46);
          return (
            <g key={index}>
              <title>{`${row.label}: 最小 ${display(row.min)}，Q1 ${display(row.q1)}，中位 ${display(row.median)}，Q3 ${display(row.q3)}，最大 ${display(row.max)} ${unit}；${display(row.count)} 筆`}</title>
              <line
                x1={x}
                x2={x}
                y1={y(Number(row.min))}
                y2={y(Number(row.max))}
                stroke={colors[index % colors.length]}
                strokeWidth={2}
              />
              {[row.min, row.max].map((value, i) => (
                <line
                  key={i}
                  x1={x - boxWidth / 3}
                  x2={x + boxWidth / 3}
                  y1={y(Number(value))}
                  y2={y(Number(value))}
                  stroke={colors[index % colors.length]}
                  strokeWidth={2}
                />
              ))}
              <rect
                x={x - boxWidth / 2}
                y={y(Number(row.q3))}
                width={boxWidth}
                height={Math.max(1, y(Number(row.q1)) - y(Number(row.q3)))}
                fill={colors[index % colors.length]}
                fillOpacity={0.2}
                stroke={colors[index % colors.length]}
                strokeWidth={2}
              />
              <line
                x1={x - boxWidth / 2}
                x2={x + boxWidth / 2}
                y1={y(Number(row.median))}
                y2={y(Number(row.median))}
                stroke={colors[index % colors.length]}
                strokeWidth={3}
              />
              <text
                x={x}
                y={bottom + 25}
                textAnchor="middle"
                fill="var(--muted)"
                fontSize={13}
              >
                <tspan x={x}>{labels[index][0]}</tspan>
                {labels[index][1] && (
                  <tspan x={x} dy={19}>
                    {labels[index][1]}
                  </tspan>
                )}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Heatmap({ chart }: { chart: AnalysisChart }) {
  const columns = [...new Set(chart.data.map((row) => String(row.x ?? "")))];
  const rows = [...new Set(chart.data.map((row) => String(row.y ?? "")))];
  const values = chart.data.map((row) => row.value).filter(finite);
  const min = Math.min(...values),
    max = Math.max(...values);
  const lookup = new Map(
    chart.data.map((row) => [
      JSON.stringify([String(row.x ?? ""), String(row.y ?? "")]),
      row.value,
    ]),
  );
  return (
    <div className="ai-heatmap">
      <div
        className="ai-table-scroll"
        tabIndex={0}
        role="region"
        aria-label={`${chart.title}熱圖`}
      >
        <table className="ai-data-table ai-heatmap-table">
          <thead>
            <tr>
              <th scope="col">分類</th>
              {columns.map((x) => (
                <th scope="col" key={x}>
                  {x}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((y) => (
              <tr key={y}>
                <th scope="row">{y}</th>
                {columns.map((x) => {
                  const value = lookup.get(JSON.stringify([x, y]));
                  const intensity = finite(value)
                    ? (value - min) / (max - min || 1)
                    : 0;
                  return (
                    <td key={x}>
                      <span
                        className={
                          finite(value)
                            ? "ai-heat-cell"
                            : "ai-heat-cell ai-missing"
                        }
                        style={
                          finite(value)
                            ? {
                                background: `rgba(39,123,101,${0.12 + intensity * 0.75})`,
                                color: intensity > 0.55 ? "#fff" : "var(--ink)",
                              }
                            : undefined
                        }
                        title={`${y} / ${x}: ${display(value)} ${chart.series[0]?.unit ?? ""}`}
                      >
                        {display(value)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="ai-heat-legend">
        <span>較低 {finite(min) ? display(min) : "—"}</span>
        <i />
        <span>較高 {finite(max) ? display(max) : "—"}</span>
        <span>— 無資料</span>
      </div>
    </div>
  );
}

export function AnalysisVisualization({ chart }: { chart: AnalysisChart }) {
  if (!chart.data.length)
    return <p className="ai-chart-empty">這個範圍還沒有可顯示的資料。</p>;
  if (chart.type === "table") return <AnalysisDataTable chart={chart} />;
  if (chart.type === "boxplot") return <BoxPlot chart={chart} />;
  if (chart.type === "heatmap") return <Heatmap chart={chart} />;
  const data = chart.data.map((row) =>
    Object.fromEntries(
      Object.entries(row).map(([key, value]) => [
        key,
        typeof value === "number" && !Number.isFinite(value) ? null : value,
      ]),
    ),
  );
  const unit = chart.series[0]?.unit ?? "";
  const scatterX = chart.series.find((series) => series.key === "x");
  const scatterY = chart.series.find((series) => series.key === "y");
  const common = { data, margin: { top: 12, right: 15, bottom: 12, left: 0 } };
  const axes = (
    <>
      <CartesianGrid
        stroke="var(--border)"
        strokeDasharray="3 4"
        vertical={false}
      />
      <XAxis
        dataKey={chart.x_key}
        tick={tick}
        axisLine={false}
        tickLine={false}
        minTickGap={25}
      />
      <YAxis
        tick={tick}
        width={52}
        axisLine={false}
        tickLine={false}
        tickFormatter={(value) => formatNumber(value, 1)}
      />
      <Tooltip
        contentStyle={tooltip}
        formatter={(value, name) => [display(value), String(name)]}
      />
      <Legend wrapperStyle={{ fontSize: 13, paddingTop: 12 }} />
    </>
  );
  const name = (series: AnalysisChart["series"][number]) =>
    `${series.label}${series.unit ? ` (${series.unit})` : ""}`;
  let plot;
  switch (chart.type) {
    case "line":
      plot = (
        <LineChart {...common}>
          {axes}
          {chart.series.map((series, i) => (
            <Line
              key={series.key}
              dataKey={series.key}
              name={name(series)}
              type="linear"
              stroke={colors[i % colors.length]}
              strokeWidth={2.5}
              dot={data.length < 20 ? { r: 3 } : false}
              activeDot={{ r: 5 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      );
      break;
    case "area":
      plot = (
        <AreaChart {...common}>
          {axes}
          {chart.series.map((series, i) => (
            <Area
              key={series.key}
              dataKey={series.key}
              name={name(series)}
              type="linear"
              stroke={colors[i % colors.length]}
              fill={colors[i % colors.length]}
              fillOpacity={0.15}
              strokeWidth={2.5}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      );
      break;
    case "bar":
    case "stacked_bar":
    case "histogram":
      plot = (
        <BarChart
          {...common}
          barCategoryGap={chart.type === "histogram" ? "3%" : "22%"}
        >
          {axes}
          {chart.series.map((series, i) => (
            <Bar
              key={series.key}
              dataKey={series.key}
              name={name(series)}
              fill={colors[i % colors.length]}
              stackId={chart.type === "stacked_bar" ? "count" : undefined}
              maxBarSize={48}
              radius={chart.type === "stacked_bar" ? 0 : [3, 3, 0, 0]}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      );
      break;
    case "scatter": {
      const pairs = data.filter((row) => finite(row.x) && finite(row.y));
      if (!pairs.length)
        return (
          <p className="ai-chart-empty">這個範圍沒有完整的有效配對數據。</p>
        );
      plot = (
        <ScatterChart margin={{ top: 12, right: 22, bottom: 22, left: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 4" />
          <XAxis
            type="number"
            dataKey="x"
            name={scatterX?.label ?? "X"}
            unit={scatterX?.unit ?? ""}
            tick={tick}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={scatterY?.label ?? "Y"}
            unit={scatterY?.unit ?? ""}
            tick={tick}
            width={58}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={tooltip}
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(value, label, item) => [
              `${display(value)}${item.unit ? ` ${item.unit}` : ""}`,
              label,
            ]}
          />
          <Scatter
            data={pairs}
            fill={colors[0]}
            fillOpacity={0.7}
            isAnimationActive={false}
          />
        </ScatterChart>
      );
      break;
    }
    case "donut": {
      if (!chart.series.length)
        return <p className="ai-chart-empty">未提供分類數值。</p>;
      const counts = data.filter(
        (row) =>
          finite(row[chart.series[0].key]) &&
          Number(row[chart.series[0].key]) >= 0,
      );
      if (!counts.length)
        return <p className="ai-chart-empty">沒有可計算比例的分類數據。</p>;
      if (!counts.some((row) => Number(row[chart.series[0].key]) > 0))
        return <p className="ai-chart-empty">分類數量均為 0，無法計算比例。</p>;
      plot = (
        <PieChart>
          <Pie
            data={counts}
            dataKey={chart.series[0].key}
            nameKey={chart.x_key}
            cx="50%"
            cy="43%"
            innerRadius="48%"
            outerRadius="72%"
            paddingAngle={2}
            isAnimationActive={false}
          >
            {counts.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={tooltip}
            formatter={(value, label) => [`${display(value)} ${unit}`, label]}
          />
          <Legend wrapperStyle={{ fontSize: 14 }} />
        </PieChart>
      );
      break;
    }
    default:
      return (
        <p className="ai-chart-empty">
          這種圖表尚未支援，請切換資料表查看數值。
        </p>
      );
  }
  return (
    <div className="ai-visualization">
      <ResponsiveContainer width="100%" height={282} minWidth={0}>
        {plot}
      </ResponsiveContainer>
    </div>
  );
}
