/**
 * Shadowrocket YouTube request hostname observer.
 * Sends only the request hostname for initplayback events.
 * Never forwards full URLs, query strings, headers, bodies, client keys or playback data.
 * This is an observation-only replacement; it does not perform Maasea UMP processing.
 */
(() => {
  const INTAKE = "https://sr-domain-intake.inner-archetype.workers.dev/v1/observe";
  const req = (typeof $request !== "undefined" && $request) ? $request : {};
  const rawUrl = String(req.url || "");
  if (!rawUrl.includes("initplayback")) {
    $done({});
    return;
  }

  let hostname = "";
  try {
    hostname = new URL(rawUrl).hostname.toLowerCase();
  } catch (_) {
    $done({});
    return;
  }

  if (!hostname || hostname.length > 253 || !hostname.includes(".")) {
    $done({});
    return;
  }

  const options = {
    url: INTAKE,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domains: [hostname] })
  };

  // Upload is best-effort. The original YouTube request is never redirected or modified.
  try {
    if (typeof $httpClient !== "undefined" && $httpClient && typeof $httpClient.post === "function") {
      $httpClient.post(options, () => $done({}));
    } else if (typeof $task !== "undefined" && $task && typeof $task.fetch === "function") {
      $task.fetch(options).finally(() => $done({}));
    } else {
      $done({});
    }
  } catch (_) {
    $done({});
  }
})();
