'use strict';

// This worker deliberately does not cache portal pages, form submissions,
// invoices, damage reports, customer data, PDFs, or any other runtime records.
// It keeps only a small public shell allowlist for installation and an offline
// notice; authenticated portal requests always go to the network.
const APP_CONFIG = {
  protocol: { entry: 'pwa-protokoll.php', manifest: 'manifest-protokoll.webmanifest' },
  invoice: { entry: 'pwa-underlag.php', manifest: 'manifest-underlag.webmanifest' },
  skadeblankett: { entry: 'skadeblankett-kund.php', manifest: 'manifest-skadeblankett.webmanifest' }
};
const requestedApp = new URL(self.location.href).searchParams.get('app') || '';
const scopedApp = Object.prototype.hasOwnProperty.call(APP_CONFIG, requestedApp) ? requestedApp : '';
const scopedConfig = scopedApp ? APP_CONFIG[scopedApp] : null;
const CACHE_PREFIX = scopedApp ? 'tadega-pwa-' + scopedApp + '-shell-' : 'tadega-portal-shell-';
const CACHE_NAME = scopedApp ? CACHE_PREFIX + 'v2' : 'tadega-portal-shell-v3';
const APP_ENTRY_URL = scopedApp ? './' + scopedConfig.entry : './index.php';
const APP_MANIFEST_URL = scopedApp ? './' + scopedConfig.manifest : './manifest.webmanifest';
const SHELL_URLS = [
  new URL('./offline.html', self.registration.scope).href,
  new URL(APP_MANIFEST_URL, self.registration.scope).href,
  new URL(APP_ENTRY_URL + '?view_file=assets/pwa-icon-192.png', self.registration.scope).href,
  new URL(APP_ENTRY_URL + '?view_file=assets/pwa-icon-512.png', self.registration.scope).href,
  ...(scopedApp ? [new URL('./index.php?view_file=assets/pwa-icon-192.png', self.registration.scope).href] : [])
];
const OFFLINE_URL = SHELL_URLS[0];
const SHELL_URL_SET = new Set(SHELL_URLS);
const MAINTENANCE_CACHE_NAME = scopedApp
  ? 'tadega-pwa-' + scopedApp + '-cache-maintenance-v1'
  : 'tadega-portal-cache-maintenance-v1';
const MAINTENANCE_URL = new URL('./__tadega_cache_maintenance__' + (scopedApp ? '-' + scopedApp : '') + '.json', self.registration.scope).href;
const MAINTENANCE_INTERVAL_MS = 24 * 60 * 60 * 1000;
let maintenancePromise = null;

async function readLastMaintenanceAt() {
  try {
    const metadataCache = await caches.open(MAINTENANCE_CACHE_NAME);
    const response = await metadataCache.match(MAINTENANCE_URL);
    if (!response) return 0;
    const data = await response.json();
    const timestamp = Number(data && data.lastRunAt);
    return Number.isFinite(timestamp) && timestamp > 0 && timestamp <= Date.now() ? timestamp : 0;
  } catch (_) {
    return 0;
  }
}

async function recordMaintenanceAt(timestamp) {
  const metadataCache = await caches.open(MAINTENANCE_CACHE_NAME);
  await metadataCache.put(MAINTENANCE_URL, new Response(JSON.stringify({ lastRunAt: timestamp }), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' }
  }));
}

async function removeUnexpectedShellEntries(cache) {
  const requests = await cache.keys();
  await Promise.all(requests
    .filter((request) => !SHELL_URL_SET.has(request.url))
    .map((request) => cache.delete(request)));
}

async function runDailyCacheMaintenance() {
  if (maintenancePromise) return maintenancePromise;

  maintenancePromise = (async () => {
    try {
      const now = Date.now();
      const lastRunAt = await readLastMaintenanceAt();
      if (lastRunAt > 0 && now - lastRunAt < MAINTENANCE_INTERVAL_MS) return;

      // Only touch caches owned by this app. Keep unrelated Cache Storage
      // caches and all server-side records, sessions, drafts, and PDFs intact.
      const cacheNames = await caches.keys();
      await Promise.all(cacheNames
        .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
        .map((name) => caches.delete(name)));

      const shellCache = await caches.open(CACHE_NAME);
      await removeUnexpectedShellEntries(shellCache);

      // Refresh the tiny public allowlist. If a request fails, retain its
      // previous cached copy so the offline notice and app shell still work.
      for (const url of SHELL_URLS) {
        try {
          const response = await fetch(new Request(url, { cache: 'reload', credentials: 'same-origin' }));
          if (response.ok && response.type === 'basic') {
            await shellCache.put(url, response.clone());
          }
        } catch (_) {
          // Keep the previous public shell entry when offline or unavailable.
        }
      }

      // Record the attempt even if offline, preventing a fetch loop on every
      // page load. The next check is eligible after 24 hours.
      await recordMaintenanceAt(now);
    } catch (_) {
      // Cache maintenance must never prevent the online portal from working.
    }
  })().finally(() => {
    maintenancePromise = null;
  });

  return maintenancePromise;
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await removeUnexpectedShellEntries(cache);
    for (const url of SHELL_URLS) {
      try {
        const response = await fetch(new Request(url, { cache: 'reload', credentials: 'same-origin' }));
        if (response.ok && response.type === 'basic') {
          await cache.put(url, response.clone());
        }
      } catch (_) {
        // A failed shell download does not block the online portal from updating.
      }
    }
    try {
      await recordMaintenanceAt(Date.now());
    } catch (_) {
      // Metadata is optional; a later app open can safely try maintenance again.
    }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames
      .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (!event.data || event.data.type !== 'TADEGA_DAILY_CACHE_MAINTENANCE') return;
  event.waitUntil(runDailyCacheMaintenance());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    // Never cache a portal response. When offline, show only a generic notice.
    event.respondWith(fetch(request).catch(async () => {
      return (await caches.match(OFFLINE_URL)) || new Response(
        '<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#07172d"><title>Offline · Tadega Dokumentportalen</title><p>Du är offline. Anslut till internet för att använda Tadega Dokumentportalen.</p></html>',
        { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      );
    }));
    return;
  }

  // Cache only the exact, explicitly public shell resources above. Never use
  // a broad URL/path rule, since PHP query routes can return private records.
  if (!SHELL_URL_SET.has(url.href)) return;

  event.respondWith((async () => {
    const cached = await caches.match(url.href);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok && response.type === 'basic') {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(url.href, response.clone());
    }
    return response;
  })());
});
