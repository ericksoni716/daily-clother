/**
 * What the main Settings page says about each part that keeps itself running (Claude, updates, backups), in one
 * line each, and which groups a phone and a computer are shown. Pure, so each case has a test; the page only lays
 * these out. Everything that changes them is on the Advanced screen (`screens/Advanced.tsx`).
 */
import { formatSize } from './labels';
import { whenAt } from './wears';
import { formatUsd } from './spend';
import type { ModelInfo, Profile, Settings, TaggingSpend, TaggingStatus } from './types';
import { availableLine, busyLine, lastInstallLine, type UpdateStatus } from './updates';

/** How a line is drawn: `ok` with a green dot, `problem` in red, `waiting` while a lookup runs, `quiet` plain. */
export type Tone = 'ok' | 'problem' | 'waiting' | 'quiet';

export interface Line {
  tone: Tone;
  text: string;
}

/** Where the page is open: on the computer Nines runs on, or on the phone (anything that is not loopback). */
export type Device = 'computer' | 'phone';

// ------------------------------------------------------------------ Claude

/** The one action the Claude line offers beside "Manage": check again, or install Claude Code (a link, then check). */
export type ClaudeAction = 'check' | 'install' | null;

export interface ClaudeLine extends Line {
  action: ClaudeAction;
}

type ClaudeSettings = Pick<Settings, 'tagging_api_enabled' | 'tagging_api_off' | 'api_key'>;

/**
 * How Nines reaches Claude, in one line: which way it uses now, or, when none works, one red sentence and what to
 * do. The routes are tried in the order the server reports (`tagging.order`); the key counts only once allowed and
 * while the month's limit is not reached.
 */
export function claudeLine(s: ClaudeSettings, spend: Pick<TaggingSpend, 'spent_usd' | 'cap_usd' | 'reached'> | null,
  tagging: TaggingStatus | null, error: string | null, offline: boolean): ClaudeLine {
  if (offline) return { tone: 'quiet', text: "You're offline, so how Nines reaches Claude can't be checked.", action: null };
  if (error) return { tone: 'problem', text: `Nines couldn't check how it reaches Claude: ${error}`, action: 'check' };
  if (!tagging) return { tone: 'waiting', text: 'Checking how Nines reaches Claude…', action: null };

  const byId = new Map(tagging.routes.map((r) => [r.id, r]));
  const planReady = !!byId.get('plan')?.available;
  const keyReady = !!byId.get('api')?.available && s.tagging_api_enabled && !spend?.reached;
  const first = tagging.order.find((id) => (id === 'plan' ? planReady : keyReady));

  if (first === 'plan') {
    const backup = keyReady && tagging.order.indexOf('api') > tagging.order.indexOf('plan');
    return { tone: 'ok', text: backup ? 'Using your Claude plan, with your API key if the plan can\'t be used.' : 'Using your Claude plan.', action: null };
  }
  if (first === 'api') {
    const month = spend?.cap_usd ? `: ${formatUsd(spend.spent_usd)} of ${formatUsd(spend.cap_usd)} this month` : '';
    return { tone: 'ok', text: `Using your API key${month}.`, action: null };
  }
  // nothing works: one sentence, and the one thing that helps
  if (s.tagging_api_off && tagging.order.includes('api')) {
    return {
      tone: 'problem', action: null,
      text: s.tagging_api_off.reason === 'credit'
        ? 'Nines stopped using your API key because your Anthropic account has no credit left.'
        : "Nines stopped using your API key because Anthropic didn't accept it.",
    };
  }
  if (byId.get('api')?.available && s.tagging_api_enabled && spend?.reached) {
    return { tone: 'problem', text: "This month's limit for the API key is reached, and your Claude plan can't be used.", action: null };
  }
  if (!tagging.order.includes('plan')) {
    return { tone: 'problem', text: "Nines can't reach Claude: you chose only the API key, and it isn't allowed yet.", action: null };
  }
  if (s.api_key.set && tagging.order.includes('api') && !s.tagging_api_enabled) {
    return { tone: 'problem', text: "Nines can't reach Claude: your API key is saved but not allowed.", action: null };
  }
  return { tone: 'problem', text: "Nines can't reach Claude yet.", action: 'install' };
}

type LeadSettings = ClaudeSettings & Pick<Settings, 'tagging_route_order'>;

/**
 * The first line of Claude on the Advanced screen: `claudeLine`, but with what is right below it in view. The month's
 * spending is left out (the limit and the spending are shown under the key), and when nothing works the one cause
 * points at the control below that puts it right: allowing the key, saving one, or choosing the plan.
 */
