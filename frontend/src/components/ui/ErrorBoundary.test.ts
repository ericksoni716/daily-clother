import { createElement, Fragment, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { CRASH, ErrorBoundary } from './ErrorBoundary';

// These tests run without a browser, so React's own catching is played out by hand: the error a child throws goes
// through the same static methods React calls, and what the boundary then draws is rendered to markup.

function Boom(): never {
  throw new Error('a response of an unexpected shape');
}

/** Draws `children` inside a boundary as React would: the error a child throws becomes the boundary's state. */
function show(props: { resetKey?: unknown; whole?: boolean }, children: () => unknown): { html: string; boundary: ErrorBoundary } {
  const boundary = new ErrorBoundary({ ...props });
  try {
    children();
  } catch (e) {
    boundary.state = { ...boundary.state, ...ErrorBoundary.getDerivedStateFromError(e) };
  }
  return { html: renderToStaticMarkup(createElement(Fragment, null, boundary.render() as ReactNode)), boundary };
}

describe('the message in place of a screen that failed', () => {
  it('replaces a child that throws with the message and its two buttons', () => {
    const { html } = show({ resetKey: '/' }, Boom);
    expect(html).toContain(CRASH.screen);
    expect(html).toContain(CRASH.body);
    expect(html).toContain(`>${CRASH.retry}</button>`);
    expect(html).toContain(`>${CRASH.reload}</button>`);
    expect(html).toContain('role="alert"');
  });

  it('shows what it holds while nothing has failed', () => {
    const boundary = new ErrorBoundary({ children: createElement('p', null, 'the closet') });
    expect(renderToStaticMarkup(createElement(Fragment, null, boundary.render() as ReactNode))).toBe('<p>the closet</p>');
  });

  it('says the whole app could not be shown when it is the last resort', () => {
    expect(show({ whole: true }, Boom).html).toContain(CRASH.whole);
  });

  it('is cleared when the screen changes, and kept while it does not', () => {
    const { boundary } = show({ resetKey: '/insights' }, Boom);
    expect(boundary.state.error).not.toBeNull();
    expect(ErrorBoundary.getDerivedStateFromProps({ resetKey: '/insights' }, boundary.state)).toBeNull();
    expect(ErrorBoundary.getDerivedStateFromProps({ resetKey: '/today' }, boundary.state)).toEqual({ error: null, resetKey: '/today' });
  });

  it('writes the error to the console', () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const error = new Error('broken');
    new ErrorBoundary({}).componentDidCatch(error, { componentStack: '\n    at Boom' });
    expect(log).toHaveBeenCalledWith(expect.any(String), error, '\n    at Boom');
    log.mockRestore();
  });

  it('words its message in the app\'s voice: sentences, no exclamation marks', () => {
    for (const words of Object.values(CRASH)) expect(words).not.toContain('!');
  });
});
