import { describe, expect, it } from 'vitest';
import { fromHomeScreen, onThisComputer, phoneAccessShows } from './here';

describe('onThisComputer', () => {
  it.each([
    ['127.0.0.1', true],
    ['localhost', true],
    ['LOCALHOST', true],
    ['[::1]', true],
    ['::1', true],
    ['closet-pc.example-tailnet.ts.net', false],
    ['100.101.102.103', false],
    ['192.168.1.20', false],
    ['127.0.0.1.example.com', false],
  ])('%s → %s', (hostname, expected) => {
    expect(onThisComputer(hostname)).toBe(expected);
  });
});

describe('fromHomeScreen', () => {
  const win = (standaloneMedia: boolean, standalone?: boolean) => ({
    matchMedia: (q: string) => ({ matches: q === '(display-mode: standalone)' && standaloneMedia }) as MediaQueryList,
    navigator: { standalone } as Navigator & { standalone?: boolean },
  });
  it('is true for an installed app, on iPhone (navigator.standalone) or elsewhere (display mode)', () => {
    expect(fromHomeScreen(win(false, true))).toBe(true);
    expect(fromHomeScreen(win(true))).toBe(true);
  });
  it('is false in a browser tab', () => {
    expect(fromHomeScreen(win(false, false))).toBe(false);
    expect(fromHomeScreen(win(false))).toBe(false);
  });
});

describe('phoneAccessShows', () => {
  it('shows how to connect the phone only on the computer, even if the computer installed it as an app', () => {
    expect(phoneAccessShows('127.0.0.1', false)).toBe('connect');
    expect(phoneAccessShows('localhost', true)).toBe('connect');
  });
  it('on the phone, says how to add it to the Home Screen, unless it is already opened from there', () => {
    expect(phoneAccessShows('closet-pc.example-tailnet.ts.net', false)).toBe('add-to-home-screen');
    expect(phoneAccessShows('closet-pc.example-tailnet.ts.net', true)).toBe('nothing');
  });
});
