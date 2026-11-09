# Recorded OpenMitraStar checkpoints

Extracted without removing checkpoint text from AGENTS.md on 2026-09-06.
These are dated observations, not proof of the device state today. Paths are
relative to the workspace root. Read the selected checkpoint only when needed.

## Latest checkpoint — 2026-09-05

- F314 is currently installed in physical `mtd4/linux_live`. It preserves the
  exact proven kernel and radio payload while adding fail-closed fixed-channel
  operation and 14 transactional Quantenna controls. Candidate SHA-256
  `a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11`,
  full-slot CRC32 `d6b13baa`, full-slot SHA-256
  `bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989`.
  A normal persistent reboot reached boot ready, SSH, 2.4 GHz enabled and 5 GHz
  ready on channel 36 with zero fatal markers. The physical control matrix is
  14/14 PASS with exact apply/readback/rollback; channel, bandwidth and TPC are
  correctly blocked until the radar provider is complete. Physical 5 GHz traffic
  passed at 34.026/26.949 Mbps with a clean 120-second soak; 2.4 GHz passed at
  approximately 18.998/13.104 Mbps. See
  `docs/OPENMITRASTAR_F314_CURRENT_STATE.md`.

- F315 packages the QT4 acquisition/classifier path in shadow mode. Its
  18-symbol provider cannot authorize DFS or invoke callbacks. The candidate is
  flash-capable but physical status is `NOT_RUN`; see
  `docs/OPENMITRASTAR_F315_CANDIDATE.md`.

- F316 is the active-capable DFS/CAC successor. Its native provider and qdrv
  link contract pass offline, but physical radar vectors, CAC, evacuation and
  NOP remain unproven. It must not replace F314 without a separately authorized
  guarded physical campaign; see `docs/OPENMITRASTAR_F316_CANDIDATE.md`.

- F317 adds the portable observe-only `lyoko-radiod`, HGW adapter, strict board
  profile and volatile A/B persistence backend. Candidate SHA-256
  `849e0ef6835cd4ad1ec78e9c0cf18fc94ca83970fdd3f8c6cd844a4220f6c84b`.
  It is deliberately non-flashable until F316 is physically proven; see
  `docs/OPENMITRASTAR_F317_CANDIDATE.md`.

- F318 is the portable two-eraseblock `lyoko_store` transaction core. It has no
  MMIO, MTD registration or SPI opcodes, exposes no global protection
  operation, and passed host/analyzer/ARC700 reproducibility gates. Its
  `libf318store.a` is 3,774 bytes with SHA-256
  `93950f425444f9bf236488fb072be6061028412c631071b406a9cc2a7ce50130`. Persistent
  writes remain disabled until a separate controller owner can prove exact
  per-block protection restoration; see
  `docs/OPENMITRASTAR_F318_STORE_TRANSACTION_CORE.md`.

- F319 is the claim-only SPI controller ownership probe. The 6,108-byte ARC700
  module has SHA-256
  `79436442b62110351fba44262a05ae0f2a9ffc87b36fabe74cc651112e431317`.
  It exclusively reserves and maps `0xe4030000+0x10000` but contains zero MMIO
  reads/writes, SPI opcodes or MTD registration. It is packaged without autoload
  in the non-flashable F314-derived candidate SHA-256
  `e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9`;
  its guarded runtime gate passes dry-run and hardware load is `NOT_RUN`. See
  `docs/OPENMITRASTAR_F319_SPI_OWNER_PROBE.md`.

- F313 is superseded by installed F314. Its physical diagnostic run exposed
  the uncontrolled qdrv channel-selection path that F314 now holds fail-closed.
  See `docs/OPENMITRASTAR_F313_PHYSICAL_RESULT.md`.

