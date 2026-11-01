# Baseline audit — YouTube Protobuf response filter

## Repository snapshot

- Repository: `instarrys-bit/default`
- Branch: `main` baseline, staged on `youtube-protobuf-shadowrocket`
- Script: `modules/adblock/scripts/youtube_protobuf_response_filter.js`
- Baseline blob SHA: `845cdec96cc536b0cee55ff70de64573ef6f0785`
- Baseline size observed: 133,487 characters
- Module entry: `modules/AdBlock.sgmodule`
- Module entry blob SHA at audit: `a3ab68f4b09e2a6e40fc3a630fd013bf4fde4bf8`
- Upstream license file: `modules/adblock/LICENSE-APACHE-2.0-Maasea`
- License blob SHA at audit: `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`

The production script, module entry, license file, README, and `shadowrocket/ss.conf` have not been modified in this staging step.

## External code loading and network access

Static scan of the script found:

- No dynamic `import()`.
- No CommonJS `require()`.
- No `eval()` or `Function()` constructor invocation.
- The only literal HTTP(S) URL is a Protobuf-ts documentation URL in a comment; it is not a runtime script source.
- The source contains three occurrences of a method named `fetch`, but these are client-adapter methods. They dispatch to client networking APIs; they are not evidence of fetching and executing remote JavaScript.
- The Shadowrocket adapter's fetch implementation calls `$httpClient`; other adapters call `$task.fetch`. Their actual runtime call sites must be traced before removing or retaining any network capability.

Conclusion: no remote JavaScript loader was identified in this file. This does not prove the entire module has no network activity; the script contains client network adapters and the module itself makes HTTP requests to YouTube endpoints as part of its interception rules.

## Client adapters found

The bundled runtime contains a common adapter selector and implementations for:

- Surge: `$persistentStore`, `$httpClient`, `$notification`, and binary body mapping.
- Quantumult X: `$prefs`, `$task.fetch`, `$notify`, and ArrayBuffer / Uint8Array conversion.
- Loon: extends the Surge-style adapter and uses its argument representation.
- The common selector chooses Loon when `$loon` exists, Quantumult X when `$task` exists, and otherwise defaults to the Surge adapter.

The target migration is to retain one Shadowrocket-compatible adapter only. The exact Shadowrocket API contract must be verified against the current Shadowrocket script environment before deleting or rewriting adapter code. In particular, persistent storage, binary response body access, notifications, argument parsing, and request completion must be checked.

## Message paths and behavior that must be preserved

The Protobuf dispatch table currently recognizes these paths:

| Path | Handler | Required audit focus |
|---|---|---|
| `browse` | feed handler | ad recognition, unknown-field preservation, feed cache |
| `next` | feed handler | continuation/feed ad filtering and cache |
| `player` | player handler | ad placements, ad slots, playback tracking, player capabilities |
| `search` | feed handler | sponsored/injected result handling |
| `reel_watch_sequence` | reel handler | Shorts/reel response behavior |
| `guide` | guide handler | navigation/guide response behavior |
| `get_setting` | settings handler | settings and background playback-related fields |
| `get_watch` | watch handler | Shorts/watch contents and ad cleanup |
| `config` | Onesie config handler | hot-config extraction and persistent key cache |
| `log_event` | Onesie config handler | config/key cache path |

Additional behavior identified in the bundle:

- Protobuf runtime and generated message schemas.
- Unknown-field read/write support.
- Feed-ad field-number and EML allow/block caches.
- Shorts/reel entry handling.
- Caption-language parameter handling.
- Background playback and picture-in-picture related player/settings fields.
- Onesie hot-config fields: `clientKey`, `encryptKey`, `keyExpiresInSeconds`, and `useHotConfigToCreateOnesieRequest`.
- Persistent stores named `YouTubeConfig` and `YouTubeAdvertiseInfo`.
- YouTube Music vs regular YouTube state separation based on the request User-Agent.
- Fail-safe top-level completion path that calls the client adapter's completion method.

This is a static inventory, not yet proof that every branch works on the current YouTube iOS client. Each item requires fixture coverage and device verification.

## Current module entry observation

`modules/AdBlock.sgmodule` already points the YouTube Protobuf script to this repository's GitHub Raw URL. It also contains a separate initplayback observer and a separate social/search JSON script. The module includes its own request interception and MITM declarations. This migration step does not edit that module or enable it.

The user has previously stated that the main Shadowrocket configuration is user-controlled and must remain untouched without explicit approval. Therefore `shadowrocket/ss.conf` is out of scope.

## Implementation gates

Do not remove code or switch the live script reference until all gates pass:

1. Build a feature-to-code mapping for every handler and state mutation.
2. Confirm the exact Shadowrocket APIs for binary body, persistent storage, arguments, network helper, and completion.
3. Implement a separate Shadowrocket-only candidate; keep the current file as comparison baseline.
4. Create sanitized fixtures for every message path and malformed/unknown messages.
5. Compare output semantics and persistent-state changes old vs candidate.
6. Verify parse errors and unrecognized paths pass through unchanged.
7. Run syntax checks and fixture regression tests.
8. Perform Shadowrocket device testing with the current YouTube app.
9. Only after explicit review, update `modules/AdBlock.sgmodule` to the candidate path.

No production switch is performed by this audit.
