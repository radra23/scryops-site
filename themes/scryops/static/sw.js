/* scryops service worker — offline resilience.
 *
 * Strategy (freshness vs. availability for a docs site):
 *   - Page navigations: network-first. You get the latest article when online;
 *     any page you've visited stays readable offline; unseen pages fall back to
 *     the offline notice.
 *   - Static assets (CSS/JS/fonts/images): cache-first. Safe because Hugo
 *     fingerprints them — the URL changes when the file changes, so a cached
 *     copy is immutable. Bumping VERSION garbage-collects old caches on activate.
 *
 * To force all clients onto a fresh cache after a structural change, bump VERSION.
 */
const VERSION = 'scryops-v2';   /* bumped for the Telemetry dark-default redesign — forces returning clients off the old cached assets */
const STATIC_CACHE = VERSION + '-static';
const PAGE_CACHE = VERSION + '-pages';
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(function (cache) { return cache.add(OFFLINE_URL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(keys.map(function (key) {
          if (key.indexOf(VERSION) !== 0) { return caches.delete(key); }
        }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') { return; }

  var url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; } // never touch cross-origin

  // Page navigations: network-first, then cache, then offline notice.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          var copy = response.clone();
          caches.open(PAGE_CACHE).then(function (c) { c.put(request, copy); });
          return response;
        })
        .catch(function () {
          return caches.match(request).then(function (cached) {
            return cached || caches.match(OFFLINE_URL);
          });
        })
    );
    return;
  }

  // Static assets: cache-first, populate on miss.
  event.respondWith(
    caches.match(request).then(function (cached) {
      return cached || fetch(request).then(function (response) {
        var copy = response.clone();
        caches.open(STATIC_CACHE).then(function (c) { c.put(request, copy); });
        return response;
      });
    })
  );
});
