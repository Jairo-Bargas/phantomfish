/* Service worker mínimo: habilita "instalar en pantalla de inicio".
   Estrategia RED PRIMERO para /static/: siempre trae la versión nueva; el
   caché solo se usa si no hay internet. Así los cambios de la app llegan
   enseguida, sin quedar pegados a una versión vieja. */
const CACHE = "phantomfish-shell-v3";
const SHELL = ["/static/styles.css", "/static/app.js", "/static/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;
  if (url.pathname === "/static/sw.js") return;
  if (!url.pathname.startsWith("/static/")) return;

  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
