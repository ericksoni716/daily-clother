import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PhoneAccess } from './components/PhoneAccess';
import { StatusLine } from './components/Toggle';
import { deviceOf } from './here';
import { backupLine, claudeLine, computerOnly, mainGroups, storageLine, updatesLine } from './settingsLines';
import type { ApiKeyInfo, Settings, TaggingStatus } from './types';
import type { UpdateStatus } from './updates';

const noKey: ApiKeyInfo = { set: false, source: null, can_save: true, where: null };
const savedKey: ApiKeyInfo = { set: true, source: 'keychain', can_save: true, where: "this Mac's keychain" };
const claude = (over: Partial<Pick<Settings, 'tagging_api_enabled' | 'tagging_api_off' | 'api_key'>> = {}) =>
  ({ tagging_api_enabled: false, tagging_api_off: null, api_key: noKey, ...over });
const routes = (plan: boolean, api: boolean, order: ('plan' | 'api')[] = ['plan', 'api']): TaggingStatus => ({
  order, routes: order.map((id) => ({ id, available: id === 'plan' ? plan : api, detail: '' })),
});
const spend = (over = {}) => ({ spent_usd: 0.16, cap_usd: 5, reached: false, ...over });

describe('the Claude line', () => {
  it('says the plan is used when it works, and nothing else', () => {
    expect(claudeLine(claude(), spend(), routes(true, false), null, false)).toEqual({ tone: 'ok', text: 'Using your Claude plan.', action: null });
  });

  it('mentions the key as the backup only when the key is allowed and comes after the plan', () => {
    const line = claudeLine(claude({ tagging_api_enabled: true, api_key: savedKey }), spend(), routes(true, true), null, false);
    expect(line.text).toBe("Using your Claude plan, with your API key if the plan can't be used.");
    expect(claudeLine(claude({ tagging_api_enabled: true }), spend(), routes(true, true, ['api', 'plan']), null, false).text)
      .toBe('Using your API key: $0.16 of $5.00 this month.');
  });

  it('uses the key when the plan cannot be used, with what the month has cost', () => {
    const line = claudeLine(claude({ tagging_api_enabled: true, api_key: savedKey }), spend(), routes(false, true), null, false);
    expect(line).toEqual({ tone: 'ok', text: 'Using your API key: $0.16 of $5.00 this month.', action: null });
  });

  it('is one red sentence when nothing works, with install as the action only when installing helps', () => {
    const none = claudeLine(claude(), spend(), routes(false, false), null, false);
    expect(none).toEqual({ tone: 'problem', text: "Closet can't reach Claude yet.", action: 'install' });
    const notAllowed = claudeLine(claude({ api_key: savedKey }), spend(), routes(false, true), null, false);
    expect(notAllowed.text).toBe("Closet can't reach Claude: your API key is saved but not allowed.");
    expect(notAllowed.action).toBeNull();   // Manage is the action: allowing the key is on the Advanced screen
    const onlyKey = claudeLine(claude(), spend(), routes(false, false, ['api']), null, false);
    expect(onlyKey.text).toBe("Closet can't reach Claude: you chose only the API key, and it isn't allowed yet.");
  });

  it('says the limit is reached when the key is the only way and its month is used up', () => {
    const line = claudeLine(claude({ tagging_api_enabled: true, api_key: savedKey }), spend({ reached: true }), routes(false, true), null, false);
    expect(line).toEqual({ tone: 'problem', text: "This month's limit for the API key is reached, and your Claude plan can't be used.", action: null });
    // with the plan working, a used-up key does not matter
    expect(claudeLine(claude({ tagging_api_enabled: true }), spend({ reached: true }), routes(true, true), null, false).tone).toBe('ok');
  });

  it('says why Closet stopped using the key, when that leaves nothing', () => {
    const off = { reason: 'credit' as const, at: '2026-11-03T10:00:00Z' };
    const line = claudeLine(claude({ tagging_api_off: off, api_key: savedKey }), spend(), routes(false, true), null, false);
    expect(line.text).toBe('Closet stopped using your API key because your Anthropic account has no credit left.');
    expect(line.tone).toBe('problem');
  });

  it('waits for the lookup, offers Check again after a failed one, and says it cannot check offline', () => {
    expect(claudeLine(claude(), spend(), null, null, false)).toEqual({ tone: 'waiting', text: 'Checking how Closet reaches Claude…', action: null });
    expect(claudeLine(claude(), spend(), null, 'timed out', false)).toEqual({
      tone: 'problem', text: "Closet couldn't check how it reaches Claude: timed out", action: 'check',
    });
    expect(claudeLine(claude(), spend(), routes(true, false), null, true).tone).toBe('quiet');
  });
});