export function claudeLead(s: LeadSettings, spend: Pick<TaggingSpend, 'spent_usd' | 'cap_usd' | 'reached'> | null,
  tagging: TaggingStatus | null, error: string | null, offline: boolean): ClaudeLine {
  const line = claudeLine(s, spend ? { ...spend, cap_usd: null } : null, tagging, error, offline);
  if (line.tone !== 'problem' || error || !tagging) return line;
  const order = tagging.order;
  const keyHere = !!tagging.routes.find((r) => r.id === 'api')?.available;
  if (s.tagging_api_off && order.includes('api')) {
    // the sentence under the key says when, why and what to do
    return { tone: 'problem', text: "Nines can't reach Claude: it stopped using your API key.", action: null };
  }
  if (keyHere && s.tagging_api_enabled && spend?.reached) return line;
  if (!order.includes('plan')) {
    return {
      tone: 'problem', action: null,
      text: s.api_key.set
        ? "Nines can't reach Claude yet: you chose only the API key, and it isn't allowed. Allow it below, or choose your Claude plan."
        : "Nines can't reach Claude yet: you chose only the API key, and none is saved. Save one below, or choose your Claude plan.",
    };
  }
  if (s.api_key.set && order.includes('api') && !s.tagging_api_enabled) {
    return { tone: 'problem', text: "Nines can't reach Claude yet: your API key is saved but not allowed. Allow it below, or use your Claude plan.", action: 'install' };
  }
  return line;
}

/**
 * What the API key part of Advanced shows. With no key, only the box to paste one: the limit, the switch and the order
 * can do nothing yet. The order stays reachable when the saved one needs a key that is no longer there, so it can be
 * changed back.
 */
export function apiKeyShows(s: Pick<Settings, 'api_key' | 'tagging_route_order'>): { spending: boolean; order: boolean } {
  const keyFirst = s.tagging_route_order === 'api-first' || s.tagging_route_order === 'api';
  return { spending: s.api_key.set, order: s.api_key.set || keyFirst };
}

// ------------------------------------------------------------------ Updates

/** What the Updates line offers: Install, a link to download by hand, or nothing. */
export type UpdateAction = 'install' | 'download' | null;

export interface UpdatesLine extends Line {
  action: UpdateAction;
}

/** "Nines 0.4.0 · up to date", "Nines 0.4.1 is ready to install.", a step of an install, or what went wrong. */
export function updatesLine(status: UpdateStatus | null, version: string, offline: boolean): UpdatesLine {
  if (!status) {
    return { tone: 'quiet', text: offline ? `Nines ${version}. Updates can't be checked while you're offline.` : `Nines ${version}`, action: null };
  }
  if (status.busy) return { tone: 'waiting', text: busyLine(status.busy), action: null };
  if (status.problem) return { tone: 'problem', text: status.problem, action: status.available && status.can_install ? 'install' : null };
  if (status.available) {
    return { tone: 'ok', text: availableLine(status), action: status.can_install ? 'install' : 'download' };
  }
  if (status.last_install && !status.last_install.ok) return { tone: 'problem', text: lastInstallLine(status), action: null };
  const here = `Nines ${status.version}`;
  if (status.latest && status.checked_at && (status.can_install || status.latest === status.version)) {
    return { tone: 'ok', text: `${here} · up to date`, action: null };
  }
  if (status.latest && status.checked_at && status.latest !== status.version) {
    return { tone: 'quiet', text: `${here} · the latest is ${status.latest}`, action: null };
  }
  if (status.mode === 'never') return { tone: 'quiet', text: `${here} · not looking for new versions`, action: null };
  return { tone: 'quiet', text: here, action: null };
}

// ------------------------------------------------------------------ Your data

/** What the backup line offers: choosing a folder (on the computer, on the Advanced screen), or nothing. */
export type BackupAction = 'choose' | null;

export interface BackupLine extends Line {
  action: BackupAction;
}

type BackupSettings = Pick<Settings, 'backup_folder' | 'last_backup' | 'last_good_backup'>;

/** The backups in one line: where they go and the last good one, or that there are none yet and how to start. */
export function backupLine(s: BackupSettings, profile: Profile, device: Device): BackupLine {
  if (profile === 'demo') return { tone: 'quiet', text: 'The demo closet is never backed up.', action: null };
  if (!s.backup_folder) {
    return device === 'computer'
      ? { tone: 'problem', text: "Your closet isn't backed up yet.", action: 'choose' }
      : { tone: 'problem', text: "Your closet isn't backed up yet. Choose a backup folder in Settings on your computer.", action: null };
  }
  const last = s.last_backup;
  if (last && !last.ok) {
    return { tone: 'problem', text: `The last backup didn't work (${whenAt(last.at)})${last.error ? `: ${last.error}` : '.'}`, action: null };
  }
  const when = s.last_good_backup ? `last good backup ${whenAt(s.last_good_backup)}` : 'no backup yet';
  return { tone: 'ok', text: `Backed up every day to ${s.backup_folder} · ${when}.`, action: null };
}

// ------------------------------------------------------------------ what each device is shown

/** The main page's groups, in order. */
export type Group = 'style' | 'everyday' | 'claude' | 'updates' | 'phone' | 'device' | 'data' | 'leave';

