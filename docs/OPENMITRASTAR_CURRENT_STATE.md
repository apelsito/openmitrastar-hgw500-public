# OpenMitraStar Current State

Generated from live and artifact evidence: `2026-09-02T14:15:23.827659+00:00`.

## Physical Unit

- Firmware: `lyoko-foundation-3.7-f222-device`.
- Kernel: `5.10.260-openmitrastar-radiohw`.
- Boot state: `ready`.
- Degraded services: `none`.
- 2.4 GHz control plane: `ENABLED`.
- 5 GHz control plane: `ready`.
- Fatal markers: `0`.

The physical unit runs F222 from `mtd4/linux_live`. Its persistent flash,
readback, SquashFS boot, SSH identity, web/API protection and dual-radio
control-plane gates are hardware-proven.

## Recovery

- Current mtd3: `RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE`.
- Cause: valid kernel payload reaches Linux but cannot mount its rootfs.
- F194: offline Linux 5.10 safety-slot candidate, SHA-256 `231f01b44667e90accae4cf1b0561c72dcf66e8ccd86e57bd0f6728f21e4399e`.
- F194 provisioning contract: `WAITING_EXPLICIT_EXCEPTION_AUTHORIZATION`.
- F194 write authorization: `False`.

## Current Candidates

| Role | Version | Bytes | SHA-256 | Hardware |
|---|---|---:|---|---|
| Generic | F213 | 5201920 | `2fe1dbbca0e5bb065ce4147b94c8ee74cc2683bfe35a4bcb4a61b7d59a90e333` | NOT_RUN |
| Device-bound | F222 | 5206016 | `ab8f8727f3b1c29a312eddb21f1aa5bc9f474d7be91569f57c9230aaf1fc1c21` | PASS |
| Datapath experiment | F223 | 5206016 | `a63ccce69776732269ac4c08f29062c74b93eda945c88778ab63efd9215be2bc` | NOT_RUN |
| Foundation experiment | F231 | 5214208 | `d305221d6b60aac224fda793debeaa1dbd2cfd6f6722e746aead3b87a13fe111` | NOT_RUN |
| Quantenna control experiment | F233 | 5214208 | `16f90110a788b06b9f236afa2a419b8f5dd35d422668da273faaaac0d28dce04` | NOT_RUN |
| Superseded dual-radio experiment | F235 | 5214208 | `e8984886b169b49d8459b66cafd1c2445a63498a28c95f62211ddd7f841f5b5e` | NOT_RUN |
| Hardened control candidate | F237 | 5218304 | `46d7ab2fe356742854533834f69081b90701b95f1c163c86cb4afcbbb24607ed` | NOT_RUN |
| DFS observability experiment | F239 | 5218304 | `780562d937e3b8cb3a02dfe931cb9e1259570e21068ad9399ded0ec9a2feaea5` | NOT_RUN |
| Network observability experiment | F241 | 5218304 | `61f9d00c09e4146d816d48115910e216967e09a8b4115b4f1106d4af6f0aecbe` | NOT_RUN |
| Hardware provenance experiment | F243 | 5238784 | `b3e1d8b1577b38e2eda6b9b8d9cf2cadd88c8cbe909d765f33c02efc49227b75` | NOT_RUN |
| Package catalog experiment | F245 | 5238784 | `64ca0dae2f5dc49896bc228aa4d901a79a00a52d5d5fb5d6ef03569abfb4052b` | NOT_RUN |
| Integrated hold | F246 | 5238784 | `8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12` | NOT_RUN |
| Physical test candidate | F247 | 5238784 | `8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12` | NOT_RUN |
| OpenWrt package CLI experiment | F248 | 5242880 | `cffb237439c9240aef3e800d0a6308d79658e8becfa1e513c2341ec91170b273` | NOT_RUN |
| Integrated OpenWrt package hold | F249 | 5242880 | `3f6c5775abd93e6003c59fe425d6a8609c8fab5e1b9eca53f4975654e7f6618a` | NOT_RUN |
| LED control experiment | F250 | 5242880 | `df99f6cb40d62da2fa8180d87f2c1898cfdfb7cff42b79ea0f2124de72d8c9b2` | NOT_RUN |
| Integrated LED hold | F251 | 5242880 | `aa96a520099ac54a34b815143faf512be80b51280f6e9078402e340a2e937cb8` | NOT_RUN |
| Configuration-store experiment | F252 | 5242880 | `77efef238561251a94a87c2a788975cd51e5f82ddb25336a164df5cdd1da43a4` | NOT_RUN |
| Integrated configuration-store hold | F253 | 5242880 | `db533e42e9b35c242772a9b0b14660ab941b261b4ab6d866e2d4bf5f9e9f3c98` | NOT_RUN |
| Configuration-store status | F254 | 5242880 | `18c9f0c129266d39d5963fa25d614127acd48b9a0af6af7843673cde01ccff26` | NOT_RUN |
| Integrated configuration status hold | F255 | 5242880 | `cc230eb9a1458ef7bd6a0ff16312ce486668e6f90ba5b184421477cfd5ce4066` | NOT_RUN |
| Configuration-store API experiment | F256 | 5242880 | `2c9eba1b9fba5660668b3bc6a665261145c90d1e292e8f7659aa7bbf0f2ba0b8` | NOT_RUN |
| Integrated configuration API hold | F257 | 5242880 | `f9bf753d1c936f532db4b30d6c72d50901c11c0cf1de307f2392c447d008e966` | NOT_RUN |

