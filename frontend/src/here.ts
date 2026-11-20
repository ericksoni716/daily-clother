/** Where the page is open: on the computer Closet runs on, or somewhere else (the phone, through Tailscale). */

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
