const CACHE = 'scryops-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e =>
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
);

self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  if (request.mode === 'navigate') {
    // Network-first for navigations: always get fresh HTML
    e.respondWith(
      fetch(request).catch(() => caches.match(request))
    );
  } else if (
    url.pathname.match(/\.(css|js|woff2?|png|jpg|svg|ico)$/)
  ) {
    // Cache-first for fingerprinted static assets
    e.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(request, clone));
          }
          return res;
        });
      })
    );
  }
});
