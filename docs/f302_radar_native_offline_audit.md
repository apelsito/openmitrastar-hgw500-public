# F302 qtn_radar_native offline audit

Date: 2026-09-04

## Result

The Linux 5.10 module boundary is sufficiently understood to build and link a
fail-closed provider, but not to claim or implement a radar detector.

- ABI skeleton: PASS.
- Exact F301 kernel compatibility: PASS.
- Current qdrv source external-provider link probe: PASS.
- Radar detection: NOT IMPLEMENTED.
- Firmware integration, module load and hardware validation: NOT RUN.
- DFS readiness: BLOCKED.

The resulting `qtn_radar_native_f302.ko` is deliberately incapable of enabling
radar detection. It exists to freeze and test the module boundary while the
missing detector is recovered or independently implemented and validated.

## Exact F301 target

- Kernel release: `5.10.260-openmitrastar-radiohw`.
- Architecture: ARC700 little-endian.
- F301 config SHA-256:
  `cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e`.
- F301 vmlinux SHA-256:
  `8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc`.
- Exact generated Module.symvers SHA-256:
  `29e86facebed934166e4c52bf9e0a95972d677d49b0bc4e0a49df19e8b7c1269`.
- `CONFIG_MODULES=y`, `CONFIG_MODULE_UNLOAD=y`.
- `CONFIG_MODVERSIONS` and module signatures are disabled.
- F301 qdrv SHA-256:
  `0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff`.
- F301 qdrv vermagic:
  `5.10.260-openmitrastar-radiohw mod_unload ARC700`.

The F302 provider has the same vermagic and imports only the exported F301
kernel symbol `printk`.

## qdrv contract

The historical header declares 18 functions. The OEM radar binary exports 16,
and a current qdrv build with `qdrv_radar_compat.o` removed imports those same
16. The two header-only functions are not referenced by qdrv.

| Symbol | Header | OEM export | qdrv import |
|---|---:|---:|---:|
| `detect_drv_sample_loc_get` | yes | yes | yes |
| `dfs_rqmt_code` | yes | yes | yes |
| `radar_disable` | yes | yes | yes |
| `radar_enable` | yes | yes | yes |
| `radar_get_status` | yes | yes | yes |
| `radar_ocac_info_addr_get` | yes | yes | yes |
| `radar_record_buffer_pt` | yes | yes | yes |
| `radar_register` | yes | yes | yes |
| `radar_register_is_dfs_chan` | yes | yes | yes |
| `radar_register_is_dfs_weather_chan` | yes | yes | yes |
| `radar_register_statcb` | yes | yes | yes |
| `radar_set_bw` | yes | yes | yes |
| `radar_set_chan` | yes | yes | yes |
| `radar_start` | yes | yes | yes |
| `radar_stop` | yes | yes | yes |
| `sta_dfs_is_region_required` | yes | yes | yes |
| `radar_get_chan` | yes | no | no |
| `radar_set_shared_params` | yes | no | no |

The exact F301 qdrv does not import an external provider. It contains global,
non-exported implementations from `qdrv_radar_compat.o`. Therefore merely
packaging F302 would have no effect. A later integration must remove that one
object from qdrv and load the provider before qdrv.

That future linkage was tested only in an isolated build tree. The rebuilt
qdrv acquired an explicit dependency on `qtn_radar_native_f302`, retained the
F301 vermagic and had no unresolved modpost symbols. It was not packaged or
loaded.

## OEM binary boundary

The preserved OEM module is:

- SHA-256:
  `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332`.
- License: proprietary.
- Vermagic: `2.6.35.12 mod_unload ARC700`.
- Declared dependencies: `qtn_debug,bootcfg`.

The GPL drop contains `drivers/radar/radar.h` and `detect.h`, but no detector
implementation. The binary contains substantial missing logic: `radar_start`
is 4100 bytes, `detect_radar` is 3580 bytes and it embeds region-specific pulse
classification, long-sequence/weather-radar handling, zero-crossing analysis,
thresholds, pulse history and polling state.

