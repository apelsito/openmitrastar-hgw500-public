# F366r3: restore OEM filter setup and observe the strict startup guard

2026-09-22. **PASS_OFFLINE_F366R3_NATIVE_START_IMAGE**. Physical acquisition
and exact F365 recovery remain separate root-owned gates. R3 does not claim
that the cause of the R2 rejection has already been observed on the device.

The R2 event record showed `qdrv_control_input_serialized` rejecting command
`radar` before its void API call. `(10)` is the command-table index, not errno.
`diagnostic_stopped=1` was observed after failure/cleanup and does not establish
that the latch prevented initial startup. R2 did not record the guard's RAM
fields, so its particular failing predicate cannot be reconstructed uniquely.

The producer review found a definite missing step. `ic_radar_bw` is configured
by `IEEE80211_PARAM_RADAR_BW=235`; that switch case assigns the value to RAM.
The OEM `buildroot/target/device/Quantenna/Ruby/scripts/start-vap` explicitly
uses `iwpriv wifi0 radar_bw 80` for Topaz80. `BW_HT80` is80. Our earlier loader
omitted this setup, while the R2 test fixture supplied80 directly. In contrast,
`ieee80211_get_bw()` queries the MuC through the driver and is not a suitable
extra accessor for a cached-only diagnostic snapshot.

The wlan artifact in the source tree is byte-identical to the actual F365 peer:
SHA-256 `f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f`.
Source, OEM script, enum/header and peer hashes are pinned in
`work/kernel-port/f366r3/source-manifest.json`.

R3 restores that exact setter under the existing watchdog phase before native
enable. It retains AP, channel36, radar filter80, exact `eu`, authority0 and
one admitted native attempt. The qdrv guard logs its cached values and precise
reason before rejection or API admission. It does not query the MuC, touch
new MMIO, print pointers/MACs, or relax an admission predicate.

The new observations are:

```text
OMF366_NATIVE_FILTER_CONFIG radar_bw=80 setter=ieee80211-param-235 authority=0
OMF366_NATIVE_GUARD revision=3 reason=allow core_started=1 vap_created=1 attempt_used=0 args_eu=1 mac_present=1 wlan_present=1 opmode=6 channel_valid=1 channel=36 radar_bw=80 phymode=13 reads=ram-only
```

The second line illustrates an admitted snapshot; the physical record must
supply the actual values. `phymode` is observed rather than synthesized or used
to explain the previous failure. Rejection reasons distinguish argument/order,
used attempt, missing MAC/wlan, role, channel and radar filter width.

The immutable result is private
`analysis/f366r3-fullimage-20260922T112259Z/result.json`.

| Property | Value |
| --- | --- |
| Image directory | `f366r3-f365-radar-filter-start-device-bound/` |
| Bytes | 5,451,776 |
| Image SHA-256 | `ca66ddf07a6a1ef4470a77ca85c4151354e9d7dd831abc7e5f02c1a53a8b5d2d` |
| Manifest SHA-256 | `166a519028c5e2463b12de7e8599f628ae9bf56b86da843691c6eba421027a2f` |
| Product | `lyoko-foundation-6.10.4-f366r3-radar-filter-start-diagnostic` |
| Build | `97737ec9efec7a28` |
| Prefix CRC32 | `2014b133` |
| Full-slot CRC32 | `94ddd37e` |
| Full-slot SHA-256 | `bf5fa7fe1ab116d3cedf9d3ab4bcc5eec253d3c4087f60a66f1bc5d9df796f13` |
| Headroom before store | 708,608 bytes |

Exact F365 remains the fallback: SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
full-slot CRC32 `118901d4`; the preserved journal is CRC32 `5d2ee646`.

Only the qdrv control source changes from R2. qdrv is691,708 bytes, SHA-256
`1f0ce9a2cb97c76a3d9f3354ed2d0ef388486d7957d919fa611f04e8daeaa235`.
Provider, original OEM userspace engine, kernel, DT and peers are reused exactly.
The double qdrv build, 1,977 imports across41 installed modules, GPL/taint,
original parameters, lifetime and protected-function checks pass. Two complete
image repacks, Bootbase, slot fit, all catalogues, inventory and stale-hash
checks also pass.

Offline tests are:

- `outputs/preflight/f366r3-guard-20260922T111743Z/result.json`:32 checks of
  the actual guard/handler and real RAM producer case, including zero filter,
  exact80 setup, every retained rejection family and single-attempt behavior.
- `outputs/preflight/f366r3-runtime-20260922T111916Z/result.json`:29 shell
  checks and six-phase actual F340 IPC with fake watchdog/radio backends.
- `outputs/preflight/f366r3-readback-20260922T111917Z/result.json`:five
  cases execute the actual loader block. Setter failure invokes no native API;
  asynchronous progress, absent start/readiness and invalid counters remain
  bounded without a repeated activation.

The physical campaign adds the separate observation of the exact Quantenna
U-Boot banner. That observer does not prove reset cause or alter recovery
commands, acquisition acceptance, masks or watchdog deadlines.
