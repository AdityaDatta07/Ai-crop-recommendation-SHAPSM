/* eslint-disable no-restricted-globals */

/**
 * Service worker: the thing that makes the offline cache reachable.
 *
 * THE PROBLEM IT SOLVES
 * ---------------------
 * The app already stored the last ten results in localStorage and read them
 * before hitting the network. None of it worked, because reaching that cache
 * meant loading the app, and loading the app meant fetching HTML and JS from a
 * server that was not there. Turn the network off and you got the browser's
 * error page. The cache was correct, and unreachable in exactly the situation
 * it existed for.
 *
 * WRITTEN BY HAND, NOT GENERATED
 * ------------------------------
 * next-pwa and Serwist both work, and both add a build-time dependency to a
 * project that has already lost days to build tooling on Windows. This is
 * ninety lines with no build step, and it can be read in full by whoever
 * maintains it next.
 *
 * STRATEGIES
 * ----------
 *   app shell + fixtures   cache-first, because they only change on deploy
 *   API GETs               network-first, cache as a fallback
 *   API POSTs             not touched: the Cache API cannot store them, and
 *                          the client handles that failure in offline.ts
 *   navigations            network-first, falling back to the cached shell so
 *                          any URL opens offline, including /r/<id>
 */

// Bump this whenever a precached file changes.
//
// v2: renamed to Beej Nirnay. The manifest is precached, so an already-
// installed app would have kept showing "Crop Advisor" under its icon
// indefinitely — the rename would have looked done everywhere except the one
// place a user actually installed it.
const VERSION = 'v2';
const SHELL_CACHE = `crop-shell-${VERSION}`;
const DATA_CACHE = `crop-data-${VERSION}`;

/**
 * Precached at install. Deliberately short: everything else arrives through
 * runtime caching, so a single 404 here cannot fail the whole installation and
 * leave the app with no worker at all.
 */
const PRECACHE = [
  '/',
  '/offline',
  '/manifest.webmanifest',
  // The backdrop is precached rather than left to runtime caching: without it
  // the first offline load is a bare tint, which looks like a broken page
  // rather than a deliberate one. 18 KB is worth that.
  '/img/field-bg-sm.webp',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // addAll is atomic: one bad URL rejects everything. Add individually so
      // a missing icon does not cost us the service worker.
      .then((cache) => Promise.allSettled(PRECACHE.map((url) => cache.add(url))))
      .then(() => self.skipWaiting()),
  );
});

/**
 * Pull every recorded response into the cache, in the background.
 *
 * Runtime caching alone only covers districts the farmer already visited while
 * online. Precaching the full set — 71 files, under a megabyte — means the app
 * can answer for any supported district with the network off, which is both
 * the point of the feature and the first thing anyone testing it will try.
 *
 * Failures are swallowed on purpose: this runs after activation, and a farmer
 * on a metered connection losing signal halfway through should end up with a
 * partially warmed cache, not a broken worker.
 */
async function warmFixtures() {
  try {
    const response = await fetch('/fixtures/index.json');
    if (!response.ok) return;

    const paths = await response.json();
    const cache = await caches.open(SHELL_CACHE);
    // Small batches: 71 parallel requests on a rural connection is a stampede.
    for (let i = 0; i < paths.length; i += 6) {
      await Promise.allSettled(paths.slice(i, i + 6).map((path) => cache.add(path)));
    }
  } catch {
    // No index, no warm cache. Runtime caching still covers what gets visited.
  }
}

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== SHELL_CACHE && key !== DATA_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim())
      .then(() => warmFixtures()),
  );
});

/** Same-origin GETs we are willing to keep. */
function isCacheableAsset(url) {
  return (
    url.origin === self.location.origin &&
    (url.pathname.startsWith('/_next/') ||
      url.pathname.startsWith('/fixtures/') ||
      url.pathname.startsWith('/icons/') ||
      url.pathname.startsWith('/img/') ||
      /\.(css|js|woff2?|png|jpe?g|webp|svg|webmanifest|json)$/.test(url.pathname))
  );
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
  }
  return response;
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // POST and friends are the client's problem, not the cache's.
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Map tiles are somebody else's servers and a large, unbounded set. Left
  // alone on purpose: filling the cache quota with tiles would evict the app.
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    // Any route must open offline, including a shared /r/<id> link. Falling
    // back to the cached root lets the client-side router take it from there,
    // and the result itself comes from localStorage.
    event.respondWith(
      networkFirst(request, SHELL_CACHE).catch(
        async () => (await caches.match('/')) ?? caches.match('/offline'),
      ),
    );
    return;
  }

  if (isCacheableAsset(url)) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, DATA_CACHE));
  }
});