- F312 is the earlier accepted physical baseline, now superseded on `mtd4` by
  accepted F314.
  Candidate SHA-256
  `14677b30886f91f67a664f02623f8f1cfa29220e33bab867b8eed5ab3c8728f7`,
  full-slot CRC32 `e5dcf574`, full-slot SHA-256
  `039e18bb7f4addd373513fcd6307ab22b2d88b39f301455271f0e41b19a0db82`.
  It reports the real Quantenna QT4 DFS hardware while keeping the unfinished
  Linux 5.10 provider fail-closed, exposes only the physically proven 5 GHz
  SSID transaction, and uses HTTP/1.1-compatible POST/body transaction data.
  Flash/readback, protected partitions, authenticated web/API, SSID
  apply/rollback, 2.4 GHz traffic and 5 GHz traffic/120-second soak passed.
  See `docs/OPENMITRASTAR_F312_CURRENT_STATE.md`.

- F301 Full is the earlier integrated baseline superseded by installed F312.
  Candidate SHA-256
  `4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262`,
  full-slot CRC32 `2483522f`, full-slot SHA-256
  `c9c98d000fa9ea1c2fd53738e97decf83ef9a21132b382a23df03121fac1577b`.
  It keeps the exact F300 kernel/radio payload and adds the corrected 6.6.1
  capability-truth web/API. Flash/readback, protected partitions, authenticated
  dashboard/API, live asset hashes, 2.4 GHz regression and 5 GHz traffic passed.
  See `docs/OPENMITRASTAR_F301_CURRENT_STATE.md`.

- F306 is an older guarded physical candidate. It preserves F301's exact
  kernel and 86/86 radio payload files while integrating the unified
  Normal/Advanced/Developer console and canonical API. Candidate SHA-256
  `a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2`,
  full-slot CRC32 `71548682`, full-slot SHA-256
  `c0a17995cbde98d28748dce3a7163b3629dd3a9783ea33dde32cda5eaf077b36`.
  Its flash coordinator is intentionally blocked by the active F301 soak.

- F306 post-promotion multicast/IGMP, read-only store-protection and isolated
  VLAN 4090 gates are prepared offline. They pin the exact F306 runtime and
  candidate SHA-256, use SSH v2 host-key policy, share the existing physical
  lock, preserve separate evidence, restore runtime snapshots and stop on the
  first non-PASS result. The final dry-run passed all three child preflights
  and correctly remained blocked by the active F301 soak. Preparation and
  regression validation performed no SSH, UART, radio, flash or MTD action.

- F307 is the deterministic offline DFS replay. It models the preserved CAC,
  evacuation and 1,800-second NOP state transitions for the Spain profile from
  explicit synthetic or sanitized OEM-oracle outcomes. It does not implement
  pulse classification, prove physical RF detection or produce firmware. The
  F302/F303/F307 regression is 41/41 PASS.

- F308 is the bounded ARC700/Linux 5.10 radar acquisition observer that led to
  F315/F316. Its standalone artifact remains offline. It exports the complete qdrv radar
  provider ABI, performs no RF register writes, callbacks, IRQs or workers, and
  keeps `radar_start=false`. Two independent builds produced the same
  15,580-byte module with SHA-256
  `2a60c95d51cfd00dab25f91eea3d43945e9305c603399036b56710646cd74eca`;
  its qdrv external-provider link probe and the combined 65-test suite pass.
  Any future physical observation must use a versioned `mtd4` diagnostic image,
  not an ad-hoc RAM image or module transfer.

- F300 Full is the proven datapath and rollback baseline for F301.
  Candidate SHA-256
  `734bba8ad1b706c0c17ad5e73341cbb7c7a5c4d78cf05e069d955705d789edbb`,
  full-slot CRC32 `841f11c8`, full-slot SHA-256
  `fb7867874640a428124a18be38b8521e52e5d27322393f88ab44bbd6d17baf9b`.
  Flash/readback, protected partitions, platform and current live-health checks
  passed.

- F300 physically proved the hardware-demand recovery branch on 2.4 GHz. It
  restarted at poke 2 and 2510 ms with a DMA-owned head descriptor, two
  consecutive MAC progress samples and a real `NO_RX_DESC` observation. Three
  32 MiB bidirectional runs passed at median 27.929 Mbps down / 14.861 Mbps up,
  above the 95 percent F290 acceptance floors. The exact image also passed a
  real 5 GHz WPA2/CCMP gate at 30.588 Mbps down / 24.166 Mbps up with a
  120-second soak and zero disconnects. Evidence is in
  `docs/OPENMITRASTAR_F300_CURRENT_STATE.md`.