Direct reuse on 5.10 is impossible. In addition to the vermagic mismatch, five
OEM imports have no loadable provider in the exact F301 kernel/module set:

- `boot_tvec_bases`
- `create_proc_entry`
- `do_gettimeofday`
- `schedule_delayed_work`
- `slowpath_copy_from_user`

Most have modern replacements, but replacing APIs does not recover the missing
detection algorithm or prove hardware behavior.

## Hardware facts recovered offline

The headers and OEM disassembly identify the Topaz radar blocks and show that
the old module directly programmed baseband registers and polled pulse data.

- Pulse memory: `0xe6401000` to `0xe6401400`.
- Zero-crossing memory: `0xe6400000` to `0xe6401000`.
- Control/status registers are under `0xe6091000` for Topaz/QT4.
- `radar_set_bw(80)` writes one IIR coefficient set; the alternate branch writes
  the 40 MHz set. A safe 20 MHz interpretation is not established.
- `radar_enable` touches baseband state and starts delayed polling.
- qdrv owns CAC, channel-switch, NOP and TX suppression plumbing; the external
  module owns physical pulse acquisition and classification.

These addresses and constants are evidence for future work, not permission to
write them from an unvalidated module.

## F302 fail-closed module

Artifact:

- `qtn_radar_native_f302.ko`
- Size: 7924 bytes.
- SHA-256:
  `de2e5750625941e41411b9b1186401706e37e91dcf6d8c6829717517e4439a1f`.
- Two independent builds: byte-identical.
- 18 declared API symbols exported.
- Only kernel import: `printk`.
- No MMIO, IRQ, timer, worker, procfs, debugfs or MTD primitive.

Its behavior is intentionally conservative:

- `radar_start()` returns `false`.
- `radar_get_status()` returns `false`.
- `dfs_rqmt_code()` returns `DFS_RQMT_UNKNOWN`.
- registration and channel mutation return `-EOPNOTSUPP`.
- no callback is retained and no hardware state is changed.

The companion consumer probe imports all 18 header functions and returns
`-EOPNOTSUPP` from module init. It is a link artifact, not a load test.

## Risks before a real backend

1. A false negative would permit illegal transmission on a DFS channel.
2. A false positive would cause unnecessary CSA/NOP events and client loss.
3. Direct MMIO without the original baseband locking/order can race MuC/QMAC.
4. Pulse FIFO pointer, wrap, acknowledge and zero-crossing semantics are not
   sufficiently proved from headers alone.
5. Region tables and thresholds are regulatory behavior, not tuning knobs.
6. Callback lifetime must be synchronized with qdrv unload and packet logger.
7. CAC completion in qdrv is only valid if continuous physical monitoring was
   active for the complete required interval.
8. The old 40/80 MHz filter branch does not establish correct 20 MHz behavior.

## Next discriminating proof

Do not integrate this skeleton into F301/F302 firmware. The next useful proof
is an OEM-oracle register trace, not a DFS channel test with the stub:

1. Boot the preserved OEM stack without writing flash.
2. Snapshot only the documented radar control, count and pointer registers.
3. Record transitions for `start -> set_bw(20/40/80) -> set_chan -> enable ->
   disable -> stop`, including baseband lock ordering and poll cadence.
4. Repeat with a calibrated authorized radar source to capture one known pulse
   sequence, callback timing, FIFO wrap/ack behavior and channel evacuation.
5. Reproduce those transitions with a Linux 5.10 read-only observer before any
   detector implementation is allowed to write registers.

Without that trace or the missing detector source, a module that returned
`radar_start=true` would be fabricated behavior and must remain forbidden.

## Evidence

- `outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904/manifest.json`
- `outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904/oem-radar-import-provider-map.tsv`
- `outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904/qdrv-external-provider-link-probe.log`
- `outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904/provider-modinfo.txt`
- `outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904/SHA256SUMS`

No router, UART, TFTP, radio, module load, firmware integration, flash or MTD
operation was performed.
