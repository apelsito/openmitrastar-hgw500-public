# F363r2: admit the expected S16 temperature owner

F363r2 fixes the startup incompatibility between S16 temperature registration
and the inherited S55 radio clean-state check. It is an offline-qualified new
image. No hardware operation was performed by this implementation task.

The F363 physical platform transcript at
`/workspace/OpenMitraStar/f363-evidence/f363-install-20260921T210511Z-7e8c7914/platform-f363/router.stdout.log`
reports degraded boot, radio5 stopped and S55-radio5-ap exit code 1, while the
kernel, management and 2.4 GHz are available and the fatal count is zero. It
does not contain the precise last-refusal marker. The cause below is reproduced
from the exact installed helper; an unrecorded physical marker is not claimed.

S16 successfully registering the F363 interface leaves `temp_sens` loaded.
The F363 `om-radio5-start` helper, SHA-256
`59e84ce1ffd76ffdb88389336fc494502b9a5162241378b311b484c4b7882ba4`,
still includes `temp_sens` in its dirty-module loop at line 461. It therefore
refuses `dirty-temp_sens` before reaching the new `require-module` at line 524.
The initial composition changed the load operation but missed this earlier
admission check. Its individual helper tests did not cover the S16-to-S55
combination. This is a startup software incompatibility, not evidence of a
sensor MMIO or clock failure.

F363r2 changes only the admission:

- Require the loaded `hwmon` and `temp_sens` module directories.
- Call the existing temperature `require-module`, which reads the registered
  node name, requires exactly one `topaz_internal` node and module version 363.
- Exclude only that expected `temp_sens` from the dirty-module loop. Retain
  rejection of qdrv, wlan, legacy temp_sensor, switch_emac, switch_tqe, hbm and
  fwt_ctrl. Retain the later temperature requirement and dependency sequence.

These are registration metadata reads. Admission neither activates the sensor
nor reads `temp1_input`. Default sensor state remains 0 / 0 / -19, with explicit
experimental activation still required.

The six tests execute the actual admission fragment and the original
`find_sensor` function against fake proc/sys files. They reproduce the old
failure, accept the new expected state, and reject profile 339, missing hwmon,
preloaded qdrv and the legacy temperature module. No whole radio helper is run
on the host. Both rootfs/image compositions match. All 55 catalog rows and
40 unchanged kernel modules are checked; raw kernel, compressed kernel, config,
DT and vmlinux match F363 byte-for-byte.

The new immutable result is
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f363r2-fullimage-20260921T211851Z/result.json`,
SHA-256 `817ceda97570ef09a40a16209ad693dc5942563e02fa55e6dac8678c289efded`.

- Schema: `openmitrastar.f363r2-temperature-owner-image/v1`.
- Status: `PASS_OFFLINE_TEMPERATURE_OWNER_IMAGE`.
- Product: `lyoko-foundation-6.9.11-f363r2-temperature-owner-device`.
- Build: `ada15e45a6fa0e49`; kernel identity stays `#358`.
- Image: `firmware/f363r2-f363-temperature-owner-device-bound/openmitrastar-linux510-f363r2-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
  under the private device directory, 5,382,144 bytes, SHA-256
  `be5073c2e3fca5b4a214513f3c7aeee42b463b760b8213bf55c12a6ccbc2c075`.
- Manifest SHA-256:
  `3ce73a60255ac4a0fb780703851035c7d160eff26a88c90939cfc1c44401cc14`.
- Prefix CRC32: `45a5a898`; full-slot CRC32 with the actual sequence-2 journal:
  `b8f8acc1`. Store CRC32 remains `5d2ee646`.
- `known_hosts.f363` is retained unchanged in the new artifact directory.

Only `om-radio5-start`, release metadata and the two affected catalogs change.
The temperature helper/catalog, modules, calibration, Ethernet, watchdog and
journal inputs are untouched. Recovery remains the accepted F362 image,
SHA-256 `9582b92f1c68ec192ee14c55ba9ab69015749cc69ecde392bd6ad3392d105f2b`,
not the failed F363 installation. Physical installation, sensor sampling and
release acceptance remain separate gates. RF/client tests remain deferred.

New generation tools are `tools/f363r2_rootfs_worker.py` and
`tools/build_f363r2_temperature_owner_image.py`. The original F363 builders,
images and the active installer's frozen inputs were not modified.
