import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { KeepRunning } from './components/KeepRunning';
import { ACTION_LABEL, keepActions, keepLine, keepPhoneLine, keepPoll, keepShows, portLine } from './keepRunning';
import { mainGroups } from './settingsLines';
import type { BackgroundState } from './types';

const off: BackgroundState = { available: true, on: false, starts: null, running: false, port: 8766, problem: null };
const on: BackgroundState = { ...off, on: true, starts: 'startup', running: true };

function drawn(state: BackgroundState, device: 'computer' | 'phone' = 'computer'): string {
  return renderToStaticMarkup(createElement(QueryClientProvider, { client: new QueryClient() },
    createElement(KeepRunning, { state, device, offline: false })));
}

describe('keeping Nines running', () => {
  it('is shown only where Windows can do it', () => {
    expect(keepShows(off)).toBe(true);
    expect(keepShows({ ...off, available: false })).toBe(false);
    expect(keepShows(undefined)).toBe(false);
    expect(drawn({ ...off, available: false })).toBe('');
    expect(drawn({ ...off, available: false }, 'phone')).toBe('');
  });

  it('says whether it is on, how it starts and whether it runs now', () => {
    expect(keepLine(off, null)).toEqual({ tone: 'quiet', text: 'This is off, so other devices reach Nines only while it is open on this computer.' });
    expect(keepLine(on, null)).toEqual({ tone: 'ok', text: 'Nines starts when this computer turns on, and it is running now.' });
    expect(keepLine({ ...on, starts: 'logon' }, null).text).toBe('Nines starts when you sign in to this computer, and it is running now.');
    expect(keepLine({ ...on, running: false }, null)).toEqual({
      tone: 'problem', text: 'Nines is set to start when this computer turns on, but it is not running in the background now.',
    });
  });

  it('says what it is waiting for after a button, and why turning it off did not work', () => {
    expect(keepLine(off, 'turning-on').text).toBe('Windows is asking for permission on this screen.');
    expect(keepLine(on, 'handing-over').text).toBe('Windows keeps Nines running now. This window closes and opens again in a moment.');
    expect(keepLine(on, 'turning-off').tone).toBe('waiting');
    const declined = { ...on, problem: 'Windows asked for permission on this computer\'s screen and it was not given, so nothing changed.' };
    expect(keepLine(declined, null)).toEqual({ tone: 'problem', text: declined.problem });
  });

  it('shows the port Nines answers on, and that it stays put once Windows keeps it running', () => {
    expect(portLine(off)).toBe('Nines answers on port 8766 on this computer.');
    expect(portLine(on)).toBe('Nines answers on port 8766 on this computer. While Windows keeps it running, the port does not change, so Tailscale and Cloudflare stay pointed at it.');
  });

  it('offers turning it on, off, or starting it again, and nothing while it waits', () => {
    expect(keepActions(off, null)).toEqual(['on']);
    expect(keepActions(on, null)).toEqual(['off']);
    expect(keepActions({ ...on, running: false }, null)).toEqual(['restart', 'off']);
    expect(keepActions(on, 'turning-off')).toEqual([]);
    expect(Object.values(ACTION_LABEL)).toEqual(['Keep Nines running', 'Start it again', 'Turn this off']);
  });

  it('says on the phone in one sentence whether the computer keeps it running, and where that is changed', () => {
    expect(keepPhoneLine(on)).toBe('Your computer keeps Nines running, so you can reach it from here whenever the computer is awake. You change this in Settings on the computer.');
    expect(keepPhoneLine(off)).toContain('only while it is open there');
    expect(keepPhoneLine({ ...on, available: false })).toBeNull();
    const phone = drawn(on, 'phone');
    expect(phone).toContain('You change this in Settings on the computer.');
    expect(phone).not.toContain('<button');
  });

  it('draws the card on the computer with the explanation only while it is off', () => {
    const card = drawn(off);
    expect(card).toContain('Keep Nines running</button>');
    expect(card).toContain('scheduled task');
    expect(card).toContain('updates then go to the copy Windows runs');
    expect(card).toContain('port 8766');
    expect(drawn(on)).not.toContain('scheduled task');
    expect(drawn(on)).toContain('Turn this off</button>');
  });

  it('asks again only while turning off from the window, until Windows has answered', () => {
    expect(keepPoll(on, 'turning-off')).toBe(2000);
    expect(keepPoll({ ...on, problem: 'no' }, 'turning-off')).toBe(false);
    expect(keepPoll(off, 'turning-off')).toBe(false);
    expect(keepPoll(on, null)).toBe(false);
  });

  it('shows Phone on the phone as an app only when there is something to say', () => {
    expect(mainGroups('nothing')).not.toContain('phone');
    expect(mainGroups('nothing', true)).toContain('phone');
  });
});
