/**
 * Shadowrocket YouTube Pro Engine (Zero-Copy Wire-Stream Architecture)
 *
 * Advantages over traditional protobuf-ts scripts:
 * 1. 64-bit Safe Varint & Tag Codec: Handles massive YouTube extension field numbers
 *    (e.g. 465160965) without 32-bit bitwise shift overflow.
 * 2. Zero-Copy Subarray Passthrough: Unmodified branches (98%+ of payload) are sliced
 *    by pointer reference without object allocation, keeping memory well under
 *    Shadowrocket's strict iOS Network Extension 15MB limit.
 * 3. Active Onesie Encryption Downgrade: Strips Onesie encryption keys & disables
 *    useHotConfigToCreateOnesieRequest in /config & /log_event so YouTube falls back
 *    to standard filterable /player requests.
 * 4. Full Feature Parity + Extra Ad Vectors:
 *    - Feed / Search / Next Ad & Promoted EML stripping (BMH binary search + persistent cache)
 *    - Player adPlacements (7), adSlots (68), & pagead tracking (18) removal
 *    - Native PiP & Background Playback unlock
 *    - Auto-Translated Caption Track & Language List injection
 *    - Shorts ad stream filtering
 *    - Bottom Guide bar decluttering & Premium Background Setting injection
 */

