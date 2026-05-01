// VIR GOO PWA service worker — minimal offline cache for shell + assets.
const CACHE = "virgoo-shell-v1";
const SHELL = [
  "/index.html",
  "/about.html",
  "/cabinet.html",
  "/env/css/tailwind.min.css",
  "/env/css/yacy-public.css",
  "/favicon.ico"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => null)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
  ));
  self.clients.claim();
});

// Cache-first for static shell, network-first for everything else.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (SHELL.some((p) => url.pathname === p)) {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
  } else if (url.pathname.startsWith("/yacysearch")) {
    // Search results — bypass cache (always fresh)
    return;
  }
});
