# F365 — cached temperature DATA diagnostics

F365 is a diagnostic derivative of the exact F364r3 image. This revision
preserves manual activation and the inactive state at boot.

## Completed offline image — 2026-09-21

**PASS_OFFLINE_CACHED_TEMPERATURE_DATA_IMAGE**. Physical diagnostic capture is
not performed or claimed by this build.

- Private directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f365-f364r3-temperature-data-device-bound/`.
- Image: `openmitrastar-linux510-f365-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Bytes: **5,382,144**.
- SHA-256: `43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`.
- Manifest SHA-256: `a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c`.
- Result: private `analysis/f365-fullimage-20260921T215511Z/result.json`.
- Product: `lyoko-foundation-6.9.13-f365-temperature-data-device`.
- Build ID: `ffba9cf702b14ed2`; pinned SSH file: `known_hosts.f365`.
- Prefix CRC32: `b858f5da`; full-slot CRC32 with preserved sequence2 store: `118901d4`.
- Full-slot SHA-256: `498ce25fa8108232fd274ce6342d70d2da02b73582bcc0c0703eb8ee5d5e9870`.

The input F364r3 image is exactly
`ee6b7d09fd9e2dc5e0009d6756910510409ae13fb17108089a4caf7043056a15`.
The diagnostic sensor is **11,528 bytes**, SHA-256
`e3ab1338753f3af4713a1f4cebf4b5b9ed4998922e8bf1cdb7424491f54d5fd1`,
qualified in `/workspace/OpenMitraStar-build/f365/f365-diagnostic-module-20260921T215213Z/result.json`
(SHA-256 `afdb2cb55235344a7ba2780a3f66584e5ed0196f44914df4271b71d230ee2909`).
Its two builds match; the existing bank passes 2,082 assertions and resolves
17 imports. The composer reused this evidence without rebuilding binaries.

Seven rootfs files change: sensor module, temperature helper/profile, release
and the temperature/radio/storage catalogues. Kernel, DT, configuration, qdrv,
S16/S55/S90, radio start/stop, Ethernet, identity, journal and supervisor remain
exact. Bootbase, prefix fit, full catalogue/inventory checks and two independent
repacks pass. The source F364r3 recovery image has prefix CRC32 `afe22de2` and
full-slot CRC32 `d7a19077` with the same store; root selects the accepted physical
fallback before installation.

The watchdog agent owns the new sensor module and its existing test-bank
qualification. The image composer is `tools/build_f365_temperature_data_image.py`;
the isolated SquashFS worker is `tools/f365_rootfs_worker.py`. Both are new
files. F364r3 sources, image and installer pins are left untouched.

## Module and helper contract

The module keeps `name=temp_sens` and `MODULE_VERSION=363`; its additional
`MODULE_INFO(diagnostic_revision,"365")` identifies the diagnostic derivative.
This preserves the legitimate F363r2/F364r3 preload checks. The temperature
catalogue is updated to the exact new module/helper/profile hashes.

The driver records the first/last DATA values, poll count, elapsed time and
errno from reads already performed. It retains independent hwmon and legacy
caches under the existing sensor lock. The F339 core, table, start sequence and
100 ms conversion timeout remain unchanged. No additional sensor read or new
MMIO protocol is introduced.

Read-only `diag_hwmon` and `diag_legacy` attributes return one JSON line each:

- schema: `openmitrastar.f365-temperature-access/v1`;
- source: `hwmon` or `legacy`;
- operation: `none`, `temp1_input`, `interval` or `legacy`;
- sequence, complete, errno and read_count;
- first_word/last_word: `0xXXXXXXXX`, or null when no DATA word was read;
- elapsed_us and elapsed_valid.

`om-temperature-f363 diagnostics` only reads these two cached attributes. It
does not enable the sensor or read `temp1_input`. Existing load, status,
require-module, enable and read actions are unchanged. S16, S55, S90, qdrv,
Ethernet, journal, identity and watchdog remain unchanged.

## Build gate

```powershell
python tools/build_f365_temperature_data_image.py --f364r3-image-result <F364r3-result.json> --sensor-result <F365-module-result.json>
```

The builder requires the actual qualified diagnostic-module result, exact
F364r3 baseline, reproducible sensor binary, matching module metadata,
unchanged core hash and the existing bank's accepted evidence. It does not
recompile kernel, qdrv or sensor. The complete image must pass exact rootfs
delta/catalogue checks, Bootbase, prefix fit and two matching repacks, with the
actual sequence2 store preserved in full-slot calculations.

An offline image does not establish useful temperature measurements: the previous physical
conversion returned ETIMEDOUT. Diagnostic capture and installation remain
separate root-owned physical gates. No hardware is accessed by these builders.
