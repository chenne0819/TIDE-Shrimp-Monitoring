const test = require("node:test");
const assert = require("node:assert/strict");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { loadSource } = require("./helpers.cjs");
const { AssistantMessageContent } = loadSource(
  "src/components/assistant-message-content.tsx",
);
const render = (content) =>
  renderToStaticMarkup(
    React.createElement(AssistantMessageContent, { content }),
  );

test("numeric bold emphasis and inline code render without changing their values", () => {
  const html = render(
    "最大寬度為 **16.4 mm**，欄位為 `width_mm`。\n平均為 **12.75 mm**。",
  );
  assert.match(html, /<strong>16\.4 mm<\/strong>/);
  assert.match(html, /<code>width_mm<\/code>/);
  assert.match(html, /<br\/>/);
  assert.match(html, /<strong>12\.75 mm<\/strong>/);
});

test("ordinary paragraphs and CRLF line breaks remain readable", () => {
  const html = render(
    "今天有 12 筆量測。\r\n缺值不當作零。\r\n\r\n明天再比較。",
  );
  assert.equal((html.match(/<p>/g) || []).length, 2);
  assert.equal((html.match(/<br\/>/g) || []).length, 1);
  assert.match(html, /今天有 12 筆量測。/);
  assert.doesNotMatch(html, /<strong>|<code>|<ul>|<ol>/);
});

test("bullets and numbered lists have semantic list elements and preserve explicit numbering", () => {
  const html = render(
    "結果如下：\n- 長度 **90 mm**\n- 寬度 **16.4 mm**\n\n2. 先核對影片\n4. 再檢查校正",
  );
  assert.equal((html.match(/<ul>/g) || []).length, 1);
  assert.equal((html.match(/<li(?: |\>)/g) || []).length, 4);
  assert.match(html, /<ol start="2">/);
  assert.match(html, /<li value="4">/);
  assert.match(html, /<strong>16\.4 mm<\/strong>/);
});

test("model-supplied HTML, scripts and attribute payloads remain escaped literal text", () => {
  const html = render(
    '<script>alert(1)</script>\n<img src=x onerror="alert(1)"> **<svg onload=alert(1)>** `<iframe src=x>`',
  );
  assert.doesNotMatch(html, /<script|<img|<svg|<iframe/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /<strong>&lt;svg onload=alert\(1\)&gt;<\/strong>/);
  assert.match(html, /<code>&lt;iframe src=x&gt;<\/code>/);
});

test("URLs, Markdown links, headings, italics and unmatched emphasis stay plain text", () => {
  const html = render(
    "# 標題\n[按這裡](javascript:alert(1)) https://example.com\n*斜體* **未結束 `未結束",
  );
  assert.doesNotMatch(html, /<a[ >]|href=|<h1|<em>|<strong>|<code>/);
  assert.match(html, /\[按這裡\]\(javascript:alert\(1\)\)/);
  assert.match(html, /\*斜體\*/);
});

test("unsupported fenced code stays literal and its contents are not interpreted as a list or bold", () => {
  const html = render(
    "```text\n- **原始內容**\n<script>alert(1)</script>\n```\n\n已完成。",
  );
  assert.doesNotMatch(html, /<ul>|<li>|<strong>|<script/);
  assert.match(html, /```text/);
  assert.match(html, /- \*\*原始內容\*\*/);
  assert.match(html, /已完成。/);
});

test("empty content and a maximum-size plain message remain bounded", () => {
  assert.equal(render("\n \n"), '<div class="ai-message-prose"></div>');
  const html = render("蝦".repeat(8000));
  assert.equal((html.match(/蝦/g) || []).length, 8000);
  assert.equal((html.match(/<p>/g) || []).length, 1);
});
