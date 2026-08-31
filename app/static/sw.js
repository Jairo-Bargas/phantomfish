/* Service worker mínimo: habilita "instalar en pantalla de inicio".
   No cachea respuestas de datos para no mostrar información desactualizada. */
const CACHE = "phantomfish-shell-v1";
const SHELL = ["/static/styles.css", "/static/app.js", "/static/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
  }
});
