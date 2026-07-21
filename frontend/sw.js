// Service Worker intentionally removed — all data served from DB only.
// No caching. This file exists only to unregister previous SW.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
self.addEventListener('fetch', (event) => event.respondWith(fetch(event.request)));