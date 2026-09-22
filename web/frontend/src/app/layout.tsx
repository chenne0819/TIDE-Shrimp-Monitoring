import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./landing-refinement.css";
import "./dashboard-readability.css";

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});
const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});
export const metadata: Metadata = {
  title: {
    default: "蝦況 TIDE | 蝦隻影像分析",
    template: "%s | 蝦況 TIDE",
  },
  description:
    "上傳蝦隻影片，查看追蹤結果、估計長度、寬度與重量，並依日期與池別比較分析資料。",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant" data-scroll-behavior="smooth">
      <body className={`${geist.variable} ${mono.variable}`}>
        <a href="#main-content" className="skip-link">
          跳至主要內容
        </a>
        {children}
      </body>
    </html>
  );
}
