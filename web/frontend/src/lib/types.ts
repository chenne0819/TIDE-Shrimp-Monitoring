export type JobStatus =
  "queued" | "processing" | "completed" | "stopped" | "failed";
export type Job = {
  id: string;
  filename: string;
  pond: string;
  recorded_at: string;
  created_at: string;
  status: JobStatus;
  progress: number;
  mode: "general" | "head_tail" | "predict";
  water_label: "clear" | "turbid" | null;
  water_confidence: number | null;
  shrimp_count: number;
  avg_length_mm: number | null;
  avg_width_mm: number | null;
  avg_weight_g: number | null;
  source_video_url: string | null;
  result_video_url: string | null;
  thumbnail_url: string | null;
  error: string | null;
  processed_frames: number;
};
export type Track = {
  track_id: string;
  label: "Male" | "Female" | "Unknown";
  observations: number;
  length_mm: number | null;
  width_mm: number | null;
  weight_g: number | null;
};
export type JobDetail = Job & {
  tracks: Track[];
  metadata: Record<string, unknown>;
  artifacts: { kind: string; label: string; url: string }[];
};
export type Daily = {
  date: string;
  videos: number;
  shrimp_count: number;
  avg_length_mm: number | null;
  avg_width_mm: number | null;
  avg_weight_g: number | null;
  clear_count: number;
  turbid_count: number;
};
export type Overview = {
  summary: {
    jobs_total: number;
    completed: number;
    processing: number;
    shrimp_count: number;
    avg_length_mm: number | null;
    avg_width_mm: number | null;
    avg_weight_g: number | null;
    clear_count: number;
    turbid_count: number;
  };
  daily: Daily[];
  distributions: {
    length: { label: string; count: number }[];
    width: { label: string; count: number }[];
    weight: { label: string; count: number }[];
  };
  sex: { male: number; female: number; unknown: number };
  recent_jobs: Job[];
  available_ponds: string[];
};
export type Filters = { start_date?: string; end_date?: string; pond?: string };
