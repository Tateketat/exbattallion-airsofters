const CACHE_NAME = "exbattallion-cache-v1";
const urlsToCache = [
  "/",
  "/static/images/logo-192.png",
  "/static/images/logo-512.png",
  "/static/offline.html"
  // Add more assets if needed
];

// Cache assets on install
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

// Intercept fetches (offline fallback)
self.addEventListener("fetch", event => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request).then(response => {
        // Fallback to offline.html for navigation requests
        if (response) return response;
        if (event.request.mode === "navigate" || event.request.destination === "document") {
          return caches.match("/static/offline.html");
        }
      });
    })
  );
});

// Optional: Clean up old caches (best practice)
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME)
            .map(key => caches.delete(key))
      )
    )
  );
});