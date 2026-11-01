# YouTube Protobuf — Shadowrocket maintenance track

This directory is the isolated maintenance track for the repository's YouTube Protobuf response filter.

## Status

- Stage: baseline audit and migration preparation.
- Runtime: Shadowrocket only is the target.
- The existing production script at `modules/adblock/scripts/youtube_protobuf_response_filter.js` remains unchanged.
- The existing module entry at `modules/AdBlock.sgmodule` remains unchanged.
- No change is made to `shadowrocket/ss.conf`.
- Do not switch production references until parity tests and an actual Shadowrocket device test pass.

## Source and licensing

The current script is a derivative of the Maasea upstream script. Required copyright notices, license text, and modification notices must remain available. The repository retains the upstream Apache-2.0 license at `modules/adblock/LICENSE-APACHE-2.0-Maasea`. This project may maintain its own release history and Shadowrocket-specific changes, but must not represent upstream-authored portions as original authorship.

## Migration objective

Keep the behavior of the current script while removing unused client adapters and maintaining only the Shadowrocket runtime adapter. Do not remove a behavior merely because it is not directly an ad-filtering feature. Each existing behavior must be mapped and regression-tested before any deletion or rewrite.

## Required behavior inventory

The baseline audit is recorded in [AUDIT.md](./AUDIT.md). At minimum, migration must preserve:

- Protobuf binary decoding and encoding, including safe handling of unknown fields.
- Browse / next / search response handling and feed-ad recognition/cache behavior.
- Player response handling, including ad placement and playback-tracking cleanup.
- Shorts / reel response handling.
- Guide and settings response handling.
- Get-watch response handling.
- Config and log-event handling, including Onesie hot-config key caching.
- Caption/subtitle parameter behavior.
- Background playback and picture-in-picture related behavior.
- Persistent state, argument parsing, and fail-open response completion.

## Safety and rollout

1. Keep the current production file as the immutable comparison baseline during development.
2. Build the Shadowrocket-only candidate as a separate file in this directory.
3. Compare old and new outputs on sanitized fixtures for every supported message path.
4. Require byte-for-byte pass-through when parsing fails or a message is not recognized.
5. Verify persistent-state migration and Onesie key-cache behavior.
6. Run static syntax checks and fixture tests.
7. Test on Shadowrocket with YouTube before changing the module's script-path.
8. Only then propose a separate production switch. No automatic switch is authorized by this staging branch.


## Repository-branded baseline

A repository-branded copy is staged at `instarrys_youtube_protobuf_filter.js`. It changes the project header and user-facing diagnostic labels while preserving the upstream attribution and license notice. It is not yet wired into the production module and has not been device-tested. The original production script remains the comparison baseline.
