# F363 — internal temperature diagnostic on F362

F363 adds the F339 Topaz internal sensor to the F362 firmware as an explicitly
activated diagnostic. The default boot loads/registers hwmon and the replacement
`temp_sens` module, but performs **no sensor register reads or writes**. It does
not claim a measured clock, END_CONV behavior or physical temperature accuracy.
Root owns the subsequent installation/activation; this work is offline only.

F362's dual Ethernet, configuration journal, watchdog supervisor, identity,
calibration and existing management setup are preserved. F355 lifetime changes
are not included here. No WPS/RF test or new reset procedure is introduced.

## Reused and new behavior

`topaz_temp_core.h` is byte-identical to the qualified F339 core, SHA-256
`cc86ae1c45828f66681d7eb8a78ea31955770d77135319e380e1987f5bb93a3c`.
The existing F339 17,584-check OEM conversion/protocol result is reused, not
rerun. The table and exact startup writes `2`, `0xfffffffe`, `1` are unchanged.
Valid samples still represent the upper bound of a five-degree interval.

The F363 wrapper exposes the `topaz_internal` hwmon device with cached fields:

| Attribute | Default | Sensor MMIO when read |
|---|---:|---|
| `enabled` | 0 | None |
| `activation_attempted` | 0 | None |
| `activation_error` | -19 (`ENODEV`) | None |

`enabled=0` describes software admission, not a proven physical shutdown of a
converter left by an earlier boot. Probe only reserves/maps the exact resource
and registers interfaces. It neither starts nor samples the converter.

`experimental_enable` is write-only, root/CAP_SYS_RAWIO, and accepts only `1`.
It makes one startup attempt per driver instance and rejects repeated attempts.
The source-reviewed DT property is
`openmitrastar,experimental-temperature-control`; F363 does not fabricate
`quantenna,clock-map-ownership-qualified` or a sensor clock frequency.

`om-temperature-f363 status` reads only cached state. `enable` performs the
explicit startup operation; `read` reads `temp1_input`. Reading `temp1_input`,
`interval` or the legacy API before activation returns ENODEV without sampling.
After activation, they use F339's END_CONV/range/error handling. Separate reads
are not claimed to be independent newly completed hardware conversions.

The existing qdrv worker now checks the returned index before updating its
shared temperature data. An error retains the previous data; it is not turned
into a zero or a fabricated fresh temperature. No converter-stop operation is
invented when removing the software interface.

## Exact integration boundary

The only enabled configuration change is `CONFIG_HWMON=m`. Kernel build identity
remains `#358 @1790006400` and release remains
`5.10.260-openmitrastar-radiohw`, preserving the F362 supervisor contract.
The exact new config/ELF/DT hashes are in the component manifest.

The DT adds `/soc/temperature-sensor@e0000108`, range `0xe0000108+0xc`, and
shortens only recovery's SYSCTL resource from 0x200 to 8 bytes. Its current
GPIO/watchdog resource tail and all F362 Ethernet properties are preserved.

Two broad existing SYSCTL mappings remain unchanged:

- IRQ uses `of_iomap`, with actual accesses at +0x10/+0x4c/+0x58/+0xac.
- PCIe uses shared `devm_ioremap`, with actual accesses at +0x14/+0x17c.

They do not make exclusive claims on the whole range and do not access the
sensor's registers. Their source snapshots/hashes are recorded; no IRQ/PCIe
driver change or unsupported narrowing of their range is performed.

`S16-f363-temperature` loads hwmon and temp_sens before configuration/radio
startup, using the existing verified single-string `ram-insmod-qtn`. The qdrv
loader verifies that replacement is present instead of loading a second owner.
The helper/module/profile catalogs are verified again after rootfs repacking.

## qdrv comparison, including the necessary ABI correction

The F362 qdrv profile is retained: internal radar compatibility, original
parameters and beacon preflight. F334's source reconstruction of that profile
is rebuilt against the actual kernel configuration; no F344/F355 feature set
is substituted.