- F299 was a successful diagnostic but rejected performance candidate. Its
  four-sample gate fired at poke 13 and 5390 ms, but median downstream was only
  26.628 Mbps, so automatic rollback restored F292. F293 likewise proved MAC
  ingress at the F290 fallback instant. See
  `docs/OPENMITRASTAR_F299_PHYSICAL_RESULT.md` and
  `docs/OPENMITRASTAR_F293_PHYSICAL_RESULT.md`.

- F292 Full is the exact rollback baseline used during the F293/F299/F300
  campaigns. It is no longer the current installed image.
  Candidate SHA-256
  `bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e`,
  full-slot CRC32 `e40dada0`, full-slot SHA-256
  `9c6dbb456207eb4006c791be76e8f40d58843e198f03abb9c0676d60202a94b1`.
  It is rootfs-only over F290 and adds the interactive causal EMAC diagnostics
  workbench. Flash/readback, protected partitions, platform and live asset/API
  checks passed.

- F293 Full is the current offline hardware-test candidate. It preserves the
  exact F290/F292 recovery decisions and adds only Arasan MAC RX-demand and DMA
  missed-frame telemetry during the existing stall probe. Candidate SHA-256
  `76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37`,
  full-slot CRC32 `3cc67f08`, full-slot SHA-256
  `e93b0320d5a1032182661cdd4a26a31248edec6867328e9f8ac09d0ba662d3bb`.
  Build, binary contract, hashes, slot fit and dry-run preflight pass; hardware
  boot is NOT RUN and F292 remains installed.
  `tools/run_f293_flash_test_rollback.ps1` now provides the complete guarded
  flash, three-run 2.4 GHz, 5 GHz sanity and automatic F292 rollback sequence.
  Its dry-run currently reports router SSH, AELITA SSH, UART and TFTP ready.

- F294 is a packaged offline successor hold for F293. Its Developer page renders
  the receive path as MAC, DMA, descriptors, NAPI and recovery, with 18
  selectable metrics and plain-language explanations. The Foundation and
  F294-specific suites are 39/39 PASS; desktop/mobile browser checks pass with no overflow or
  console errors. Candidate SHA-256
  `60a5ffc05a384aca112c998887958f7cc6c4e40124f3aece6bb5bc4ec17c16e3`,
  full-slot CRC32 `2c852b72`. Its manifest enforces `candidate_eligible=false`
  and `flash_supported=false` until F293 hardware validation.

- F295 is an 8,368-byte ARC700 store-protection observer. It contains only the
  OEM-derived JEDEC/status/SCUR/DPB read sequence and no write-enable, erase,
  program, protection mutation or MTD registration path. SHA-256
  `2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8`;
  hardware load is NOT RUN.
- F296 packages F295 disabled and without autoload, and adds fail-closed storage
  API/UI reporting. Candidate SHA-256
  `2b9c7adc2ec6ecfc40e7f150d468feea61c7b9468db57a68cbdfa0327b10c2c6`,
  full-slot CRC32 `07e435dc`. It is an offline hold with
  `candidate_eligible=false` and `flash_supported=false`. Its future physical
  gate records UART, hashes the complete store and MTD table before/after, and
  unloads the module without exposing any write operation.

- F297 restores the guarded multicast/IGMP harness that is absent from the
  installed F292 rootfs. Candidate SHA-256
  `742523351bf22c49e6730e56b4fbc1c45123487588e99ecb2200d363b81dfa15`,
  full-slot CRC32 `fb0ba260`. It changes no kernel/radio bytes, is disabled at
  boot and remains an offline non-flashable hold until F293 is proven. Its
  bidirectional AELITA runner passes dry-run, PowerShell parser checks and an
  8/8 packet controller-side multicast socket smoke test.

- F298 is the latest integrated offline hold. It keeps F297's exact kernel and
  runtime controls while replacing stale capability labels with 23 readable,
  evidence-backed entries. Candidate SHA-256
  `7786fd8e68b16dccc4245bbf0f716a1063e39d0d7cc6a17121bf397950898389`,
  full-slot CRC32 `775fa9be`; hardware boot is NOT RUN and flash is disabled.

