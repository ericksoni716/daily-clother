/**
 * A small, safe part of Markdown, read into a tree the page draws as React elements (components/ui/Markdown.tsx).
 * Used for a release's "What's new". It reads paragraphs, headings, `-`/`*`/`1.` lists, **bold**, *emphasis*,
 * `code` and links, which are kept as their words only. Anything else, HTML included, stays the text it is:
 * nothing here is ever put on the page as HTML.
 */

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; children: Inline[] }
  | { kind: 'em'; children: Inline[] }
  | { kind: 'code'; text: string };

export type Block =
  /** `level` 1 is the largest heading in the text, whatever its number of #: 1 to 3. */
  | { kind: 'heading'; level: 1 | 2 | 3; children: Inline[] }
  | { kind: 'paragraph'; children: Inline[] }
  | { kind: 'list'; ordered: boolean; start: number; items: Inline[][] };

const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
const ITEM = /^\s*(?:([-*+•])|(\d{1,9})[.)])\s+(.*)$/;
const RULE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const FENCE = /^\s{0,3}(```|~~~)/;
const LINK = /^\[([^\]\n]+)\]\(([^)\s]*)(?:\s+"[^"]*")?\)/;

function text(out: Inline[], s: string) {
  if (!s) return;
  const last = out[out.length - 1];
  if (last?.kind === 'text') last.text += s;
  else out.push({ kind: 'text', text: s });
}

/** The inline marks of one block's text. An opening mark with no closing one is kept as written. */
export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\' && i + 1 < s.length && /[!-/:-@[-`{-~]/.test(s[i + 1])) {
      text(out, s[i + 1]);
      i += 2;
      continue;
    }
    if (c === '`') {
      const end = s.indexOf('`', i + 1);
      if (end > i + 1) {
        out.push({ kind: 'code', text: s.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (c === '*' && s[i + 1] === '*') {
      const end = s.indexOf('**', i + 2);
      if (end > i + 2) {
        out.push({ kind: 'strong', children: parseInline(s.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
      text(out, '**');
      i += 2;
      continue;
    }
    if (c === '*' && s[i + 1] && s[i + 1] !== ' ') {
      const end = s.indexOf('*', i + 1);
      if (end > i + 1 && s[end - 1] !== ' ') {
        out.push({ kind: 'em', children: parseInline(s.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    }
    if (c === '[') {
      const m = LINK.exec(s.slice(i));
      if (m) {
        // a link keeps its words only: nothing on this page leaves for another site
        for (const part of parseInline(m[1])) {
          if (part.kind === 'text') text(out, part.text);
          else out.push(part);
        }
        i += m[0].length;
        continue;
      }
    }
    text(out, c);
    i += 1;
  }
  return out;
}

type Open = { kind: 'heading'; depth: number; text: string } | { kind: 'paragraph'; lines: string[] }
  | { kind: 'list'; ordered: boolean; start: number; items: string[] };

/** Markdown text as blocks. */
export function parseMarkdown(source: string): Block[] {
  const open: Open[] = [];
  let current: Open | null = null;
  const close = () => {
    if (current) open.push(current);
    current = null;
  };
  for (const raw of source.replace(/\r\n?/g, '\n').split('\n')) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim() || RULE.test(line) || FENCE.test(line)) {
      close();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      close();
      open.push({ kind: 'heading', depth: heading[1].length, text: heading[2] });
      continue;
    }
    const item = ITEM.exec(line);
    if (item) {
      const ordered = item[2] !== undefined;
      if (current?.kind !== 'list' || current.ordered !== ordered) {
        close();
        current = { kind: 'list', ordered, start: ordered ? Number(item[2]) : 1, items: [] };
      }
      current.items.push(item[3]);
      continue;
    }
    const words = line.trim().replace(/^>\s?/, '');
    if (current?.kind === 'list') current.items[current.items.length - 1] += ` ${words}`;   // the item goes on
    else if (current?.kind === 'paragraph') current.lines.push(words);
    else current = { kind: 'paragraph', lines: [words] };
  }
  close();
  const top = Math.min(...open.map((b) => (b.kind === 'heading' ? b.depth : 7)));
  return open.map((b): Block => {
    if (b.kind === 'heading') return { kind: 'heading', level: Math.min(b.depth - top + 1, 3) as 1 | 2 | 3, children: parseInline(b.text) };
    if (b.kind === 'list') return { kind: 'list', ordered: b.ordered, start: b.start, items: b.items.map(parseInline) };
    return { kind: 'paragraph', children: parseInline(b.lines.join(' ')) };
  });
}
