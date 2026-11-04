/**
 * Clean Pro — YouTube request-side compatibility handler
 *
 * Scope:
 * - Only handles youtubei.googleapis.com/youtubei/v1/log_event.
 * - Removes two request headers observed in the upstream request handler:
 *   content-encoding and x-youtube-hot-hash-data.
 * - Does not read, rewrite, upload, or redirect request bodies.
 * - Does not contact any remote Worker or external service.
 *
 * The initplayback Worker-redirection path is intentionally excluded.
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