- The complete signed package lifecycle was repeated on physical F292 on
  2026-09-04. Feed verification, install, execution and removal passed in RAM;
  the persistent data hash was identical before/after and fatal count stayed at
  zero. The API mutation gate was restored to disabled.

- `tools/run_f293_sequential_dual_radio_soak.py` prepares a resumable six-hour
  F293 soak using the available AELITA client. Each cycle runs 32 MiB in both
  directions on 2.4 and 5 GHz, restores AELITA between bands and checkpoints
  health, memory and fatal markers. It is not a substitute for the final
  simultaneous two-client soak.

- F290 Full is the kernel/datapath baseline inherited by F292, previously
  installed directly in physical `mtd4/linux_live` after
  rollback from rejected F291. Candidate SHA-256
  `b3512d5098f1e47e68995836e8e7ed1cef7d8c0a733cbe5e651ae75591770bfc`,
  full-slot CRC32 `a91859e2`, full-slot SHA-256
  `bf2a923fffad5825357c261568fd1d5bea0eba6e5503880cdcb3c0fc9969cf03`.
- F290's three-run 2.4 GHz median is 29.258 Mbps down / 14.410 Mbps up. Its
  telemetry proved the one recovery followed a real NO_RX_DESC event by
  6.15 seconds. Its 5 GHz gate passed at 33.133 Mbps down / 27.880 Mbps up.
- F291 was flashed and initially passed the platform gate, but lost
  Ethernet/SSH before its third run while Linux remained alive over UART. The
  ten-second remembered-fault window is insufficient. F291 is rejected and the
  exact F290 image was restored with complete readback and protected partitions
  unchanged.

- F288 Full was previously installed in physical `mtd4/linux_live` after
  an explicit rollback from rejected F289. Candidate SHA-256
  `567a4f02fd405094766c42240b1ba4587af34852d605c3fbbf05f1c885a9d3da`,
  full-slot CRC32 `ec06695b`, full-slot SHA-256
  `8de9d162364aa20f87bcbb4166b41f7201cd538ac8fb0b9021aa9bea2c466c62`.
- F288 completed three physical 2.4 GHz runs at median 25.442 Mbps down /
  14.910 Mbps up. NO_RX_DESC sampled state and attributed restarts were zero
  in all runs; one run retained a generic `stagnant` recovery. Its 5 GHz gate
  passed at 20.991 Mbps down / 25.107 Mbps up with zero disconnects.
- F289 was flashed, initially passed the platform gate, then lost Ethernet/SSH
  while Linux remained alive over UART with RX packets frozen and no recovery
  attempt. It is rejected. F288 was restored through Bootbase TFTP and passed
  full readback, protected-partition and platform gates.

- F285 Full was previously installed in physical `mtd4/linux_live`; candidate SHA-256
  `ad0a668df4a05f841483157c778292664011148cbaef598d2fbde1ec0d7232e4`,
  full-slot CRC32 `670899dd`, full-slot SHA-256
  `68348c17312b0f8f23c3e1146e0e918b3af0a60910f96d3f3cc35bace3291357`.
- F285 completed two physical material 5 GHz SSID transactions. The second held
  `Lyoko-5G-Material-Test` for 30 seconds and restored `MOVISTAR_PLUS_55CB`
  exactly, with SSH alive, zero fatal markers and no MTD writes.
- AELITA then deliberately associated to the temporary F285 SSID. Sanitized
  evidence proves 5 GHz channel 36, 802.11ac, WPA2/CCMP, 866.7 Mbps negotiated
  PHY in both directions, 93 percent signal, DHCP, router ping and client
  restoration. No client MAC, PSK or calibration data is retained. Evidence:
  `outputs/f3-certification/f285-material-aelita-20260903/sanitized-association-result.json`.
