/**
 * Targeted Social & Search JSON AdBlock Script for Shadowrocket
 * Targets: X (Twitter) GraphQL & REST Timelines, Instagram Web/GraphQL, Google Search JSON/HTML, and YouTube JSON fallback
 * Repository Path: https://raw.githubusercontent.com/instarrys-bit/default/main/modules/adblock/scripts/Social_Adblock.js
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

      function isRtbAdNode(item) {
        if (!item || typeof item !== "object") return false;

        // GraphQL may expose the Kotlin timeline model name directly or through
        // a serialized discriminator. Keep matching exact to avoid deleting
        // ordinary tweets that merely contain advertising-related text.
        const markers = [
          item.__typename,
          item.typename,
          item.itemType,
          item.type,
          item.contentType,
          item.entryType,
          item.entryId,
          item.entry_id
        ];
        for (const marker of markers) {
          if (typeof marker === "string" &&
              (marker === "UrtTimelineRtbImageAd" ||
               marker.includes("UrtTimelineRtbImageAd"))) {
            return true;
          }
        }

        // Some serializers wrap the RTB item under a named property.
        if (Object.prototype.hasOwnProperty.call(item, "UrtTimelineRtbImageAd") ||
            Object.prototype.hasOwnProperty.call(item, "rtbImageAd")) {
          return true;
        }
        return false;
      }

      function isXAdEntry(item) {
        if (!item || typeof item !== "object") return false;
        if (isRtbAdNode(item)) return true;

        const entryId = String(item.entryId || item.sortIndex || "");
        if (AD_ENTRY_PREFIXES.some(p => entryId.startsWith(p) || entryId.includes("promoted"))) {
          return true;
        }
        const content = item.content || item.item || {};
        const itemContent = content.itemContent || (content.item && content.item.itemContent) || {};
        const nestedRtb = [
          item.itemContent,
          item.item && item.item.itemContent,
          item.content && item.content.itemContent,
          item.content && item.content.item && item.content.item.itemContent,
          itemContent
        ];
        if (nestedRtb.some(isRtbAdNode)) return true;
        if (
          itemContent.promotedMetadata ||
          content.promotedMetadata ||
          item.promotedMetadata ||
          itemContent.itemType === "TimelinePromotedTweet"
        ) {
          return true;
        }
        // A module may contain several normal items plus one RTB item. Filter
        // its child list in place; only remove the outer entry if it becomes empty.
        const childArrays = [content.items, item.items, item.items && item.items.items];
        for (const children of childArrays) {
          if (Array.isArray(children)) {
            const before = children.length;
            for (let i = children.length - 1; i >= 0; i--) {
              if (isXAdEntry(children[i])) children.splice(i, 1);
            }
            if (before > 0 && children.length === 0) return true;
          }
        }
        return false;
      }

      // RTB ads can be nested in URT timeline modules rather than exposed as
      // top-level promoted-tweet entries. Recursively remove only nodes carrying
      // the exact RTB discriminator; preserve normal siblings and cursor data.
      function walkX(node) {
        if (!node || typeof node !== "object") return;

        if (Array.isArray(node)) {
          for (let i = node.length - 1; i >= 0; i--) {
            if (isXAdEntry(node[i])) {
              node.splice(i, 1);
            } else {
              walkX(node[i]);
            }
          }
          return;
        }

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
            if (node.globalObjects.tweets[k] &&
                node.globalObjects.tweets[k].promotedMetadata) {
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