# F334: restore the proven qdrv hardware profile for the one-boot diagnostic

Prepared on 2026-09-21. F334 is an offline, versioned diagnostic candidate;
physical installation and capture are separate results. It retains the F325
20-second single-boot capture and mandatory exact F321 return.

## Observed failure and exact cause

F326 was written and verified in
`outputs/flash-watch/f325-ethernet-20260921T103704Z-59134aab/`, then failed the
platform gate with `beacon-preflight-readback`. Its final cycle result is
`FAIL_F325_EXACT_F321_RESTORED`. Exact F321 restoration, full-slot CRC
`6ed8e483`, complete candidate comparison, platform 27/27, unchanged firewall
permission, process containment and lease release all passed. Capture was not
reached. Preserve the failed diagnostic result and successful return separately.

The F315 external-qdrv donor used by F325/F326 was built from the generic
`quantenna-v6-scheduler-diag/qdrv` subdirectory without the parent build's
`OPENMITRASTAR_QDRV_V89_PAIR` define. Its ELF has one 20-byte parameter entry,
`tqe_sem_en`; it lacks the beacon and other HGW-specific parameters.
`qdrv_openmitrastar_beacon_preflight_enabled()` is a four-byte return-zero stub.

The exact F321 qdrv, SHA-256
`0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff`, instead has
14 parameter entries and a 48-byte functional preflight helper. Root's pinned
read-only observation confirms both beacon parameters read `Y` on F321.

The accompanying `fs/sysfs/group.c:59` warning is separate: `tqe_sem_en` has
legacy permission `0700`, whose executable bit sysfs rejects/clamps. F321 has
the same permission. F334 preserves it and does not misrepresent that warning
as a corrupted parameter layout or the cause of the missing beacon setting.

## Corrected qdrv inputs

The F321 source/profile provenance is the canonical `quantenna` tree and
`outputs/kernel-port/quantenna-linux510-radiohw-txpool-trace-f155-20260831/`.
F334 uses an isolated clone at
`work/linux510-radio-port/quantenna-f334-f321-profile/`, restoring the small
later F168 TX-pool option change to the baseline source behavior.

The inherited defines apply to every qdrv object:

```text
OPENMITRASTAR_QDRV_V89_PAIR=1
OPENMITRASTAR_SWITCH_EMAC_PORT=1
OPENMITRASTAR_SWITCH_EMAC_NO_PHY=1
```

The target kernel configuration is byte-identical to F321, SHA-256
`cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e`.
The target `vmlinux` is also byte-identical to the F321 sidecar, SHA-256
`8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc`.

The baseline rebuild comparison covers 783 functions. After masking relocation
fields, 782 match the installed qdrv. The sole differing function is the
266-byte `qdrv_wps_button_read`: its task signal offsets change from 168/176
to 182/190. Those latter offsets are directly used by the installed F321
kernel's `recalc_sigpending_tsk`. The C operation was not changed and obsolete
offsets were not forced to obtain a cosmetic binary match. Full `.text`
identity is explicitly false; this target-kernel ABI difference is preserved
in the comparison and qualification evidence.

Only the radar compatibility object is removed from the corrected qdrv link.
The resulting module depends on the unchanged F325 shadow provider through
the established radar ABI. It does not activate DFS callbacks or transmission.

Module evidence:
`outputs/kernel-port/f334-qdrv-profile-20260921T105936Z/`.

- qdrv: 681,672 bytes, SHA-256
  `ec787ee6877638dc2b48dabf385e5f4f9e94d6f631e460608b75eeb2e899a625`.
- Two complete external-qdrv builds are byte-identical.
- All 14 parameter names and permissions match F321.
- The seven actual load arguments resolve to five integer parameter operations
  and the two correct boolean beacon operations. Both strict `Y` readbacks
  remain in the packed startup script.
- The packed script reads qdrv's digest from the updated driver contract and
  contains no embedded old `1dda...` donor hash.
- Full packed check:
  `outputs/preflight/f334-qdrv-profile-20260921T105210Z/packed-port-gate.json`.

## Immutable firmware candidate

Private directory:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f334-f321-radar-once-device-bound`.

- File: `openmitrastar-linux510-f334-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Bytes: 5,332,992.
- SHA-256: `e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec`.
- RAM CRC32: `1d9146bc`; expected complete-slot CRC32: `cc7d1938`.
- Locally calculated complete-slot SHA-256:
  `6f9596e3025d9aaa50fd4996561d2102622104080ed33c50e6d3dab5c744b55d`.
  This is not a hardware measurement.
- Product: `lyoko-foundation-6.9.5-f334-radar-once-f321-device`.
- Firmware build: `aa3e7af55f4c6db8`; unchanged UI build: `72dd5d1877544af9`.
- Manifest SHA-256:
  `0795f398d09de8346ce29468633e9f90a264f2fbba676b09d554089a20c0d1a9`.
- Complete inventory SHA-256:
  `c658c7e048e23030c1631d3aea697b029b272e85af27c11b76b137f1b490cf24`.

Build evidence: `outputs/preflight/f334-shadow-build-20260921T110903Z/result.json`.
Independent reproduction:
`outputs/preflight/f334-shadow-repro-20260921T111001Z/result.json`.
Image, rootfs, complete slot, kernel, DTB, configuration and metadata inventory
all compare identically. Bootbase and slot-fit pass. All 39 catalogue entries
pass before packing and after extraction. The Linux catalogue suite passes
45/45, including a real SquashFS round trip and unchanged strict readbacks.

## Execution boundary

The new owner-delegated firmware/network/existing-permission records are in
`outputs/authorizations/f334-executor-20260921T111605Z/`. Their prose explicitly
states the agent bound the new hashes after verification; it does not claim
the owner dictated a digest. The interface, Python executable, existing
Windows rule and permission fingerprint are unchanged.

Executor preparation and new reviews are under
`outputs/preflight/f334-executor-20260921T111605Z/`. Earlier F326 images,
authorizations, 86-source snapshots and physical results remain untouched.
The protocol still uses F325 filenames/environment keys. Promotion ACK is
`OPENMITRASTAR_F334_MTD4_E18B221D`; exact F321 return ACK remains unchanged.

Only `mtd4/linux_live` is a write target. The native provider remains unarmed at
boot, may capture once under its existing software deadline, and must return
to F321 after the diagnostic. No CAC, radar decision, NOP, weather, client
traffic or release acceptance is granted by these offline results.

Final executor qualification: **205/205 UART/context and 685/685 Ethernet**.
The first Ethernet report preserves 684 PASS and one source-pin failure; the
guard was rebound to the reviewed F334 context source without relaxing checks.
The final review is `ethernet-executor-review.json` in the preparation directory,
SHA-256 `b63ea0f0fe901bc0430bc841ec3a0511d2998c9d81215c27978cfed4904d776f`.
Its 86 sources are frozen in `final-source-snapshot/`.

The one-use launcher is
`outputs/launchers/f334-executor-20260921T111605Z/launch.ps1`, SHA-256
`e4a40e0439ed06d06fa09a12086cb8722eba11571176e73eb9063ff2d8edb211`.
Its file-only default was verified without consuming its execution claim.
Execution requires `-Execute` and that exact self hash; it uses the existing
permission directly and contains no elevation path. The parent operator owns
any physical launch and its subsequent results.
