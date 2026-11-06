/**
 * Shadowrocket YouTube request hostname observer (local-only).
 *
 * Captures only the hostname of YouTube initplayback requests.
 * Stores a bounded, de-duplicated list in Shadowrocket persistent storage.
 *
 * Privacy:
 * - No network requests or third-party Worker dependencies.
 * - Does not store full URLs, query strings, headers, request bodies,
 *   client identifiers, or playback data.
 * - Does not modify the original request.
 *
 * Storage key: sr_youtube_observed_hosts_v1
 * Maximum retained hosts: 100
 */
(function () {
  const STORAGE_KEY = "sr_youtube_observed_hosts_v1";
  const MAX_HOSTS = 100;

  try {
    const request = (typeof $request !== "undefined" && $request) ? $request : null;
    const rawUrl = request && request.url ? String(request.url) : "";

    if (!rawUrl || !/initplayback/i.test(rawUrl)) {
      $done({});
      return;
    }

    // Extract hostname only; never persist the URL or its query string.
    const match = rawUrl.match(/^https?:\/\/([^\/?#:]+)(?::\d+)?(?:[\/?#]|$)/i);
    if (!match || !match[1]) {
      $done({});
      return;
    }

    const hostname = match[1].toLowerCase().replace(/\.$/, "");
    if (
      hostname.length > 253 ||
      !/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i.test(hostname)
    ) {
      $done({});
      return;
    }

    if (
      typeof $persistentStore !== "undefined" &&
      $persistentStore &&
      typeof $persistentStore.read === "function" &&
      typeof $persistentStore.write === "function"
    ) {
      let hosts = [];
      try {
        const saved = $persistentStore.read(STORAGE_KEY);
        const parsed = saved ? JSON.parse(saved) : [];
        if (Array.isArray(parsed)) {
          hosts = parsed.filter(
            value => typeof value === "string" && value.length <= 253
          );
        }
      } catch (_) {
        hosts = [];
      }

      hosts = [hostname].concat(hosts.filter(value => value !== hostname));
      hosts = hosts.slice(0, MAX_HOSTS);
      $persistentStore.write(JSON.stringify(hosts), STORAGE_KEY);
    }
  } catch (_) {
    // Observation must never interfere with the original request.
  }

  $done({});
})();
