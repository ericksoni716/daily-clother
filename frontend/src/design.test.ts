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
    const sizes = ['xs', 'sm', 'md', 'lg', 'xl', '2xl'].map((k) => Number(new RegExp(`--text-${k}: (\\d+)px`).exec(tokens)?.[1]));
    expect(sizes).toEqual([12, 14, 16, 20, 25, 31]);
  });

  it('uses only the type scale for font sizes', () => {
    expect(values('font-size').filter((v) => !/^var\(--text-(xs|sm|md|lg|xl|2xl)\)$/.test(v.value))).toEqual([]);
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

  it('defines every token it uses', () => {
    const defined = new Set([...styles.matchAll(/(--[\w-]+):/g)].map((m) => m[1]));
    const used = new Set(files.flatMap((f) => [...f.text.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1])));
    expect([...used].filter((v) => !defined.has(v))).toEqual([]);
  });
});
