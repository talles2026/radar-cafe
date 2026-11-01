// Radar de Preços mudou para talles2026.github.io/radar-precos: este serviço se desliga sozinho.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.registration.unregister()));
