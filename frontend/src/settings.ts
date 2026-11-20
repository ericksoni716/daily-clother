/**
 * Settings through the query cache. `GET /api/settings` answers at once and carries, each exactly as its own endpoint
 * answers it, the model, the updates, Your style and the spending: the page is drawn from that one answer, and those
 * parts are written under their own keys so the rest of the app agrees without asking again. The slow lookups
 * (`/api/tagging`, `/api/storage`, `/api/weather`) are queries of their own. See docs/DEVELOPING.md, "Reading and
 * saving data".
 */
import { queryOptions, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { api } from './api';
import { touch } from './queries';
import { queryKeys, type KeyName } from './queryKeys';
import type { ModelInfo, RouteOrder, Settings, StyleProfile, TaggingRoute } from './types';
import { updates } from './updates';

/** How often Settings asks again, on the computer, while the phone has no address yet (a share just set up in the
 * Terminal shows without a reload). The server looks Tailscale up again when its last lookup is 10 s old. */
export const PHONE_MS = 3000;
/** How often, while Tailscale is not installed on the computer at all: installing it takes minutes, not seconds. */
export const PHONE_SLOW_MS = 30_000;

export type SettingsChange = Parameters<typeof api.putSettings>[0];

/** The parts of the settings that are another endpoint's answer, under their own keys (and the updates in the
 * page's one copy of their status too). */
function writeParts(qc: QueryClient, s: Settings): void {
  if (s.model) qc.setQueryData(queryKeys.model(), s.model);
  if (s.style_profile) qc.setQueryData(queryKeys.styleProfile(), s.style_profile);
  if (s.tagging_spend) qc.setQueryData(queryKeys.spend(), s.tagging_spend);
  if (s.updates) {
    const before = qc.getQueryData(queryKeys.updates());
    // the same status keeps the same object, so the banner and the Updates card only draw again on a change
    if (qc.setQueryData(queryKeys.updates(), s.updates) !== before) updates.set(s.updates);
  }
}

/** The settings, which also fill the model, the updates, Your style and the spending. */
export const settingsQuery = () => queryOptions({
  queryKey: queryKeys.settings(),
  queryFn: async ({ client }) => {
    const s = await api.settings();
    writeParts(client, s);
    return s;
  },
});

/** How Claude is reached. Settings asks it once each time it opens (`refetchOnMount: 'always'` there: Claude Code
 * may have been signed in meanwhile), while what was known stays shown; the card itself only reads it. */
export const taggingQuery = () => queryOptions({ queryKey: queryKeys.tagging(), queryFn: api.tagging });

export const storageQuery = () => queryOptions({ queryKey: queryKeys.storage(), queryFn: api.storage });

export const weatherQuery = () => queryOptions({ queryKey: queryKeys.weather(), queryFn: api.weather });

/** Settings as a save answered them: written in, with their parts, over any read from before the save. */
export function writeSettings(qc: QueryClient, s: Settings): void {
  void qc.cancelQueries({ queryKey: queryKeys.settings(), exact: true });
  qc.setQueryData(queryKeys.settings(), s);
  writeParts(qc, s);
}

/** A part saved through its own endpoint (the model's address, Your style): under its own key and in the settings. */
export function writePart(qc: QueryClient, part: { model: ModelInfo } | { style_profile: StyleProfile }): void {
  if ('model' in part) qc.setQueryData(queryKeys.model(), part.model);
  else qc.setQueryData(queryKeys.styleProfile(), part.style_profile);
  qc.setQueryData<Settings>(queryKeys.settings(), (s) => (s ? { ...s, ...part } : s));
}

/**
 * What a settings save has already written, so is not asked again: the settings and the spending always (the answer
 * carries them); the weather unless the place changed; how Claude is reached unless the order of the routes changed
 * (or, for the API key, always asked again: whether a key is set is part of it).
 */
export function settingsWritten(kind: 'settings' | 'apiKey', changes: SettingsChange = {}): KeyName[] {
  const written: KeyName[] = ['settings', 'spend'];
  if (kind === 'apiKey') return written;
  if (!('place' in changes)) written.push('weather');
  if (!('tagging_route_order' in changes)) written.push('tagging');
  return written;
}

/** After a save answered with the settings: written in, and the rest of what it touches made stale. */
export function settingsSaved(qc: QueryClient, s: Settings, kind: 'settings' | 'apiKey' = 'settings', changes: SettingsChange = {}): void {
  writeSettings(qc, s);
  void touch(qc, kind, settingsWritten(kind, changes));
}

/** `PUT /api/settings`, written into the cache. Returns the settings, and throws what the server said. */
export function useSaveSettings(): (changes: SettingsChange) => Promise<Settings> {
  const qc = useQueryClient();
  return useCallback(async (changes: SettingsChange) => {
    const s = await api.putSettings(changes);
    settingsSaved(qc, s, 'settings', changes);
    return s;
  }, [qc]);
}

/**
 * How often to ask for the settings again: on the computer, every few seconds while the phone has no address (or
 * is still being looked up), so a share set up meanwhile shows; every half minute while Tailscale is not even
 * installed; never on the phone, offline or once there is one.
 */
export function phonePoll(shows: 'connect' | 'add-to-home-screen' | 'nothing', s: Settings | undefined, offline: boolean): number | false {
  if (offline || shows !== 'connect' || !s) return false;
  if (s.phone?.address) return false;
  return s.phone && !s.phone.tailscale_installed ? PHONE_SLOW_MS : PHONE_MS;
}

/** The routes to Claude in the order chosen, as the server tries them (`tagger/routes.py`, `ORDERS`). */
export function routeIds(order: RouteOrder): TaggingRoute['id'][] {
  if (order === 'plan') return ['plan'];
  if (order === 'api') return ['api'];
  if (order === 'api-first') return ['api', 'plan'];
  return ['plan', 'api'];
}