const updates = (over: Partial<UpdateStatus> = {}): UpdateStatus => ({
  version: '0.4.0', mode: 'ask', can_install: true, checked_at: '2026-11-19T09:00:00Z', check_error: null, latest: '0.4.0',
  available: null, download_size: null, ready: false, problem: null, busy: null, last_install: null,
  releases_page: 'https://example.com/releases', ...over,
});
const release = { version: '0.4.1', notes: '', page: 'https://example.com/releases/0.4.1', published_at: null };

describe('the Updates line', () => {
  it('is "up to date" once checked, and plain before', () => {
    expect(updatesLine(updates(), '0.4.0', false)).toEqual({ tone: 'ok', text: 'Closet 0.4.0 · up to date', action: null });
    expect(updatesLine(updates({ checked_at: null, latest: null }), '0.4.0', false).text).toBe('Closet 0.4.0');
    expect(updatesLine(updates({ checked_at: null, latest: null, mode: 'never' }), '0.4.0', false).text)
      .toBe('Closet 0.4.0 · not looking for new versions');
  });

  it('offers Install when a new version is ready, and a download when this copy cannot replace itself', () => {
    expect(updatesLine(updates({ available: release, ready: true }), '0.4.0', false))
      .toEqual({ tone: 'ok', text: 'Closet 0.4.1 is ready to install.', action: 'install' });
    const byHand = updatesLine(updates({ available: release, can_install: false }), '0.4.0', false);
    expect(byHand.action).toBe('download');
    expect(byHand.text).toBe('Closet 0.4.1 is out. Download it from the release page and install it by hand.');
  });

  it('shows a step of an install while it runs, and a problem in red', () => {
    expect(updatesLine(updates({ busy: 'downloading' }), '0.4.0', false)).toEqual({ tone: 'waiting', text: 'Downloading the new version…', action: null });
    const problem = updatesLine(updates({ available: release, problem: "Closet couldn't back up your closets." }), '0.4.0', false);
    expect(problem).toEqual({ tone: 'problem', text: "Closet couldn't back up your closets.", action: 'install' });
    const failed = updatesLine(updates({ last_install: { at: '2026-11-19T09:00:00Z', from: '0.4.0', to: '0.4.1', ok: false, note: null } }), '0.4.0', false);
    expect(failed.tone).toBe('problem');
    expect(failed.text).toBe('Closet 0.4.1 did not start, so Closet 0.4.0 was put back.');
  });

  it('names the version even with no updater, and says offline when it cannot check', () => {
    expect(updatesLine(null, '0.4.0', false).text).toBe('Closet 0.4.0');
    expect(updatesLine(null, '0.4.0', true).text).toBe("Closet 0.4.0. Updates can't be checked while you're offline.");
  });
});

