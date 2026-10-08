// Both fetches go to "localhost", a host other than the page's 127.0.0.1:
// either one reaching the scanner's listener would come out as external.
const elsewhere = path => `http://localhost:${self.location.port}${path}`;

self.addEventListener('install', event => {
  self.skipWaiting();
  // A failed fetch here fails the install, and the page is never controlled.
  event.waitUntil(fetch(elsewhere('/beacon?install'), {mode: 'no-cors'}));
});

self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', event => {
  if (new URL(event.request.url).pathname.endsWith('/through-sw')) {
    event.respondWith(
      fetch(elsewhere('/beacon?respond'), {mode: 'no-cors'})
        .then(r => new Response(`answered by the service worker (${r.type})`))
    );
  }
});