F213 remains the latest shareable generic image. F222 is the installed private
device-bound image with stable SSH identity and the complete dashboard behind
the session gate. Its signed volatile package lifecycle is hardware-proven. It
is not yet a final release.

F223 is the next private datapath candidate. Its rootfs, kernel configuration
and DTB are byte-identical to F222; the only datapath change is the EMAC RX
ring from 128 to 256 descriptors. It is built and offline-verified but has not
been flashed or performance-tested.

F231 is the next private product candidate. It keeps the F222 kernel and the
F229 hardware/package surface, then makes the 5 GHz control contract match the
real Linux 5.10 image: status remains readable, while SSID/channel/bandwidth
stay fail-closed until a qcsapi-compatible control backend is present.

F233 adds an experimental native Quantenna control backend using the already
working WEXT and hostapd-qtn binaries. It supports only SSID, non-DFS channels
36/40/44/48 and 20/40/80 MHz through the existing transactional rollback path.
It is offline-only until a physical change/reconnect/rollback campaign passes.

F235/F236 are superseded by the adversarial review. They lacked a real
unconfirmed-change watchdog and had insufficient Quantenna process recovery.

F237 adds verified automatic rollback, explicit commit, PID ownership checks,
`PONG` plus `state=ENABLED`, fail-closed DFS staging and UI reset on contract
failure. F239 adds read-only DFS/CAC/regulatory observability. F241 adds
read-only multicast, IGMP and VLAN state. F243 adds exact input GPIO and LED
provider provenance while explicitly reporting absent thermal/watchdog/gpiochip
interfaces. F244 combines the exact F223 kernel with the exact F243 rootfs.
F245 adds authenticated signed-catalog queries, searchable package metadata and
the exact dependency plan before any volatile install. F246 combines the exact
F223 RX-ring-256 kernel with the exact F245 rootfs; it remains an offline hold.
F247 promotes those exact F246 bytes into a guarded hardware-test envelope and
adds an F222-to-mtd4 rollback tool. Its preflight currently blocks before flash
only because AELITA SSH is unavailable; router SSH, COM3 and the traffic server
are ready.
F248 continues on a separate offline branch with a fail-closed `opkg` subset
over `lyoko-pkg`; it does not supersede the frozen F247 physical candidate.
F249 combines that exact F248 rootfs with the exact F223 RX-ring-256 kernel and
remains an offline integration hold.
F250 adds a feature-gated, time-bounded LED identification operation with exact
snapshot restoration. It remains offline until a person observes the panel.
F251 combines the exact F250 rootfs with the exact F223 kernel and remains an
offline integration hold.
F252 adds a disabled JFFS2 A/B configuration journal validated entirely in a
file-backed simulation. F253 combines it with the exact F223 kernel.
F254 exposes only the journal status through authenticated API/UI; persistence
writes remain disabled and the store remains unmounted.
F255 combines the exact F254 rootfs with the exact F223 kernel.
F256 adds confirmed, feature-gated journal commit/rollback controls while the
physical writable store remains disabled.
F257 combines the exact F256 rootfs with the exact F223 kernel.

## Physical Radio Validation

- 2.4 GHz: three 32 MiB bidirectional runs passed transport; median
  `7.074` Mbps down and
  `16.218` Mbps up.
- NAPI-128 optimization decision: `NO_GO_RETAIN_F170_OR_ACCEPTED_F171`. The next driver
  change must target RX descriptor starvation rather than increasing NAPI
  weight again.
- 5 GHz: `PASS`, 32 MiB bidirectional plus 120-second
  continuity; `18.546` Mbps down and
  `22.097` Mbps up with
  `25` router samples.

## Storage

- F211 store format: `PASS`, `1835008` bytes, SHA-256 `d42427203214e3c304bb0f65c2586a0552d94f2a1a5abb23ab92ac0ab912d3b1`.
- F212 prefix-preserving update simulation: `PASS`.
- Full `mtd4` erase after store initialization: `False`.
- Runtime store writes remain disabled.
- Normal firmware updates erase only the `0x5e0000` firmware prefix of `mtd4`
  and preserve the `0x1c0000` `lyoko_store` tail.

## Release Blockers

- validate the device-label credential through a real browser session.
- restore AELITA SSH, then run the guarded F247 full physical campaign.
- validate F233 native Quantenna SSID/channel/bandwidth apply and rollback on hardware.
- validate F237 hardened Realtek and Quantenna transactions with real client reconnects and watchdog rollback.
- restore AELITA SSH and certify multicast/IGMP with bidirectional real traffic.
- provide an independent management path before attempting tagged VLAN traffic.
- certify DFS/CAC/radar behavior.
- validate F239 DFS readbacks against physical driver state before any regulated-channel test.
- validate F241 multicast/VLAN readbacks before isolated tagged and multicast traffic tests.
- run the guarded front-panel LED identification gate with an observer and record the physical colour/window mapping.
- validate F245 signed package queries and volatile package lifecycle on the physical unit.
- complete dual-radio 8-hour and 24-hour soaks.
