# F364: qualified F355 lifetime on the real F363 temperature image

## Current offline candidate — F364r3 on corrected F363r2

F364r3 is complete offline. It uses the real corrected F363r2 result
`analysis/f363r2-fullimage-20260921T211851Z/result.json`, SHA-256
`817ceda97570ef09a40a16209ad693dc5942563e02fa55e6dac8678c289efded`.
No kernel or module was rebuilt for this revision. F363r2 physical acceptance
and the sensor campaign are separate root-owned gates and are not claimed here.

- Directory: `firmware/f364r3-f363r2-lifetime-device-bound` under the private device directory.
- Image: `openmitrastar-linux510-f364r3-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Bytes: **5,382,144**.
- SHA-256: `ee6b7d09fd9e2dc5e0009d6756910510409ae13fb17108089a4caf7043056a15`.
- Manifest SHA-256: `45050fbc20981c6e76115acd01bd3e7a5e0138dcd24605b0624ec37a7fb1899d`.
- Result: private `analysis/f364r3-fullimage-20260921T212001Z/result.json`.
- Product: `lyoko-foundation-6.9.12-f364r3-lifetime-device`; build ID `324a6ee1541f95aa`.
- Prefix CRC32: `afe22de2`; full-slot CRC32 with sequence2 store: `d7a19077`.
- Full-slot SHA-256: `1152b6b0bf442596cd03c51bca2c5110d2afbde48310288beaa8a91482f09b2e`.
- Pinned SSH file: `known_hosts.f364`.

Bootbase, prefix fit and two complete compositions pass. The exact qualified
qdrv module remains `cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01`.
Relative to F363r2 there are six changed rootfs files: qdrv, its single startup
hash literal, driver contract, radio catalogue, release and storage catalogue.
The new hwmon/temp_sens/require-module checks and corrected dirty-module loop
remain byte-identical except for that unrelated qdrv hash literal. No old
`7b7b8d...` hash remains in the rootfs; the new qdrv hash is bound in exactly
startup, driver contract and radio catalogue. All other files are preserved.

The source F363r2 image is `be5073c2e3fca5b4a214513f3c7aeee42b463b760b8213bf55c12a6ccbc2c075`,
with prefix CRC32 `45a5a898` and full-slot CRC32 `b8f8acc1` using the same store.
The installer must still select and verify the actual accepted physical
fallback. F365 remains postponed and has no built or sealed image.

## Promotion hold — F364 and F364r2 are NO_GO

The original F364 image `1e2d07de...` has a stale hardcoded qdrv hash in
`om-radio5-start`. Its catalogue and driver contract were updated, but the
separate `expected_qdrv_sha` literal was missed. Do not install that image.

F364r2 fixes exactly that binding and is preserved in
`firmware/f364r2-f363-lifetime-device-bound`, with image SHA-256
`c6c8a39acaec3423deb8a3a612c960f15471c7ab9f05c886e6ecb72a9308657b`,
5,382,144 bytes, manifest SHA-256
`c74a0f8fabba5faceeb2f5e6c45612384993cb2c8e21cfe7626c16812fe87c9a`.
Its result is private `analysis/f364r2-fullimage-20260921T211441Z/result.json`.
The single startup literal is now `cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01`;
the same value occurs only in startup, driver contract and radio catalogue.
The previous `7b7b8d...` module hash occurs in no rootfs file. Its prefix CRC32
is `22dc4537`; full-slot CRC32 with the existing journal is `ae18e8c2`.

**F364r2 is nevertheless NO_GO for installation.** The physical F363 platform
gate failed radio5 readiness: S16 legitimately preloads `temp_sens`, but the
unchanged radio startup dirty-module loop rejects that loaded module before
reaching its new `require-module` check. F364r2 inherits this condition. The
watchdog agent owns the separate corrected startup candidate. No original
image, manifest, frozen input or historical result is modified by this hold.

Failure evidence:
`/workspace/OpenMitraStar/f363-evidence/f363-install-20260921T210511Z-7e8c7914/platform-f363/status.json`.
The UART redactor excludes normal OMRADIO5/S16/S55 messages, so it cannot supply
the missing refusal text retrospectively. F365 is postponed, with no image
built or sealed, until the dependency and required physical sensor gate pass.

## Completed offline artifact — 2026-09-21

Historical **PASS_OFFLINE_LIFETIME_INTEGRATION_IMAGE**. This does not override
the promotion hold above. No hardware was accessed by these builders.

- Private directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f364-f363-lifetime-device-bound/`.
- Image: `openmitrastar-linux510-f364-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Bytes: **5,382,144**.
- SHA-256: `1e2d07de0aaee45295b7cd27e5418898d7ceeaa7a2e4060391f0695092da2857`.
- Manifest SHA-256: `8454cc2bda282e27cefdbc756eae50449ecf2c8c0b79a1ea233e1ffe1f16589e`.
- Result: private `analysis/f364-fullimage-20260921T205724Z/result.json`.
- Firmware build ID: `77630934c673db7e`; product `lyoko-foundation-6.9.12-f364-lifetime-device`.
- qdrv: **685,332 bytes**, SHA-256 `cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01`.
- Component result: `/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z/result.json`.

The actual input is the final F363 image result
`analysis/f363-fullimage-20260921T204859Z/result.json`, image SHA-256
`c8d49e9d44ff86e5045d4a28aa2e0a90dd68e8bb89c7fc3104f0b874e37ea26d`.
The earlier F363 metadata result is not used. Kernel, raw kernel, compressed
kernel, DT and configuration are copied byte-for-byte from that F363 image.

Only five rootfs files differ: `qdrv.ko`, release metadata, the driver contract,
the radio artifact catalogue and the storage catalogue's release hash. Every
other entry is preserved, including thermal modules/helpers, radio start/stop,
Ethernet, identity, journal and supervisor. Bootbase, prefix fit, both module
builds and both image repacks pass. No kernel rebuild was needed for F364.

The exact preserved sequence2 store remains SHA-256
`fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873`,
CRC32 `5d2ee646`. F364 prefix CRC32 is `ec6e02d4`; full-slot CRC32 with that
store is `82a74b48`, SHA-256
`7105f0b76b9912d8ee9f12c27570ff829bce43c6897bb7a1d10331d20621fae7`.
The exact source F363 has prefix CRC32 `da4b82d7` and full-slot CRC32
`2a855242` with the same store. The installer must independently select the
actual accepted physical fallback; these file checks do not establish it.

The strict compiled comparison initially identified nine extra functions.
Their complete ARC disassembly delta was reviewed without rebuilding:
eight changes are real diagnostic `__LINE__` values, including instruction
encoding/branch displacement changes when the constant encoding changes;
the dump function's six loads resolve to the same `set_num`/`buf1_num` fields
of its relocated static object. Function bodies and the inlined dump helper
remain exact. The closed review is
`work/kernel-port/versions/f364-lifetime-integration/reviewed-nonfunctional-delta.json`,
SHA-256 `90298fb0a646751ebf138e505b9dcf024998c8328dde5ffb610ae74cab039792`.
The qualifier binds its exact module/function hashes and disassembly evidence;
it does not permit arbitrary extra functions. Thermal and WPS functions remain
byte-equivalent after relocation normalization.

## Preparation checkpoint

F364 is a separate source derivative of
`work/linux510-radio-port/quantenna-f363-temperature`. F363 sources and build
outputs are not modified. The source preparation passed its bounded combination
checks before the completed artifact above was built.

Source: `work/linux510-radio-port/quantenna-f364-lifetime`.
Source proof/diff: `work/kernel-port/versions/f364-lifetime-integration/`.

F355 originally derived from F344, while F363 retains the F334/F321 profile.
F364 therefore transplants only lifetime changes into nine source files. It
does not copy F355's full qdrv files, mode implementation or external DFS stack.

The three qualified F355 lifetime adapter files and the proc init/exit bodies
are exact. The F363 temperature-consumer error guard is preserved. The control
entry point gains its own serialization mutex and the F355 readiness checks;
no F344 mode workflow is introduced.

## Lifetime boundary

The first matched policy-admitted mutation retains a reference to qdrv before
dispatch. The module and published allocations/callbacks remain resident until
reboot. Core initialization cannot retry over partial state. Stop/release paths
refuse destructive cleanup after retention; forced module unloading remains
unsupported and disabled by the kernel configuration.

The existing userspace `om-radio5-stop` stays unchanged: it already closes the
radio while leaving qdrv and dependencies loaded. F364 does not claim hardware
quiescence, hot restart, safe post-mutation unload or a new firmware epoch.

## Build chain and verification

1. `python tools/prepare_f364_lifetime_integration.py` creates the immutable
   source derivative. It refuses to overwrite its own completed directories.
2. `python tools/build_f364_lifetime_component.py --f363-components-result <real-result.json>`
   requires `PASS_OFFLINE_TEMPERATURE_INTEGRATION`. It copies the F363 output
   context to its own directory and builds only qdrv twice. The F363 kernel
   sources are read-only inputs; kernel/config/DT are not rebuilt.
3. `python tools/build_f364_lifetime_image.py --f363-image-result <real-image-result.json> --lifetime-result <real-lifetime-result.json>`
   requires the complete F363 image with status
   `PASS_OFFLINE_TEMPERATURE_DIAGNOSTIC_IMAGE`. It never substitutes F362.

Existing F355 lifetime/proc test evidence is reused with exact adapter/function
bindings. Thirteen source-combination contracts check readiness, serialization,
admission, initialization unwind and release ordering. The component builder
also checks the compiled function delta, exact F363 thermal/WPS function
equivalence, unchanged parameters/exports, resolved imports and paired binary
identity. It does not rerun the general historical suites.

Image composition replaces only qdrv, its driver-contract/catalogue hashes and
release metadata. All temperature components, F363 kernel/DT/config, existing
radio helpers, F352 Ethernet, identity, journal and watchdog remain intact.
Two independent rootfs repacks must match. The real preserved journal is used
for candidate and source-image full-slot hashes; FF padding is never substituted
for that store.

## Physical boundary

All work here is offline. No UART, SSH, RF/client test, restart or flash action
is performed by these builders. They do not update the physically accepted
baseline; root records any later accepted installation. The installer must
select the actually accepted recovery image and preserve mtd0/1/2/3/5 plus the
configuration store. Only a separately gated physical mtd4 firmware-prefix
write may install a completed image. Full port/release acceptance remains open.
