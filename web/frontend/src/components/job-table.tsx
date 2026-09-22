"use client";
import Link from "next/link";
import Image from "next/image";
import { ArrowRightIcon, FilmStripIcon } from "@phosphor-icons/react";
import { formatDate, formatNumber, mediaUrl } from "@/lib/api";
import type { Job } from "@/lib/types";
import { StatusBadge, WaterBadge } from "./ui";
export function JobTable({
  jobs,
  demo = false,
}: {
  jobs: Job[];
  demo?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table className="job-table">
        <thead>
          <tr>
            <th>分析影片</th>
            <th>池別 / 拍攝時間</th>
            <th>分析狀態</th>
            <th>追蹤個體</th>
            <th>水色分類</th>
            <th>
              <span className="sr-only">查看</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <Link
                  className="recording-link"
                  href={`/recordings/${job.id}${demo ? "?demo=1" : ""}`}
                >
                  <div className="recording-thumbnail">
                    {job.thumbnail_url ? (
                      <Image
                        src={mediaUrl(job.thumbnail_url)!}
                        alt=""
                        width={59}
                        height={40}
                        unoptimized
                      />
                    ) : (
                      <FilmStripIcon size={22} />
                    )}
                  </div>
                  <div>
                    <strong>{job.filename}</strong>
                    <span>
                      {job.mode === "head_tail"
                        ? "頭尾追蹤"
                        : job.mode === "predict"
                          ? "單幀分析"
                          : "個體追蹤"}
                    </span>
                  </div>
                </Link>
              </td>
              <td>
                <strong className="pond-name">{job.pond}</strong>
                <span className="table-sub">
                  {formatDate(job.recorded_at, true)}
                </span>
              </td>
              <td>
                <StatusBadge status={job.status} />
                {job.status === "processing" && (
                  <span className="table-sub">{job.progress}%</span>
                )}
              </td>
              <td className="numeric">
                {job.status === "completed"
                  ? formatNumber(job.shrimp_count, 0)
                  : "待完成"}
                <span className="unit">
                  {job.status === "completed" ? "隻" : ""}
                </span>
              </td>
              <td>
                <WaterBadge label={job.water_label} />
              </td>
              <td>
                <Link
                  className="table-arrow"
                  href={`/recordings/${job.id}${demo ? "?demo=1" : ""}`}
                  aria-label={`查看 ${job.filename}`}
                >
                  <ArrowRightIcon size={19} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
