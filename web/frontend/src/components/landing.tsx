"use client";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { motion } from "motion/react";
import { useReducedMotionPreference } from "@/lib/use-reduced-motion";
import {
  ArrowUpRightIcon,
  ArrowRightIcon,
  WavesIcon,
  RulerIcon,
  CrosshairIcon,
  UploadSimpleIcon,
  ChartBarIcon,
  ListIcon,
  XIcon,
} from "@phosphor-icons/react";
import { Brand } from "./brand";
import { HeroScene } from "./hero-scene";

// Preserve the ocean brand while explaining the actual analysis workflow.
export function Landing() {
  const reduce = useReducedMotionPreference();
  const [menu, setMenu] = useState(false);
  const reveal = {
    initial: reduce ? (false as const) : { opacity: 0, y: 32 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.2 },
    transition: { duration: 0.65 },
  };
  return (
    <div className="landing">
      <header className="landing-header">
        <Brand />
        <nav
          className={menu ? "landing-nav open" : "landing-nav"}
          aria-label="首頁導覽"
        >
          <a href="#observation" onClick={() => setMenu(false)}>
            功能介紹
          </a>
          <a href="#workflow" onClick={() => setMenu(false)}>
            分析流程
          </a>
          <Link href="/dashboard?demo=1">查看示範</Link>
        </nav>
        <Link href="/dashboard" className="button nav-button">
          進入工作台
          <ArrowUpRightIcon size={17} />
        </Link>
        <button
          className="icon-button mobile-menu"
          onClick={() => setMenu(!menu)}
          aria-label={menu ? "關閉選單" : "開啟選單"}
          aria-expanded={menu}
        >
          {menu ? <XIcon /> : <ListIcon />}
        </button>
      </header>
      <main id="main-content">
        <HeroScene />
        <section
          className="observation-section page-width"
          id="observation"
          tabIndex={-1}
        >
          <motion.div {...reveal} className="observation-heading">
            <h2>
              追蹤結果與體型數據，
              <br />
              對照影片一起看。
            </h2>
            <p>選擇日期與養殖池，查看影片、個體記錄和尺寸分布。</p>
          </motion.div>
          <div className="observation-grid">
            <motion.figure {...reveal} className="observation-media">
              <div className="observation-image">
                <Image
                  src="/images/shrimp-observation.webp"
                  alt="從上方觀察水中的草蝦，AI 生成示意"
                  fill
                  sizes="(max-width: 760px) 100vw, 50vw"
                />
              </div>
            </motion.figure>
            <div className="feature-list">
              {[
                {
                  icon: CrosshairIcon,
                  title: "查看蝦隻追蹤結果",
                  text: "播放標記後的影片，對照各追蹤 ID 的量測記錄。",
                },
                {
                  icon: RulerIcon,
                  title: "比較長度、寬度與重量",
                  text: "查看平均值和分布，依日期與池別比較體型變化。",
                },
                {
                  icon: WavesIcon,
                  title: "記錄清澈與混濁情況",
                  text: "依影片畫面分類水色，搭配現場水質量測一起判斷。",
                },
              ].map(({ icon: Icon, title, text }, i) => (
                <motion.article
                  key={title}
                  {...reveal}
                  transition={{ duration: 0.6, delay: i * 0.08 }}
                >
                  <Icon key="icon" size={27} />
                  <div key="copy">
                    <h3>{title}</h3>
                    <p>{text}</p>
                  </div>
                  <ArrowUpRightIcon
                    key="arrow"
                    size={19}
                    className="feature-arrow"
                  />
                </motion.article>
              ))}
            </div>
          </div>
        </section>
        <section className="workflow-section page-width" id="workflow">
          <motion.div {...reveal} className="workflow-heading">
            <h2>上傳後，怎麼看結果？</h2>
            <p>影片交給系統分析，完成後就能播放、比較和匯出。</p>
          </motion.div>
          <div className="workflow-grid">
            {[
              {
                icon: UploadSimpleIcon,
                title: "上傳影片",
                text: "選擇影片，填寫池別與拍攝時間，也能使用收件資料夾。",
              },
              {
                icon: CrosshairIcon,
                title: "等待分析完成",
                text: "系統依序追蹤蝦隻、估計體型並分類水色，可在影片清單查看進度。",
              },
              {
                icon: ChartBarIcon,
                title: "查看與下載結果",
                text: "播放分析影片、比較每日分布，或下載 CSV 做進一步整理。",
              },
            ].map(({ icon: Icon, title, text }) => (
              <motion.article {...reveal} key={title}>
                <Icon key="icon" size={31} />
                <h3 key="title">{title}</h3>
                <p key="description">{text}</p>
              </motion.article>
            ))}
          </div>
        </section>
        <motion.section {...reveal} className="landing-cta page-width">
          <div>
            <h2>已有拍好的影片？</h2>
            <p>上傳一段影片，查看這次拍攝的蝦隻體型與水色情況。</p>
          </div>
          <Link href="/upload" className="button button-lime">
            新增影片分析
            <ArrowRightIcon size={21} />
          </Link>
        </motion.section>
      </main>
      <footer className="landing-footer page-width">
        <Brand compact />
        <p>蝦隻影像分析與記錄</p>
        <span>體型為估計值；更換拍攝條件後需重新校正。</span>
      </footer>
    </div>
  );
}
