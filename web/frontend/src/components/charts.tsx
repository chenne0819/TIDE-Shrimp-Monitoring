"use client";
import { useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import type { Overview } from "@/lib/types";
import { formatNumber } from "@/lib/api";
const tooltipStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 10,
  color: "var(--ink)",
  fontSize: 14,
  lineHeight: 1.6,
};
export function TrendChart({ data }: { data: Overview["daily"] }) {
  const [metric, setMetric] = useState<
    "shrimp_count" | "avg_length_mm" | "avg_width_mm" | "avg_weight_g"
  >("shrimp_count");
  const names = {
    shrimp_count: "追蹤個體",
    avg_length_mm: "平均估計長度",
    avg_width_mm: "平均估計寬度",
    avg_weight_g: "平均估計重量",
  };
  const units = {
    shrimp_count: "隻",
    avg_length_mm: "mm",
    avg_width_mm: "mm",
    avg_weight_g: "g",
  };
  const labels = {
    shrimp_count: "個體數",
    avg_length_mm: "長度",
    avg_width_mm: "寬度",
    avg_weight_g: "重量",
  };
  return (
    <section className="chart-panel trend-panel">
      <div className="panel-heading">
        <div>
          <h2>每日分析結果</h2>
          <p>依拍攝日期彙整，可切換下方指標。</p>
        </div>
        <div className="segmented" role="group" aria-label="趨勢指標">
          {(
            [
              "shrimp_count",
              "avg_length_mm",
              "avg_width_mm",
              "avg_weight_g",
            ] as const
          ).map((key) => (
            <button
              key={key}
              onClick={() => setMetric(key)}
              aria-pressed={metric === key}
              className={metric === key ? "selected" : ""}
            >
              {labels[key]}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-axis-label">
        {names[metric]} ({units[metric]})
      </div>
      <div className="chart-box">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 16, right: 22, bottom: 8, left: 0 }}
          >
            <defs>
              <linearGradient id="tide-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#26806e" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#26806e" stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 5"
              vertical={false}
              stroke="var(--border)"
            />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => String(v).slice(5).replace("-", "/")}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--muted)", fontSize: 13 }}
              minTickGap={24}
              height={42}
              dy={8}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--muted)", fontSize: 13 }}
              width={50}
              allowDecimals={metric !== "shrimp_count"}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value) => [
                `${formatNumber(Number(value))} ${units[metric]}`,
                names[metric],
              ]}
              labelFormatter={(label) => String(label)}
            />
            <Area
              type="monotone"
              dataKey={metric}
              stroke="#26806e"
              strokeWidth={2.5}
              fill="url(#tide-area)"
              dot={{ r: 3, strokeWidth: 2, fill: "var(--surface)" }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-footnote">
        {metric === "avg_width_mm"
          ? "寬度為 OBB 框短邊換算的估計值，用作體寬代理。"
          : "個體數為各影片追蹤 ID 的加總，跨影片不會去重。"}
      </p>
    </section>
  );
}
export function DistributionChart({
  data,
}: {
  data: Overview["distributions"];
}) {
  const [kind, setKind] = useState<"length" | "width" | "weight">("length");
  const axisLabels = {
    length: "長度 mm",
    width: "寬度 mm（OBB 框寬估計）",
    weight: "重量 g",
  };
  return (
    <section className="chart-panel distribution-panel">
      <div className="panel-heading">
        <div>
          <h2>體型分布</h2>
          <p>比較各估計長度、寬度或重量區間的個體數。</p>
        </div>
        <div className="segmented" role="group" aria-label="分布指標">
          <button
            className={kind === "length" ? "selected" : ""}
            aria-pressed={kind === "length"}
            onClick={() => setKind("length")}
          >
            長度
          </button>
          <button
            className={kind === "width" ? "selected" : ""}
            aria-pressed={kind === "width"}
            onClick={() => setKind("width")}
          >
            寬度
          </button>
          <button
            className={kind === "weight" ? "selected" : ""}
            aria-pressed={kind === "weight"}
            onClick={() => setKind("weight")}
          >
            重量
          </button>
        </div>
      </div>
      <div className="chart-axis-label">個體數 / {axisLabels[kind]}</div>
      <div className="chart-box distribution-box">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data[kind]}
            margin={{ top: 12, right: 22, bottom: 8, left: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 5"
              vertical={false}
              stroke="var(--border)"
            />
            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--muted)", fontSize: 13 }}
              angle={-25}
              textAnchor="end"
              interval={0}
              height={54}
              dy={8}
            />
            <YAxis
              allowDecimals={false}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--muted)", fontSize: 13 }}
              width={46}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              cursor={{ fill: "var(--soft)" }}
              formatter={(value) => [`${value} 隻`, "個體數"]}
            />
            <Bar
              dataKey="count"
              fill="#3c8068"
              radius={[4, 4, 0, 0]}
              maxBarSize={45}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
export function SexChart({ data }: { data: Overview["sex"] }) {
  const segments = [
    { name: "母蝦", value: data.female, color: "#256454" },
    { name: "公蝦", value: data.male, color: "#7aa282" },
    { name: "未判定", value: data.unknown, color: "#b5bcb8" },
  ];
  const total = data.male + data.female + data.unknown;
  return (
    <section className="chart-panel sex-panel">
      <div className="panel-heading">
        <div>
          <h2>性別組成</h2>
          <p>已分析影片的追蹤個體</p>
        </div>
      </div>
      <div className="donut-wrap">
        <ResponsiveContainer width="100%" height={190}>
          <PieChart>
            <Pie
              data={segments}
              dataKey="value"
              innerRadius={61}
              outerRadius={80}
              paddingAngle={2}
              stroke="none"
              isAnimationActive={false}
            >
              {segments.map((s) => (
                <Cell key={s.name} fill={s.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value) => [`${value} 隻`, "個體數"]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <strong>{formatNumber(total, 0)}</strong>
          <span>追蹤個體</span>
        </div>
      </div>
      <div className="chart-legend">
        {segments.map((s) => (
          <div key={s.name}>
            <span className="legend-key" style={{ background: s.color }} />
            <span>{s.name}</span>
            <strong>{formatNumber(s.value, 0)}</strong>
            <span>{total ? Math.round((s.value / total) * 100) : 0}%</span>
          </div>
        ))}
      </div>
    </section>
  );
}
