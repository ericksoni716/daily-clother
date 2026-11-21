/**
 * Windows keeping Nines running (backend/closet/background.py), as Settings shows it under Phone: on the computer a
 * card with what it is, whether it is on, how it starts, whether it runs now, the port, and the buttons; on the phone
 * one sentence. Nothing on a Mac or when run from source, where it is not available. Words and decisions only.
 */
import type { Line } from './settingsLines';
import type { BackgroundState } from './types';

/** What the card is doing after a button: waiting for Windows' question, or handing over to the background copy. */
export type KeepBusy = 'turning-on' | 'handing-over' | 'turning-off' | null;

export const KEEP_TITLE = 'Keep Nines running';

export const KEEP_ABOUT =
  'Windows can start Nines when this computer turns on and start it again if it stops, so your phone can reach it ' +
  'whenever the computer is awake. It takes the place of Start Nines when I log in. Windows asks for permission on ' +
  'this screen once, in what it calls a scheduled task.';

/** Whether the card is shown at all: on Windows, in the downloaded program. */
export function keepShows(state: BackgroundState | undefined): boolean {
  return state?.available === true;
}

function starts(state: BackgroundState): string {
  return state.starts === 'startup' ? 'when this computer turns on' : 'when you sign in to this computer';
}

/** The card's one status line. */
export function keepLine(state: BackgroundState, busy: KeepBusy): Line {
  if (busy === 'turning-on') return { tone: 'waiting', text: 'Windows is asking for permission on this screen.' };
  if (busy === 'handing-over') {
    return { tone: 'waiting', text: 'Windows keeps Nines running now. This window closes and opens again in a moment.' };
  }
  if (busy === 'turning-off' && !state.problem) {
    return { tone: 'waiting', text: 'Windows is asking for permission on this screen. Nines opens again once it is off.' };
  }
  if (state.problem) return { tone: 'problem', text: state.problem };
  if (!state.on) return { tone: 'quiet', text: 'This is off, so your phone reaches Nines only while it is open on this computer.' };
  if (state.running) return { tone: 'ok', text: `Nines starts ${starts(state)}, and it is running now.` };
  return { tone: 'problem', text: `Nines is set to start ${starts(state)}, but it is not running in the background now.` };
}

/** Where Nines answers, which phone access (Tailscale, Cloudflare) must point at; and that it stays there once on. */
export function portLine(state: BackgroundState): string {
  const here = `Nines answers on port ${state.port} on this computer.`;
  return state.on
    ? `${here} While Windows keeps it running, the port does not change, so Tailscale and Cloudflare stay pointed at it.`
    : here;
}

/** The buttons the card offers, in order. */
export type KeepAction = 'on' | 'restart' | 'off';

export function keepActions(state: BackgroundState, busy: KeepBusy): KeepAction[] {
  if (busy) return [];
  if (!state.on) return ['on'];
  return state.running ? ['off'] : ['restart', 'off'];
}

export const ACTION_LABEL: Record<KeepAction, string> = { on: 'Keep Nines running', restart: 'Start it again', off: 'Turn this off' };

/** On the phone: one sentence, and that it is changed on the computer. */
export function keepPhoneLine(state: BackgroundState | undefined): string | null {
  if (!keepShows(state)) return null;
  return state!.on
    ? 'Your computer keeps Nines running, so your phone can reach it whenever the computer is awake. You change this in Settings on the computer.'
    : 'Nines runs on your computer only while it is open there. You can have Windows keep it running in Settings on the computer.';
}

/** While turning off from the window: ask again every two seconds, until it is off or Windows' answer is in. */
export function keepPoll(state: BackgroundState | undefined, busy: KeepBusy): number | false {
  if (busy !== 'turning-off' || !state) return false;
  return state.on && !state.problem ? 2000 : false;
}
