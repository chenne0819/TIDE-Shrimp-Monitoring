const test = require("node:test");
const assert = require("node:assert/strict");
const { loadSource, createHooks, elements } = require("./helpers.cjs");
const sessionExports = loadSource("src/lib/assistant-session.ts");
function ProgressIndicator() {}
const statuses = {
  planning: "正在整理問題",
  querying: "正在查詢資料",
  answering: "正在整理分析結果",
  completed: "完成",
  failed: "分析未完成",
  cancelled: "已停止",
};
const capabilities = {
  enabled: true,
  today: "2026-09-20",
  timezone: "Asia/Taipei",
  available_ponds: [],
  templates: [],
  earliest_date: null,
  latest_date: null,
};
const board = (id) => ({ id, title: id, charts: [], kpis: [] });
const answer = (id, status, result = null) => ({
  id,
  role: "assistant",
  content: "",
  status,
  created_at: "2026-09-20T00:00:00Z",
  board: result,
  followups: [],
  error: null,
  activity: [],
});
const detail = (messages) => ({
  id: "conversation",
  title: "已存對話",
  messages,
});

function setup() {
  const hooks = createHooks();
  let change;
  let panelWidth = 440;
  const { AssistantWorkspace } = loadSource(
    "src/components/assistant-workspace.tsx",
    {
      react: hooks.react,
      "next/link": "a",
      "./app-shell": { AppShell: function AppShell() {} },
      "./assistant-charts": {
        AnalysisDataTable: function Data() {},
        AnalysisVisualization: function Plot() {},
      },
      "./assistant-statistics": { StatisticalCard: function Statistic() {} },
      "./assistant-message-content": {
        AssistantMessageContent: function MessageText() {},
      },
      "@/lib/assistant-panel": {
        useAssistantPanelResize: () => ({
          layoutRef: { current: null },
          panelWidth,
          style: {},
          dragging: false,
          separatorProps: {},
        }),
      },
      "./assistant-activity": {
        AnalysisProgress: ProgressIndicator,
        ActivityDetails: function Activity() {},
        CompletionSummary: function Completion() {},
        assistantStageNames: statuses,
      },
      "@/lib/assistant-api": { assistantApi: {} },
      "@/lib/assistant-session": {
        ...sessionExports,
        createAssistantSession: (options) => {
          change = options.onChange;
          return {
            start() {},
            destroy() {},
            select() {},
            send: async () => true,
          };
        },
      },
      "@/lib/assistant-utils": { downloadChartCsv() {} },
      "@/lib/api": {
        formatDate: (value) => value,
        formatNumber: (value) => String(value),
      },
    },
  );
  hooks.render(AssistantWorkspace, {});
  return {
    resizePanel(width) {
      panelWidth = width;
    },
    render(patch = {}) {
      change({
        ...sessionExports.initialAssistantState,
        loading: false,
        capabilities,
        conversations: [],
        ...patch,
      });
      return hooks.render(AssistantWorkspace, {});
    },
    cleanup: () => hooks.cleanup(),
  };
}

