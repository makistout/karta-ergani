'use strict';
const CACHE = 'erganios-scanner-v6';
const ASSETS = ['/static/img/erganios-logo.png', '/scanner/', '/static/scanner/scanner.css', '/static/scanner/scanner.js', '/static/scanner/jsQR.js', '/static/scanner/icon-192.png?v=2', '/static/scanner/icon-512.png?v=2', '/static/scanner/apple-touch-icon.png?v=2', '/static/scanner/icon-maskable-512.png?v=2', '/static/scanner/manifest.webmanifest'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('erganios-scanner-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !ASSETS.some(asset => new URL(asset, self.location.origin).pathname === url.pathname)) return;
  // API responses, credentials and employee history are never cached.
  event.respondWith(fetch(event.request).then(async response => {
    if (response.ok) { const cache = await caches.open(CACHE); await cache.put(event.request, response.clone()); }
    return response;
  }).catch(() => caches.match(event.request)));
});
