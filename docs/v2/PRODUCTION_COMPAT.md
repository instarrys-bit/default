# V2 Production — Isolated Deterministic Builder Compatibility

## Direct reuse

V2 runs the existing deterministic `scripts/build_rulesets.py` and its pinned helper bundle inside a temporary workspace outside the repository checkout. It copies only the required read-only inputs, the current ruleset baseline and the helper scripts. The builder is not rewritten or duplicated.

The sandbox:
- pins the complete Python builder bundle by SHA-256;
- pins the current source ledger, source registry, source snapshot, protected-domain list, production control policy, prior ruleset baseline and `modules/uu.conf`;
- copies sharded JSON manifests and all referenced shards;
- replaces the V1 repository lease guard only inside the temporary process with a temp-root-only guard;
- fixes the builder timestamp through an explicit `--as-of` value for reproducible output;
- rejects any changed input or write outside the seven declared ruleset/report outputs;
- verifies `modules/uu.conf` is byte-identical before and after the build.

## Output

The compatibility runner emits seven deterministic candidate files: DIRECT, PROXY, REJECT, ruleset manifest, pending queue, REJECT recheck queue and the REJECT secondary-review report. These are immutable candidate artifacts, not canonical repository outputs.

The builder preserves the existing deterministic evidence gates, config-scope conflict checks, REJECT secondary filtering, 30,000 published-rule cap and lifecycle queues. No AI review is introduced.

## Activation

Dry-run is the default. Durable staging requires an initialized V2 epoch, a Storage Management credential, a RUNNING V2 task lease and the matching active `storage/v2/artifacts` resource lease. The lease is revalidated before each artifact and before the final candidate manifest. No release commit or publication is performed by this adapter.
