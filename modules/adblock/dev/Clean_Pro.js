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
  const CACHE_VER = "2.0";

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
  // PART 1: BOUNDED PROTOBUF WIRE CODEC (YOUTUBE BINARY MODE)
  // ============================================================================
  // Independent, bounded Protobuf wire codec.
  // It preserves raw field payloads and rejects malformed/truncated input.
  class SafeWireReader {
    constructor(buf, limits) {
      if (!(buf instanceof Uint8Array)) throw new TypeError("Expected Uint8Array");
      this.buf = buf;
      this.pos = 0;
      this.len = buf.length;
      this.maxDepth = limits && Number.isInteger(limits.maxDepth) ? limits.maxDepth : 64;
      this.lastFieldNo = 0;
    }

    eof() {
      return this.pos === this.len;
    }

    _readVarintRaw() {
      const start = this.pos;
      let value = 0;
      let factor = 1;
      for (let i = 0; i < 10; i++) {
        if (this.pos >= this.len) throw new RangeError("Truncated protobuf varint");
        const byte = this.buf[this.pos++];
        if (i === 9 && byte > 1) throw new RangeError("Protobuf varint exceeds 64 bits");
        value += (byte & 0x7f) * factor;
        if ((byte & 0x80) === 0) return { value, start, end: this.pos };
        factor *= 128;
      }
      throw new RangeError("Protobuf varint exceeds 10 bytes");
    }

    varintNumber() {
      const result = this._readVarintRaw().value;
      if (!Number.isSafeInteger(result)) {
        throw new RangeError("Protobuf integer exceeds JavaScript safe integer range");
      }
      return result;
    }

    tag() {
      const rawTag = this.varintNumber();
      const wireType = rawTag % 8;
      const fieldNo = Math.floor(rawTag / 8);
      if (!Number.isInteger(fieldNo) || fieldNo < 1 || fieldNo > 536870911 || wireType > WT_32) {
        throw new Error("Invalid protobuf tag");
      }
      this.lastFieldNo = fieldNo;
      return [fieldNo, wireType];
    }

    bytes() {
      const length = this.varintNumber();
      if (!Number.isSafeInteger(length) || length < 0 || length > this.len - this.pos) {
        throw new RangeError("Invalid or truncated length-delimited field");
      }
      const start = this.pos;
      this.pos += length;
      return this.buf.subarray(start, this.pos);
    }

    string() {
      return bytesToUtf8(this.bytes());
    }

    _skipValue(wireType) {
      switch (wireType) {
        case WT_VARINT:
          this._readVarintRaw();
          return;
        case WT_64:
          if (this.len - this.pos < 8) throw new RangeError("Truncated fixed64 field");
          this.pos += 8;
          return;
        case WT_LEN: {
          const length = this.varintNumber();
          if (!Number.isSafeInteger(length) || length < 0 || length > this.len - this.pos) {
            throw new RangeError("Invalid or truncated length-delimited field");
          }
          this.pos += length;
          return;
        }
        case WT_32:
          if (this.len - this.pos < 4) throw new RangeError("Truncated fixed32 field");
          this.pos += 4;
          return;
        default:
          throw new Error("Invalid wire value");
      }
    }

    skip(wireType) {
      const start = this.pos;
      if (wireType === WT_EGROUP) throw new Error("Unexpected end-group tag");
      if (wireType !== WT_SGROUP) {
        this._skipValue(wireType);
        return this.buf.subarray(start, this.pos);
      }

      const stack = [this.lastFieldNo];
      if (stack.length > this.maxDepth) throw new RangeError("Protobuf group nesting limit exceeded");
      while (stack.length) {
        const rawTag = this._readVarintRaw().value;
        if (!Number.isSafeInteger(rawTag)) throw new RangeError("Invalid group tag");
        const fieldNo = Math.floor(rawTag / 8);
        const nestedWireType = rawTag % 8;
        if (fieldNo < 1 || fieldNo > 536870911 || nestedWireType > WT_32) {
          throw new Error("Invalid group tag");
        }
        if (nestedWireType === WT_EGROUP) {
          if (stack.pop() !== fieldNo) throw new Error("Mismatched protobuf end-group tag");
        } else if (nestedWireType === WT_SGROUP) {
          stack.push(fieldNo);
          if (stack.length > this.maxDepth) throw new RangeError("Protobuf group nesting limit exceeded");
        } else {
          this._skipValue(nestedWireType);
        }
      }
      return this.buf.subarray(start, this.pos);
    }
  }

  class SafeWireWriter {
    constructor() {
      this.chunks = [];
      this.scratch = [];
    }

    _flushScratch() {
      if (this.scratch.length) {
        this.chunks.push(new Uint8Array(this.scratch));
        this.scratch = [];
      }
    }

    varintNumber(value) {
      if (!Number.isSafeInteger(value)) throw new RangeError("Writer requires a safe integer");
      if (value < 0) {
        if (typeof BigInt !== "function") throw new Error("BigInt is required for negative int64 values");
        let big = BigInt(value) & ((1n << 64n) - 1n);
        while (big > 0x7fn) {
          this.scratch.push(Number((big & 0x7fn) | 0x80n));
          big >>= 7n;
        }
        this.scratch.push(Number(big));
        return this;
      }
      let v = value;
      while (v > 127) {
        this.scratch.push((v % 128) | 0x80);
        v = Math.floor(v / 128);
      }
      this.scratch.push(v);
      return this;
    }

    tag(fieldNo, wireType) {
      if (!Number.isInteger(fieldNo) || fieldNo < 1 || fieldNo > 536870911 ||
          !Number.isInteger(wireType) || wireType < 0 || wireType > 5 ||
          wireType === WT_SGROUP || wireType === WT_EGROUP) {
        throw new RangeError("Invalid protobuf field tag");
      }
      return this.varintNumber(fieldNo * 8 + wireType);
    }

    raw(bytes) {
      if (!bytes || bytes.length === 0) return this;
      this._flushScratch();
      this.chunks.push(bytes);
      return this;
    }

    bytes(payload) {
      if (!(payload instanceof Uint8Array)) throw new TypeError("Expected Uint8Array payload");
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
      if (!this.chunks.length) return new Uint8Array(0);
      if (this.chunks.length === 1) return this.chunks[0];
      let total = 0;
      for (const chunk of this.chunks) {
        total += chunk.length;
        if (!Number.isSafeInteger(total)) throw new RangeError("Encoded message is too large");
      }
      const out = new Uint8Array(total);
      let offset = 0;
      for (const chunk of this.chunks) {
        out.set(chunk, offset);
        offset += chunk.length;
      }
      return out;
    }
  }

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
      if (fn === 7) continue;
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
    w.tag(11, WT_VARINT).varintNumber(3);
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
      if (fn === 1 && wt === WT_LEN) captionTracks.push(r.bytes());
      else if (fn === 2 && wt === WT_LEN) audioTracks.push(r.bytes());
      else if (fn === 3 && wt === WT_LEN) r.skip(wt);
      else otherFields.push([fn, wt, r.skip(wt)]);
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
    for (const tb of updatedCaptionTracks) w.tag(1, WT_LEN).bytes(tb);
    for (const ab of audioTracks) w.tag(2, WT_LEN).bytes(patchAudioTrack(ab, targetTrackIndex));
    for (const [code, label] of Object.entries(TRANSLATION_LANGS)) {
      const tlBytes = new SafeWireWriter()
        .tag(1, WT_LEN).string(code)
        .tag(2, WT_LEN).bytes(buildLabelBytes(label))
        .finish();
      w.tag(3, WT_LEN).bytes(tlBytes);
    }
    for (const [fn, wt, raw] of otherFields) w.tag(fn, wt).raw(raw);
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
    49399797,
    50195462,
    51431404,
    51779735,
    51845067,
    58173949,
    58174010
  ]);

  function filterFeedPayload(bytes, cache, opts, parentFieldNo = 0) {
    const r = new SafeWireReader(bytes);
    const w = new SafeWireWriter();
    let modified = false;

    while (!r.eof()) {
      const [fn, wt] = r.tag();

      if (opts.blockShortsFeed && fn === 51431404 && wt === WT_LEN) {
        r.skip(wt);
        modified = true;
        continue;
      }

      if ((parentFieldNo === 50195462 || parentFieldNo === 51431404) && fn === 1 && wt === WT_LEN) {
        const itemBytes = r.bytes();
        if (isRichItemBlocked(itemBytes, cache, opts)) {
          modified = true;
          continue;
        }
        w.tag(fn, wt).bytes(itemBytes);
        continue;
      }

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
          w.tag(fn, wt).bytes(subBytes);
        }
        continue;
      }

      w.tag(fn, wt).raw(r.skip(wt));
    }

    return { bytes: modified ? w.finish() : bytes, modified };
  }

  function neutralizeOnesieHotConfig(onesieBytes) {
    const r = new SafeWireReader(onesieBytes);
    const w = new SafeWireWriter();
    while (!r.eof()) {
      const [fn, wt] = r.tag();
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
      .tag(2, WT_VARINT).bool(true)
      .tag(3, WT_VARINT).bool(true)
      .tag(9, WT_VARINT).bool(true)
      .tag(10, WT_VARINT).bool(true)
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
    if (typeof $response === "undefined" || !$response) {
      $done({});
      return;
    }

    const url = (typeof $request !== "undefined" && $request.url) || "";
    const headers = ($response && $response.headers) || {};
    const contentType = String(headers["Content-Type"] || headers["content-type"] || "").toLowerCase();

    // 1. Google Search Web HTML
    if (url.includes("google.") && url.includes("/search?")) {
      const html = getTextBody($response);
      if (!html) return $done({});
      const res = processGoogleSearchHtml(html);
      return res.modified ? $done({ body: res.body }) : $done({});
    }

    // 2. X (Twitter) GraphQL & REST JSON
    if (url.includes("x.com") || url.includes("twitter.com")) {
      const text = getTextBody($response);
      if (!text) return $done({});
      const res = processXJsonString(text);
      return res.modified ? $done({ body: res.body }) : $done({});
    }

    // 3. Instagram GraphQL & REST JSON
    if (url.includes("instagram.com")) {
      const text = getTextBody($response);
      if (!text) return $done({});
      const res = processInstagramJsonString(text);
      return res.modified ? $done({ body: res.body }) : $done({});
    }

    // 4. YouTube (Auto-detect Binary Protobuf vs Web JSON Fallback)
    if (url.includes("youtubei.googleapis.com") || url.includes("youtube.com")) {
      const bin = getBinaryBody($response);
      const isJsonContent =
        contentType.includes("json") ||
        (typeof $response.body === "string" && $response.body.trim().startsWith("{")) ||
        (bin && bin.length > 0 && bin[0] === 0x7b); // 0x7b === '{'

      if (isJsonContent) {
        const text = getTextBody($response);
        if (!text) return $done({});
        // Only suppress the Shorts shelf on the YouTube home browse feed.
        const res = processYouTubeJsonString(text, url.includes("/browse") && /browseId=FEwhat_to_watch|browseId%3DFEwhat_to_watch/.test(url));
        return res.modified ? $done({ body: res.body }) : $done({});
      }

      if (!bin || bin.length === 0) return $done({});

      const opts = parseRuntimeOptions();
      const cache = loadAdCache();
      let res = { bytes: bin, modified: false };

      if (url.includes("/player")) {
        res = processPlayer(bin, opts);
      } else if (url.includes("/browse") || url.includes("/next") || url.includes("/search")) {
        res = filterFeedPayload(bin, cache, opts, 0);
      } else if (url.includes("/reel_watch_sequence")) {
        res = processShorts(bin);
      } else if (url.includes("/guide")) {
        res = processGuide(bin, opts);
      } else if (url.includes("/get_setting")) {
        res = processSetting(bin);
      } else if (url.includes("/get_watch")) {
        res = processWatch(bin, cache, opts);
      } else if (url.includes("/config") || url.includes("/log_event")) {
        res = processConfigPayload(bin);
      }

      if (cache.dirty) saveAdCache(cache);
      return res.modified && res.bytes ? $done({ body: res.bytes }) : $done({});
    }

    $done({});
  }

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
      processGoogleSearchHtml,
      processXJsonString,
      processInstagramJsonString,
      processYouTubeJsonString,
      loadAdCache,
      DEFAULT_OPTS
    };
  } else {
    try {
      dispatch();
    } catch (e) {
      console.log(`[SR-AIO-Pro] ${e}`);
      $done({});
    }
  }
})();