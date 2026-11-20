import { describe, expect, it } from 'vitest';
import { cameInLine, fromHomeScreen, onThisComputer, phoneAccessShows, throughCloudflare } from './here';

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

describe('throughCloudflare', () => {
  it.each([
    ['closet.example.com', true],
    ['CLOSET.EXAMPLE.COM', true],
    ['closet-pc.example-tailnet.ts.net', false],
    ['closet-pc.example-tailnet.ts.net.', false],
    ['127.0.0.1', false],
    ['localhost', false],
    ['[::1]', false],
  ])('%s → %s', (hostname, expected) => {
    expect(throughCloudflare(hostname)).toBe(expected);
  });
});

describe('cameInLine', () => {
  it('says nothing on the computer itself', () => {
    expect(cameInLine({ via: 'computer', login: null, name: null })).toBeNull();
    expect(cameInLine(undefined)).toBeNull();
  });
  it('says who Tailscale said is using a device, or that it did not say', () => {
    expect(cameInLine({ via: 'tailscale', login: 'owner@example.com', name: 'owner@example.com' }))
      .toBe('This device came in through Tailscale as owner@example.com.');
    expect(cameInLine({ via: 'tailscale', login: 'owner@example.com', name: 'Sam Owner' }))
      .toBe('This device came in through Tailscale as Sam Owner (owner@example.com).');
    expect(cameInLine({ via: 'tailscale', login: null, name: null }))
      .toBe('This device came in through Tailscale, but Tailscale did not say who is using it.');
  });
  it('says which email signed in through Cloudflare', () => {
    expect(cameInLine({ via: 'cloudflare', login: 'owner@example.com', name: 'owner@example.com' }))
      .toBe('This device came in through Cloudflare, signed in as owner@example.com.');
  });
});