/**
 * Which groups are shown, in order. Other devices is shown on the computer until a share reaches Nines (after that it is
 * one line there too); on the phone, in Safari, to say how to add Nines to the Home Screen, and, as an app, only when
 * it has something to say (`phoneLine`: whether the computer keeps Nines running).
 */
export function mainGroups(phoneShows: 'connect' | 'add-to-home-screen' | 'nothing', phoneLine = false): Group[] {
  const groups: Group[] = ['style', 'everyday', 'claude', 'updates'];
  if (phoneShows !== 'nothing' || phoneLine) groups.push('phone');
  groups.push('device', 'data', 'leave');
  return groups;
}

/**
 * What only makes sense on the computer Nines runs on, and so is not offered on the phone: Quit, start at login,
 * a typed folder path, the model's files to put in place by hand, the data folder, and the door through Cloudflare
 * (its connector is installed on the computer, so that is where it is set up; the server refuses a change to it from a
 * device that came in through Cloudflare whatever the page shows).
 */
export interface ComputerOnly {
  quit: boolean;
  autostart: boolean;
  backupFolder: boolean;
  modelFiles: boolean;
  dataFolder: boolean;
  cloudflare: boolean;
}

export function computerOnly(device: Device): ComputerOnly {
  const on = device === 'computer';
  return { quit: on, autostart: on, backupFolder: on, modelFiles: on, dataFolder: on, cloudflare: on };
}

/** "Nines uses 2.7 MB for 49 items · 62 GB free", from the storage lookup. */
export function storageLine(total: string, items: number, free: string | null): string {
  return `Nines uses ${total} for ${items === 1 ? '1 item' : `${items.toLocaleString('en-US')} items`}${free ? ` · ${free} free on this disk` : ''}.`;
}

// ------------------------------------------------------------------ background removal

/** What a model's line offers: start its download, or try it again; one call starts whichever is not ready. */
export type ModelAction = 'download' | 'retry' | null;

export interface ModelLine extends Line {
  id: 'main' | 'second';
  action: ModelAction;
  /** The button's name for a screen reader, which hears both lines' buttons apart. */
  actionLabel: string | null;
}

const MODEL_ROLE = {
  main: 'The first set of files cuts the clothes out of every photo.',
  second: 'The second set is asked as well, for stripes and checks.',
} as const;

const MODEL_NAME = { main: 'the first set', second: 'the second set' } as const;

/**
 * The two background-removal models, one line each (Advanced → Background removal): what each is for and how it
 * stands, worded as the notice on Add words it. The second line is left out when the server has no second model.
 */
export function modelLines(model: ModelInfo): ModelLine[] {
  const lines: ModelLine[] = [modelLine('main', model)];
  if (model.second) lines.push(modelLine('second', model.second));
  return lines;
}

export interface ModelAddress {
  id: 'main' | 'second';
  /** The box's name: "Address for the first set". */
  label: string;
  url: string;
  /** Where the file goes when it is put in place by hand: on the computer only, else null. */
  path: string | null;
}

/**
 * The fold under the two lines (Advanced → Background removal, "If a download keeps failing"): one sentence, then each
 * set's address and, on the computer, where its file goes. The same for both sets; only the first when the server has
 * no second.
 */
export function modelAddresses(model: ModelInfo, filesHere: boolean): { intro: string; sets: ModelAddress[] } {
  const sets = [['main', model] as const, ...(model.second ? [['second', model.second] as const] : [])].map(([id, m]) => ({
    id, label: `Address for ${MODEL_NAME[id]}`, url: m.url, path: filesHere ? m.path : null,
  }));
  const intro = filesHere
    ? 'Each set is downloaded from the address in its box; you can type another address, or download the file yourself and put it where it is shown.'
    : 'Each set is downloaded from the address in its box, and you can type another address.';
  return { intro, sets };
}

function modelLine(id: 'main' | 'second', m: ModelInfo): ModelLine {
  const role = MODEL_ROLE[id];
  const name = MODEL_NAME[id];
  if (m.state === 'ready') return { id, tone: 'ok', text: `${role} It is ready.`, action: null, actionLabel: null };
  if (m.state === 'downloading') {
    const far = m.total_bytes ? `: ${formatSize(m.downloaded_bytes)} of ${formatSize(m.total_bytes)}`
      : m.downloaded_bytes > 0 ? `: ${formatSize(m.downloaded_bytes)} so far` : '';
    return { id, tone: 'waiting', text: `${role} It is downloading${far}.`, action: null, actionLabel: null };
  }
  if (m.state === 'failed') {
    return { id, tone: 'problem', text: `${role} It didn't download.${m.error ? ` ${m.error}` : ''}`, action: 'retry',
      actionLabel: `Try downloading ${name} again` };
  }
  return { id, tone: 'quiet', text: `${role} It isn't downloaded yet.`, action: 'download', actionLabel: `Download ${name}` };
}
