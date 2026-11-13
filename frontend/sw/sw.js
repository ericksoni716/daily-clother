/* Closet's service worker (hand-written).
 *
 * - The app's own files are saved at install so the closet opens without the server.
 * - Closet data (items, vocabulary, session) is fetched fresh and saved; when the server
 *   cannot be reached, the saved copy is used and marked with a header so the page can
 *   say "Offline".
 * - Images never change at a given address, so a saved copy is used first.
 * - Nothing but GET is ever saved, and never login/setup/logout.
 */
const VERSION = self.__VERSION__;
const PRECACHE = self.__PRECACHE__;
const SHELL = `closet-shell-${VERSION}`;
const DATA = 'closet-data';
const MEDIA = 'closet-media';
const FROM_CACHE = 'x-closet-from-cache';

self.addEventListener('install', (event) => {
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
const IMMUTABLE_PATHS = [/^\/media\//, /^\/api\/items\/[^/]+\/illustration\.svg$/];

function markFromCache(response) {
  const headers = new Headers(response.headers);
  headers.set(FROM_CACHE, '1');
  return response.blob().then((body) => new Response(body, { status: response.status, statusText: response.statusText, headers }));
}

async function networkFirst(request) {
  const cache = await caches.open(DATA);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (err) {
    const saved = await cache.match(request);
    if (saved) return markFromCache(saved);
    throw err;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(MEDIA);
  const saved = await cache.match(request);
  if (saved) return saved;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function page(request) {
  try {
    const response = await fetch(request);
    return response;
  } catch (err) {
    const shell = await caches.open(SHELL);
    const saved = await shell.match('/');
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