- The association run exposed a final restore-readback false negative. The
  restore apply itself returned verified success and the watchdog later found
  the original configuration already restored as an exact no-op. F286 is the
  offline rootfs-only correction: it waits up to 20 seconds for restored
  SSID/channel/bandwidth convergence. Candidate SHA-256
  `7f59bc0f05a9bc85bd8b6723d2198bd9c54b8e7c77e623cc929821036069430d`;
  full-slot CRC32 `c3f59e4d`; hardware boot NOT RUN.
- F285 also completed three current-image 2.4 GHz 32 MiB bidirectional runs.
  Median throughput was 14.681 Mbps down and 14.265 Mbps up. Every run passed
  association, transfer, router-health and restoration gates with no WLAN
  errors or drops, but also recorded one NO_RX_DESC-attributed RX restart,
  20-43 NO_RX_DESC IRQs and 33-47 NAPI budget exhaustions.
- F287 was the first NAPI-256 physical baseline. It passed
  flash/readback, protected-partition and platform gates. Candidate SHA-256
  `c808359b3ff1a68dd360e1358ae2c258d3a206cb1dd2987c7bbbc401fe149154`;
  full-slot CRC32 `8c931453`.
- F287's three-run 2.4 GHz median is 27.062 Mbps down / 14.394 Mbps up. Two
  runs had zero descriptor starvation and zero restart; the third reproduced
  one NO_RX_DESC restart. Its 5 GHz sanity gate passed at 30.315 Mbps down /
  26.566 Mbps up with zero disconnects.
- F282 Full was previously installed in physical `mtd4/linux_live`; candidate SHA-256
  `b3cebdd208199edc7bbeabef53e2c033a3dd926a590101d8e25e75f2a26b0733`,
  full-slot CRC32 `a347aceb`, full-slot SHA-256
  `5f53dd9629563d6e1be99631cf38bbaa0720ae565bce8e856caa7aae84aa2904`.
- F282 flash/readback, protected partitions and platform gate passed. Its
  physical `hostapd-restart-same` gate also passed with exact state preserved,
  SSH alive, zero fatal markers and convergence in 1.609 seconds.
- F276 Full was previously installed in physical `mtd4/linux_live`; candidate SHA-256
  `678bb33018905939d07da33c39a988cc78f66a9f1488751c44d24aac0ee2dced`,
  full-slot CRC32 `04a21521`, full-slot SHA-256
  `aad63e4690520be876821f01fa13021d13e6618277b07e409129bdf558e8fe6b`.
- F276 fixes the authenticated POST-only 5 GHz plan endpoint. A physical plan
  for channel 44 / 40 MHz reported the exact required operations, kept
  `apply_allowed=false`, preserved radio state and produced zero fatal markers.
- F277 Full was installed and physically validated before F281/F282/F285. It changes only `om-qtnctl` plus
  release identity and compares the requested Quantenna mode against the live
  WEXT mode. Candidate SHA-256
  `da49978c362df08dda35f7c666f250cc182114c01504845240237e3570a2b2c5`;
  full-slot CRC32 `b1fa61ae`; 8/8 tests and packaged hashes PASS. Its boot,
  read-only plans and same-value mode/channel/SSID/TPC sequence were exercised
  physically and led directly to the F281/F282 fixes.
- AELITA physically observed both F276 SSIDs in one complete read-only scan:
  2.4 GHz channel 1 at 91 percent and 5 GHz channel 36 at 94 percent. A later
  scan returned only A348 while both router TX counters continued advancing;
  visibility is proved but repeatable association/traffic remains unproved on
  this boot. See `docs/OPENMITRASTAR_F276_AELITA_VISIBILITY.md`.
- F274 Full was previously installed in physical `mtd4/linux_live`; candidate SHA-256
  `ffbc2cb44acb2514c33adebeaec212122f7cc13e6cef3ef7b81a9d306f623bfe`,
  full-slot CRC32 `b0df3f11`, full-slot SHA-256
  `fda72a7c0e3685c044d40ef237a920b4a2d1b750614a791fc2c910bcc8709750`.
- F274 platform/readback/protected-partition gates passed. Its delta planner
  reports the current 5 GHz configuration as an exact no-op, and the physical
  no-op apply returned verified success without stopping hostapd-qtn or issuing
  WEXT/MuC changes.
