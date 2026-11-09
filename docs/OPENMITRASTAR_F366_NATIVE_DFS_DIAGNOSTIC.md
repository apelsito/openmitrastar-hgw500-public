# F366 native DFS pipeline on the F365 baseline

2026-09-22. Status: **PASS_OFFLINE_NATIVE_DFS_DIAGNOSTIC_IMAGE**.
This is a concrete diagnostic image, not operational DFS or RF acceptance.
The implementation agent performed no SSH, UART, TFTP, flash or radio action.

## Immutable image

Private firmware directory: `f366-f365-native-dfs-diagnostic-device-bound/`.
Image: `openmitrastar-linux510-f366-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.

| Property | Value |
| --- | --- |
| Bytes | 5,447,680 |
| SHA-256 | `6b9e77c56de0a374531e2e863f6bd7f5668cd2dd5e87fa0b6eb00f03c4449fe6` |
| Manifest SHA-256 | `06d86b53aa9cccb25679ad247d529a7b5c9e59f50a104e032d5da1dd0b45292e` |
| Product | `lyoko-foundation-6.10.2-f366-native-dfs-diagnostic` |
| Build | `b613d9254bb9a8ea` |
| Bootbase / slot fit | PASS / PASS |
| Independent full compositions | Two, byte-identical |
| Prefix CRC32 | `f314db74` |
| Full slot CRC32 with preserved journal | `5ac61b5e` |
| Full slot SHA-256 | `5282193da4e982b5a29c9025795da2c5a6500322c1e3fa20921d45773cf2979a` |
| Space before store boundary | 712,704 bytes |

Authoritative build result is private
`analysis/f366-fullimage-20260922T093933Z/result.json`.
Its `runtime_bindings` contains the fifteen exact installed paths/hashes for
the root physical executor. It also contains the recovery image, retained
journal binding, module closure and runtime test bindings.

The exact fallback is F365, 5,382,144 bytes,
SHA-256 `43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
prefix CRC32 `b858f5da`, full-slot CRC32 `118901d4`. The same sequence2 journal
has CRC32 `5d2ee646`. Root must bind current accepted physical F365 evidence
before executing the separately qualified campaign. Offline composition does
not establish physical installation or recovery.

## What is integrated

F366 reuses the existing F333 acquisition, F331 GPL postfilter and the exact
F338 userspace OEM preprocessing/classifier binary. It does not replace those
algorithms with stubs, synthesized pulses or a new detector.

The native qdrv source begins with F364, which is the actual F365 qdrv source.
Only six source files differ: the module object list, native radar adapter,
the qualified F332 readiness and F338 availability helpers, their existing
test harness, and the provider-drain call in the unretained teardown path.
The F355 lifetime implementation and F363 thermal/WPS sources remain exact.
No F344 managed-mode changes are imported.

The provider is a versioned F341 source copy. Only its module, proc and log
identity changes. Its `/dev/om-radar-f338` wire ABI and
`openmitrastar.f341-provider/v1` telemetry ABI remain unchanged. F366's status
helper emits `openmitrastar.f366-status/v1`. GPL kernel code remains in the
kernel; original proprietary OEM math remains in the separate userspace
process. No license string or GPL-only import check is relaxed.

| Component | Bytes | SHA-256 |
| --- | ---: | --- |
| qdrv | 689,696 | `c179de4e167a53127cab945577766f685e60400522ae3e6583f5a7601dfdae35` |
| `qtn_radar_f366.ko` | 69,604 | `a92a14b119857c8ab0680bdc1b51538b11e1459de9b36e157f894589aa2ecd39` |
| `om-radar-engine-f366` | 75,212 | `737cbdfeb429caba42929374c4a22eab549791c6af42fb3149c5ad64c048c85b` |

Both changed modules were rebuilt twice against an isolated copy of the actual
F363/F365 kernel context, not the older F340 closure. The exact F365 kernel,
configuration, DT, F352 Ethernet, watchdog supervisor, F365 temperature module,
temperature helpers, journal, identity and other existing modules are retained.
The complete installed graph of 41 modules resolves 1,977 imports, has no
dependency cycle, and passes export ownership and GPL-only/taint checks.
qdrv's fourteen parameters and beacon profile match F365; protected lifetime,
temperature and WPS functions are byte-equivalent after relocation masking.

Component result:
`/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/result.json`.
Source: `work/kernel-port/f366/source-manifest.json`.

## Startup and diagnostic boundary

Normal boot retains Ethernet, 2.4 GHz, management, storage and the inactive
temperature provider. The 5 GHz entrypoint reports pending and returns without
loading qdrv, the native provider or the OEM service. This prevents an unsafe
attempt to replace the pinned F355 radio after normal startup.

The one-attempt-per-boot controller is:

```text
om-f366-diagnostic activate TOKEN32
```

This is a contract for the root-owned physical runner, not a request to execute
it outside that campaign. The unchanged supervisor's live ARM acknowledgement
must prove its FD, hardware enable and first pet before module loading. The
session remains bounded to 180,000 ms with the existing phase deadlines.

The native ladder is derived from the actual F365 `om-radio5-start`, preserving
its sensor admission, calibrated profile, management checks and module order.
It adds the qualified provider/service order and F341 watchdog phase hooks.
The private ladder independently checks the live watchdog before loading any
native dependency. The old asynchronous AP rollback timer is removed so it
cannot race the diagnostic owner.

Only channel36/BW80 is admitted. Module arguments include `hardware_enable=1`,
`diagnostic_capture=1`, `authoritative_enable=0`; compiled
`F338_RELEASE_QUALIFIED=0` rejects authority even if a caller requests it.
The OEM engine starts before native `radar_start`. Twenty allowlisted JSON
observations stream to host stdout before CEASE, preserving evidence across the
mandatory reboot. Errors emit a bounded failure marker and available status
before CEASE. No pulse arrays, calibration, credentials or client addresses
are emitted by these status helpers.

`STOP_DIAGNOSTIC` joins software work and callbacks; it does not prove hardware
producer quiescence. Both dirty provider and F355 qdrv remain pinned. CEASE
retains the watchdog FD and stops feeding. The physical runner must observe
the reset, restore exact F365, and verify management and the preserved store.

## Validation and remaining work

The existing actual-C F338 readiness/availability and teardown harnesses pass
against the transplanted source. Runtime evidence
`outputs/preflight/f366-runtime-20260922T093744Z/result.json` passes 25 shell
checks plus actual F340 IPC ARM/phase/CEASE exchanges with explicitly fake
watchdog and radio backends. The image verifies all catalogues and the complete
rootfs inventory before and after two independent repacks. Exactly fifteen
rootfs paths are added or changed.

The minimum remaining sequence is:

1. Physically qualify this native acquisition/service pipeline and its actual
   latency/errors under the bounded watchdog campaign, then verify exact F365
   recovery. An advancing job counter alone is not RF classification proof.
2. Complete physical detection, detector-loss/return and recovery evidence.
   Confirm RF silence before any DFS authority is enabled.
3. Build a separately versioned operational candidate using the already present
   native readiness/availability/CAC/NOP machinery. Its watchdog/campaign must
   support the required 600-second weather CAC and 1,800-second NOP; F366's
   180-second diagnostic session cannot qualify them.
4. Prove CAC silence, continuous detection, radar evacuation, NOP persistence,
   non-DFS return, client bidirectional traffic and soak on the real HGW.

The underlying qualified qdrv retains its existing 70/600-second CAC and
1,800-second NOP logic. F366 neither shortens them nor enables authority to
claim they have passed. Operational DFS and release acceptance remain open.
