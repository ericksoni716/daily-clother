/* Nines' service worker (hand-written).
 *
 * - The app's own files are saved at install so the closet opens without the server.
 * - Nines' data (items, vocabulary, which closet is open) is fetched fresh and saved; when the server
 *   cannot be reached, the saved copy is used and marked with a header so the page can
 *   say "Offline".
 * - Images never change at a given address, so a saved copy is used first.
 * - Nothing but GET is ever saved.
 * - A page loaded with `?signin=` (after Cloudflare's sign-in ran out) always waits for the network.
 * - Saves (anything but GET) go straight to the server without passing through here, where the
 *   browser supports it: one sent as the page is reloaded or closed was otherwise sometimes lost.
 */
const VERSION = self.__VERSION__;
const PRECACHE = self.__PRECACHE__;
const SHELL = `closet-shell-${VERSION}`;
const DATA = 'closet-data';
const MEDIA = 'closet-media';
const FROM_CACHE = 'x-closet-from-cache';

const SAVE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE'];

/** Sends saves to the network without waking this worker (static routing; skipped where unsupported). */
function routeSavesPast(event) {
  if (typeof event.addRoutes !== 'function') return Promise.resolve();
  return event.addRoutes(SAVE_METHODS.map((requestMethod) => ({ condition: { requestMethod }, source: 'network' })))
    .catch(() => undefined);
}

self.addEventListener('install', (event) => {
  event.waitUntil(routeSavesPast(event));
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(PRECACHE.map((url) => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n.startsWith('closet-shell-') && n !== SHELL).map((n) => caches.delete(n)),
      ))
      .then(() => self.clients.claim()),
  );
});

const DATA_PATHS = [/^\/api\/items$/, /^\/api\/items\/[^/]+$/, /^\/api\/vocab$/, /^\/api\/session$/];
const IMMUTABLE_PATHS = [/^\/media\//, /^\/api\/items\/[^/]+\/(?:illustration|back)\.svg$/];

// How long to wait for Nines before answering from the saved copy, when there is one. A computer that is asleep or
// switched off may never answer, and the system can take a minute or more to give up on it.
const PAGE_WAIT_MS = 4000;
const DATA_WAIT_MS = 6000;

/** The network's answer, or `fallback` once `ms` have passed without one (the network answer still lands later). */
function withinOr(pending, ms, fallback) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => fallback().then(resolve, reject), ms);
    pending.then((r) => { clearTimeout(timer); resolve(r); }, (err) => { clearTimeout(timer); reject(err); });
  });
}

function markFromCache(response) {
  const headers = new Headers(response.headers);
  headers.set(FROM_CACHE, '1');
  return response.blob().then((body) => new Response(body, { status: response.status, statusText: response.statusText, headers }));
}

async function networkFirst(request) {
  const cache = await caches.open(DATA);
  const saved = await cache.match(request);
  const fresh = fetch(request).then(async (response) => {
    if (response.ok) await cache.put(request, response.clone());
    return response;
  });
  try {
    return saved ? await withinOr(fresh, DATA_WAIT_MS, () => markFromCache(saved.clone())) : await fresh;
  } catch (err) {
    if (saved) return markFromCache(saved);
    throw err;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(MEDIA);
  const saved = await cache.match(request);
  if (saved) return saved;
  const response = await fetch(request);
  if (response.ok && !/\bno-store\b/i.test(response.headers.get('Cache-Control') ?? '')) await cache.put(request, response.clone());
  return response;
}

// The page loaded again after Cloudflare's sign-in ran out (src/signin.ts) carries this: the network's answer is always
// waited for, so Cloudflare's redirect to its sign-in reaches the browser; the saved page only if the network fails.
const SIGNIN_PARAM = 'signin';

async function page(request) {
  const shell = await caches.open(SHELL);
  const saved = await shell.match('/');
  if (new URL(request.url).searchParams.has(SIGNIN_PARAM)) {
    try {
      return await fetch(request);
    } catch (err) {
      if (saved) return saved;
      throw err;
    }
  }
  try {
    return saved ? await withinOr(fetch(request), PAGE_WAIT_MS, async () => saved.clone()) : await fetch(request);
  } catch (err) {
    if (saved) return saved;
    throw err;
  }
}

async function shellFile(request) {
  const shell = await caches.open(SHELL);
  const saved = await shell.match(request, { ignoreSearch: true });
  if (saved) return saved;
  return fetch(request);
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname;

  if (request.mode === 'navigate') {
    event.respondWith(page(request));
  } else if (IMMUTABLE_PATHS.some((re) => re.test(path))) {
    event.respondWith(cacheFirst(request));
  } else if (DATA_PATHS.some((re) => re.test(path))) {
    event.respondWith(networkFirst(request));
  } else if (path.startsWith('/api/')) {
    // everything else under /api (settings, model, …) is never saved
  } else if (PRECACHE.includes(path)) {
    event.respondWith(shellFile(request));
  }
});

self.addEventListener('message', (event) => {
  if (event.data === 'clear-data') {
    event.waitUntil(Promise.all([caches.delete(DATA), caches.delete(MEDIA)]));
  }
});