test("mobile board view does not overwrite hidden chat scroll and reopening restores bottom and draft height", () => {
  const h = setup();
  let currentDetail = detail([answer("pending", "planning")]);
  const textbox = (tree) =>
    elements(tree, (node) => node.type === "textarea")[0];
  const chat = (tree) =>
    elements(tree, (node) => node.props?.className === "ai-chat-messages")[0];
  const tab = (tree, name) =>
    elements(
      elements(tree, (node) => node.props?.className === "ai-mobile-tabs")[0],
      (node) => node.type === "button" && node.props.children.includes(name),
    )[0];
  let tree = h.render({ detail: currentDetail });
  const input = {
    clientWidth: 350,
    scrollHeight: 96,
    style: { height: "96px" },
  };
  const scroll = { clientHeight: 400, scrollHeight: 1000, scrollTop: 600 };
  textbox(tree).props.ref.current = input;
  chat(tree).props.ref.current = scroll;
  textbox(tree).props.onChange({ target: { value: "保留多行草稿" } });
  tree = h.render({ detail: currentDetail });
  tab(tree, "圖表").props.onClick();
  input.clientWidth = 0;
  input.scrollHeight = 0;
  scroll.clientHeight = 0;
  scroll.scrollHeight = 0;
  scroll.scrollTop = 600;
  currentDetail = detail([answer("pending", "querying")]);
  tree = h.render({ detail: currentDetail });
  assert.equal(
    scroll.scrollTop,
    600,
    "polling must not write to a display:none chat",
  );
  assert.equal(
    input.style.height,
    "96px",
    "hidden input must not be measured as one line",
  );
  tab(tree, "對話").props.onClick();
  input.clientWidth = 300;
  input.scrollHeight = 124;
  scroll.clientHeight = 400;
  scroll.scrollHeight = 1400;
  tree = h.render({ detail: currentDetail });
  assert.equal(
    scroll.scrollTop,
    1400,
    "a visible sticky chat catches up without waiting for another poll",
  );
  assert.equal(input.style.height, "124px");
  assert.equal(textbox(tree).props.value, "保留多行草稿");
  h.cleanup();
});

test("resizing chat remeasures a multiline draft without pulling an older-message reader to the bottom", () => {
  const h = setup();
  const currentDetail = detail([answer("done", "completed")]);
  let tree = h.render({ detail: currentDetail });
  const textarea = elements(tree, (node) => node.type === "textarea")[0];
  const messages = elements(
    tree,
    (node) => node.props?.className === "ai-chat-messages",
  )[0];
  const input = {
    clientWidth: 400,
    scrollHeight: 80,
    style: { height: "80px" },
  };
  const scroll = { clientHeight: 400, scrollHeight: 2000, scrollTop: 250 };
  textarea.props.ref.current = input;
  messages.props.ref.current = scroll;
  messages.props.onScroll();
  input.clientWidth = 280;
  input.scrollHeight = 140;
  h.resizePanel(320);
  tree = h.render({ detail: currentDetail });
  assert.equal(input.style.height, "140px");
  assert.equal(scroll.scrollTop, 250);
  h.cleanup();
});

test("unselected history leaves the central canvas empty and chart examples stay in chat", () => {
  const h = setup();
  const tree = h.render({ conversations: [{ id: "old", title: "舊對話" }] });
  const canvas = elements(
    tree,
    (node) => node.props?.className === "ai-canvas",
  )[0];
  assert.equal(
    elements(canvas, (node) => node.props?.["data-state"] === "empty").length,
    1,
  );
  assert.equal(
    elements(
      canvas,
      (node) =>
        node.type?.name === "Board" || node.type?.name === "ChatExamples",
    ).length,
    0,
  );
  const chat = elements(tree, (node) => node.props?.className === "ai-chat")[0];
  assert.equal(
    elements(chat, (node) => node.type?.name === "ChatExamples").length,
    1,
  );
  h.cleanup();
});

test("execution history comes before the answer while completion stays after it", () => {
  const h = setup();
  const message = {
    ...answer("finished", "completed"),
    content: "量測結果已完成",
  };
  const tree = h.render({ detail: detail([message]) });
  const messageNode = elements(
    tree,
    (node) => node.type?.name === "Message",
  )[0];
  const rendered = messageNode.type(messageNode.props);
  const sections = elements(rendered, (node) =>
    ["Activity", "MessageText", "Completion"].includes(node.type?.name),
  );
  assert.deepEqual(
    sections.map((node) => node.type.name),
    ["Activity", "MessageText", "Completion"],
  );
  h.cleanup();
});