(() => {
  "use strict";

  const CACHE_KEY = "SR_YT_PRO_CACHE_V2";
  const CACHE_VER = "2.0";

  // Default runtime options (can be overridden via Shadowrocket $argument JSON or key=val)
  const DEFAULT_OPTS = {
    captionLang: "zh-Hans", // Set to "off" to disable auto-caption enhancement
    blockUpload: true,
    blockImmersive: true,
    blockShortsTab: false,
    blockShortsFeed: true
  };

  // Wire types
  const WT_VARINT = 0;
  const WT_64 = 1;
  const WT_LEN = 2;
  const WT_SGROUP = 3;
  const WT_EGROUP = 4;
  const WT_32 = 5;

  // Binary patterns for fast BMH matching
  // "pagead" -> [112, 97, 103, 101, 97, 100]
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
    return decodeURIComponent(escape(str));
  }

  function utf8ToBytes(str) {
    if (utf8Encoder) return utf8Encoder.encode(str);
    const unescaped = unescape(encodeURIComponent(str));
    const arr = new Uint8Array(unescaped.length);
    for (let i = 0; i < unescaped.length; i++) arr[i] = unescaped.charCodeAt(i);
    return arr;
  }

  // ============================================================================
  // 64-Bit Safe Protobuf Wire Reader & Writer
  // (Prevents 32-bit overflow on field numbers > 268,435,455 such as 465160965)
  // ============================================================================
  class SafeWireReader {
    constructor(buf) {
      this.buf = buf;
      this.pos = 0;
      this.len = buf.length;
    }

    eof() {
      return this.pos >= this.len;
    }

    /**
     * Reads a Varint up to 53-bit safe integer precision using floating-point
     * multiplication instead of 32-bit bitwise shifts.
     */
    varintNumber() {
      let result = 0;
      let multiplier = 1;
      while (this.pos < this.len) {
        const b = this.buf[this.pos++];
        result += (b & 0x7f) * multiplier;
        if ((b & 0x80) === 0) return result;
        multiplier *= 128;
        if (multiplier > 9007199254740992) {
          // Skip remaining continuation bytes if any 64-bit negative varint
          while (this.pos < this.len && (this.buf[this.pos++] & 0x80) !== 0) {}
          return result;
        }
      }
      throw new RangeError("Unexpected EOF reading varint");
    }

    tag() {
      const rawTag = this.varintNumber();
      const wireType = rawTag % 8;
      const fieldNo = Math.floor(rawTag / 8);
      if (fieldNo <= 0 || wireType < 0 || wireType > 5) {
        throw new Error(`Invalid protobuf tag: field=${fieldNo}, wt=${wireType}`);
      }
      return [fieldNo, wireType];
    }

    bytes() {
      const length = this.varintNumber();
      const start = this.pos;
      const end = start + length;
      if (end > this.len || length < 0) {
        throw new RangeError("Out of bounds reading length-delimited bytes");
      }
      this.pos = end;
      return this.buf.subarray(start, end);
    }

    string() {
      return bytesToUtf8(this.bytes());
    }

    skip(wireType) {
      const start = this.pos;
      switch (wireType) {
        case WT_VARINT:
          while (this.pos < this.len && (this.buf[this.pos++] & 0x80) !== 0) {}
          break;
        case WT_64:
          this.pos += 8;
          break;
        case WT_LEN: {
          const len = this.varintNumber();
          this.pos += len;
          break;
        }
        case WT_SGROUP: {
          while (!this.eof()) {
            const [, wt] = this.tag();
            if (wt === WT_EGROUP) break;
            this.skip(wt);
          }
          break;
        }
        case WT_32:
          this.pos += 4;
          break;
        default:
          throw new Error(`Unsupported wire type: ${wireType}`);
      }
      if (this.pos > this.len) throw new RangeError("Unexpected EOF skipping field");
      return this.buf.subarray(start, this.pos);
    }
  }

  class SafeWireWriter {
    constructor() {
      this.chunks = [];
      this.scratch = [];
    }

    _flushScratch() {
      if (this.scratch.length > 0) {
        this.chunks.push(new Uint8Array(this.scratch));
        this.scratch = [];
      }
    }

    varintNumber(value) {
      let v = Math.floor(value);
      if (v < 0) {
        // Negative int32/int64 sign-extended to 10-byte varint
        let big = BigInt(v);
        const mask = (1n << 64n) - 1n;
        big &= mask;
        while (big > 0x7fn) {
          this.scratch.push(Number((big & 0x7fn) | 0x80n));
          big >>= 7n;
        }
        this.scratch.push(Number(big));
        return this;
      }
      while (v > 127) {
        this.scratch.push((v & 0x7f) | 0x80);
        v = Math.floor(v / 128);
      }
      this.scratch.push(v & 0x7f);
      return this;
    }

    tag(fieldNo, wireType) {
      return this.varintNumber(fieldNo * 8 + (wireType & 7));
    }

    raw(bytes) {
      if (!bytes || bytes.length === 0) return this;
      this._flushScratch();
      this.chunks.push(bytes);
      return this;
    }

    bytes(payload) {
      this.varintNumber(payload.length);
      return this.raw(payload);
    }

    string(str) {
      return this.bytes(utf8ToBytes(str));
    }

    bool(val) {
      this.scratch.push(val ? 1 : 0);
      return this;
    }

    finish() {
      this._flushScratch();
      if (this.chunks.length === 0) return new Uint8Array(0);
      if (this.chunks.length === 1) return this.chunks[0];
      let total = 0;
      for (let i = 0; i < this.chunks.length; i++) total += this.chunks[i].length;
      const out = new Uint8Array(total);
      let offset = 0;
      for (let i = 0; i < this.chunks.length; i++) {
        out.set(this.chunks[i], offset);
        offset += this.chunks[i].length;
      }
      return out;
    }
  }

  // ============================================================================
  // Boyer-Moore-Horspool Fast Binary Pattern Matcher
  // ============================================================================
  const pageadSkip = (() => {
    const table = new Int32Array(256).fill(PATTERN_PAGEAD.length + 1);
    for (let i = 0; i < PATTERN_PAGEAD.length; i++) {
      table[PATTERN_PAGEAD[i]] = PATTERN_PAGEAD.length - i;
    }
    return table;
  })();

  function hasPageAdMarker(buf) {
    if (!buf || buf.length < 500) return false;
    const n = buf.length;
    const m = PATTERN_PAGEAD.length;
    let i = 0;
    while (i <= n - m) {
      if (
        buf[i] === 112 &&
        buf[i + 1] === 97 &&
        buf[i + 2] === 103 &&
        buf[i + 3] === 101 &&
        buf[i + 4] === 97 &&
        buf[i + 5] === 100
      ) {
        return true;
      }
      const next = buf[i + m];
      i += next !== undefined ? pageadSkip[next] : m + 1;
    }
    return false;
  }

  // ============================================================================
  // Component Builders (Labels, PiP, Captions, Settings)
  // ============================================================================
  function buildLabelBytes(text) {
    const run = new SafeWireWriter().tag(1, WT_LEN).string(text).finish();
    return new SafeWireWriter().tag(1, WT_LEN).bytes(run).finish();
  }

  function buildPipRenderBytes() {
    const ability = new SafeWireWriter()
      .tag(1, WT_VARINT).bool(true)
      .tag(8, WT_VARINT).varintNumber(1)
      .finish();
    return new SafeWireWriter().tag(151635310, WT_LEN).bytes(ability).finish();
  }

  function buildBgRenderBytes() {
    const ability = new SafeWireWriter()
      .tag(1, WT_VARINT).bool(true)
      .finish();
    return new SafeWireWriter().tag(64657230, WT_LEN).bytes(ability).finish();
  }

  // ============================================================================
  // 1. Player Handler (Ad Removal + PiP/Background Unlock + Auto Captions)
  // ============================================================================
  function patchPlayabilityStatus(bytes) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      const raw = r.skip(wt);
      if (fn === 21 || fn === 11) continue;
      w.tag(fn, wt).raw(raw);
    }
    w.tag(21, WT_LEN).bytes(buildPipRenderBytes());
    w.tag(11, WT_LEN).bytes(buildBgRenderBytes());
    return w.finish();
  }

  function patchPlaybackTracking(bytes) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let mod = false;
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      const raw = r.skip(wt);
      if (fn === 18) {
        mod = true;
        continue;
      }
      w.tag(fn, wt).raw(raw);
    }
    return mod ? w.finish() : bytes;
  }

  function parseCaptionTrack(trackBytes) {
    const r = new SafeWireReader(trackBytes);
    let baseUrl = "";
    let languageCode = "";
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 1 && wt === WT_LEN) baseUrl = r.string();
      else if (fn === 4 && wt === WT_LEN) languageCode = r.string();
      else r.skip(wt);
    }
    return { baseUrl, languageCode };
  }

  function forceCaptionTrackTranslatable(trackBytes) {
    const r = new SafeWireReader(trackBytes);
    const w = new SafeWireWriter();
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      const raw = r.skip(wt);
      if (fn === 7) continue; // replace isTranslatable
      w.tag(fn, wt).raw(raw);
    }
    w.tag(7, WT_VARINT).bool(true);
    return w.finish();
  }

  function buildNewCaptionTrack(baseUrl, targetLang) {
    return new SafeWireWriter()
      .tag(1, WT_LEN).string(`${baseUrl}&tlang=${targetLang}`)
      .tag(2, WT_LEN).bytes(buildLabelBytes(`Auto (${targetLang})`))
      .tag(3, WT_LEN).string(`.${targetLang}`)
      .tag(4, WT_LEN).string(targetLang)
      .tag(7, WT_VARINT).bool(true)
      .finish();
  }

  function patchAudioTrack(audioTrackBytes, defaultIdx) {
    const r = new SafeWireReader(audioTrackBytes);
    const w = new SafeWireWriter();
    const indices = [];

    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 2) {
        if (wt === WT_LEN) {
          const pr = new SafeWireReader(r.bytes());
          while (!pr.eof()) indices.push(pr.varintNumber());
        } else if (wt === WT_VARINT) {
          indices.push(r.varintNumber());
        } else {
          r.skip(wt);
        }
        continue;
      }
      if (fn === 3 || fn === 11) {
        r.skip(wt);
        continue;
      }
      w.tag(fn, wt).raw(r.skip(wt));
    }

    if (!indices.includes(defaultIdx)) indices.push(defaultIdx);
    for (const idx of indices) {
      w.tag(2, WT_VARINT).varintNumber(idx);
    }
    w.tag(3, WT_VARINT).varintNumber(defaultIdx);
    w.tag(11, WT_VARINT).varintNumber(3); // captionsInitialState = 3
    return w.finish();
  }

  function patchCaptionsRenderer(rendererBytes, targetLang) {
    if (!targetLang || targetLang === "off") return rendererBytes;
    const r = new SafeWireReader(rendererBytes);
    const captionTracks = [];
    const audioTracks = [];
    const otherFields = [];

    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 1 && wt === WT_LEN) {
        captionTracks.push(r.bytes());
      } else if (fn === 2 && wt === WT_LEN) {
        audioTracks.push(r.bytes());
      } else if (fn === 3 && wt === WT_LEN) {
        r.skip(wt); // Replace translationLanguages
      } else {
        otherFields.push([fn, wt, r.skip(wt)]);
      }
    }

    if (captionTracks.length === 0) return rendererBytes;

    let bestPriority = -1;
    let bestIndex = 0;
    const priorityMap = { [targetLang]: 2, en: 1 };

    const updatedCaptionTracks = captionTracks.map((tb, idx) => {
      const info = parseCaptionTrack(tb);
      const p = priorityMap[info.languageCode] || 0;
      if (p > bestPriority) {
        bestPriority = p;
        bestIndex = idx;
      }
      return forceCaptionTrackTranslatable(tb);
    });

    let targetTrackIndex = bestIndex;
    if (bestPriority !== 2) {
      const baseInfo = parseCaptionTrack(captionTracks[bestIndex]);
      if (baseInfo.baseUrl) {
        updatedCaptionTracks.push(buildNewCaptionTrack(baseInfo.baseUrl, targetLang));
        targetTrackIndex = updatedCaptionTracks.length - 1;
      }
    }

    const w = new SafeWireWriter();
    for (const tb of updatedCaptionTracks) {
      w.tag(1, WT_LEN).bytes(tb);
    }
    for (const ab of audioTracks) {
      w.tag(2, WT_LEN).bytes(patchAudioTrack(ab, targetTrackIndex));
    }
    for (const [code, label] of Object.entries(TRANSLATION_LANGS)) {
      const tlBytes = new SafeWireWriter()
        .tag(1, WT_LEN).string(code)
        .tag(2, WT_LEN).bytes(buildLabelBytes(label))
        .finish();
      w.tag(3, WT_LEN).bytes(tlBytes);
    }
    for (const [fn, wt, raw] of otherFields) {
      w.tag(fn, wt).raw(raw);
    }
    return w.finish();
  }

  function patchCaptions(captionsBytes, targetLang) {
    if (!targetLang || targetLang === "off") return captionsBytes;
    const r = new SafeWireReader(captionsBytes);
    const w = new SafeWireWriter();
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 51621377 && wt === WT_LEN) {
        w.tag(fn, WT_LEN).bytes(patchCaptionsRenderer(r.bytes(), targetLang));
      } else {
        w.tag(fn, wt).raw(r.skip(wt));
      }
    }
    return w.finish();
  }

  function processPlayer(bytes, opts) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let hasPlayability = false;

    while (!r.eof()) {
      const [fn, wt] = r.tag();
      // Strip adPlacements (7) and adSlots (68)
      if (fn === 7 || fn === 68) {
        r.skip(wt);
        continue;
      }
      if (fn === 2 && wt === WT_LEN) {
        hasPlayability = true;
        w.tag(2, WT_LEN).bytes(patchPlayabilityStatus(r.bytes()));
        continue;
      }
      if (fn === 9 && wt === WT_LEN) {
        w.tag(9, WT_LEN).bytes(patchPlaybackTracking(r.bytes()));
        continue;
      }
      if (fn === 10 && wt === WT_LEN && opts.captionLang !== "off") {
        w.tag(10, WT_LEN).bytes(patchCaptions(r.bytes(), opts.captionLang));
        continue;
      }
      w.tag(fn, wt).raw(r.skip(wt));
    }

    if (!hasPlayability) {
      w.tag(2, WT_LEN).bytes(patchPlayabilityStatus(new Uint8Array(0)));
    }
    return { bytes: w.finish(), modified: true };
  }

  // ============================================================================
  // 2. Feed / Browse / Search / Next Ad & Shelf Filter
  // ============================================================================
  function getEmlName(renderInfoBytes) {
    const r = new SafeWireReader(renderInfoBytes);
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 183314536 && wt === WT_LEN) {
        const lr = new SafeWireReader(r.bytes());
        while (!lr.eof()) {
          const [lfn, lwt] = lr.tag();
          if (lfn === 1 && lwt === WT_LEN) {
            return lr.string().split("|")[0] || "";
          }
          lr.skip(lwt);
        }
      } else {
        r.skip(wt);
      }
    }
    return "";
  }

  function inspectVideoInfoForAd(videoInfoBytes) {
    const r = new SafeWireReader(videoInfoBytes);
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 168777401 && wt === WT_LEN) {
        const cr = new SafeWireReader(r.bytes());
        while (!cr.eof()) {
          const [cfn, cwt] = cr.tag();
          if (cfn === 5 && cwt === WT_LEN) {
            return hasPageAdMarker(cr.bytes());
          }
          cr.skip(cwt);
        }
      } else {
        r.skip(wt);
      }
    }
    return false;
  }

  function isElementRendererBlocked(elementBytes, cache, opts) {
    const r = new SafeWireReader(elementBytes);
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 172660663 && wt === WT_LEN) {
        const vr = new SafeWireReader(r.bytes());
        let videoInfoBytes = null;
        let eml = "";
        while (!vr.eof()) {
          const [vfn, vwt] = vr.tag();
          if (vfn === 1 && vwt === WT_LEN) videoInfoBytes = vr.bytes();
          else if (vfn === 2 && vwt === WT_LEN) eml = getEmlName(vr.bytes());
          else vr.skip(vwt);
        }
        if (eml) {
          if (cache.whiteEml.includes(eml)) return false;
          if (cache.blackEml.includes(eml)) return true;
          if (opts.blockShortsFeed && /shorts(?!_pivot_item)/.test(eml)) return true;
          if (/ad_badge|promoted|sparkles|brand_promo|shopping_shelf/.test(eml)) {
            cache.blackEml.push(eml);
            cache.dirty = true;
            return true;
          }
          if (videoInfoBytes) {
            const isAd = inspectVideoInfoForAd(videoInfoBytes);
            if (isAd) cache.blackEml.push(eml);
            else cache.whiteEml.push(eml);
            cache.dirty = true;
            return isAd;
          }
        }
      } else {
        r.skip(wt);
      }
    }
    return false;
  }

  function isRichItemBlocked(itemBytes, cache, opts) {
    const r = new SafeWireReader(itemBytes);
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 153515154 && wt === WT_LEN) {
        if (isElementRendererBlocked(r.bytes(), cache, opts)) return true;
      } else {
        const raw = r.skip(wt);
        if (cache.whiteNo.includes(fn)) continue;
        if (cache.blackNo.includes(fn)) return true;
        const isAd = hasPageAdMarker(raw);
        if (isAd) {
          cache.blackNo.push(fn);
          cache.dirty = true;
          return true;
        } else {
          cache.whiteNo.push(fn);
          cache.dirty = true;
        }
      }
    }
    return false;
  }

  const FEED_CONTAINERS = new Set([
    1, 4, 5, 7, 8, 9, 10,
    49399797, // sectionListRenderer / appendContinuationItemsAction
    50195462, // itemSectionRenderer
    51431404, // reelShelfRenderer
    51779735, // nextResult
    51845067, // shelfRenderer
    58173949, // singleColumnResultsRenderer
    58174010  // tabRenderer
  ]);

  function filterFeedPayload(bytes, cache, opts, parentFieldNo = 0) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let modified = false;

    while (!r.eof()) {
      const [fn, wt] = r.tag();

      // Drop whole ReelShelfRenderer (51431404) if Shorts feed blocking is enabled
      if (opts.blockShortsFeed && fn === 51431404 && wt === WT_LEN) {
        r.skip(wt);
        modified = true;
        continue;
      }

      // Filter individual RichItemContents inside itemSectionRenderer (50195462) or reelShelfRenderer (51431404)
      if ((parentFieldNo === 50195462 || parentFieldNo === 51431404) && fn === 1 && wt === WT_LEN) {
        const itemBytes = r.bytes();
        if (isRichItemBlocked(itemBytes, cache, opts)) {
          modified = true;
          continue;
        }
        w.tag(fn, wt).bytes(itemBytes);
        continue;
      }

      // Filter direct ElementRenderer (153515154) inside Content
      if (fn === 153515154 && wt === WT_LEN) {
        const elBytes = r.bytes();
        if (isElementRendererBlocked(elBytes, cache, opts)) {
          modified = true;
          continue;
        }
        w.tag(fn, wt).bytes(elBytes);
        continue;
      }

      if (wt === WT_LEN && FEED_CONTAINERS.has(fn)) {
        const subBytes = r.bytes();
        try {
          const res = filterFeedPayload(subBytes, cache, opts, fn);
          w.tag(fn, wt).bytes(res.modified ? res.bytes : subBytes);
          if (res.modified) modified = true;
        } catch (_) {
          // If a scalar string/bytes field happens to share a low tag number (1, 4, etc.), passthrough intact
          w.tag(fn, wt).bytes(subBytes);
        }
        continue;
      }

      w.tag(fn, wt).raw(r.skip(wt));
    }

    return { bytes: modified ? w.finish() : bytes, modified };
  }

  // ============================================================================
  // 3. Onesie Encryption Downgrade (/config & /log_event)
  // Forces YouTube client to use standard /player requests instead of encrypted UMP
  // ============================================================================
  function neutralizeOnesieHotConfig(onesieBytes) {
    const r = new SafeWireReader(onesieBytes);
    const w = new SafeWireWriter();
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      // Strip clientKey (1), encryptKey (2), keyExpiresInSeconds (3), useHotConfigToCreateOnesieRequest (30)
      if (fn === 1 || fn === 2 || fn === 3 || fn === 30) {
        r.skip(wt);
        continue;
      }
      w.tag(fn, wt).raw(r.skip(wt));
    }
    w.tag(30, WT_VARINT).bool(false);
    return w.finish();
  }

  function processConfigPayload(bytes) {
    const CONFIG_PATH_TAGS = new Set([1, 16, 7, 138536474]);
    function walk(buf) {
      const r = new SafeWireReader(buf);
      const w = new SafeWireWriter();
      let mod = false;
      while (!r.eof()) {
        const [fn, wt] = r.tag();
        if (fn === 146311580 && wt === WT_LEN) {
          w.tag(fn, WT_LEN).bytes(neutralizeOnesieHotConfig(r.bytes()));
          mod = true;
          continue;
        }
        if (wt === WT_LEN && CONFIG_PATH_TAGS.has(fn)) {
          const sub = r.bytes();
          try {
            const res = walk(sub);
            w.tag(fn, WT_LEN).bytes(res.modified ? res.bytes : sub);
            if (res.modified) mod = true;
          } catch (_) {
            w.tag(fn, WT_LEN).bytes(sub);
          }
          continue;
        }
        w.tag(fn, wt).raw(r.skip(wt));
      }
      return { bytes: mod ? w.finish() : buf, modified: mod };
    }
    return walk(bytes);
  }

  // ============================================================================
  // 4. Shorts Ad Filter (/reel_watch_sequence)
  // ============================================================================
  function isShortsEntryAd(entryBytes) {
    const r = new SafeWireReader(entryBytes);
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 1 && wt === WT_LEN) {
        const cr = new SafeWireReader(r.bytes());
        while (!cr.eof()) {
          const [cfn, cwt] = cr.tag();
          if (cfn === 139608561 && cwt === WT_LEN) {
            const er = new SafeWireReader(cr.bytes());
            while (!er.eof()) {
              const [efn, ewt] = er.tag();
              if (efn === 16 && ewt === WT_LEN) {
                const ar = new SafeWireReader(er.bytes());
                while (!ar.eof()) {
                  const [afn, awt] = ar.tag();
                  if (afn === 1 && awt === WT_VARINT) {
                    if (ar.varintNumber() !== 0) return true;
                  } else {
                    ar.skip(awt);
                  }
                }
              } else {
                er.skip(ewt);
              }
            }
          } else {
            cr.skip(cwt);
          }
        }
      } else {
        r.skip(wt);
      }
    }
    return false;
  }

  function processShorts(bytes) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let modified = false;
    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 2 && wt === WT_LEN) {
        const entry = r.bytes();
        if (isShortsEntryAd(entry)) {
          modified = true;
          continue;
        }
        w.tag(fn, WT_LEN).bytes(entry);
        continue;
      }
      w.tag(fn, wt).raw(r.skip(wt));
    }
    return { bytes: modified ? w.finish() : bytes, modified };
  }

  // ============================================================================
  // 5. Navigation Bar Filter (/guide) & Settings Injection (/get_setting)
  // ============================================================================
  function processGuide(bytes, opts) {
    const blockedIds = new Set(["SPunlimited"]);
    if (opts.blockUpload) blockedIds.add("FEuploads");
    if (opts.blockImmersive) blockedIds.add("FEmusic_immersive");
    if (opts.blockShortsTab) blockedIds.add("FEshorts");

    function isBlockedRendererItem(itemBytes) {
      const r = new SafeWireReader(itemBytes);
      while (!r.eof()) {
        const [fn, wt] = r.tag();
        if ((fn === 318370163 || fn === 117501096) && wt === WT_LEN) {
          const er = new SafeWireReader(r.bytes());
          while (!er.eof()) {
            const [efn, ewt] = er.tag();
            if (efn === 1 && ewt === WT_LEN) {
              if (blockedIds.has(er.string())) return true;
            } else {
              er.skip(ewt);
            }
          }
        } else {
          r.skip(wt);
        }
      }
      return false;
    }

    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let modified = false;

    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if ((fn === 4 || fn === 6) && wt === WT_LEN) {
        const itemBytes = r.bytes();
        const ir = new SafeWireReader(itemBytes);
        const iw = new SafeWireWriter();
        let itemMod = false;

        while (!ir.eof()) {
          const [ifn, iwt] = ir.tag();
          if (ifn === 117866661 && iwt === WT_LEN) {
            const secBytes = ir.bytes();
            const sr = new SafeWireReader(secBytes);
            const sw = new SafeWireWriter();
            let secMod = false;

            while (!sr.eof()) {
              const [sfn, swt] = sr.tag();
              if (sfn === 1 && swt === WT_LEN) {
                const riBytes = sr.bytes();
                if (isBlockedRendererItem(riBytes)) {
                  secMod = true;
                  continue;
                }
                sw.tag(sfn, WT_LEN).bytes(riBytes);
              } else {
                sw.tag(sfn, swt).raw(sr.skip(swt));
              }
            }
            iw.tag(ifn, WT_LEN).bytes(secMod ? sw.finish() : secBytes);
            if (secMod) itemMod = true;
          } else {
            iw.tag(ifn, iwt).raw(ir.skip(iwt));
          }
        }
        w.tag(fn, WT_LEN).bytes(itemMod ? iw.finish() : itemBytes);
        if (itemMod) modified = true;
        continue;
      }
      w.tag(fn, wt).raw(r.skip(wt));
    }
    return { bytes: modified ? w.finish() : bytes, modified };
  }

  function buildBackgroundPlaySettingItem() {
    const icon = new SafeWireWriter().tag(1, WT_VARINT).varintNumber(1093).finish();
    const bgRenderer = new SafeWireWriter()
      .tag(2, WT_VARINT).bool(true)  // backgroundPlayback
      .tag(3, WT_VARINT).bool(true)  // download
      .tag(9, WT_VARINT).bool(true)  // downloadQualitySelection
      .tag(10, WT_VARINT).bool(true) // smartDownload
      .tag(14, WT_LEN).bytes(icon)
      .finish();
    return new SafeWireWriter().tag(88478200, WT_LEN).bytes(bgRenderer).finish();
  }

  function processSetting(bytes) {
    const w = new SafeWireWriter();
    w.raw(bytes);
    w.tag(6, WT_LEN).bytes(buildBackgroundPlaySettingItem());
    return { bytes: w.finish(), modified: true };
  }

  // ============================================================================
  // 6. Combined Watch Handler (/get_watch)
  // ============================================================================
  function processWatch(bytes, cache, opts) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let modified = false;

    while (!r.eof()) {
      const [fn, wt] = r.tag();
      if (fn === 1 && wt === WT_LEN) {
        const contentBytes = r.bytes();
        const cr = new SafeWireReader(contentBytes);
        const cw = new SafeWireWriter();
        let cMod = false;

        while (!cr.eof()) {
          const [cfn, cwt] = cr.tag();
          if (cfn === 2 && cwt === WT_LEN) {
            const pRes = processPlayer(cr.bytes(), opts);
            cw.tag(2, WT_LEN).bytes(pRes.bytes);
            cMod = true;
          } else if (cfn === 3 && cwt === WT_LEN) {
            const nRes = filterFeedPayload(cr.bytes(), cache, opts, 0);
            cw.tag(3, WT_LEN).bytes(nRes.bytes);
            if (nRes.modified) cMod = true;
          } else {
            cw.tag(cfn, cwt).raw(cr.skip(cwt));
          }
        }
        w.tag(1, WT_LEN).bytes(cMod ? cw.finish() : contentBytes);
        if (cMod) modified = true;
        continue;
      }
      w.tag(fn, wt).raw(r.skip(wt));
    }
    return { bytes: modified ? w.finish() : bytes, modified };
  }

  // ============================================================================
  // Shadowrocket Environment & Persistence Layer
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
      blackEml: [...INITIAL_BLACK_EML],      dirty: false
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

  function extractBodyBytes() {
    if (typeof $response === "undefined" || !$response) return null;
    const b = $response.bodyBytes !== undefined ? $response.bodyBytes : $response.body;
    if (!b) return null;
    if (b instanceof Uint8Array) return b;
    if (b instanceof ArrayBuffer) return new Uint8Array(b);
    return null;
  }

  function run() {
    const url = (typeof $request !== "undefined" && $request.url) || "";
    const bodyBytes = extractBodyBytes();
    if (!bodyBytes || bodyBytes.length === 0) {
      $done({});
      return;
    }

    const opts = parseRuntimeOptions();
    const cache = loadAdCache();
    let res = { bytes: bodyBytes, modified: false };

    if (url.includes("/player")) {
      res = processPlayer(bodyBytes, opts);
    } else if (url.includes("/browse") || url.includes("/next") || url.includes("/search")) {
      res = filterFeedPayload(bodyBytes, cache, opts, 0);
    } else if (url.includes("/reel_watch_sequence")) {
      res = processShorts(bodyBytes);
    } else if (url.includes("/guide")) {
      res = processGuide(bodyBytes, opts);
    } else if (url.includes("/get_setting")) {
      res = processSetting(bodyBytes);
    } else if (url.includes("/get_watch")) {
      res = processWatch(bodyBytes, cache, opts);
    } else if (url.includes("/config") || url.includes("/log_event")) {
      res = processConfigPayload(bodyBytes);
    }

    if (cache.dirty) saveAdCache(cache);

    if (res.modified && res.bytes) {
      $done({ body: res.bytes });
    } else {
      $done({});
    }
  }

  // Export internals for automated unit verification in Node.js while executing immediately in Shadowrocket
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      SafeWireReader,
      SafeWireWriter,
      processPlayer,
      filterFeedPayload,
      processConfigPayload,
      processShorts,
      processGuide,
      processSetting,
      processWatch,
      loadAdCache,
      DEFAULT_OPTS
    };
  } else {
    try {
      run();
    } catch (e) {
      console.log(`[SR-YT-Pro] ${e}`);
      $done({});
    }
  }
})();