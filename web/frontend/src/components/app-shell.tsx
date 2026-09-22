"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  ChartPieSliceIcon,
  FilmStripIcon,
  UploadSimpleIcon,
  ArrowUpRightIcon,
  ListIcon,
  XIcon,
  InfoIcon,
  ArrowLeftIcon,
  WavesIcon,
  SparkleIcon,
} from "@phosphor-icons/react";
import { Brand } from "./brand";
import { ServiceStatus } from "./service-status";

export function AppShell({
  children,
  demo = false,
  variant,
}: {
  children: React.ReactNode;
  demo?: boolean;
  variant?: "assistant";
}) {
  const path = usePathname();
  const [menu, setMenu] = useState(false);
  const suffix = demo ? "?demo=1" : "";
  return (
    <div
      className={`app-shell${variant === "assistant" ? " app-shell-assistant" : ""}`}
    >
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <Brand compact />
        <div className="workspace-label">
          分析工作台<span>TIDE WORKSPACE</span>
        </div>
        <nav aria-label="工作台導覽">
          {[
            { href: "/dashboard", label: "分析總覽", icon: ChartPieSliceIcon },
            { href: "/assistant", label: "AI 分析", icon: SparkleIcon },
            { href: "/recordings", label: "影片記錄", icon: FilmStripIcon },
            { href: "/upload", label: "新增分析", icon: UploadSimpleIcon },
          ].map(({ href, label, icon: Icon }) => (
            <Link
              onClick={() => setMenu(false)}
              key={href}
              href={`${href}${suffix}`}
              className={
                path === href ||
                (href === "/recordings" && path.startsWith("/recordings/"))
                  ? "nav-item active"
                  : "nav-item"
              }
            >
              <Icon size={22} weight={path === href ? "fill" : "regular"} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <WavesIcon size={26} />
            <p>
              上傳影片後，
              <br />
              在這裡查看分析結果。
            </p>
          </div>
          <Link href="/" className="nav-item">
            <ArrowLeftIcon size={18} />
            回到首頁
            <ArrowUpRightIcon size={16} />
          </Link>
        </div>
      </aside>
      {menu && (
        <button
          className="sidebar-backdrop"
          onClick={() => setMenu(false)}
          aria-label="關閉導覽"
        />
      )}
      <div className="app-body">
        <header className="app-topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setMenu(!menu)}
            aria-expanded={menu}
            aria-label="切換導覽"
          >
            {menu ? <XIcon /> : <ListIcon />}
          </button>
          <div className="breadcrumb">
            分析工作台<span>/</span>
            <strong>
              {path === "/dashboard"
                ? "分析總覽"
                : path === "/assistant"
                  ? "AI 分析"
                  : path === "/upload"
                    ? "新增分析"
                    : "影片記錄"}
            </strong>
          </div>
          <ServiceStatus demo={demo} variant={variant} />
        </header>
        {demo && variant !== "assistant" && (
          <div className="demo-banner">
            <InfoIcon size={18} />
            <span>
              <strong>示範模式</strong>{" "}
              數值為合成範例，未附實際影片；不代表實際養殖結果。
            </span>
            <Link href={path.startsWith("/recordings/") ? "/dashboard" : path}>
              切換真實資料
              <ArrowUpRightIcon size={15} />
            </Link>
          </div>
        )}
        <main id="main-content" className="app-main">
          {children}
        </main>
        <footer className="app-footer">
          <span>蝦況 TIDE</span>
          <span>日期以台北時間顯示。體型數值為模型估計。</span>
        </footer>
      </div>
    </div>
  );
}
