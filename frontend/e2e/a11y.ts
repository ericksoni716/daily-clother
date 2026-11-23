import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

/**
 * Accessibility checks shared by the browser tests (see 17-accessibility.spec.ts).
 * axe-core checks the page against WCAG 2.2 A and AA: contrast, names and roles, text alternatives.
 * `include` (a CSS selector) checks only that part of the page.
 */
export async function axeViolations(page: Page, include?: string): Promise<string[]> {
  const builder = new AxeBuilder({ page });
  if (include) builder.include(include);
  builder.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']);
  // Something fading in (a sheet, a toast) is measured half-transparent, so the page is settled first; and when an
  // animation started while axe was reading (a toast arriving from a save just made), it is read again once settled.
  let result = null;
  for (let tries = 0; tries < 3; tries++) {
    await settled(page);
    await watchStarts(page);
    result = await builder.analyze();
    if (!(await startedMeanwhile(page))) break;
  }
  return result!.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(' ')} — ${n.failureSummary?.split('\n').slice(1).join(' ').trim()}`));
}

/** Waits until no animation or transition that ends is running, looking again a few frames later for ones that began
 * meanwhile (a toast mounted just after a save answers). Never waits for time alone, nor for one that never ends. */
async function settled(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const frames = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    for (let round = 0; round < 20; round++) {
      const running = document.getAnimations().filter((a) => a.playState === 'running'
        && a.effect?.getComputedTiming().iterations !== Infinity);
      if (!running.length) {
        await frames();
        if (!document.getAnimations().some((a) => a.playState === 'running' && a.effect?.getComputedTiming().iterations !== Infinity)) return;
        continue;
      }
      await Promise.all(running.map((a) => a.finished.catch(() => undefined)));
    }
  });
}

/** Notes any animation or transition that starts from now on (one that ends before axe finishes is caught too). */
function watchStarts(page: Page): Promise<void> {
  return page.evaluate(() => {
    const w = window as unknown as { axeMoved?: boolean; axeWatching?: boolean };
    w.axeMoved = false;
    if (w.axeWatching) return;
    w.axeWatching = true;
    const moved = () => { w.axeMoved = true; };
    document.addEventListener('animationstart', moved, true);
    document.addEventListener('transitionstart', moved, true);
  });
}

/** Whether something started moving while axe was reading the page: what it read may have been mid-fade. */
function startedMeanwhile(page: Page): Promise<boolean> {
  return page.evaluate(() => !!(window as unknown as { axeMoved?: boolean }).axeMoved);
}

/** Anything visible that reaches past the right edge of the screen without being inside something that scrolls sideways. */
export function sideways(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const out: string[] = [];
    for (const el of document.body.querySelectorAll<HTMLElement>('*')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0 || r.right <= width + 1) continue;
      let clipped = false;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX;
        if (o !== 'visible' && p.getBoundingClientRect().right <= width + 1) { clipped = true; break; }
      }
      const s = getComputedStyle(el);
      if (clipped || s.visibility === 'hidden' || s.position === 'fixed' && r.left >= width) continue;
      if (el.closest('.visually-hidden, .skip-link')) continue;
      out.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} right=${Math.round(r.right)}`);
    }
    return out;
  });
}

/**
 * Controls smaller than 44px a side on a phone. A control's hit area counts any ::after the CSS adds around it.
 * Links inside a sentence are left out, as WCAG does.
 */
export function smallTargets(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=menuitem], [role=tab]';
    for (const el of document.querySelectorAll<HTMLElement>(sel)) {
      const s = getComputedStyle(el);
      // a radio or checkbox inside its label: the whole label is what a finger presses
      const label = el instanceof HTMLInputElement && /^(radio|checkbox)$/.test(el.type) ? el.closest('label') : null;
      const r = (label ?? el).getBoundingClientRect();
      if (r.width <= 1 || r.height <= 1 || s.visibility === 'hidden') continue;
      if (s.display === 'inline' && el.closest('p, li, dd, span.muted, .hint')) continue;
      // a hidden input whose label is the target (the switches)
      if (el instanceof HTMLInputElement && el.closest('label') && s.opacity === '0') continue;
      if (el.closest('.visually-hidden, .skip-link')) continue;
      const after = getComputedStyle(el, '::after');
      let w = r.width;
      let h = r.height;
      if (after.content !== 'none' && after.position === 'absolute') {
        const top = parseFloat(after.top) || 0;
        const bottom = parseFloat(after.bottom) || 0;
        const left = parseFloat(after.left) || 0;
        const right = parseFloat(after.right) || 0;
        h = Math.max(h, r.height - top - bottom);
        w = Math.max(w, r.width - left - right);
      }
      if (w < 43.5 || h < 43.5) {
        const name = (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30);
        out.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} "${name}" ${Math.round(w)}x${Math.round(h)}`);
      }
    }
    return out;
  });
}
