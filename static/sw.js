const CACHE_NAME = 'finsaathi-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return new Response(
        '<html><body style="background:#080810;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column"><h2>You are offline</h2><p style="color:#888">Reconnect to continue using FinSaathi</p></body></html>',
        { headers: { 'Content-Type': 'text/html' } }
      );
    })
  );
});
