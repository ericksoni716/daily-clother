import { QueryClient } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { queryKeys } from './queryKeys';
import { PHONE_MS, phonePoll, routeIds, settingsSaved, settingsWritten, writePart, writeSettings } from './settings';
import type { ModelInfo, Settings, StyleProfile, TaggingSpend } from './types';
import { updates, type UpdateStatus } from './updates';

const status = (over: Partial<UpdateStatus> = {}) => ({ version: '0.2.0', mode: 'ask', can_install: false, ...over }) as UpdateStatus;
const settings = (over: Partial<Settings> = {}) => ({
  version: '0.2.0',
  phone: null,
  model: { state: 'ready', url: 'https://example.com/a.onnx' } as ModelInfo,
  updates: status(),
  style_profile: { text: 'Navy with brown.', is_default: false, max_length: 4000 } as StyleProfile,
  tagging_spend: { month: '2026-11', spent_usd: 0 } as unknown as TaggingSpend,
  ...over,
}) as Settings;
const phone = (address: string | null) => ({ tailscale_installed: true, running: true, address, command: 'tailscale serve', stop_command: null, others_share: false });

afterEach(() => updates.reset());

describe('the settings in the cache', () => {
  it('fill the model, Your style, the spending and the updates under their own keys', () => {
    const qc = new QueryClient();
    const s = settings();
    writeSettings(qc, s);
    expect(qc.getQueryData(queryKeys.settings())).toBe(s);
    expect(qc.getQueryData(queryKeys.model())).toBe(s.model);
    expect(qc.getQueryData(queryKeys.styleProfile())).toBe(s.style_profile);
    expect(qc.getQueryData(queryKeys.spend())).toBe(s.tagging_spend);
    expect(qc.getQueryData(queryKeys.updates())).toBe(s.updates);
  });

  it('put the updates in the page’s one copy only when they changed', () => {
    const qc = new QueryClient();
    const set = vi.spyOn(updates, 'set');
    writeSettings(qc, settings());
    writeSettings(qc, settings());   // asked again, the same answer
    expect(set).toHaveBeenCalledTimes(1);
    writeSettings(qc, settings({ updates: status({ mode: 'never' }) }));
    expect(set).toHaveBeenCalledTimes(2);
    writeSettings(qc, settings({ updates: null }));   // no updater: what the page knows stays
    expect(set).toHaveBeenCalledTimes(2);
    set.mockRestore();
  });

  it('take a part saved through its own endpoint', () => {
    const qc = new QueryClient();
    writeSettings(qc, settings());
    const style = { text: 'No ties.', is_default: false, max_length: 4000 } as StyleProfile;
    writePart(qc, { style_profile: style });
    expect(qc.getQueryData(queryKeys.styleProfile())).toEqual(style);
    expect(qc.getQueryData<Settings>(queryKeys.settings())?.style_profile).toEqual(style);
    const model = { state: 'ready', url: 'https://example.com/b.onnx' } as ModelInfo;
    writePart(qc, { model });
    expect(qc.getQueryData(queryKeys.model())).toEqual(model);
    expect(qc.getQueryData<Settings>(queryKeys.settings())?.model).toEqual(model);
  });

  it('after a save, ask again only for what the answer does not carry', async () => {
    const qc = new QueryClient();
    for (const key of [queryKeys.weather(), queryKeys.tagging(), queryKeys.gaps()]) qc.setQueryData(key, {});
    settingsSaved(qc, settings(), 'settings', { laundry: { auto: true } });
    await Promise.resolve();
    const stale = (key: readonly unknown[]) => qc.getQueryState(key)?.isInvalidated;
    expect(stale(queryKeys.settings())).toBe(false);
    expect(stale(queryKeys.weather())).toBe(false);
    expect(stale(queryKeys.tagging())).toBe(false);
    expect(stale(queryKeys.gaps())).toBe(true);
  });
});

describe('settingsWritten', () => {
  it('a switch or a number: everything Settings shows is in the answer', () => {
    expect(settingsWritten('settings', { autostart: true }).sort()).toEqual(['settings', 'spend', 'tagging', 'weather']);
  });
  it('a new place asks for the weather again, a new order for how Claude is reached', () => {
    expect(settingsWritten('settings', { place: null })).not.toContain('weather');
    expect(settingsWritten('settings', { tagging_route_order: 'plan' })).not.toContain('tagging');
  });
  it('a key saved or removed asks again how Claude is reached', () => {
    expect(settingsWritten('apiKey')).toEqual(['settings', 'spend']);
  });
});

describe('phonePoll', () => {
  it('asks again on the computer until the phone has an address', () => {
    expect(phonePoll('connect', settings({ phone: null }), false)).toBe(PHONE_MS);
    expect(phonePoll('connect', settings({ phone: phone(null) }), false)).toBe(PHONE_MS);
    expect(phonePoll('connect', settings({ phone: phone('https://pc.example.ts.net') }), false)).toBe(false);
  });
  it('never on the phone, offline, or before the first answer', () => {
    expect(phonePoll('add-to-home-screen', settings(), false)).toBe(false);
    expect(phonePoll('nothing', settings(), false)).toBe(false);
    expect(phonePoll('connect', settings(), true)).toBe(false);
    expect(phonePoll('connect', undefined, false)).toBe(false);
  });
});

describe('routeIds', () => {
  it('lists the routes in the order the server tries them', () => {
    expect(routeIds('auto')).toEqual(['plan', 'api']);
    expect(routeIds('api-first')).toEqual(['api', 'plan']);
    expect(routeIds('plan')).toEqual(['plan']);
    expect(routeIds('api')).toEqual(['api']);
  });
});
