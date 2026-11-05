/**
 * Clean Pro — Shadowrocket response filtering and enhancement engine
 *
 * Unified Dual-Mode Architecture:
 * [Mode A - Binary Wire-Stream Engine] -> YouTube / YouTube Music App (Protobuf)
 *   1. Bounded Protobuf Tag & Varint Codec (lossless on massive field numbers like 465160965)
 *   2. Zero-Copy Subarray Passthrough (ultra-low memory footprint for iOS 15MB NE limit)
 *   3. Onesie Encryption Downgrade (/config & /log_event key stripping)
 *   4. Video Player Ad Removal (adPlacements, adSlots, pagead conversion ping)
 *   5. Native Picture-in-Picture (PiP) & Background Playback Unlock
 *   6. Auto-Translated Caption Track & Language List Injection
 *   7. Feed / Search / Next / Shorts Ad & Promoted EML Stripping
 *   8. Navigation Bar Cleanup & Premium Background Setting Injection
 *
 * [Mode B - Fast-Path JSON & HTML Engine] -> X (Twitter), Instagram, Google Search, YouTube Web JSON
 *   1. 0.1ms Pre-Parse Keyword Fast-Path (skips JSON.parse if no ad markers exist)
 *   2. Dirty-Flag Mutation Tracking (skips JSON.stringify if no ads were removed)
 *   3. X (Twitter): GraphQL & REST promoted tweets, trends, who-to-follow, upsells, & empty module pruning
 *   4. Instagram: GraphQL (xdt_*) & REST timeline, Reels, Stories, and Explore sponsored post stripping
 *   5. Google Search Web: Case-insensitive CSS injection + shopping/sponsored container hiding
 *   6. YouTube Web JSON Fallback: In-place mutation stripping adPlacements/adSlots/sparkles
 */

