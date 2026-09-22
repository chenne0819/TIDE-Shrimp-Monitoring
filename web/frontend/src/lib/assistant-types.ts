export type ChartKind =
  | "line"
  | "area"
  | "bar"
  | "stacked_bar"
  | "histogram"
  | "scatter"
  | "boxplot"
  | "heatmap"
  | "donut"
  | "table";
export type AnalysisPeriod = {
  id: string;
  label: string;
  start_date: string;
  end_date: string;
};
export type AnalysisSeries = { key: string; label: string; unit: string };
export type AnalysisChart = {
  id: string;
  type: ChartKind;
  title: string;
  description: string;
  x_key: string;
  series: AnalysisSeries[];
  data: Record<string, string | number | null>[];
  note: string;
  sample_count: number;
};
export type AnalysisKpi = {
  label: string;
  value: number | null;
  unit: string;
  previous_value: number | null;
  delta_pct: number | null;
};
export type AnalysisSource = {
  id: string;
  filename: string;
  pond: string;
  recorded_at: string;
};
export type Dimension = "length_mm" | "width_mm" | "weight_g";
export type StatisticalMethod =
  "descriptive" | "pearson" | "spearman" | "welch_t" | "anova";
export type StatisticalSummary = {
  count: number;
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
  std_dev: number | null;
  q1: number | null;
  q3: number | null;
};
export type StatisticalResult = {
  id: string;
  method: StatisticalMethod;
  title: string;
  status: "completed" | "not_applicable";
  metric: Dimension;
  secondary_metric: Dimension | null;
  unit: "mm" | "g";
  sample_unit: "track" | "video_mean";
  groups: (Omit<StatisticalSummary, "count"> & { label: string; n: number })[];
  values: { label: string; value: number | null; unit: string }[];
  warnings: string[];
  reason: string | null;
};
export type AnalysisBoard = {
  id: string;
  title: string;
  generated_at: string;
  demo: boolean;
  timezone: string;
  query: { periods: AnalysisPeriod[]; ponds: string[]; aggregation: string };
  kpis: AnalysisKpi[];
  charts: AnalysisChart[];
  statistics?: StatisticalResult[];
  descriptive_summary?: {
    period_id: string;
    label: string;
    metrics: Record<Dimension, StatisticalSummary>;
  }[];
  warnings: string[];
  sources: AnalysisSource[];
  total_jobs: number;
  total_tracks: number;
  period_summaries: {
    id: string;
    label: string;
    days: number;
    videos: number;
    tracks: number;
    valid_length: number;
    valid_width: number;
    valid_weight: number;
  }[];
};
export type AssistantStatus =
  "planning" | "querying" | "answering" | "completed" | "failed" | "cancelled";
export type AssistantActivity = {
  id: string;
  kind: "context" | "plan" | "query" | "charts" | "answer" | "complete";
  label: string;
  status: "running" | "completed" | "failed" | "cancelled";
  started_at: string;
  finished_at: string | null;
  detail: string;
  metadata: Record<string, unknown>;
};
export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: AssistantStatus;
  response_kind?: "pending" | "answer" | "analysis";
  created_at: string;
  board: AnalysisBoard | null;
  followups: string[];
  error: string | null;
  activity: AssistantActivity[];
};
export type AssistantConversation = {
  id: string;
  title: string;
  demo: boolean;
  created_at: string;
  updated_at: string;
};
export type AssistantDetail = AssistantConversation & {
  messages: AssistantMessage[];
};
export type AssistantCapabilities = {
  enabled: boolean;
  provider: string;
  model: string;
  reason: string | null;
  today: string;
  timezone: string;
  available_ponds: string[];
  earliest_date: string | null;
  latest_date: string | null;
  templates: { type: ChartKind; label: string; description: string }[];
  statistical_methods?: {
    method: StatisticalMethod;
    label: string;
    description: string;
  }[];
};
