import { useSyncExternalStore } from 'react';
import { api } from './api';
import { formatDateTime } from './labels';

/** The owner's choice in Settings: install by themselves, ask first (the default) or never check. */
export type UpdateMode = 'auto' | 'ask' | 'never';
export type UpdateBusy = 'checking' | 'downloading' | 'backing-up' | 'replacing' | 'restarting';

export interface UpdateRelease {
  version: string;
  /** The first lines of the release's notes, as plain text: shown as text, never as HTML. */
  notes: string;
  page: string;
  published_at: string | null;
}

export interface UpdateInstall {
  at: string;
  from: string;
  to: string;
  ok: boolean;
  note: string | null;
}

export interface UpdateStatus {
  version: string;
  mode: UpdateMode;
  /** Only the downloaded program on Windows or a Mac can replace itself; elsewhere a new version is only reported. */
  can_install: boolean;
  checked_at: string | null;
  check_error: string | null;
  latest: string | null;
  available: UpdateRelease | null;
  download_size: number | null;
  /** Downloaded and checked against GitHub's checksum, so Install is quick. */
  ready: boolean;
  problem: string | null;
  busy: UpdateBusy | null;
  last_install: UpdateInstall | null;
  releases_page: string;
}

export const MODES: { value: UpdateMode; label: string; short: string; hint: string }[] = [
  { value: 'auto', label: 'Install updates by themselves', short: 'By itself', hint: 'Closet backs up your closets, installs the new version and restarts. This page reconnects by itself.' },
  { value: 'ask', label: 'Ask me first', short: 'Ask first', hint: 'Closet gets a new version ready and asks before installing it.' },
  { value: 'never', label: 'Never check', short: 'Never', hint: 'Closet does not look for new versions unless you press Check now.' },
];

const BUSY: Record<UpdateBusy, string> = {
  checking: 'Checking for a new version…',
  downloading: 'Downloading the new version…',
  'backing-up': 'Backing up your closets…',
  replacing: 'Putting the new version in place…',
  restarting: 'Restarting Closet…',
};

export function busyLine(busy: UpdateBusy | null): string {
  return busy ? BUSY[busy] : '';
}

/** "Last checked" and how it went. */
export function checkedLine(s: Pick<UpdateStatus, 'checked_at' | 'mode'>): string {
  if (s.checked_at) return `Last checked ${formatDateTime(s.checked_at)}.`;
  return s.mode === 'never' ? 'Not checked: you chose never to check.' : 'Not checked yet.';
}

/** What the Updates section says about the newest release. */
export function availableLine(s: UpdateStatus): string {
  const r = s.available;
  if (!r) {
    if (s.latest && s.checked_at) return s.can_install || s.latest === s.version ? 'You have the latest version.' : `The latest version is ${s.latest}.`;
    return '';
  }
  if (!s.can_install) return `Closet ${r.version} is out. Download it from the release page and install it by hand.`;
  return s.ready ? `Closet ${r.version} is ready to install.` : `Closet ${r.version} is out.`;
}

/** The slim banner on every screen, only in "Ask me first" once the new version is downloaded and checked. */
export function showBanner(s: UpdateStatus | null): boolean {
  return !!s && s.mode === 'ask' && s.can_install && s.ready && !!s.available && !s.busy;
}

/** How the last update went, when there is something to say. */
export function lastInstallLine(s: UpdateStatus): string {
  const last = s.last_install;
  if (!last) return '';
  if (!last.ok) return last.note || `Closet ${last.to} did not start, so Closet ${last.from} was put back.`;
  return last.to === s.version ? `Updated from ${last.from} to ${last.to} on ${formatDateTime(last.at)}.` : '';
}

// ------------------------------------------------------------------ one copy of the status for the whole page
export interface Installing {
  from: string;
  to: string;
  /** Closet has not come back in time */
  late: boolean;
}

interface Snapshot {
  status: UpdateStatus | null;
  installing: Installing | null;
}

let snapshot: Snapshot = { status: null, installing: null };
const listeners = new Set<() => void>();

function set(next: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...next };
  listeners.forEach((l) => l());
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => void listeners.delete(l);
}

export function useUpdates(): Snapshot {
  return useSyncExternalStore(subscribe, () => snapshot);
}

export const updates = {
  set: (status: UpdateStatus) => set({ status }),
  async refresh(): Promise<UpdateStatus | null> {
    try {
      const status = await api.updates();
      set({ status });
      return status;
    } catch {
      return null;
    }
  },
  /** Starts installing and follows Closet as it restarts; resolves once the page is about to reload or it stopped. */
  async install(toast: (m: string, k?: 'ok' | 'error') => void): Promise<void> {
    const before = snapshot.status;
    const status = await api.installUpdate();
    const to = status.available?.version ?? before?.available?.version ?? '';
    set({ status, installing: { from: status.version, to, late: false } });
    const result = await followInstall(status.version, {
      status: () => api.updates(),
      health: async () => {
        const r = await fetch('/api/health', { cache: 'no-store', credentials: 'same-origin' });
        if (!r.ok) throw new Error(String(r.status));
        return (await r.json()) as { version: string };
      },
      sleep: (ms) => new Promise((res) => window.setTimeout(res, ms)),
      now: () => Date.now(),
    });
    if (result.outcome === 'back') {
      window.location.reload();
      return;
    }
    if (result.outcome === 'timeout') {
      set({ installing: { from: status.version, to, late: true } });
      return;
    }
    set({ installing: null, status: result.status ?? snapshot.status });
    if (result.problem) toast(result.problem, 'error');
  },
  /** For tests. */
  reset: () => set({ status: null, installing: null }),
};

export interface FollowDeps {
  status(): Promise<UpdateStatus>;
  health(): Promise<{ version: string }>;
  sleep(ms: number): Promise<void>;
  now(): number;
}

export interface FollowResult {
  /** back: a Closet answers again after restarting (the new one, or the old one put back); stopped: the update
   * stopped before Closet restarted; timeout: nothing answered in time. */
  outcome: 'back' | 'stopped' | 'timeout';
  problem?: string | null;
  status?: UpdateStatus;
}

/** Follows an update: while the old Closet still answers, asks how it is going; once it has gone away and a Closet
 * answers again (or a different version answers), the page can reload. */
export async function followInstall(from: string, deps: FollowDeps, limitMs = 180_000, everyMs = 1000): Promise<FollowResult> {
  const deadline = deps.now() + limitMs;
  let wentAway = false;
  while (deps.now() < deadline) {
    let version: string | null = null;
    try {
      version = (await deps.health()).version;
    } catch {
      wentAway = true;
    }
    if (version !== null && (wentAway || version !== from)) return { outcome: 'back' };
    if (version !== null) {
      try {
        const s = await deps.status();
        if (!s.busy) return { outcome: 'stopped', problem: s.problem || (s.last_install && !s.last_install.ok ? lastInstallLine(s) : null), status: s };
      } catch {
        wentAway = true;
      }
    }
    await deps.sleep(everyMs);
  }
  return { outcome: 'timeout' };
}