describe('the backup line', () => {
  const none = { backup_folder: null, last_backup: null, last_good_backup: null };
  it('asks for a folder on the computer, and sends the phone to the computer', () => {
    expect(backupLine(none, 'main', 'computer')).toEqual({ tone: 'problem', text: "Your closet isn't backed up yet.", action: 'choose' });
    const phone = backupLine(none, 'main', 'phone');
    expect(phone.action).toBeNull();
    expect(phone.text).toContain('on your computer');
  });

  it('says where the copies go and when the last good one was', () => {
    const line = backupLine({ backup_folder: 'D:\\Closet backups', last_backup: null, last_good_backup: '2026-11-19T03:00:00Z' }, 'main', 'computer');
    expect(line.tone).toBe('ok');
    expect(line.text).toMatch(/^Backed up every day to D:\\Closet backups · last good backup /);
    expect(backupLine({ backup_folder: '/Volumes/USB', last_backup: null, last_good_backup: null }, 'main', 'phone').text)
      .toBe('Backed up every day to /Volumes/USB · no backup yet.');
  });

  it('is red when the last backup failed, and quiet in the demo closet', () => {
    const failed = backupLine({
      backup_folder: '/Volumes/USB', last_good_backup: null,
      last_backup: { at: '2026-11-19T03:00:00Z', ok: false, error: 'the folder is missing', folder: '/Volumes/USB', kind: 'daily' },
    }, 'main', 'computer');
    expect(failed.tone).toBe('problem');
    expect(failed.text).toMatch(/^The last backup didn't work \(.+\): the folder is missing$/);
    expect(backupLine(none, 'demo', 'computer')).toEqual({ tone: 'quiet', text: 'The demo closet is never backed up.', action: null });
  });
});

describe('what a phone and the computer are shown', () => {
  it('tells the computer from the phone by the address the page is open on', () => {
    expect(deviceOf('127.0.0.1')).toBe('computer');
    expect(deviceOf('closet-pc.example-tailnet.ts.net')).toBe('phone');
  });

  it('keeps the main page in the order of the outline, with Phone only where it has something to say', () => {
    expect(mainGroups('connect')).toEqual(['style', 'everyday', 'claude', 'updates', 'phone', 'device', 'data', 'leave']);
    expect(mainGroups('add-to-home-screen')).toContain('phone');
    expect(mainGroups('nothing')).toEqual(['style', 'everyday', 'claude', 'updates', 'device', 'data', 'leave']);
  });

  it('offers Quit, start at login, folders and files to put in place only on the computer', () => {
    expect(computerOnly('computer')).toEqual({ quit: true, autostart: true, backupFolder: true, modelFiles: true, dataFolder: true, cloudflare: true });
    expect(Object.values(computerOnly('phone')).some(Boolean)).toBe(false);
  });

  it('puts the space used in one line', () => {
    expect(storageLine('2.7 MB', 49, '62 GB')).toBe('Closet uses 2.7 MB for 49 items · 62 GB free on this disk.');
    expect(storageLine('1 KB', 1, null)).toBe('Closet uses 1 KB for 1 item.');
  });
});

describe('the status line as drawn', () => {
  const html = (line: Parameters<typeof StatusLine>[0]['line']) => renderToStaticMarkup(createElement(StatusLine, { line, testId: 'x' }));
  it('draws a green dot when all is well, a red line on a problem, and keeps waiting quiet for screen readers', () => {
    expect(html({ tone: 'ok', text: 'Using your Claude plan.' })).toContain('state-ready');
    const problem = html({ tone: 'problem', text: "Closet can't reach Claude yet." });
    expect(problem).toContain('state-problem');
    expect(problem).toContain('role="status"');
    expect(html({ tone: 'waiting', text: 'Checking…' })).toContain('aria-busy="true"');
    expect(html({ tone: 'quiet', text: 'Closet 0.4.0' })).not.toContain('state-dot');
  });
});

describe('the Phone group on the computer', () => {
  const info = (address: string | null) => ({
    tailscale_installed: true, running: true, address, command: 'tailscale serve --bg 8765', stop_command: address ? 'tailscale serve --https=443 off' : null, others_share: false,
  });
  it('is one line once a share reaches Closet, with the code folded under it', () => {
    const html = renderToStaticMarkup(createElement(PhoneAccess, { phone: info('https://pc.example.ts.net') }));
    expect(html).toContain('Shared with your phone at');
    expect(html).toMatch(/<details[^>]*data-testid="phone-code"[^>]*><summary>Show the QR code<\/summary>/);
    expect(html).not.toContain('<details open');
    expect(html).toContain('aria-label="QR code of https://pc.example.ts.net"');
  });

  it('shows the command to run until then, and no code', () => {
    const html = renderToStaticMarkup(createElement(PhoneAccess, { phone: info(null) }));
    expect(html).toContain('tailscale serve --bg 8765');
    expect(html).not.toContain('phone-qr');
  });
});