Against installed F362, 782 of 783 relocation-normalized functions match. The
remaining WPS function uses the current kernel's task_struct signal offsets
182/190 instead of the obsolete 168/176 used by the older binary. This is an
ABI correction in the rebuild, not a WPS activation or physical WPS test.

The thermal patch changes `qdrv_get_internal_temp`. It also moves the source
line number embedded in a `WARN_ON_ONCE` inside `qdrv_wlan_exit`, from 9170 to
9177. The exit source body is identical, 986 bytes of function code have the
same layout, and after relocation normalization only byte 966 of the line
immediate differs. A narrow check validates the `mov r1,limm`, its actual
source line and the associated `warn_slowpath_fmt` relocation; all other
normalized exit bytes must match. No generic exception permits exit changes.

## Evidence and limits

- Component result: `/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/result.json`,
  SHA-256 `5036e7a5980a22c81c08506c1a77ba1af7ec3ceeeab69393e2d0bfdbb6d7bdf3`.
- New integration test: 1,048 checks of actual driver/consumer functions with
  fake hardware, including zero default accesses, one startup and error retention.
- Helper test: 11 cases with fake sysfs/loader, including cached-only status.
- Sensor and both baseline/patched qdrv builds are paired and byte-identical.
  Kernel/hwmon have one incremental build; no second kernel build is claimed.
- New component imports close against the recorded kernel/peer exports.
- Two full rootfs/image compositions are compared, with Bootbase/prefix fit,
  exact declared delta, catalogs and preserved store checked.

The first full image at `analysis/f363-fullimage-20260921T204653Z` is historical:
its module-closure metadata inherited F362's unchanged-module labels. It is not
the delivery for installation. The corrected image is composed separately;
neither that historical directory nor F362 is overwritten.

The firmware installer must preserve the real sequence-2 journal, SHA-256
`fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873`,
CRC32 `5d2ee646`, and all protected partitions. Initial post-install checks read
only cached 0/0/-19 attributes. Sensor activation and measurement remain a
separate root-owned physical campaign; Wi-Fi/client/RF tests remain deferred.

## Final immutable image — 2026-09-21 20:48 UTC

- Result: private `analysis/f363-fullimage-20260921T204859Z/result.json`, SHA-256
  `9948197f20c1875af08d39f9884c1a5321ae06c4f36ae25e845a716bf3d652cd`.
- Directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f363-f362-temperature-diagnostic-device-bound/`.
- Image: `openmitrastar-linux510-f363-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`,
  5,382,144 bytes, SHA-256
  `c8d49e9d44ff86e5045d4a28aa2e0a90dd68e8bb89c7fc3104f0b874e37ea26d`.
- Manifest SHA-256:
  `d16e034887c9c8f47c50352b71ec82126fa9108c79bf560ded64988c49a2e6c6`.
- Product: `lyoko-foundation-6.9.11-f363-temperature-diagnostic-device`;
  build ID `7465f33c1ad5ccd0`; kernel `#358`; unchanged F340 watchdog DT marker.
- Firmware-prefix CRC32 `da4b82d7`; full slot with the preserved sequence-2
  journal CRC32 `2a855242`. These are not FF-store assumptions.
- New temp_sens: 9,920 bytes, SHA-256
  `fe3ed5f920df4b00a16dfcd7e153d4d52971e476351ce0b494fa35abf66dcf01`.
- Rebuilt qdrv: 682,648 bytes, SHA-256
  `7b7b8d0d69e4b0edc3338f462dc878988d78ce8743855456968f8f6186f71346`.

Bootbase, slot/prefix fit, both image compositions and installed catalog hashes
pass. Exactly 12 rootfs paths change; the full inventory comparison preserves
every other F362 path. The corrected manifest explicitly records the replaced
modules and new Module.symvers hash. The installer and F364 agent have received
this final result. All F363 build processes are complete; no F363 hardware
operation was performed by this agent.