test("collapsing and reopening chat preserves draft, selected board and mounted messages", () => {
  const h = setup();
  const saved = answer("result", "completed", board("existing"));
  const state = { detail: detail([saved]) };
  const button = (tree, label) =>
    elements(
      tree,
      (node) => node.type === "button" && node.props["aria-label"] === label,
    )[0];
  const layout = (tree) =>
    elements(tree, (node) => node.props?.className?.startsWith("ai-layout"))[0];
  const textbox = (tree) =>
    elements(tree, (node) => node.type === "textarea")[0];
  let tree = h.render(state);
  textbox(tree).props.onChange({ target: { value: "保留尚未送出的問題" } });
  tree = h.render(state);
  button(tree, "收合對話").props.onClick();
  tree = h.render(state);
  assert.equal(layout(tree).props["data-chat-collapsed"], true);
  assert.equal(button(tree, "展開對話").props["aria-expanded"], false);
  assert.equal(textbox(tree).props.value, "保留尚未送出的問題");
  assert.equal(
    elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
    "existing",
  );
  assert.equal(
    elements(tree, (node) => node.type?.name === "Message").length,
    1,
  );
  button(tree, "展開對話").props.onClick();
  tree = h.render(state);
  assert.equal(layout(tree).props["data-chat-collapsed"], undefined);
  assert.equal(textbox(tree).props.value, "保留尚未送出的問題");
  assert.equal(
    elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
    "existing",
  );
  h.cleanup();
});

for (const statisticsOnly of [false, true]) {
  test(`a fresh ${statisticsOnly ? "statistics-only result" : "overview"} moves from empty through confirmed analysis to its first board, then retains it for text follow-ups`, () => {
    const h = setup();
    const renderedBoards = (tree) =>
      elements(tree, (node) => node.type?.name === "Board");
    const progress = (tree) =>
      elements(tree, (node) => node.type === ProgressIndicator);
    const assertEmpty = (tree) => {
      assert.equal(renderedBoards(tree).length, 0);
      assert.equal(progress(tree).length, 0);
      assert.equal(
        elements(tree, (node) => node.props?.["data-state"] === "empty").length,
        1,
      );
    };
    try {
      assertEmpty(h.render());
      assertEmpty(h.render({ sending: true, sendingStartedAt: 1000 }));
      const planning = {
        ...answer("first", "planning"),
        response_kind: "pending",
      };
      assertEmpty(h.render({ detail: detail([planning]) }));

      const querying = {
        ...planning,
        status: "querying",
        response_kind: "analysis",
      };
      let tree = h.render({ detail: detail([querying]) });
      assert.equal(renderedBoards(tree).length, 0);
      assert.equal(progress(tree).length, 1);
      assert.equal(progress(tree)[0].props.message.id, "first");

      const result = {
        ...board("first-board"),
        query: { periods: [], ponds: [], aggregation: "有效個體平均" },
        warnings: [],
        period_summaries: [],
        sources: [],
        total_jobs: 2,
        total_tracks: 8,
        charts: statisticsOnly
          ? []
          : [{ id: "width-chart", type: "histogram", title: "寬度分布" }],
        statistics: statisticsOnly
          ? [{ id: "width-stat", method: "descriptive", title: "寬度摘要" }]
          : [],
      };
      const completed = {
        ...querying,
        status: "completed",
        board: result,
      };
      tree = h.render({ detail: detail([completed]) });
      assert.equal(progress(tree).length, 0);
      assert.equal(renderedBoards(tree).length, 1);
      const firstBoard = renderedBoards(tree)[0];
      assert.equal(firstBoard.props.board, result);
      if (statisticsOnly) {
        // An actual zero-chart board must render the statistical card, not the
        // generic no-results state or a chart-count based empty placeholder.
        const boardTree = firstBoard.type(firstBoard.props);
        assert.equal(
          elements(boardTree, (node) => node.type?.name === "Statistic").length,
          1,
        );
        assert.equal(
          elements(
            boardTree,
            (node) => node.props?.className === "ai-chart-empty",
          ).length,
          0,
        );
      }

      for (const status of ["planning", "querying", "answering", "completed"]) {
        tree = h.render({
          detail: detail([
            completed,
            {
              ...answer("followup", status),
              response_kind: status === "planning" ? "pending" : "answer",
            },
          ]),
        });
        assert.equal(progress(tree).length, 0);
        assert.equal(renderedBoards(tree).length, 1);
        assert.equal(renderedBoards(tree)[0].props.board, result);
      }
    } finally {
      h.cleanup();
    }
  });
}

