"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRightIcon,
  ArrowUpIcon,
  ChartBarIcon,
  ChatCircleTextIcon,
  CheckIcon,
  ClockIcon,
  DownloadSimpleIcon,
  FileTextIcon,
  InfoIcon,
  ClockCounterClockwiseIcon,
  PencilSimpleLineIcon,
  PlusIcon,
  SparkleIcon,
  SidebarSimpleIcon,
  StopIcon,
} from "@phosphor-icons/react";
import { AppShell } from "./app-shell";
import {
  ActivityDetails,
  CompletionSummary,
  AnalysisProgress,
  assistantStageNames as statusNames,
} from "./assistant-activity";
import { AnalysisDataTable, AnalysisVisualization } from "./assistant-charts";
import { StatisticalCard } from "./assistant-statistics";
import { AssistantMessageContent } from "./assistant-message-content";
import { assistantApi } from "@/lib/assistant-api";
import {
  createAssistantSession,
  initialAssistantState,
  isPending,
  type AssistantSession,
} from "@/lib/assistant-session";
import type {
  AnalysisBoard,
  AnalysisChart,
  AssistantCapabilities,
  AssistantMessage,
  ChartKind,
  StatisticalMethod,
} from "@/lib/assistant-types";
import { downloadChartCsv } from "@/lib/assistant-utils";
import { useAssistantPanelResize } from "@/lib/assistant-panel";
import { formatDate, formatNumber } from "@/lib/api";

const chartNames: Record<ChartKind, string> = {
  line: "折線圖",
  area: "面積圖",
  bar: "分組長條圖",
  stacked_bar: "堆疊長條圖",
  histogram: "直方圖",
  scatter: "散佈圖",
  boxplot: "箱型圖",
  heatmap: "熱圖",
  donut: "環圈圖",
  table: "資料表",
};
const templateDescriptions: Record<ChartKind, string> = {
  line: "看每日的體型變化",
  area: "看一段時間的數量起伏",
  bar: "並排比較各池或不同期間",
  stacked_bar: "看各池的公母或水色組成",
  histogram: "看長度、寬度或重量分布",
  scatter: "看兩項體型數值的關係",
  boxplot: "比較各池體型是否集中",
  heatmap: "找出日期與池別的變化",
  donut: "看各種分類占多少",
  table: "逐欄查看精確數值",
};
const templateQuestions: Record<ChartKind, string> = {
  line: "用折線圖查看本月每天的平均估計長度，並與上月比較。",
  area: "用面積圖查看本月每天的追蹤個體數。",
  bar: "用分組長條圖比較各池本月和上月的平均估計長度。",
  stacked_bar: "用堆疊長條圖查看本月各池追蹤個體的公母與未知分類。",
  histogram: "用直方圖查看本月蝦隻的估計長度分布。",
  scatter: "用散佈圖查看本月每隻蝦的估計長度與寬度關係。",
  boxplot: "用箱型圖比較本月各池蝦隻的估計長度分布。",
  heatmap: "用熱圖查看本月各池每天的追蹤個體數。",
  donut: "用環圈圖查看本月影片的水色分類比例。",
  table: "用資料表比較本月與上月各池的平均估計長度、寬度與重量。",
};
const statisticsQuestions: Record<StatisticalMethod, string> = {
  descriptive: "整理本月各池寬度的最大值、最小值、中位數和標準差。",
  pearson: "用 Pearson 分析本月估計長度與重量的相關程度，並顯示散佈圖。",
  spearman: "用 Spearman 分析本月估計長度與重量的等級相關。",
  welch_t: "用 Welch t 檢定比較本月與上月的平均估計寬度，以影片平均值為單位。",
  anova:
    "用 Welch 單因子 ANOVA 比較本月各池的平均估計寬度，以影片平均值為單位。",
};

