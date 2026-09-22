import type { StatisticalResult } from "@/lib/assistant-types";

const methods = {
  descriptive: "描述統計",
  pearson: "Pearson 相關",
  spearman: "Spearman 等級相關",
  welch_t: "Welch t 檢定",
  anova: "Welch 單因子 ANOVA",
};
const dimensions = {
  length_mm: "估計長度",
  width_mm: "估計寬度",
  weight_g: "估計重量",
};

/** Preserve very small probabilities instead of presenting them as exact zero. */
export function formatStatistic(
  value: number | null,
  probability = false,
): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (probability && value === 0) return "低於數值精度";
  if (value !== 0 && (Math.abs(value) < 0.0001 || Math.abs(value) >= 1e8))
    return value.toExponential(3);
  return new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: probability ? 6 : 4,
  }).format(value);
}

export function StatisticalCard({ result }: { result: StatisticalResult }) {
  const unit = result.unit;
  const columns = [
    ["min", "最小值"],
    ["max", "最大值"],
    ["mean", "平均值"],
    ["median", "中位數"],
    ["std_dev", "樣本標準差"],
    ["q1", "Q1"],
    ["q3", "Q3"],
  ] as const;
  return (
    <section
      className="ai-chart-card ai-chart-wide ai-stat-card"
      aria-label={result.title}
    >
      <header className="ai-chart-heading">
        <div>
          <span className="ai-chart-kind">{methods[result.method]}</span>
          <h3>{result.title}</h3>
        </div>
        <span className="ai-stat-status">
          {result.status === "completed" ? "已計算" : "無法計算"}
        </span>
      </header>
      <p className="ai-chart-description">
        {dimensions[result.metric]}
        {result.secondary_metric
          ? ` × ${dimensions[result.secondary_metric]}`
          : ""}
        {" · "}
        {result.sample_unit === "video_mean"
          ? "每部影片先取平均，影片等權"
          : "以影片內追蹤 ID 為單位"}
      </p>
      {result.reason && (
        <p className="ai-stat-reason" role="note">
          {result.reason}
        </p>
      )}
      {!!result.values.length && (
        <dl className="ai-stat-values">
          {result.values.map((item, index) => (
            <div key={index}>
              <dt>{item.label}</dt>
              <dd>
                {formatStatistic(
                  item.value,
                  /^p(?:$|\s|[-（(])/i.test(item.label),
                )}
                {item.unit && <small>{item.unit}</small>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {!!result.secondary_metric && !!result.groups.length && (
        <p className="ai-chart-description">
          下表為{dimensions[result.metric]}
          摘要（兩項指標皆有效的配對樣本），單位 {unit}。
        </p>
      )}
      {!!result.groups.length && (
        <div
          className="ai-table-scroll"
          tabIndex={0}
          role="region"
          aria-label={`${result.title}統計數值`}
        >
          <table className="ai-data-table">
            <caption className="sr-only">
              {result.title}，數值單位 {unit}，n 為有效
              {result.sample_unit === "video_mean" ? "影片" : "追蹤 ID"}數
            </caption>
            <thead>
              <tr>
                <th scope="col">分組</th>
                <th scope="col">n</th>
                {columns.map(([key, label]) => (
                  <th scope="col" key={key}>
                    {label} ({unit})
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.groups.map((group, index) => (
                <tr key={index}>
                  <th scope="row">{group.label}</th>
                  <td className="ai-number">{formatStatistic(group.n)}</td>
                  {columns.map(([key]) => (
                    <td className="ai-number" key={key}>
                      {formatStatistic(group[key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!!result.warnings.length && (
        <details className="ai-stat-notes">
          <summary>計算方式與使用限制</summary>
          <ul>
            {result.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
