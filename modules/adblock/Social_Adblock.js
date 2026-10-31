/**
 * Targeted Social & Search JSON AdBlock Script for Shadowrocket
 * Targets: X (Twitter) GraphQL & REST Timelines, Instagram Web/GraphQL, Google Search JSON/HTML, and YouTube JSON fallback
 * Repository Path: https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/social_adblock.js
 */
(function () {
  if (typeof $response === "undefined" || !$response || !$response.body) {
    $done({});
    return;
  }

  const url = ($request && $request.url) ? $request.url : "";
  let body = $response.body;

  try {
    // 1. Google Search Web HTML Sponsored Ads Cleanup
    if (url.includes("google.") && url.includes("/search?")) {
      if (typeof body === "string" && (body.includes("id=\"tads\"") || body.includes("id=\"bottomads\"") || body.includes("data-text-ad"))) {
        const styleInject = "<style>#tads,#bottomads,#tvcap,.uEierd,.commercial-unit-desktop-top,.commercial-unit-mobile-top,[data-text-ad]{display:none!important;height:0!important;visibility:hidden!important;}</style></head>";
        body = body.replace("</head>", styleInject);
        $done({ body });
        return;
      }
      $done({});
      return;
    }

    // Parse JSON for X (Twitter), Instagram, or YouTube JSON endpoints
    const obj = JSON.parse(body);

    // 2. X (Twitter) GraphQL & REST 1.1/2 Timeline Promoted Tweet & Upsell Stripping
    if (url.includes("x.com") || url.includes("twitter.com")) {
      const AD_ENTRY_PREFIXES = [
        "promoted-tweet",
        "promotedTweet",
        "promoted-user",
        "who-to-follow",
        "whoToFollow",
        "premium-upsell",
        "cursor-show-more-threads-prompt",
        "message-prompt",
        "relevance-prompt"
      ];

      function isXAdEntry(item) {
        if (!item || typeof item !== "object") return false;
        const entryId = String(item.entryId || item.sortIndex || "");
        if (AD_ENTRY_PREFIXES.some(p => entryId.startsWith(p) || entryId.includes("promoted"))) {
          return true;
        }
        const content = item.content || item.item || {};
        const itemContent = content.itemContent || (content.item && content.item.itemContent) || {};
        if (
          itemContent.promotedMetadata ||
          content.promotedMetadata ||
          item.promotedMetadata ||
          itemContent.itemType === "TimelinePromotedTweet"
        ) {
          return true;
        }
        // Filter embedded array of module items (e.g. conversation thread ads)
        if (Array.isArray(content.items)) {
          content.items = content.items.filter(sub => !isXAdEntry(sub));
        }
        return false;
      }

      function walkX(node) {
        if (!node || typeof node !== "object") return;
        if (Array.isArray(node.instructions)) {
          for (const inst of node.instructions) {
            if (Array.isArray(inst.entries)) {
              inst.entries = inst.entries.filter(e => !isXAdEntry(e));
            }
            if (Array.isArray(inst.addEntries && inst.addEntries.entries)) {
              inst.addEntries.entries = inst.addEntries.entries.filter(e => !isXAdEntry(e));
            }
            if (inst.entry && isXAdEntry(inst.entry)) {
              delete inst.entry;
            }
          }
        }
        if (node.globalObjects && node.globalObjects.tweets) {
          for (const k of Object.keys(node.globalObjects.tweets)) {
            if (node.globalObjects.tweets[k] && node.globalObjects.tweets[k].promotedMetadata) {
              delete node.globalObjects.tweets[k];
            }
          }
        }
        for (const key of Object.keys(node)) {
          const val = node[key];
          if (val && typeof val === "object") {
            walkX(val);
          }
        }
      }

      walkX(obj);
      $done({ body: JSON.stringify(obj) });
      return;
    }

    // 3. Instagram Web / GraphQL Feed, Stories & Reels Ad Stripping
    if (url.includes("instagram.com")) {
      function isIgAd(item) {
        if (!item || typeof item !== "object") return false;
        const m = item.media_or_ad || item.explore_item_info || item.media || item;
        return Boolean(
          item.ad_id ||
          item.ad_action ||
          item.is_sponsored ||
          item.injected ||
          item.ad_link_type ||
          (m && (m.ad_id || m.is_sponsored || m.ad_action || m.injected || m.product_type === "ad" || m.organic_tracking_token === "ad"))
        );
      }

      function walkIg(node) {
        if (!node || typeof node !== "object") return;
        for (const arrKey of ["feed_items", "items", "medias", "reels_media", "tray", "edges", "clips_items"]) {
          if (Array.isArray(node[arrKey])) {
            node[arrKey] = node[arrKey].filter(el => !isIgAd(el && el.node ? el.node : el));
          }
        }
        for (const k of Object.keys(node)) {
          if (node[k] && typeof node[k] === "object") {
            walkIg(node[k]);
          }
        }
      }

      walkIg(obj);
      $done({ body: JSON.stringify(obj) });
      return;
    }

    // 4. YouTube JSON Fallback Stripping
    const YT_AD_KEYS = new Set([
      "adPlacements",
      "adSlots",
      "playerAds",
      "adBreakParams",
      "adBreakHeartbeatParams",
      "mastheadAdRenderer",
      "promotedSparklesWebRenderer",
      "promotedSparklesTextSearchRenderer",
      "compactPromotedVideoRenderer",
      "promotedVideoRenderer",
      "searchPyvRenderer",
      "adSlotRenderer",
      "inFeedAdLayoutRenderer",
      "statementBannerRenderer"
    ]);

    function walkYt(node) {
      if (Array.isArray(node)) {
        return node
          .map(walkYt)
          .filter(el => {
            if (!el || typeof el !== "object") return true;
            for (const k of Object.keys(el)) {
              if (YT_AD_KEYS.has(k)) return false;
            }
            if (
              el.elementRenderer &&
              el.elementRenderer.newElement &&
              JSON.stringify(el.elementRenderer.newElement).includes("_ad_")
            ) {
              return false;
            }
            return true;
          });
      }
      if (node && typeof node === "object") {
        const res = {};
        for (const [k, v] of Object.entries(node)) {
          if (YT_AD_KEYS.has(k)) continue;
          res[k] = walkYt(v);
        }
        return res;
      }
      return node;
    }

    const cleaned = walkYt(obj);
    $done({ body: JSON.stringify(cleaned) });
  } catch (e) {
    $done({});
  }
})();