# F362: F361 plus qualified F352 dual Ethernet

## Physical result - 2026-09-21 20:20 UTC

The root operator installed this exact image successfully. Evidence:
`/workspace/OpenMitraStar/f362-evidence/f362-install-20260921T201238Z-d650b1af/result.json`,
SHA256 `37d2e11cbe710f9028457ac476f46617f776a339e6d50e459ed21cd9faaac518`.
Result `PASS_F362_PRESERVED_JOURNAL`: byte comparison, protected partitions,
sequence2 store, boot configuration and platform27PASS. Both netdevs are in br0;
eth1/MAC0/PHY1 has carrier, eth0/MAC1/PHY3 is disconnected. No fallback was needed.

`outputs/handoff-live/f362-management-stream-20260921T202006Z/result.json`
records a1MiBstream in each direction through the connected eth1 management path,
matching both hashes with no new RX/TX errors or reboot. Second-connector traffic,
simultaneous forwarding, cold power-cycle and release soak remain untested.
The root closed all installer helpers, UART, lease and awake hold. Wi-Fi tests
remain deferred. The remainder below describes the original immutable build.

Built offline on 2026-09-21. No router, SSH, UART, reset, TFTP or flash action
was performed by the image builder. Physical acceptance remains separate.

## Immutable candidate

- Private directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f362-f361-dual-ethernet-device-bound/`.
- Image: `openmitrastar-linux510-f362-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Bytes: **5,390,336**.
- SHA-256: `9582b92f1c68ec192ee14c55ba9ab69015749cc69ecde392bd6ad3392d105f2b`.
- Manifest SHA-256: `8e576d3d5f4676dcf5287d8dc640784a7756daf9af2a9ce77c585c1eb3300957`.
- Product: `lyoko-foundation-6.9.10-f362-dual-ethernet-device`.
- Build ID: `45e3d7e50423fd4b`; kernel identity remains F358 `#358`.
- Result: private `analysis/f362-fullimage-20260921T200242Z/result.json`.
- Kernel result: private `analysis/f362-dual-ethernet-kernel-20260921T200040Z/result.json`.

## Bounded change

The F358 kernel configuration, exported ABI and all individual C objects are
unchanged. Of 820 compared `.o` files, only the Ethernet DT object and aggregate
`vmlinux.o` differ. The DT changes only `compatible` and `qtn,f352-dual-direct`
on `/soc/ethernet@e8000000`; existing `status=okay` is preserved. All other
properties and reserved memory entries remain intact.

Six rootfs files change relative to F361:

- Add `etc/init.d/S15-f352-driver`, using `/usr/sbin/ram-insmod-qtn` before config/network startup.
- Add the exact qualified `qtn-topaz-emac-f352.ko` under the Ethernet module directory.
- Add the exact qualified `usr/sbin/om-ethernet-f352`.
- Add the exact qualified `etc/init.d/S56-f352-ethernet` after bridge startup.
- Update `etc/openmitrastar/release`.
- Update only the release hash in `usr/share/openmitrastar/storage/artifacts.sha256`.

`eth0` is MAC1/PHY3; `eth1` is MAC0/PHY1. The F352 helper derives the secondary
MAC from the actual runtime primary using the OEM first-byte-plus-two rule,
before raising eth1 and joining br0. Existing radio code/modules, network base,
device identity, journal consumer and watchdog supervisor remain byte-identical.

## Evidence and installation boundary

Bootbase contract, prefix fit, embedded DT equality, module imports, unchanged
configuration/exports, exact rootfs delta, shell syntax/startup ordering and
installed artifact catalogues pass. Two independent rootfs repacks/compositions
are byte-identical. Existing F352 qualification is reused: 4,933 C checks and
12 bridge-helper scenarios; these were not rerun.

The current store must remain **1,835,008 bytes**, SHA-256
`fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873`,
CRC32 `5d2ee646`. Its source is private
`analysis/f361-store-seq2-20260921T193734Z/store.bin`.

- F362 padded firmware-prefix CRC32: `5f10bf14`.
- F362 full slot with that store: CRC32 `1a6e28c0`, SHA-256
  `3938b335346ab03b2ead396289daff0905b1b85a15bf125fddbad09934a8b209`.
- Exact F361 fallback: 5,378,048 bytes, SHA-256
  `0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af`.
- F361 prefix CRC32: `4cb7f99e`; full-slot CRC32 with the same store: `815b9440`.

**OFFLINE GO; physical recovery and installer gates pending.** The only future
write target is the physical mtd4 firmware prefix at `0x7e0000+0x5e0000`, ending
before `0xdc0000`. Preserve DC/DD store and mtd0/1/2/3/5. Never write logical
mtd6 or change boot environment. Root is the sole hardware operator. Boot,
both connectors, simultaneous bridge operation and traffic remain unrun;
Wi-Fi/client/RF acceptance remains deferred.

Rebuild with `python tools/build_f362_dual_ethernet_kernel.py`, then
`python tools/build_f362_dual_ethernet_image.py --kernel-result <result.json>`.
The image builder refuses to replace the immutable private release directory.
