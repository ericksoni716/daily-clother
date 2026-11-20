/** Where the page is open: on the computer Closet runs on, or somewhere else (the phone, through Tailscale or Cloudflare). */
import type { CameIn } from './types';

/** Closet listens on this computer only, so the page is open on the computer exactly when its address is loopback. */
export function onThisComputer(hostname: string): boolean {
  return ['127.0.0.1', 'localhost', '[::1]', '::1'].includes(hostname.toLowerCase());
}

/** Whether the page runs as an app from the Home Screen rather than in a browser tab. */
export function fromHomeScreen(win: Pick<Window, 'matchMedia'> & { navigator: Navigator & { standalone?: boolean } }): boolean {
  return win.navigator.standalone === true || win.matchMedia('(display-mode: standalone)').matches;
}

/**
 * What Settings offers about the phone. On the computer: how to connect it (the code, the address, the commands).
 * On the phone in Safari: one line on keeping Closet on the Home Screen. On the phone as an app: nothing.
 */
export function phoneAccessShows(hostname: string, homeScreen: boolean): 'connect' | 'add-to-home-screen' | 'nothing' {
  if (onThisComputer(hostname)) return 'connect';
  return homeScreen ? 'nothing' : 'add-to-home-screen';
}

export const ADD_TO_HOME_SCREEN = 'To open Nines like an app, tap Share in Safari and then Add to Home Screen.';

/** The computer Closet runs on, or the phone: what Settings offers depends on it (see `computerOnly` in settingsLines.ts). */
export function deviceOf(hostname: string): 'computer' | 'phone' {
  return onThisComputer(hostname) ? 'computer' : 'phone';
}

/**
 * Whether the page was opened at the Cloudflare address. The server answers only at this computer's own names, at a
 * Tailscale name (`….ts.net`) and at the Cloudflare address set in Settings (backend/closet/gate.py), so any other
 * name the page is open at is that one. Decided from the address alone, so it still holds when Cloudflare's sign-in
 * has run out and the server cannot be asked.
 */
export function throughCloudflare(hostname: string): boolean {
  const name = hostname.toLowerCase().replace(/\.$/, '');
  return !onThisComputer(name) && !name.endsWith('.ts.net');
}

/** "Sam Owner (owner@example.com)", or the login alone when the name says nothing more. */
function who(cameIn: CameIn): string {
  const { login, name } = cameIn;
  return name && name !== login ? `${name} (${login})` : login ?? '';
}

/**
 * The one sentence Settings shows, under This device, about how a device that came in from outside did: through
 * Tailscale (as whom, or that Tailscale did not say), or through Cloudflare's sign-in (as which email). Nothing on the
 * computer itself.
 */
export function cameInLine(cameIn: CameIn | undefined): string | null {
  if (!cameIn || cameIn.via === 'computer') return null;
  if (cameIn.via === 'cloudflare') {
    return cameIn.login ? `This device came in through Cloudflare, signed in as ${who(cameIn)}.` : 'This device came in through Cloudflare.';
  }
  return cameIn.login
    ? `This device came in through Tailscale as ${who(cameIn)}.`
    : 'This device came in through Tailscale, but Tailscale did not say who is using it.';
}
