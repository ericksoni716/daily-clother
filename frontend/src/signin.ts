/**
 * When Cloudflare's sign-in runs out on a device that came in through Cloudflare.
 *
 * What happens then (assumed from how Cloudflare Access and browsers behave; it cannot be tried here): Cloudflare
 * answers every request whose sign-in has run out with a redirect to its own sign-in page, on the team's address
 * (`….cloudflareaccess.com`). A `fetch` from the page follows it to that other address, which does not let the page
 * read it, so the fetch fails exactly as it does when the computer cannot be reached. The page's calls (`api.ts`) then
 * say Closet is offline, and the service worker answers the closet's lists from its saved copy, so the page looks as if
 * the computer were off, and stays that way: nothing ever loads the whole page again for Cloudflare to ask for its code.
 *
 * So, on the Cloudflare address only (`throughCloudflare`), each time the page goes offline it asks the health check
 * once more with `redirect: 'manual'`, which the service worker leaves alone. A redirect there (an "opaque redirect":
 * Closet itself never redirects that call) or a 401 (Closet's own answer when Cloudflare's sign-in is missing) means the
 * sign-in ran out, not the computer: the page is loaded again in full, at its own address with `?signin=` added, which
 * the service worker always fetches rather than answering from its saved copy (`sw/sw.js`), so Cloudflare's redirect
 * reaches the browser and asks for the code. After signing in, Cloudflare brings the browser back to that address,
 * and `?signin=` is taken out of it again. A real loss of network makes the health check fail too, and nothing happens.
 *
 * It never loops: a full load is tried at most once every two minutes (kept in this browser's storage; without
 * storage it is not tried at all). On this computer and through Tailscale none of this runs.
 */
import { connection } from './api';
import { throughCloudflare } from './here';

export const SIGNIN_PARAM = 'signin';
export const RELOAD_GAP_MS = 2 * 60_000;
export const LAST_RELOAD_KEY = 'closet-signin-reload';

type Answer = Pick<Response, 'type' | 'status'>;

/** Whether the health check's answer says Cloudflare's sign-in has run out. `null`: it could not be reached at all. */
export function signInRanOut(answer: Answer | null): boolean {
  return !!answer && (answer.type === 'opaqueredirect' || answer.status === 401);
}

/** Whether a full load may be tried now, given when one was last tried (null: never, or not known). */
export function mayReload(now: number, last: number | null): boolean {
  return last === null || !Number.isFinite(last) || last > now || now - last >= RELOAD_GAP_MS;
}

/** The page's own address with `?signin=` added, for the full load. */
export function signInAddress(href: string, now: number): string {
  const url = new URL(href);
  url.searchParams.set(SIGNIN_PARAM, String(now));
  return url.toString();
}

/** The address without `?signin=`, or null when it has none. */
export function withoutSignIn(href: string): string | null {
  const url = new URL(href);
  if (!url.searchParams.has(SIGNIN_PARAM)) return null;
  url.searchParams.delete(SIGNIN_PARAM);
  return `${url.pathname}${url.search}${url.hash}`;
}

export interface Page {
  hostname: string;
  href: string;
  fetch(input: string, init: RequestInit): Promise<Answer>;
  storage: Pick<Storage, 'getItem' | 'setItem'> | null;
  go(address: string): void;
  now(): number;
}

/** Looks, and loads the page again in full when Cloudflare's sign-in ran out. True when it did. */
export async function recoverSignIn(page: Page): Promise<boolean> {
  if (!throughCloudflare(page.hostname)) return false;
  let answer: Answer | null;
  try {
    answer = await page.fetch('/api/health', { redirect: 'manual', cache: 'no-store', credentials: 'same-origin' });
  } catch {
    answer = null;   // the network itself is gone: offline as it says
  }
  if (!signInRanOut(answer) || !page.storage) return false;
  const now = page.now();
  try {
    const kept = page.storage.getItem(LAST_RELOAD_KEY);
    if (!mayReload(now, kept === null ? null : Number(kept))) return false;
    page.storage.setItem(LAST_RELOAD_KEY, String(now));
  } catch {
    return false;   // without a note of the last try, a loop could not be ruled out
  }
  page.go(signInAddress(page.href, now));
  return true;
}

function storage(win: Window): Storage | null {
  try {
    return win.localStorage;
  } catch {
    return null;
  }
}

/** Started once with the page: takes `?signin=` out of the address, and looks each time the page goes offline. */
export function watchSignIn(win: Window = window): void {
  const clean = withoutSignIn(win.location.href);
  if (clean !== null) win.history.replaceState(win.history.state, '', clean);
  if (!throughCloudflare(win.location.hostname)) return;
  let looking = false;
  connection.subscribe((offline) => {
    if (!offline || looking) return;
    looking = true;
    void recoverSignIn({
      hostname: win.location.hostname,
      href: win.location.href,
      fetch: (input, init) => win.fetch(input, init),
      storage: storage(win),
      go: (address) => win.location.assign(address),
      now: () => Date.now(),
    }).finally(() => { looking = false; });
  });
}
