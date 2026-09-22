import type { AnalysisChart } from "./assistant-types";

export function chartColumns(chart: AnalysisChart) {
  const keys = [
    ...new Set([
      chart.x_key,
      ...chart.series.map((series) => series.key),
      ...chart.data.flatMap(Object.keys),
    ]),
  ].filter(Boolean);
  return keys.map((key) => ({
    key,
    unit:
      chart.series.find((series) => series.key === key)?.unit ??
      (chart.type === "boxplot" &&
      ["min", "q1", "median", "q3", "max"].includes(key)
        ? (chart.series.find((series) => series.key === "median")?.unit ?? "")
        : ""),
    label:
      chart.series.find((series) => series.key === key)?.label ??
      (
        {
          label: "分類",
          date: "日期",
          count: "筆數",
          min: "最小值",
          q1: "第一四分位數",
          median: "中位數",
          q3: "第三四分位數",
          max: "最大值",
          value: "數值",
          x: "X",
          y: "Y",
        } as Record<string, string>
      )[key] ??
      key,
  }));
}

/** Quote every cell and neutralize spreadsheet formulas, including whitespace-prefixed payloads. */
export function csvCell(value: string | number | null | undefined): string {
  if (value == null) return '""';
  if (typeof value === "number")
    return Number.isFinite(value) ? `"${value}"` : '""';
  const safe =
    /^[\s\uFEFF]*[=+\-@]/u.test(value) || /^[\t\r\n]/u.test(value)
      ? `'${value}`
      : value;
  return `"${safe.replaceAll('"', '""')}"`;
}
export function chartCsv(chart: AnalysisChart): string {
  const columns = chartColumns(chart);
  return (
    "\uFEFF" +
    [
      columns
        .map((column) =>
          csvCell(`${column.label}${column.unit ? ` (${column.unit})` : ""}`),
        )
        .join(","),
      ...chart.data.map((row) =>
        columns.map((column) => csvCell(row[column.key])).join(","),
      ),
    ].join("\r\n")
  );
}
export function downloadChartCsv(chart: AnalysisChart) {
  const anchor = document.createElement("a");
  const url = URL.createObjectURL(
    new Blob([chartCsv(chart)], { type: "text/csv;charset=utf-8" }),
  );
  try {
    anchor.href = url;
    anchor.download = `tide-${chart.id.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "chart"}.csv`;
    anchor.hidden = true;
    document.body.appendChild(anchor);
    anchor.click();
  } finally {
    try {
      anchor.remove();
    } finally {
      // Give the browser time to start the download, including after a failed click.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }
}
