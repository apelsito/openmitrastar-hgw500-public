# F370 TQE result observation - 2026-10-21

Updated milestone: F370 has now been linked and qualified as a complete module.
See `docs/OPENMITRASTAR_F370_COMPLETE_MODULE_20261021.md`. The historical
source/object stage below remains the evidence for that earlier milestone.
F372 packages the qualified module in a full image, still physically UNRUN.
Neither F370 nor F372 has been loaded on the HGW.

F370 is an offline source/object candidate based on the exact F365 qdrv lineage.
It is not a linked module or firmware image and has not been loaded on the HGW.
F369 remains a separate STORE38 correctness candidate; TX BA policy is unchanged.

The source manifest is `work/kernel-port/f370-tqe-observation/source-manifest.json`.
Only `source/qdrv/qdrv_tx.c` changes, SHA256
`b8944de325340e2ae9fea75157f50b0c06c12672314cc49327cef1763b98c38f`.
Four saturating, read-only module counters record raw OK, other results, BUSY
followed by the existing qdrv free, and the existing success return. They add
no allocation or per-packet logging and preserve the original condition,
packet/node ownership, return, RF, queue and aggregation policy. Counters are
approximate under concurrent callers; they do not prove packet delivery.

The actual baseline and candidate AuC function fixture passes 12 cases and
87 checks. It compares frees, station release, call count and return for OK,
BUSY, other results, target/non-target and data/management, plus saturation.
Evidence: `outputs/rea/arc700-20261021-r2/f370-fixture/result.json`.

The ARC object gate compiles qdrv_tx baseline and candidate twice. Forty-seven
unambiguous baseline function bodies match exact F365 qdrv bytes; three names
are ambiguous and excluded. Candidate objects are byte-identical, 44436 bytes,
SHA256 `99c30326175a8374460fb5093f95ca13d3e75217efacbe07d6d43c88f42f2ebe`.
All 78 object imports are unchanged. Evidence:
`outputs/rea/arc700-20261021-r2/f370-objects/result.json`.
Source pins were checked after compilation. Object success does not establish
complete module metadata, ABI closure, firmware packaging or physical behavior.

REA inspected the exact active F365 qdrv and exact switch_tqe dependency using
the local ARC/Ghidra lane. Derived linked ELF files contain synthetic external
addresses and must never be installed, booted or included in firmware.

- `f365-rea-auc-tx/rea.json`: tqe_tx returns BUSY, qdrv frees skb and reports success.
- `tqe-rea-tx/rea.json`: missing HBM payload returns BUSY without consuming skb;
  oversize returns OK after discard; accepted path consumes the original skb
  and actively waits for the send register busy bit before publication.

These are static observations, not observed physical pool exhaustion or hang.
F370 counters after tqe_tx cannot observe completion of a call stuck inside that
wait. Raw OK is consumption, not RF success. Returning raw NETDEV_TX_BUSY from
this qdisc path would not implement an ownership-safe queue or wakeup.

The next physical discriminator is a real WPA2 client, matched bidirectional
transfers and reconnection/soak while observing existing AuC/HBM/EMAC/GSO counters.
Installing an observation module needs a linked-module contract, immutable image,
current physical binding/protection/readback and its recovery gates. F355 still
pins qdrv after mutation; no hot reload of a started instance is claimed.

The owner deferred the current mobile test because they could not perform it.
As last observed, exact F365 modules remain active in RAM on F367r9, channel36/80,
RF1/carrier1/hostapdPONG, 2.4 GHz ENABLED, zero fatal markers and watchdog inactive.
That state is independent of F370 and disappears on reboot.

Detailed performance plan:
`outputs/rea/arc700-20261021-r2/performance-plan/README.md`.

Audit note: the historical objective script regenerated its fixed
`outputs/audit/lyoko-full-liberation-20260905.json` during this work. Previous
bytes were unavailable in Git or retained evidence, so no reconstruction was
invented. The timestamped 2026-10-21 audit/execution receipt is retained; its
historical F314-F319 scope is not the current physical device state.