- F272's corrected live Quantenna readback remains in F274: WMM, SSID
  visibility, isolation, DTIM, retries, Short GI, LDPC, BA, AMPDU density, TPC
  interval and multicast rate are emitted as valid JSON.
- The F267 radio workbench remains present: ten transactional Realtek controls,
  contract-derived UI state, contextual help and separate 2.4/5 GHz navigation.
- The F270 step runner is present and has proved `rf-write-same` and
  `interface-up-same` preserve SSH and both APs with zero fatal markers.
- F273's delta-aware plan and exact no-op fast path are physically present in
  F274, while dynamic 5 GHz mutation remains disabled.
- The same-value sequence through mode, SSID, channel, init power, DOTH, TPC,
  TPC interval, hostapd restart and post-rearm has now been exercised. The fixed
  WEXT txpower-limit setter is rejected by the driver and intentionally removed.
- `tools/run_f277_qtn_step_gate.py` is the prepared F277-only gate. It requires
  the exact installed runtime, pinned host key, UART, before/after radio and
  mode snapshots, an unchanged fatal count and explicit physical-recovery
  acknowledgement; it contains no flash path or automatic retry.
- F278 is an offline successor hold, not a flash candidate. It inherits F277
  and adds only a guarded multicast/IGMP certification harness. SHA-256
  `929c11cbb7e3245a159778a26560f39f2e6fb97748640b8dd1667a73310b82ed`;
  6/6 tests and packaged hashes PASS. It must not skip F277 physical proof.
- F279 adds only offline store tooling: a bounded mtd4 transaction simulator
  and an unintegrated ARC700 `qtn-topaz-store-mtd.ko`. The module defaults to
  read-only, has no bulk erase path, imports only symbols exported by the exact
  F276 kernel lineage, and has never been loaded on hardware.
- F280 packages that exact F279 module into the SquashFS without autoloading it
  and with `OPENMITRASTAR_STORE_MTD_DRIVER=0`. It is an offline successor hold,
  not a flash candidate. SHA-256
  `a9b418569b4643b121e0bfb1c6c96d3eafefeea150decd8e9ff6f1a9312ad82f`.

## Previous checkpoint — 2026-09-02

- F263 Full is installed in physical `mtd4/linux_live` through Bootbase TFTP.
- F263 candidate SHA-256 is
  `9333feba1fa190e76f60cc1a1cc52a4473aafff3a50d7bbe06b062720ceb869f`;
  full-slot CRC32 `34b37586` and readback passed.
- F263 platform, SSH, SquashFS, dual-radio ready state, web/API and signed
  package lifecycle passed after installation.
- A subsequent radio transaction left Ethernet/SSH unavailable and UART did
  not accept SysRq. A physical power cycle is required before more hardware
  work. Do not start another flash attempt while the device remains unreachable.
- F265 Full was installed through TFTP and passed platform plus package
  lifecycle gates. Its Realtek 2.4 GHz transaction completed and restored, but
  the following Quantenna mutation made the management datapath unavailable.
- F266 Full supersedes F265 as the prepared recovery candidate. It keeps the
  5 GHz AP boot path but disables dynamic Quantenna mutation by default and
  emits UART-visible step markers for the isolated investigation. It is
  offline 42/42 PASS and has SHA-256
  `682b6d3d55039356b5e67d1bd14df32380b5112e4c6ea2583174d16b1c44b9df`.
- After power-cycle recovery, run `tools/promote_f266_mtd4_direct.ps1` dry-run,
  then promote only if router SSH, COM3, wired TFTP and the current F265 slot
  identity all pass.

## Historical checkpoint — 2026-09-01

- F170 is persistently installed in physical `mtd4/linux_live`.
- Kernel: `5.10.260-openmitrastar-radiohw`.
- SSH is reachable at `192.168.1.90`.
- `mtd3/linux_safety` was preserved and remains the manual UART rollback path.
- F170 boots from SquashFS-XZ and exposes the exact `rootfs_live` size
  `0x620000`; `/` and `/persist` are read-only and `/run` plus `/tmp` are tmpfs.
