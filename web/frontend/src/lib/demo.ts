import type { Filters, JobDetail, Overview, Track } from "./types";

// Explicit opt-in interface samples. Never used as a fallback for API failures.
const counts = [
  86, 102, 119, 107, 124, 138, 132, 151, 143, 166, 158, 171, 163, 184,
];
const average = (values: number[]) =>
  values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
export const demoJobs: JobDetail[] = counts
  .map<JobDetail>((count, i) => {
    const day = 14 + Math.floor(i / 2);
    const tracks: Track[] = Array.from({ length: count }, (_, n) => ({
      track_id: String(n + 1).padStart(3, "0"),
      label: n % 11 === 0 ? "Unknown" : n % 3 === 0 ? "Male" : "Female",
      observations: 14 + (n % 56),
      length_mm: Math.round((65 + ((n * 17 + i * 3) % 61)) * 10) / 10,
      width_mm: Math.round((8 + ((n * 7 + i) % 13)) * 10) / 10,
      weight_g: Math.round((6 + ((n * 11 + i * 2) % 30)) * 10) / 10,
    }));
    return {
      id: `demo-${i + 1}`,
      filename: `池邊觀察_${String(day).padStart(2, "0")}_${i % 2 ? "午後" : "清晨"}.mp4`,
      pond: i % 2 ? "B-02" : "A-01",
      recorded_at: `2026-09-${day}T${i % 2 ? "14:30" : "08:15"}:00+08:00`,
      created_at: `2026-09-${day}T15:00:00+08:00`,
      status: "completed",
      progress: 100,
      mode: "general",
      water_label: i === 3 || i === 8 ? "turbid" : "clear",
      water_confidence: 0.91 + (i % 7) / 100,
      shrimp_count: count,
      avg_length_mm: average(tracks.map((t) => t.length_mm!)),
      avg_width_mm: average(tracks.map((t) => t.width_mm!)),
      avg_weight_g: average(tracks.map((t) => t.weight_g!)),
      source_video_url: null,
      result_video_url: null,
      thumbnail_url: null,
      error: null,
      processed_frames: 8,
      tracks,
      metadata: {
        sample: true,
        note: "統計數值為合成的介面示範資料，未附實際影片或縮圖。",
        pixels_per_mm: 2.5,
      },
      artifacts: [],
    };
  })
  .reverse();
export function filteredDemoJobs(filters: Filters): JobDetail[] {
  return demoJobs.filter(
    (job) =>
      (!filters.pond || job.pond === filters.pond) &&
      (!filters.start_date ||
        job.recorded_at.slice(0, 10) >= filters.start_date) &&
      (!filters.end_date || job.recorded_at.slice(0, 10) <= filters.end_date),
  );
}
function histogram(values: number[], boundaries: number[]) {
  return boundaries.slice(0, -1).map((start, i) => ({
    label: `${start}–${boundaries[i + 1]}`,
    count: values.filter((value) => value >= start && value < boundaries[i + 1])
      .length,
  }));
}
function widthValues(tracks: Track[]): number[] {
  return tracks
    .map((track) => track.width_mm)
    .filter(
      (width): width is number => width !== null && Number.isFinite(width),
    );
}
function widthHistogram(values: number[]) {
  const labels = ["<10", "10–15", "15–20", "20–25", "≥25"];
  return histogram(values, [-Infinity, 10, 15, 20, 25, Infinity]).map(
    (bin, index) => ({ ...bin, label: labels[index] }),
  );
}
export function demoOverview(filters: Filters): Overview {
  const jobs = filteredDemoJobs(filters);
  const tracks = jobs.flatMap((job) => job.tracks);
  const dates = [
    ...new Set(jobs.map((job) => job.recorded_at.slice(0, 10))),
  ].sort();
  return {
    summary: {
      jobs_total: jobs.length,
      completed: jobs.length,
      processing: 0,
      shrimp_count: tracks.length,
      avg_length_mm: average(tracks.map((t) => t.length_mm!)),
      avg_width_mm: average(widthValues(tracks)),
      avg_weight_g: average(tracks.map((t) => t.weight_g!)),
      clear_count: jobs.filter((j) => j.water_label === "clear").length,
      turbid_count: jobs.filter((j) => j.water_label === "turbid").length,
    },
    daily: dates.map((date) => {
      const dayJobs = jobs.filter((j) => j.recorded_at.startsWith(date));
      const dayTracks = dayJobs.flatMap((j) => j.tracks);
      return {
        date,
        videos: dayJobs.length,
        shrimp_count: dayTracks.length,
        avg_length_mm: average(dayTracks.map((t) => t.length_mm!)),
        avg_width_mm: average(widthValues(dayTracks)),
        avg_weight_g: average(dayTracks.map((t) => t.weight_g!)),
        clear_count: dayJobs.filter((j) => j.water_label === "clear").length,
        turbid_count: dayJobs.filter((j) => j.water_label === "turbid").length,
      };
    }),
    distributions: {
      length: histogram(
        tracks.map((t) => t.length_mm!),
        [60, 70, 80, 90, 100, 110, 120, 130],
      ),
      width: widthHistogram(widthValues(tracks)),
      weight: histogram(
        tracks.map((t) => t.weight_g!),
        [0, 6, 12, 18, 24, 30, 36],
      ),
    },
    sex: {
      male: tracks.filter((t) => t.label === "Male").length,
      female: tracks.filter((t) => t.label === "Female").length,
      unknown: tracks.filter((t) => t.label === "Unknown").length,
    },
    recent_jobs: jobs.slice(0, 6),
    available_ponds: ["A-01", "B-02"],
  };
}