function ChartCard({ chart }: { chart: AnalysisChart }) {
  const [view, setView] = useState<"chart" | "data">("chart");
  return (
    <section
      className={`ai-chart-card ${chart.type === "heatmap" || chart.type === "table" ? "ai-chart-wide" : ""}`}
    >
      <header className="ai-chart-heading">
        <div>
          <span className="ai-chart-kind">{chartNames[chart.type]}</span>
          <h3>{chart.title}</h3>
        </div>
        <button
          className="ai-icon-button"
          onClick={() => downloadChartCsv(chart)}
          title="下載本圖資料 CSV"
          aria-label={`下載${chart.title}資料 CSV`}
        >
          <DownloadSimpleIcon size={20} />
        </button>
      </header>
      {chart.description && (
        <p className="ai-chart-description">{chart.description}</p>
      )}
      <div className="ai-card-toolbar">
        <div
          className="ai-switch"
          role="group"
          aria-label={`${chart.title}顯示方式`}
        >
          <button
            aria-pressed={view === "chart"}
            onClick={() => setView("chart")}
          >
            <ChartBarIcon size={15} />
            圖表
          </button>
          <button
            aria-pressed={view === "data"}
            onClick={() => setView("data")}
          >
            <FileTextIcon size={15} />
            資料
          </button>
        </div>
        <span>{formatNumber(chart.sample_count, 0)} 筆樣本</span>
      </div>
      {view === "chart" ? (
        <AnalysisVisualization chart={chart} />
      ) : (
        <AnalysisDataTable chart={chart} />
      )}
      {chart.note && (
        <p className="ai-chart-note">
          <InfoIcon size={16} />
          {chart.note}
        </p>
      )}
    </section>
  );
}

