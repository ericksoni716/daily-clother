import type { ReactNode } from 'react';
import { parseMarkdown, type Inline } from '../../markdown';
import { cls } from './cls';

function inline(parts: Inline[]): ReactNode[] {
  return parts.map((p, i) => {
    if (p.kind === 'strong') return <strong key={i}>{inline(p.children)}</strong>;
    if (p.kind === 'em') return <em key={i}>{inline(p.children)}</em>;
    if (p.kind === 'code') return <code key={i}>{p.text}</code>;
    return p.text;
  });
}

const HEADINGS = { 3: 'h3', 4: 'h4', 5: 'h5', 6: 'h6' } as const;

/**
 * A small, safe part of Markdown (src/markdown.ts) as React elements: every word is put on the page as text,
 * never as HTML. `headingLevel` is the HTML level its largest heading takes (3 under a card's h2).
 */
export function Markdown({ text, headingLevel = 3, className }: { text: string; headingLevel?: 3 | 4; className?: string }) {
  return (
    <div className={cls('markdown', className)}>
      {parseMarkdown(text).map((b, i) => {
        if (b.kind === 'heading') {
          const Tag = HEADINGS[(headingLevel + b.level - 1) as 3 | 4 | 5 | 6];
          return <Tag key={i} className="markdown-heading">{inline(b.children)}</Tag>;
        }
        if (b.kind === 'list') {
          const items = b.items.map((item, j) => <li key={j}>{inline(item)}</li>);
          return b.ordered ? <ol key={i} start={b.start === 1 ? undefined : b.start}>{items}</ol> : <ul key={i}>{items}</ul>;
        }
        return <p key={i}>{inline(b.children)}</p>;
      })}
    </div>
  );
}