- F170 attempted TFTP first, then transferred through the guarded UART/YMODEM
  fallback and wrote only to `mtd4`; RAM CRC,
  full-slot readback, prefix comparison and protected-partition CRC gates passed.
- F170 includes the Lyoko Foundation 1.0 dashboard, authenticated API v1,
  read-only EMAC diagnostics and a stable SSH host key.
- F167 physical client baseline: 2.4 GHz 32 MiB bidirectional PASS
  (~6.88 Mbps down / ~15.13 Mbps up), and 5 GHz 32 MiB bidirectional PASS
  (~24.56 Mbps down / ~26.75 Mbps up, zero client disconnects).
- F167 telemetry identifies `NO_RX_DESC` pressure and cause-attributed EMAC RX
  restarts during 2.4 GHz traffic. Driver optimization must use this evidence.
- F171 is built but not installed. It fixes the stale `degraded` health marker
  and no-op transaction cleanup; its exact candidate is pinned in
  `docs/OPENMITRASTAR_F171_CANDIDATE.md`.
- F172 is also offline and uninstalled. It layers the F171 rootfs over a
  single kernel change, EMAC NAPI weight `64 -> 128`, and requires three
  matched physical 2.4 GHz runs before any performance claim.
- F173 is an offline Foundation branch with a read-only inventory of all three
  buttons and six LED class devices. F174 proves signed, ABI-restricted `.ipk`
  integration into SquashFS; neither candidate is installed.
- F176 exposes the signed package inventory through authenticated API/UI and
  remains offline. F170 is still the installed firmware.
- F177 adds `lyoko-pkg`, the static ARC700 `pkgbox` and two signed bundled
  packages. Runtime installation is limited to RAM and remains hardware-unproven.
- F179 combines the F172 NAPI-128 kernel with the corrected F177 package-manager
  rootfs. It is the current integrated offline candidate; F170 remains installed.
- F180 adds only a read-only `rootfs_live`/`lyoko_store` partition view to F179.
  It is an offline storage probe, not a writable package-store release.
- F181 is a standalone read-only ARC700 SPI identity module. It has no write
  path and has not been loaded on hardware.
- F182 integrates that module into F180 and loads it nonfatally at boot while
  keeping `lyoko_store` read-only and unmounted. It remains offline.
- F184 combines the F172 datapath with F183 capability-aware Foundation and is
  the current integrated offline candidate for the next normal mtd4 iteration.
- F245 adds the authenticated signed package catalog inspector and verified
  read-only `search`, `info`, `depends`, `plan` and `update` queries.
- F246 combines the exact F223 RX-ring-256 kernel with the exact F245 rootfs.
- F247 promotes the exact F246 bytes into the current guarded physical-test
  candidate. Its SHA-256 is
  `8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12`.
- `tools/run_f247_flash_test_cycle.ps1` checks candidate, rollback, router,
  AELITA, traffic endpoint and UART before invoking any flash action. Current
  preflight: router SSH PASS, COM3 PASS, traffic server PASS, AELITA SSH FAIL.
- `tools/restore_f222_mtd4_from_f247.ps1` is the prepared rollback for a
  complete verified F247 installation. The preserved mtd3 image is not claimed
  as automatic recovery because its rootfs mount remains unproven.
- Direct Bootbase TFTP to APELSITO `192.168.1.63` reached gigabit link and sent
  an RRQ but timed out. UART/YMODEM remains the proven transfer path.

Pinned artifacts:

- OEM immutable input:
  `Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin`
  — 6,729,728 bytes — SHA-256
  `f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f`.
- Installed F170 candidate:
  `work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build/openmitrastar-linux510-q3-persistent-f170-lyoko-foundation-runtime-fix-LZMA-OFFLINE-NO-FLASH.webformat.bin`
  — 4,964,352 bytes — SHA-256
  `432e4341e92fc5162c3550d5c7df05d378b31d250086ce7a72bedb64b0e4559d`.

The historical `OFFLINE-NO-FLASH` suffix records build provenance. It does not
mean F170 is currently unflashed: the guarded transport wrote it to `mtd4`,
verified the prefix, booted Linux 5.10, and recorded protected-partition hashes.

