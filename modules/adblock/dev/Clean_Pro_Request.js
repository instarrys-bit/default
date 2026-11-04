/**
 * Clean Pro — YouTube request-side compatibility handler (development)
 *
 * This is a locally authored, minimal adaptation of the request-header
 * behavior observed in Maasea/sgmodule's youtube.request.js.
 *
 * Scope:
 * - Only handles youtubei.googleapis.com/youtubei/v1/log_event.
 * - Removes request headers that the upstream handler strips:
 *   content-encoding and x-youtube-hot-hash-data.
 * - Does not read, rewrite, upload, or redirect request bodies.
 * - Does not contact any remote Worker or external service.
 *
 * Deliberately excluded:
 * - initplayback encrypted-key caching and Worker redirection. That path
 *   depends on Maasea's remote Worker and changes playback request flow.
 *
 * Development-only: validate with real Shadowrocket request logs before
 * considering production activation.
 */
(() => {
  "use strict";

  const request = typeof $request !== "undefined" ? $request : null;
  if (!request || !request.headers || typeof $done !== "function") {
    if (typeof $done === "function") $done({});
    return;
  }

  const headers = { ...request.headers };
  let changed = false;

  for (const key of Object.keys(headers)) {
    const normalized = key.toLowerCase();
    if (
      normalized === "content-encoding" ||
      normalized === "x-youtube-hot-hash-data"
    ) {
      delete headers[key];
      changed = true;
    }
  }

  $done(changed ? { headers } : {});
})();
