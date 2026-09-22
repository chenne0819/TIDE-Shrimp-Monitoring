import type { ReactNode } from "react";

/** A deliberately small renderer: React escapes every model-provided string. */
function inlineContent(text: string): ReactNode[] {
  const tokens =
    /(?<!\*)\*\*(?!\*)[^*\n]+\*\*(?!\*)|(?<!`)`(?!`)[^`\n]+`(?!`)/g;
  const nodes: ReactNode[] = [];
  let position = 0;
  for (const match of text.matchAll(tokens)) {
    const start = match.index;
    if (start > position) nodes.push(text.slice(position, start));
    const token = match[0];
    nodes.push(
      token.startsWith("**") ? (
        <strong key={start}>{token.slice(2, -2)}</strong>
      ) : (
        <code key={start}>{token.slice(1, -1)}</code>
      ),
    );
    position = start + token.length;
  }
  if (position < text.length) nodes.push(text.slice(position));
  return nodes;
}

type ListLine = { ordered: boolean; value?: number; text: string };
function listLine(line: string): ListLine | null {
  const bullet = /^ {0,3}[-+*]\s+(.+)$/.exec(line);
  if (bullet) return { ordered: false, text: bullet[1] };
  const numbered = /^ {0,3}(\d{1,4})[.)]\s+(.+)$/.exec(line);
  if (numbered)
    return { ordered: true, value: Number(numbered[1]), text: numbered[2] };
  return null;
}

export function AssistantMessageContent({ content }: { content: string }) {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index++;
      continue;
    }
    const start = index;
    // Fenced blocks are unsupported, so keep their markers and contents literal.
    const fence = /^ {0,3}(`{3,}|~{3,})/.exec(lines[index]);
    if (fence) {
      const literal = [lines[index++]];
      while (index < lines.length) {
        const line = lines[index++];
        literal.push(line);
        if (line.trim() === fence[1]) break;
      }
      blocks.push(
        <p key={start}>
          {literal.map((line, offset) => (
            <span key={offset}>
              {offset > 0 && <br />}
              {line}
            </span>
          ))}
        </p>,
      );
      continue;
    }
    const firstItem = listLine(lines[index]);
    if (firstItem) {
      const items: ReactNode[] = [];
      while (index < lines.length) {
        const item = listLine(lines[index]);
        if (!item || item.ordered !== firstItem.ordered) break;
        items.push(
          <li key={index++} value={item.ordered ? item.value : undefined}>
            {inlineContent(item.text)}
          </li>,
        );
      }
      blocks.push(
        firstItem.ordered ? (
          <ol key={start} start={firstItem.value}>
            {items}
          </ol>
        ) : (
          <ul key={start}>{items}</ul>
        ),
      );
      continue;
    }
    const paragraph: ReactNode[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !listLine(lines[index])
    ) {
      if (index > start && /^ {0,3}(`{3,}|~{3,})/.test(lines[index])) break;
      if (index > start) paragraph.push(<br key={`break-${index}`} />);
      paragraph.push(<span key={index}>{inlineContent(lines[index++])}</span>);
    }
    blocks.push(<p key={start}>{paragraph}</p>);
  }
  return <div className="ai-message-prose">{blocks}</div>;
}