test("conversation controls stay disabled during loading and after failed initialization", () => {
  const h = setup();
  for (const loading of [true, false]) {
    const tree = h.render({
      loading,
      capabilities: null,
      conversations: [{ id: "old", title: "舊對話" }],
      error: loading ? null : "bootstrap offline",
    });
    const newConversation = elements(
      tree,
      (node) => node.props?.["aria-label"] === "開啟新對話",
    )[0];
    const history = elements(
      tree,
      (node) => node.props?.className === "ai-history-menu",
    )[0];
    assert.equal(newConversation.props.disabled, true);
    assert.equal(
      elements(history, (node) => node.type === "button")[0].props.disabled,
      true,
    );
  }
  h.cleanup();
});

test("sending, routing and plain answers keep charts; only confirmed visual analysis shows progress", () => {
  const h = setup();
  const previous = answer("previous", "completed", board("old-board"));
  let tree = h.render({ detail: detail([previous]) });
  assert.equal(
    elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
    "old-board",
  );
  tree = h.render({
    detail: detail([previous]),
    sending: true,
    sendingStartedAt: 1000,
  });
  assert.equal(
    elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
    "old-board",
  );
  assert.equal(
    elements(tree, (node) => node.type === ProgressIndicator).length,
    0,
  );
  for (const response_kind of [undefined, "pending", "answer"]) {
    tree = h.render({
      detail: detail([
        previous,
        { ...answer("plain", "querying"), response_kind },
      ]),
    });
    assert.equal(
      elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
      "old-board",
    );
    assert.equal(
      elements(tree, (node) => node.type === ProgressIndicator).length,
      0,
    );
  }
  const pending = {
    ...answer("next", "answering", board("new-board")),
    response_kind: "analysis",
  };
  tree = h.render({ detail: detail([previous, pending]) });
  assert.equal(elements(tree, (node) => node.type?.name === "Board").length, 0);
  assert.equal(
    elements(tree, (node) => node.type === ProgressIndicator)[0].props.message
      .id,
    "next",
  );
  tree = h.render({
    detail: detail([previous, { ...pending, status: "completed" }]),
  });
  assert.equal(
    elements(tree, (node) => node.type === ProgressIndicator).length,
    0,
  );
  assert.equal(
    elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
    "new-board",
  );
  h.cleanup();
});

test("failure or cancellation stops progress and identifies any restored prior result", () => {
  const h = setup();
  const previous = answer("previous", "completed", board("old-board"));
  for (const status of ["failed", "cancelled"]) {
    const tree = h.render({
      detail: detail([previous, answer("next", status)]),
    });
    assert.equal(
      elements(tree, (node) => node.type === ProgressIndicator).length,
      0,
    );
    assert.equal(
      elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
      "old-board",
    );
    const notice = elements(
      tree,
      (node) => node.props?.className === "ai-result-notice",
    )[0];
    assert.ok(notice);
    assert.ok(
      elements(notice, (node) => node.type === "p").some(
        (node) => node.props.children === "下方顯示上一份已完成的結果。",
      ),
    );
  }
  h.cleanup();
});

test("plain follow-ups retain a manually selected old board; new visual results become selected", () => {
  const h = setup();
  const first = answer("first", "completed", board("first-board"));
  const second = answer("second", "completed", board("second-board"));
  let tree = h.render({ detail: detail([first, second]) });
  elements(
    tree,
    (node) =>
      node.type?.name === "Message" && node.props.message.id === "first",
  )[0].props.viewBoard();
  for (const status of ["planning", "querying", "answering", "completed"]) {
    tree = h.render({
      detail: detail([
        first,
        second,
        { ...answer("text", status), response_kind: "answer" },
      ]),
    });
    assert.equal(
      elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
      "first-board",
    );
    assert.equal(
      elements(tree, (node) => node.type === ProgressIndicator).length,
      0,
    );
  }
  tree = h.render({
    detail: detail([
      first,
      second,
      {
        ...answer("new", "completed", board("new-board")),
        response_kind: "analysis",
      },
    ]),
  });
  assert.equal(
    elements(tree, (node) => node.type?.name === "Board")[0].props.board.id,
    "new-board",
  );
  h.cleanup();
});