function Board({ board }: { board: AnalysisBoard }) {
  const sourcesId = `ai-sources-${board.id.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <div className="ai-board">
      <header className="ai-board-heading">
        <div>
          <p className="ai-eyebrow">這次分析</p>
          <h2>{board.title}</h2>
        </div>
        <a className="ai-subtle-link" href={`#${sourcesId}`}>
          <FileTextIcon size={16} />
          查看資料來源
        </a>
      </header>
      <div className="ai-query-chips">
        {board.query.periods.map((period) => (
          <span key={period.id}>
            <ClockIcon size={15} />
            <strong>{period.label}</strong>
            {period.start_date} — {period.end_date}
          </span>
        ))}
        <span>
          {board.query.ponds.length ? board.query.ponds.join("、") : "所有池別"}
        </span>
      </div>
      {board.demo && (
        <p className="ai-small ai-demo-label">
          示範資料 · AI 回答根據合成資料生成。
        </p>
      )}
      {!!board.kpis.length && (
        <div className="ai-kpis">
          {board.kpis.map((kpi, index) => (
            <section key={`${kpi.label}-${index}`} className="ai-kpi">
              <h3>{kpi.label}</h3>
              <p className="ai-kpi-value">
                {formatNumber(kpi.value, 2)}
                <span>{kpi.unit}</span>
              </p>
              {kpi.previous_value != null && (
                <p className="ai-kpi-comparison">
                  前期 {formatNumber(kpi.previous_value, 2)} {kpi.unit}
                  {kpi.delta_pct != null && (
                    <span>
                      {kpi.delta_pct > 0 ? "+" : ""}
                      {formatNumber(kpi.delta_pct, 1)}%
                    </span>
                  )}
                </p>
              )}
            </section>
          ))}
        </div>
      )}
      {!!board.warnings.length && (
        <div className="ai-notices" role="note">
          <InfoIcon size={19} />
          <div>
            {board.warnings.map((warning, index) => (
              <p key={index}>{warning}</p>
            ))}
          </div>
        </div>
      )}
      <div className="ai-chart-grid">
        {(board.statistics ?? []).map((result) => (
          <StatisticalCard key={`${board.id}-${result.id}`} result={result} />
        ))}
        {board.charts.map((chart) => (
          <ChartCard key={`${board.id}-${chart.id}`} chart={chart} />
        ))}
      </div>
      {!board.charts.length && !board.statistics?.length && (
        <p className="ai-chart-empty">
          這次回答沒有附加圖表，可從右側繼續提問。
        </p>
      )}
      <details className="ai-sources" id={sourcesId}>
        <summary>
          <FileTextIcon size={19} />
          <span>
            資料來源與計算範圍
            <small>
              {formatNumber(board.total_jobs, 0)} 部影片 ·{" "}
              {formatNumber(board.total_tracks, 0)} 筆追蹤個體
            </small>
          </span>
          <PlusIcon size={19} />
        </summary>
        <div className="ai-source-body">
          <dl>
            <div>
              <dt>資料彙整</dt>
              <dd>{board.query.aggregation}</dd>
            </div>
            <div>
              <dt>時間基準</dt>
              <dd>
                {board.timezone} · {formatDate(board.generated_at, true)} 產生
              </dd>
            </div>
            <div>
              <dt>池別</dt>
              <dd>
                {board.query.ponds.length
                  ? board.query.ponds.join("、")
                  : "所有池別"}
              </dd>
            </div>
          </dl>
          <div
            className="ai-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="各期間有效樣本"
          >
            <table className="ai-data-table">
              <thead>
                <tr>
                  <th>期間</th>
                  <th>天數</th>
                  <th>影片</th>
                  <th>個體</th>
                  <th>有效長度</th>
                  <th>有效寬度</th>
                  <th>有效重量</th>
                </tr>
              </thead>
              <tbody>
                {board.period_summaries.map((period) => (
                  <tr key={period.id}>
                    <th scope="row">{period.label}</th>
                    {[
                      period.days,
                      period.videos,
                      period.tracks,
                      period.valid_length,
                      period.valid_width,
                      period.valid_weight,
                    ].map((value, index) => (
                      <td className="ai-number" key={index}>
                        {formatNumber(value, 0)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ai-small">
            來源影片清單：{board.sources.length} 部
            {board.sources.length < board.total_jobs
              ? `（本次共 ${board.total_jobs} 部，清單僅列出部分來源）`
              : ""}
            。跨影片的個體 ID 不代表已去除重複蝦隻。
          </p>
          <ul className="ai-source-list">
            {board.sources.map((source) => (
              <li key={source.id}>
                {board.demo ? (
                  <div className="ai-demo-source">
                    <span>
                      {source.filename}
                      <small>
                        {source.pond} · {formatDate(source.recorded_at)} ·
                        合成示範來源
                      </small>
                    </span>
                  </div>
                ) : (
                  <Link href={`/recordings/${encodeURIComponent(source.id)}`}>
                    <span>
                      {source.filename}
                      <small>
                        {source.pond} · {formatDate(source.recorded_at)}
                      </small>
                    </span>
                    <ArrowUpRightIcon size={17} />
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}

function ChatExamples({
  capabilities,
  disabled,
  choose,
}: {
  capabilities: AssistantCapabilities | null;
  disabled: boolean;
  choose: (text: string) => void;
}) {
  const templates =
    capabilities?.templates ??
    Object.keys(chartNames).map((type) => ({ type: type as ChartKind }));
  return (
    <details className="ai-chat-examples">
      <summary title="選擇圖表範例" aria-label="選擇圖表範例">
        <PlusIcon size={22} />
      </summary>
      <div>
        <p>選擇範例，會帶入輸入框。</p>
        <button
          type="button"
          disabled={disabled}
          onClick={(event) => {
            choose(
              "整理本月的關鍵指標：完成影片、追蹤個體數、平均估計長度、寬度與重量，並與上月比較。",
            );
            event.currentTarget.closest("details")?.removeAttribute("open");
          }}
        >
          <strong>關鍵指標</strong>
          <span>快速查看這次的數值</span>
        </button>
        {templates.map((template) => (
          <button
            type="button"
            disabled={disabled}
            key={template.type}
            onClick={(event) => {
              choose(templateQuestions[template.type]);
              event.currentTarget.closest("details")?.removeAttribute("open");
            }}
          >
            <strong>{chartNames[template.type]}</strong>
            <span>{templateDescriptions[template.type]}</span>
          </button>
        ))}
        {(capabilities?.statistical_methods ?? []).map((method) => (
          <button
            type="button"
            disabled={disabled}
            key={method.method}
            onClick={(event) => {
              choose(statisticsQuestions[method.method]);
              event.currentTarget.closest("details")?.removeAttribute("open");
            }}
          >
            <strong>{method.label}</strong>
            <span>{method.description}</span>
          </button>
        ))}
      </div>
    </details>
  );
}

function Message({
  message,
  active,
  canSend,
  question,
  viewBoard,
  ask,
}: {
  message: AssistantMessage;
  active: boolean;
  canSend: boolean;
  question?: string;
  viewBoard: () => void;
  ask: (text: string) => void;
}) {
  const pending = isPending(message);
  return (
    <article
      className={`ai-message ai-message-${message.role}`}
      aria-label={message.role === "user" ? "你的訊息" : "TIDE 的回覆"}
    >
      <div className="ai-message-label">
        {message.role === "assistant" ? (
          <>
            <SparkleIcon size={16} />
            TIDE 分析
          </>
        ) : (
          "你"
        )}
        <time dateTime={message.created_at}>
          {formatDate(message.created_at, true).split(" ").slice(-1).join(" ")}
        </time>
      </div>
      {message.role === "assistant" && <ActivityDetails message={message} />}
      {message.content && (
        <div className="ai-message-content">
          {message.role === "assistant" ? (
            <AssistantMessageContent content={message.content} />
          ) : (
            message.content
          )}
        </div>
      )}
      {message.role === "assistant" && pending && !message.activity?.length && (
        <p className="ai-message-status">
          <span className="ai-pending-dot" />
          {statusNames[message.status]}
        </p>
      )}
      {message.status === "failed" && (
        <div className="ai-message-failure">
          <p>{message.error || "這次未能完成分析，請稍後重試。"}</p>
          {question && (
            <button
              className="ai-subtle-link"
              disabled={!canSend}
              onClick={() => ask(question)}
            >
              重新分析
            </button>
          )}
        </div>
      )}
      {message.status === "cancelled" && (
        <p className="ai-message-status">
          <StopIcon size={14} />
          這次分析已停止。
          {question && (
            <button
              className="ai-subtle-link"
              disabled={!canSend}
              onClick={() => ask(question)}
            >
              重新分析
            </button>
          )}
        </p>
      )}
      {message.role === "assistant" && <CompletionSummary message={message} />}
      {message.board && !pending && (
        <button
          onClick={viewBoard}
          className={`ai-result-link ${active ? "selected" : ""}`}
        >
          <ChartBarIcon size={18} />
          <span>
            {active ? "正在查看這次結果" : "查看這次結果"}
            <small>
              {message.board.charts.length} 張圖表 · {message.board.kpis.length}{" "}
              個指標
              {!!message.board.statistics?.length &&
                ` · ${message.board.statistics.length} 項統計`}
            </small>
          </span>
          {active ? <CheckIcon size={17} /> : <ArrowUpRightIcon size={17} />}
        </button>
      )}
      {message.status === "completed" && message.followups.length > 0 && (
        <div className="ai-followups">
          {message.followups.map((text, index) => (
            <button disabled={!canSend} key={index} onClick={() => ask(text)}>
              {text}
              <ArrowUpRightIcon size={14} />
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

export function AssistantWorkspace({ demo = false }: { demo?: boolean }) {
  const {
    layoutRef,
    panelWidth,
    containerWidth: panelContainerWidth,
    style: panelStyle,
    dragging,
    separatorProps,
  } = useAssistantPanelResize();
  const [state, setState] = useState(initialAssistantState);
  const [draft, setDraft] = useState("");
  const [mobileTab, setMobileTab] = useState<"boards" | "chat">("chat");
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const collapseButton = useRef<HTMLButtonElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  const moveToggleFocus = useRef(false);
  const toggleChat = (collapsed: boolean) => {
    moveToggleFocus.current = chatCollapsed !== collapsed;
    setChatCollapsed(collapsed);
    setMobileTab(collapsed ? "boards" : "chat");
  };
  useEffect(() => {
    if (!moveToggleFocus.current) return;
    moveToggleFocus.current = false;
    (chatCollapsed ? expandButton : collapseButton).current?.focus({
      preventScroll: true,
    });
  }, [chatCollapsed]);
  const [selection, setSelection] = useState<{
    conversationId: string;
    messageId: string;
    resultVersion: string | undefined;
  } | null>(null);
  const session = useRef<AssistantSession | null>(null);
  const chatScroll = useRef<HTMLDivElement>(null);
  const stickyChat = useRef(true);
  const composer = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const input = composer.current;
    // Mobile tabs hide this same mounted composer without changing the desktop
    // collapse flag. Measure only visible content, including after tab/resize.
    if (!input || input.clientWidth <= 0) return;
    input.style.height = "0px";
    input.style.height = `${Math.min(168, Math.max(28, input.scrollHeight))}px`;
  }, [draft, chatCollapsed, mobileTab, panelWidth, panelContainerWidth]);
  useEffect(() => {
    const controller = createAssistantSession({
      demo,
      transport: assistantApi,
      onChange: setState,
    });
    session.current = controller;
    void controller.start();
    return () => {
      controller.destroy();
      session.current = null;
    };
  }, [demo]);
  const messages = state.detail?.messages ?? [];
  const results = messages.filter(
    (message) => message.board && !isPending(message),
  );
  const chosen =
    (selection?.conversationId === state.detail?.id &&
    selection?.resultVersion === results.at(-1)?.id
      ? results.find((message) => message.id === selection?.messageId)
      : null) ?? results.at(-1);
  const latestAssistant = messages
    .filter((message) => message.role === "assistant")
    .at(-1);
  const pending = messages.find(isPending);
  // Classification happens on the server. Sending/planning/plain answers must
  // leave the existing board mounted, including its scroll and table selection.
  const processing = Boolean(pending && pending.response_kind === "analysis");
  const busy =
    state.loading || state.sending || Boolean(pending) || state.cancelling;
  const canSend =
    Boolean(state.capabilities?.enabled) && !busy && !state.retryable;
  const terminalIssue =
    !selection &&
    latestAssistant &&
    ["failed", "cancelled"].includes(latestAssistant.status)
      ? latestAssistant
      : null;
  useEffect(() => {
    const element = chatScroll.current;
    if (stickyChat.current && element && element.clientHeight > 0)
      element.scrollTop = element.scrollHeight;
  }, [state.detail, chatCollapsed, mobileTab, panelWidth, panelContainerWidth]);
  const ask = async (text: string) => {
    if (!canSend) return;
    stickyChat.current = true;
    const accepted = await session.current?.send(text);
    if (accepted)
      setDraft((current) => (current.trim() === text.trim() ? "" : current));
  };
  const chooseExample = (text: string) => {
    setDraft(text);
    setMobileTab("chat");
    composer.current?.focus();
  };
  const selectConversation = (id: string | null) => {
    setDraft("");
    setSelection(null);
    setMobileTab(id ? "boards" : "chat");
    stickyChat.current = true;
    void session.current?.select(id);
  };
  const viewBoard = (message: AssistantMessage) => {
    if (state.detail)
      setSelection({
        conversationId: state.detail.id,
        messageId: message.id,
        resultVersion: results.at(-1)?.id,
      });
    setMobileTab("boards");
  };
  const retryRequest = () => {
    void session.current?.retry();
  };
  return (
    <AppShell demo={demo} variant="assistant">
      <div className="ai-workspace">
        <div className="ai-mobile-tabs" role="group" aria-label="分析頁面區域">
          <button
            aria-pressed={mobileTab === "boards"}
            onClick={() => setMobileTab("boards")}
          >
            <ChartBarIcon size={18} />
            圖表
            {processing ? (
              <span className="ai-pending-dot" />
            ) : results.length ? (
              <span>{results.length}</span>
            ) : null}
          </button>
          <button
            aria-pressed={mobileTab === "chat"}
            onClick={() => toggleChat(false)}
          >
            <ChatCircleTextIcon size={18} />
            對話
          </button>
        </div>
        <div
          className={`ai-layout ai-tab-${mobileTab}`}
          ref={layoutRef}
          style={panelStyle}
          data-resizing={dragging || undefined}
          data-chat-collapsed={chatCollapsed || undefined}
        >
          <section className="ai-canvas" aria-label="分析圖表">
            <header className="ai-page-heading">
              <div>
                <h1>AI 分析</h1>
                <p>詢問量測結果，或比較不同日期與池別。</p>
              </div>
              <div className="ai-page-tools">
                <div className="ai-date-context">
                  <ClockIcon size={17} />
                  <span>
                    {state.capabilities?.today ?? "讀取日期中"}
                    <small>
                      {state.capabilities?.timezone ?? "Asia/Taipei"}
                    </small>
                  </span>
                </div>
                {chatCollapsed && (
                  <button
                    type="button"
                    className="ai-panel-toggle"
                    ref={expandButton}
                    onClick={() => toggleChat(false)}
                    aria-label="展開對話"
                    title="展開對話"
                    aria-controls="ai-chat-panel"
                    aria-expanded={false}
                  >
                    <SidebarSimpleIcon size={22} mirrored aria-hidden="true" />
                    <span>展開對話</span>
                  </button>
                )}
              </div>
            </header>
            {demo && (
              <div className="ai-demo-banner">
                <InfoIcon size={17} />
                <span>示範資料 · 問答仍使用已設定模型。</span>
                <Link href="/assistant">切換真實資料</Link>
              </div>
            )}
            <div
              className={`ai-canvas-content ${processing ? "ai-canvas-processing" : ""}`}
            >
              {processing ? (
                <>
                  <AnalysisProgress
                    message={pending}
                    sendingStartedAt={state.sendingStartedAt}
                    cancelling={state.cancelling}
                  />
                  {state.error && (
                    <p className="ai-progress-warning">{state.error}</p>
                  )}
                </>
              ) : state.loading ? (
                <div className="ai-empty-canvas" data-state="loading">
                  <p>{state.detail ? "正在讀取對話…" : "正在連線…"}</p>
                </div>
              ) : (
                <>
                  {state.retryable && (
                    <div className="ai-error">
                      <span>
                        尚未確認送出結果；重試會沿用同一請求，避免重複分析。
                      </span>
                      <button onClick={retryRequest}>重試同一請求</button>
                    </div>
                  )}
                  {terminalIssue && (
                    <div className="ai-result-notice" role="status">
                      <InfoIcon size={19} />
                      <div>
                        <strong>
                          {terminalIssue.status === "cancelled"
                            ? "這次分析已停止"
                            : "這次分析未完成"}
                        </strong>
                        <p>
                          {terminalIssue.error ||
                            (terminalIssue.status === "cancelled"
                              ? "可以修改問題後再送出。"
                              : "請從對話查看原因，或重新分析。")}
                        </p>
                        {chosen?.board && (
                          <p>
                            {chosen.id === terminalIssue.id
                              ? "以下保留這次已產生的圖表。"
                              : "下方顯示上一份已完成的結果。"}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  {!!results.length && (
                    <div className="ai-results-toolbar">
                      <label>
                        分析結果
                        <select
                          value={chosen?.id ?? ""}
                          onChange={(event) => {
                            const result = results.find(
                              (message) => message.id === event.target.value,
                            );
                            if (result) viewBoard(result);
                          }}
                        >
                          {results.map((result, index) => (
                            <option key={result.id} value={result.id}>
                              {index + 1}. {result.board?.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      <span>{results.length} 次結果可回看</span>
                    </div>
                  )}
                  {chosen?.board ? (
                    <Board key={chosen.board.id} board={chosen.board} />
                  ) : !terminalIssue && !state.retryable ? (
                    <div className="ai-empty-canvas" data-state="empty">
                      <svg
                        className="ai-empty-icon"
                        viewBox="0 0 56 56"
                        fill="none"
                        aria-hidden="true"
                      >
                        <rect
                          x="8"
                          y="8"
                          width="40"
                          height="40"
                          rx="11"
                          stroke="currentColor"
                          strokeWidth="1.5"
                        />
                        <path
                          d="M18 36V29M28 36V20M38 36V25"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                        <path
                          d="M18 41H38"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          opacity=".4"
                        />
                      </svg>
                      <p>提問後，這裡會顯示分析結果。</p>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </section>
          <div className="ai-panel-resizer" {...separatorProps}>
            <span aria-hidden="true" />
          </div>
          <aside
            className="ai-chat"
            id="ai-chat-panel"
            aria-label="AI 分析對話"
          >
            <header className="ai-chat-header">
              <div>
                <button
                  type="button"
                  className="ai-icon-button"
                  ref={collapseButton}
                  onClick={() => toggleChat(true)}
                  aria-label="收合對話"
                  title="收合對話"
                  aria-controls="ai-chat-panel"
                  aria-expanded={true}
                >
                  <SidebarSimpleIcon size={22} mirrored aria-hidden="true" />
                </button>
                <h2>
                  TIDE <span>資料助理</span>
                </h2>
              </div>
              <div className="ai-chat-tools">
                <details className="ai-history">
                  <summary aria-label="對話記錄" title="對話記錄">
                    <ClockCounterClockwiseIcon size={22} />
                  </summary>
                  <div className="ai-history-menu">
                    <p>最近對話</p>
                    {!state.conversations.length && (
                      <span>還沒有對話記錄。</span>
                    )}
                    {state.conversations.map((conversation) => (
                      <button
                        key={conversation.id}
                        aria-current={
                          state.detail?.id === conversation.id
                            ? "true"
                            : undefined
                        }
                        disabled={
                          !state.capabilities ||
                          state.loading ||
                          state.sending ||
                          state.cancelling
                        }
                        onClick={(event) => {
                          selectConversation(conversation.id);
                          event.currentTarget
                            .closest("details")
                            ?.removeAttribute("open");
                        }}
                      >
                        {conversation.title}
                      </button>
                    ))}
                  </div>
                </details>
                <button
                  className="ai-icon-button"
                  onClick={() => selectConversation(null)}
                  disabled={
                    !state.capabilities ||
                    state.loading ||
                    state.sending ||
                    state.cancelling
                  }
                  title="開啟新對話"
                  aria-label="開啟新對話"
                >
                  <PencilSimpleLineIcon size={22} />
                </button>
              </div>
            </header>
            <div
              className="ai-chat-messages"
              ref={chatScroll}
              onScroll={() => {
                const element = chatScroll.current;
                if (element && element.clientHeight > 0)
                  stickyChat.current =
                    element.scrollHeight -
                      element.scrollTop -
                      element.clientHeight <
                    90;
              }}
            >
              {state.capabilities && !state.capabilities.enabled && (
                <div className="ai-service-note" role="status">
                  <InfoIcon size={20} />
                  <div>
                    <strong>AI 分析尚未啟用</strong>
                    <p>
                      {state.capabilities.reason ||
                        "請先完成後端 AI 服務設定。已有對話和圖表仍可查看。"}
                    </p>
                  </div>
                </div>
              )}
              {state.error && (
                <div className="ai-error" role="alert">
                  <span>{state.error}</span>
                  {state.retryable ? (
                    <button onClick={retryRequest} disabled={state.sending}>
                      重試同一請求
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        void (state.detail
                          ? session.current?.refresh()
                          : session.current?.start());
                      }}
                      disabled={state.loading}
                    >
                      重新整理
                    </button>
                  )}
                </div>
              )}
              {!messages.length && (
                <div className="ai-chat-intro">
                  <div className="ai-chat-intro-mark">
                    <SparkleIcon size={30} />
                  </div>
                  <h3>想了解哪些量測結果？</h3>
                  <p>可以查數值、比較池別，或一起看圖表。</p>
                  <button
                    disabled={!canSend}
                    onClick={() =>
                      chooseExample(
                        "比較本月和上月的平均估計長度、寬度與重量。",
                      )
                    }
                  >
                    比較本月與上月
                    <ArrowUpRightIcon size={15} />
                  </button>
                  <button
                    disabled={!canSend}
                    onClick={() => chooseExample("今天的量測結果怎麼樣？")}
                  >
                    今天的量測結果
                    <ArrowUpRightIcon size={15} />
                  </button>
                </div>
              )}
              {messages.map((message, index) => (
                <Message
                  key={message.id}
                  message={message}
                  active={!processing && chosen?.id === message.id}
                  canSend={canSend}
                  question={
                    messages
                      .slice(0, index)
                      .reverse()
                      .find((item) => item.role === "user")?.content
                  }
                  viewBoard={() => viewBoard(message)}
                  ask={(text) => {
                    void ask(text);
                  }}
                />
              ))}
              {state.sending && (
                <p className="ai-chat-sending" role="status">
                  正在送出問題…
                </p>
              )}
            </div>
            <form
              className="ai-composer"
              onSubmit={(event) => {
                event.preventDefault();
                void ask(draft);
              }}
            >
              <label className="sr-only" htmlFor="ai-question">
                輸入分析問題
              </label>
              <textarea
                ref={composer}
                id="ai-question"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={2000}
                rows={1}
                disabled={!state.capabilities?.enabled || state.loading}
                placeholder="詢問量測結果…"
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing &&
                    event.keyCode !== 229
                  ) {
                    event.preventDefault();
                    if (canSend) void ask(draft);
                  }
                }}
              />
              <div className="ai-composer-actions">
                <ChatExamples
                  capabilities={state.capabilities}
                  disabled={!state.capabilities?.enabled || state.loading}
                  choose={chooseExample}
                />
                <span className="ai-composer-count">
                  {draft.length > 1600
                    ? `${draft.length}/2000`
                    : "Shift + Enter 換行"}
                </span>
                {pending ? (
                  <button
                    type="button"
                    className="ai-stop-button"
                    onClick={() => {
                      void session.current?.cancel();
                    }}
                    disabled={state.cancelling || state.sending}
                  >
                    <StopIcon size={17} weight="fill" />
                    {state.cancelling ? "正在停止" : "停止"}
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="ai-send-button"
                    disabled={!canSend || !draft.trim()}
                    aria-label="送出分析問題"
                  >
                    <ArrowUpIcon size={23} weight="bold" />
                  </button>
                )}
              </div>
            </form>
            <div className="ai-chat-context">
              {state.capabilities?.earliest_date &&
              state.capabilities?.latest_date ? (
                <span>
                  資料 {state.capabilities.earliest_date} —{" "}
                  {state.capabilities.latest_date}
                </span>
              ) : (
                <span>以已完成的影片量測為準</span>
              )}
              {demo && <span> · 示範模式</span>}
            </div>
            <span className="sr-only" role="status" aria-live="polite">
              {state.cancelling
                ? "正在停止分析"
                : pending
                  ? statusNames[pending.status]
                  : latestAssistant
                    ? statusNames[latestAssistant.status]
                    : ""}
            </span>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
