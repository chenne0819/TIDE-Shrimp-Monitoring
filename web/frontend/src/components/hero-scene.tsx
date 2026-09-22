"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { useScroll } from "motion/react";
import {
  ArrowDownIcon,
  ArrowUpRightIcon,
  PlayIcon,
} from "@phosphor-icons/react";
import { useReducedMotionPreference } from "@/lib/use-reduced-motion";
import { createSwimScene } from "@/lib/swim-scene";

/** Scroll moves the underwater camera and a separately animated swimming shrimp. */
export function HeroScene() {
  const track = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const counter = useRef<HTMLOutputElement>(null);
  const copy = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotionPreference();
  const { scrollY } = useScroll();

  useEffect(() => {
    if (reduce || !track.current || !stage.current || !canvas.current) return;
    const controller = createSwimScene({
      track: track.current,
      stage: stage.current,
      canvas: canvas.current,
      counter: counter.current,
      copy: copy.current,
    });
    const unsubscribe = scrollY.on("change", controller.update);
    controller.update();
    return () => {
      unsubscribe();
      controller.destroy();
    };
  }, [reduce, scrollY]);

  const skip = (event: React.MouseEvent<HTMLAnchorElement>) => {
    const next = document.getElementById("observation");
    if (!next) return;
    event.preventDefault();
    next.scrollIntoView({ behavior: "instant", block: "start" });
    next.focus({ preventScroll: true });
  };

  return (
    <section
      className="hero-scroll-track"
      ref={track}
      aria-label="蝦隻影像分析介紹"
    >
      <div className="hero hero-living hero-pinned" ref={stage}>
        <div className="hero-image">
          <Image
            src="/images/hero-poster.webp"
            alt="深綠色水中的草蝦"
            fill
            preload
            sizes="100vw"
            quality={90}
          />
          <canvas
            ref={canvas}
            className="hero-scroll-canvas"
            aria-hidden="true"
          />
        </div>
        <div className="hero-shade" />
        <div className="hero-copy" ref={copy}>
          <span className="eyebrow">蝦隻追蹤・體型估計・水色分類</span>
          <h1>
            用影片，
            <br />
            <span>記錄蝦隻成長。</span>
          </h1>
          <p>
            追蹤蝦隻、估計長寬與重量，
            <br />
            依拍攝日期比較分析結果。
          </p>
          <div className="hero-actions">
            <Link href="/upload" className="button button-lime">
              上傳影片
              <ArrowUpRightIcon size={20} />
            </Link>
            <Link href="/dashboard?demo=1" className="text-link">
              <PlayIcon size={17} weight="fill" />
              查看示範
            </Link>
          </div>
        </div>
        <div className="scene-controls">
          <div className="scene-scroll-label">
            <ArrowDownIcon size={17} />
            <span>捲動探索</span>
            <output ref={counter} aria-hidden="true">
              水面
            </output>
          </div>
          <a href="#observation" onClick={skip}>
            略過動畫
            <ArrowDownIcon size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}
