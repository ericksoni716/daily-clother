/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/** The design system (DECISIONS.md, "The design system"): every size, colour and radius comes from the tokens. */

const SRC = join(import.meta.dirname);

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return name.endsWith('.css') ? [path] : [];
  });
}

const files = cssFiles(SRC).map((path) => ({ name: relative(SRC, path), text: readFileSync(path, 'utf8') }));
const styles = files.find((f) => f.name === 'styles.css')!.text;
const tokensEnd = styles.indexOf('*, *::before');
const tokens = styles.slice(0, tokensEnd);
/** Everything but the token blocks at the top of styles.css. */
const rules = files.map((f) => ({ name: f.name, text: f.name === 'styles.css' ? styles.slice(tokensEnd) : f.text }));

function values(prop: string): { name: string; value: string }[] {
  const re = new RegExp(`(?<![\\w-])${prop}:\\s*([^;}]+)`, 'g');
  return rules.flatMap((f) => [...f.text.matchAll(re)].map((m) => ({ name: f.name, value: m[1].trim() })));
}

function block(selector: string): string {
  const start = tokens.indexOf(selector);
  return tokens.slice(tokens.indexOf('{', start) + 1, tokens.indexOf('}', start));
}

describe('design tokens', () => {
  it('has the type scale, 1.25 from 16px', () => {
    // 39px is the page titles' on a wider screen (16 November)
    const sizes = ['xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl'].map((k) => Number(new RegExp(`--text-${k}: (\\d+)px`).exec(tokens)?.[1]));
    expect(sizes).toEqual([12, 14, 16, 20, 25, 31, 39]);
  });

  it('uses only the type scale for font sizes', () => {
    // !important only for the 16px fields on a touch screen (below), which must win over a field's own size
    expect(values('font-size').filter((v) => !/^var\(--text-(xs|sm|md|lg|xl|2xl|3xl)\)$/.test(v.value) && v.value !== 'var(--text-md) !important')).toEqual([]);
  });

  it('gives fields 16px on a touch screen, so Safari does not zoom in when you tap one', () => {
    expect(styles).toMatch(/@media \(pointer: coarse\) \{[^@]*select, textarea \{ font-size: var\(--text-md\) !important; \}/);
  });

  it('uses only the radius tokens', () => {
    expect(values('border-radius').filter((v) => !/^(var\(--radius-(sm|md|lg|pill)\)|0|50%)$/.test(v.value))).toEqual([]);
  });

  it('uses only the weight tokens', () => {
    expect(values('font-weight').filter((v) => !/^(var\(--weight-(body|label|heading)\)|inherit)$/.test(v.value))).toEqual([]);
  });

  it('writes no colour outside the tokens', () => {
    const found = rules.flatMap((f) => [...f.text.matchAll(/#[0-9a-f]{3,8}\b|\b(rgba?|hsla?)\(/gi)].map((m) => `${f.name}: ${m[0]}`));
    expect(found).toEqual([]);
  });

  it('gives a forced dark theme the same colours as a dark device', () => {
    const device = block(":root:not([data-theme='light'])").split('\n').map((l) => l.trim()).filter(Boolean);
    const forced = block(":root[data-theme='dark']").split('\n').map((l) => l.trim()).filter(Boolean);
    expect(forced).toEqual(device);
  });

  it('keeps the faintest ink for decoration, never for words', () => {
    // --ink-4 is under 4.5:1 on the surfaces (WCAG AA for text), so only icons may use it
    const found = rules.flatMap((f) => [...f.text.matchAll(/([^{}]*)\{[^}]*(?<![\w-])color:\s*var\(--ink-4\)/g)]
      .map((m) => m[1].trim()).filter((sel) => !/chevron|icon|svg/.test(sel)).map((sel) => `${f.name}: ${sel}`));
    expect(found).toEqual([]);
  });

  it('sets every small capital label in the label font and colour', () => {
    // facts about an item and the small heads over a group, like notes on a sketch (16 November)
    const labels = rules.flatMap((f) => [...f.text.matchAll(/([^{}]*)\{([^}]*text-transform:\s*uppercase[^}]*)\}/g)]
      .map((m) => ({ name: `${f.name}: ${m[1].trim()}`, body: m[2] })));
    // a guard that the pattern still finds them (two went with "What Claude saw" and the old drawing notes, 20 November)
    expect(labels.length).toBeGreaterThan(6);
    expect(labels.filter((l) => !/font-family:\s*var\(--font-label\)/.test(l.body) || !/color:\s*var\(--label-ink\)/.test(l.body)).map((l) => l.name)).toEqual([]);
  });

  it('moves on the motion tokens: one curve and two lengths', () => {
    // a transition or a one-off animation; a loop (the spinner, a skeleton) keeps its own pace, and less motion cuts
    // every one to nothing with its own rule
    const timed = [...values('transition'), ...values('animation')].filter((v) => !/infinite|^none$|!important/.test(v.value));
    expect(timed.length).toBeGreaterThan(10);
    const off = timed.filter((v) => v.value.split(',').some((part) => {
      const words = part.trim().split(/\s+/);
      const times = words.filter((w) => /^-?[\d.]+m?s$/.test(w) || w.startsWith('var(--dur'));
      const curves = words.filter((w) => /^(ease|ease-in|ease-out|ease-in-out|linear|step-start|step-end)$/.test(w) || /^(cubic-bezier|steps)\(/.test(w) || w.startsWith('var(--ease'));
      return times.length !== 1 || !/^var\(--dur-(quick|move)\)$/.test(times[0]) || curves.length !== 1 || curves[0] !== 'var(--ease-out)';
    }));
    expect(off).toEqual([]);
    expect(tokens).toMatch(/--ease-out: cubic-bezier\(0\.22, 1, 0\.36, 1\);/);
  });

  it('shows a press by tone, never by size', () => {
    // no pressed rule anywhere changes size; a press dims to --press-dim after --press-delay (homestead's touch CSS)
    const pressed = rules.flatMap((f) => [...f.text.matchAll(/([^{}]*:active[^{}]*)\{([^}]*)\}/g)]
      .filter((m) => /transform|scale|zoom|width|height/.test(m[2])).map((m) => `${f.name}: ${m[1].trim()}`));
    expect(pressed).toEqual([]);
    expect(styles).toMatch(/:active[^{]*\{\s*opacity: var\(--press-dim\); transition-duration: 0s; transition-delay: var\(--press-delay\);/);
    expect(tokens).toMatch(/--press-dim: 0\.5;/);
    expect(tokens).toMatch(/--press-delay: 70ms;/);
  });

  it('defines every token it uses', () => {
    const defined = new Set([...styles.matchAll(/(--[\w-]+):/g)].map((m) => m[1]));
    const used = new Set(files.flatMap((f) => [...f.text.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1])));
    expect([...used].filter((v) => !defined.has(v))).toEqual([]);
  });
});