(() => {
  "use strict";

  const CACHE_KEY = "SR_AIO_PRO_CACHE_V2";
  const CACHE_VER = "2.1";

  const DEFAULT_OPTS = {
    captionLang: "zh-Hans", // Set "off" to disable auto-translated captions
    blockUpload: true,
    blockImmersive: true,
    blockShortsTab: false,
    blockShortsFeed: true
  };

  // Protobuf Wire Types
  const WT_VARINT = 0;
  const WT_64 = 1;
  const WT_LEN = 2;
  const WT_SGROUP = 3;
  const WT_EGROUP = 4;
  const WT_32 = 5;

  // Binary signature for "pagead" -> [112, 97, 103, 101, 97, 100]
  const PATTERN_PAGEAD = new Uint8Array([112, 97, 103, 101, 97, 100]);

  const INITIAL_BLACK_EML = [
    "inline_injection_entrypoint_layout.eml",
    "full_width_square_image_layout.eml",
    "landscape_image_wide_button_layout.eml",
    "text_image_button_group_layout.eml",
    "statement_banner.eml"
  ];

  const TRANSLATION_LANGS = {
    "zh-Hans": "中文（简体）",
    "zh-Hant": "中文（繁體）",
    en: "English",
    ja: "日本語",
    ko: "한국어",
    fr: "Français",
    de: "Deutsch",
    es: "Español",
    ru: "Русский",
    vi: "Tiếng Việt"
  };

  const utf8Decoder = typeof TextDecoder !== "undefined" ? new TextDecoder("utf-8", { fatal: false }) : null;
  const utf8Encoder = typeof TextEncoder !== "undefined" ? new TextEncoder() : null;

  function bytesToUtf8(bytes) {
    if (utf8Decoder) return utf8Decoder.decode(bytes);
    let str = "";
    for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
    try {
      return decodeURIComponent(escape(str));
    } catch (_) {
      return str;
    }
  }

  function utf8ToBytes(str) {
    if (utf8Encoder) return utf8Encoder.encode(str);
    const unescaped = unescape(encodeURIComponent(str));
    const arr = new Uint8Array(unescaped.length);
    for (let i = 0; i < unescaped.length; i++) arr[i] = unescaped.charCodeAt(i);
    return arr;
  }

  // ============================================================================
  // PART 2: SOCIAL & SEARCH ENGINE (X/TWITTER, INSTAGRAM, GOOGLE, YOUTUBE JSON)
  // ============================================================================

  /**
   * 2A. Google Search Web HTML Sponsored Ad Cleanup
   */
  function processGoogleSearchHtml(html) {
    if (
      typeof html !== "string" ||
      (!html.includes('id="tads"') &&
        !html.includes('id="bottomads"') &&
        !html.includes("data-text-ad") &&
        !html.includes("commercial-unit"))
    ) {
      return { body: html, modified: false };
    }
    const css =
      "<style>#tads,#bottomads,#tvcap,.uEierd,.commercial-unit-desktop-top,.commercial-unit-mobile-top,.commercial-unit-mobile-bottom,.cu-container,[data-text-ad],[aria-label=\"Ads\"],[data-hveid*=\"CAEQ\"]{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;visibility:hidden!important;pointer-events:none!important;}</style>";
    if (/<\/head>/i.test(html)) {
      return { body: html.replace(/<\/head>/i, css + "</head>"), modified: true };
    }
    return { body: css + html, modified: true };
  }

  /**
   * 2B. X (Twitter) GraphQL & REST Timeline Ad & Upsell Filter
   * Includes Fast-Path check, Empty Module Pruning, and Promoted Trend removal.
   */
  const X_AD_PREFIXES = [
    "promoted-tweet",
    "promotedTweet",
    "promoted-user",
    "who-to-follow",
    "whoToFollow",
    "premium-upsell",
    "cursor-show-more-threads-prompt",
    "message-prompt",
    "relevance-prompt",
    "communities-to-join"
  ];

  function processXJsonString(rawText) {
    // 0.1ms Fast-Path: Skip JSON.parse if no ad/upsell keywords exist
    if (
      !rawText.includes("promoted") &&
      !rawText.includes("Promoted") &&
      !rawText.includes("who-to-follow") &&
      !rawText.includes("whoToFollow") &&
      !rawText.includes("upsell") &&
      !rawText.includes("-prompt")
    ) {
      return { body: rawText, modified: false };
    }

    const obj = JSON.parse(rawText);
    let dirty = false;

    function isXAdEntry(item) {
      if (!item || typeof item !== "object") return false;
      const entryId = String(item.entryId || item.sortIndex || "");
      if (X_AD_PREFIXES.some(p => entryId.startsWith(p) || entryId.includes("promoted"))) {
        return true;
      }
      const content = item.content || item.item || {};
      const itemContent = content.itemContent || (content.item && content.item.itemContent) || {};
      const trendMeta = itemContent.trend && itemContent.trend.promotedMetadata;

      if (
        itemContent.promotedMetadata ||
        content.promotedMetadata ||
        item.promotedMetadata ||
        trendMeta ||
        itemContent.itemType === "TimelinePromotedTweet" ||
        (itemContent.tweet_results &&
          itemContent.tweet_results.result &&
          itemContent.tweet_results.result.promotedMetadata)
      ) {
        return true;
      }

      // Filter nested module items (e.g., conversation thread ads)
      if (Array.isArray(content.items)) {
        const origLen = content.items.length;
        content.items = content.items.filter(sub => !isXAdEntry(sub));
        if (content.items.length !== origLen) {
          dirty = true;
          // If all items inside a TimelineTimelineModule were ads, drop the empty shell module too!
          if (content.items.length === 0) return true;
        }
      }
      return false;
    }

    function walkX(node) {
      if (!node || typeof node !== "object") return;      if (Array.isArray(node.instructions)) {
        for (const inst of node.instructions) {
          if (Array.isArray(inst.entries)) {
            const before = inst.entries.length;
            inst.entries = inst.entries.filter(e => !isXAdEntry(e));
            if (inst.entries.length !== before) dirty = true;
          }
          if (inst.addEntries && Array.isArray(inst.addEntries.entries)) {
            const before = inst.addEntries.entries.length;
            inst.addEntries.entries = inst.addEntries.entries.filter(e => !isXAdEntry(e));
            if (inst.addEntries.entries.length !== before) dirty = true;
          }
          if (inst.entry && isXAdEntry(inst.entry)) {
            delete inst.entry;
            dirty = true;
          }
        }
      }
      if (node.globalObjects && node.globalObjects.tweets) {
        for (const k of Object.keys(node.globalObjects.tweets)) {
          if (node.globalObjects.tweets[k] && node.globalObjects.tweets[k].promotedMetadata) {
            delete node.globalObjects.tweets[k];
            dirty = true;
          }
        }
      }
      for (const key of Object.keys(node)) {
        const val = node[key];
        if (val && typeof val === "object") walkX(val);
      }
    }

    walkX(obj);
    return { body: dirty ? JSON.stringify(obj) : rawText, modified: dirty };
  }

  /**
   * 2C. Instagram GraphQL (xdt_*) & REST Feed / Reels / Stories Ad Filter
   */
  function processInstagramJsonString(rawText) {
    if (
      !rawText.includes("ad_id") &&
      !rawText.includes("is_sponsored") &&
      !rawText.includes("ad_action") &&
      !rawText.includes("injected") &&
      !rawText.includes("sponsored_label") &&
      !rawText.includes('"ad"')
    ) {
      return { body: rawText, modified: false };
    }

    const obj = JSON.parse(rawText);
    let dirty = false;

    function isIgAd(item) {
      if (!item || typeof item !== "object") return false;
      if (item.ad || item.ad_id || item.ad_action || item.is_sponsored || item.injected || item.ad_link_type || item.sponsored_label) {
        return true;
      }
      const m = item.media_or_ad || item.explore_item_info || item.media || item.node || item;
      if (!m || typeof m !== "object") return false;
      return Boolean(
        m.ad ||
        m.ad_id ||
        m.is_sponsored ||
        m.ad_action ||
        m.injected ||
        m.sponsored_label ||
        m.product_type === "ad" ||
        m.organic_tracking_token === "ad" ||
        (m.media_or_ad && (m.media_or_ad.ad_id || m.media_or_ad.is_sponsored || m.media_or_ad.injected))
      );
    }

    const IG_ARRAY_KEYS = ["feed_items", "items", "medias", "reels_media", "tray", "edges", "clips_items"];

    function walkIg(node) {
      if (!node || typeof node !== "object") return;
      for (const arrKey of IG_ARRAY_KEYS) {
        if (Array.isArray(node[arrKey])) {
          const before = node[arrKey].length;
          node[arrKey] = node[arrKey].filter(el => !isIgAd(el));
          if (node[arrKey].length !== before) dirty = true;
        }
      }
      for (const k of Object.keys(node)) {
        if (node[k] && typeof node[k] === "object") walkIg(node[k]);
      }
    }

    walkIg(obj);
    return { body: dirty ? JSON.stringify(obj) : rawText, modified: dirty };
  }

  /**
   * 2D. YouTube Web JSON Fallback (In-Place Mutation with Dirty Tracking)
   */
  const YT_JSON_AD_KEYS = new Set([
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

  function processYouTubeJsonString(rawText, filterHomeShorts = false) {
    const obj = JSON.parse(rawText);
    let dirty = false;

    function textValue(node) {
      if (!node || typeof node !== "object") return "";
      if (typeof node.simpleText === "string") return node.simpleText;
      if (Array.isArray(node.runs)) return node.runs.map(x => x && x.text || "").join("");
      return "";
    }

    function isShortsShelf(node) {
      if (!node || typeof node !== "object") return false;
      if (node.reelShelfRenderer) return true;
      const rich = node.richShelfRenderer;
      if (rich && /\\bshorts\\b/i.test(textValue(rich.title))) return true;
      if (node.richSectionRenderer) {
        const content = node.richSectionRenderer.content || {};
        if (content.reelShelfRenderer) return true;
        const shelf = content.richShelfRenderer;
        if (shelf && /\\bshorts\\b/i.test(textValue(shelf.title))) return true;
      }
      return false;
    }

    function isYtJsonAdElement(el) {
      if (!el || typeof el !== "object") return false;
      for (const k of Object.keys(el)) {
        if (YT_JSON_AD_KEYS.has(k)) return true;
      }
      return false;
    }

    function walkYtInPlace(node, isRoot = false) {
      if (!node || typeof node !== "object") return;
      if (Array.isArray(node)) {
        for (let i = node.length - 1; i >= 0; i--) {
          if (isYtJsonAdElement(node[i])) {
            node.splice(i, 1);
            dirty = true;
          } else if (filterHomeShorts && isShortsShelf(node[i])) {
            node.splice(i, 1);
            dirty = true;
          } else {
            walkYtInPlace(node[i]);
          }
        }
        return;
      }
      for (const k of Object.keys(node)) {
        if (YT_JSON_AD_KEYS.has(k)) {
          delete node[k];
          dirty = true;
        } else if (filterHomeShorts && isShortsShelf({ [k]: node[k] })) {
          delete node[k];
          dirty = true;
        } else if (node[k] && typeof node[k] === "object") {
          walkYtInPlace(node[k]);
        }
      }
    }

    // Keep the filter scoped to the home feed; never remove Shorts from watch/reel pages.
    if (filterHomeShorts) {
      const hasHomeBrowseStructure = !!(
        obj && obj.contents &&
        (obj.contents.twoColumnBrowseResultsRenderer || obj.contents.singleColumnBrowseResultsRenderer)
      );
      if (!hasHomeBrowseStructure) filterHomeShorts = false;
    }

    walkYtInPlace(obj, true);
    return { body: dirty ? JSON.stringify(obj) : rawText, modified: dirty };
  }

  // ============================================================================
  // PART 3: UNIFIED ROUTER & SHADOWROCKET ADAPTER
  // ============================================================================
  function parseRuntimeOptions() {
    const opts = { ...DEFAULT_OPTS };
    if (typeof $argument === "string" && $argument.trim()) {
      const raw = $argument.trim();
      if (raw.startsWith("{")) {
        try {
          Object.assign(opts, JSON.parse(raw));
        } catch (_) {}
      } else {
        for (const pair of raw.split("&")) {
          const [k, v] = pair.split("=");
          if (!k || v === undefined) continue;
          const key = k.trim();
          const val = v.trim();
          if (val === "true") opts[key] = true;
          else if (val === "false") opts[key] = false;
          else opts[key] = val;
        }
      }
    }
    return opts;
  }

  function loadAdCache() {
    try {
      if (typeof $persistentStore !== "undefined") {
        const raw = $persistentStore.read(CACHE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (
            parsed &&
            parsed.version === CACHE_VER &&
            Array.isArray(parsed.whiteNo) &&
            Array.isArray(parsed.blackNo) &&
            Array.isArray(parsed.whiteEml) &&
            Array.isArray(parsed.blackEml)
          ) {
            return { ...parsed, dirty: false };
          }
        }
      }
    } catch (_) {}
    return {
      version: CACHE_VER,
      whiteNo: [],
      blackNo: [],
      whiteEml: [],
      blackEml: [...INITIAL_BLACK_EML],
      dirty: false
    };
  }

  function saveAdCache(cache) {
    if (!cache || !cache.dirty) return;
    try {
      if (typeof $persistentStore !== "undefined") {
        $persistentStore.write(
          JSON.stringify({
            version: CACHE_VER,
            whiteNo: cache.whiteNo.slice(-200),
            blackNo: cache.blackNo.slice(-200),
            whiteEml: cache.whiteEml.slice(-200),
            blackEml: cache.blackEml.slice(-200)
          }),
          CACHE_KEY
        );
      }
    } catch (_) {}
  }

  function getBinaryBody(resp) {
    if (!resp) return null;
    const raw = resp.bodyBytes !== undefined ? resp.bodyBytes : resp.body;
    if (!raw) return null;
    if (raw instanceof Uint8Array) return raw;
    if (raw instanceof ArrayBuffer) return new Uint8Array(raw);
    return null;
  }

  function getTextBody(resp) {
    if (!resp) return null;
    if (typeof resp.body === "string") return resp.body;
    const bin = getBinaryBody(resp);
    if (bin) return bytesToUtf8(bin);
    return null;
  }

    function dispatch() {
    if (typeof $response === "undefined" || !$response) return $done({});
    const url = (typeof $request !== "undefined" && $request.url) || "";
    const headers = ($response && $response.headers) || {};
    const contentType = String(headers["Content-Type"] || headers["content-type"] || "").toLowerCase();

    if (url.includes("google.") && url.includes("/search?")) {
      const html = getTextBody($response);
      if (!html) return $done({});
      const res = processGoogleSearchHtml(html);
      return res.modified ? $done({ body: res.body }) : $done({});
    }
    if (url.includes("x.com") || url.includes("twitter.com")) {
      const text = getTextBody($response);
      if (!text) return $done({});
      const res = processXJsonString(text);
      return res.modified ? $done({ body: res.body }) : $done({});
    }
    if (url.includes("instagram.com")) {
      const text = getTextBody($response);
      if (!text) return $done({});
      const res = processInstagramJsonString(text);
      return res.modified ? $done({ body: res.body }) : $done({});
    }
    if (url.includes("youtubei.googleapis.com") || url.includes("youtube.com")) {
      const bin = getBinaryBody($response);
      const isJsonContent =
        contentType.includes("json") ||
        (typeof $response.body === "string" && $response.body.trim().startsWith("{")) ||
        (bin && bin.length > 0 && bin[0] === 0x7b);
      if (!isJsonContent) return $done({});
      const text = getTextBody($response);
      if (!text) return $done({});
      let isHomeBrowse = false;
      if (url.includes("/browse") && typeof $request !== "undefined" && typeof $request.body === "string") {
        try {
          const requestData = JSON.parse($request.body);
          isHomeBrowse = requestData.browseId === "FEwhat_to_watch";
        } catch (_) {}
      }
      const res = processYouTubeJsonString(text, isHomeBrowse);
      return res.modified ? $done({ body: res.body }) : $done({});
    }
    return $done({});
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { processGoogleSearchHtml, processXJsonString, processInstagramJsonString, processYouTubeJsonString };
  } else {
    try {
      dispatch();
    } catch (e) {
      console.log(`[SR-Clean-Pro] ${e}`);
      $done({});
    }
  }
})();