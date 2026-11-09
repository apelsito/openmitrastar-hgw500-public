# F344 OEM MADWIFI supplicant and CLI

Prepared offline on 21 September 2026. No router, interface, RF, Wi-Fi or AELITA
operation was performed. These are userspace artifacts, not an installed
firmware or evidence of a working STA/repeater association.

## Canonical output

`outputs/userspace/f344-wpa-final-20260921T145403Z/a/`:

| File | Bytes | SHA-256 |
|---|---:|---|
| `wpa_supplicant` | 1,140,376 | `a76ccc70b018a1b37b99eab0d2c6023a4363c926fca08072ef823800ea646d79` |
| `wpa_cli` | 76,060 | `1fa6a54110624e837bb39a95c875cfb8347b0aba3b73db4afdacba03705e9dd8` |
| `libssl.a` | 550,840 | `4132ff5f801f8a0ccd6ff2c48a8ec40a5e6130c3dce1d8f12e1a72f72124b04f` |
| `libcrypto.a` | 3,008,644 | `7db0df410609f88c79a7b092a5d0980ff6eaee0ff06b6b22ad55b6dd027b07ab` |

All four files are byte-identical between independent A/B builds. Executables
are static ELF32 little-endian ARCompact, ARC700 ABI v4 (`0x403`), without
interpreter/NEEDED entries or `llock`/`scond` instructions. Static archives are
build dependencies; they do not need to be installed beside the executables.
`Module.symvers` does not apply to these userspace files.

Qualification:
`outputs/preflight/f344-qualified-20260921T145716Z/result.json`,
`PASS_OFFLINE_BUILD_AND_NATIVE_CONTROL`, 14 checks and four native CLI protocol
cases. **ARC execution remains UNRUN.** The available Linux-user emulator has
no ARC700 decoder despite accepting the CPU name. Its abort is not evidence of
a broken executable. Further emulator attempts were stopped as requested.

## Source and profile

The source is the supplied vendor
`work/sources/Quantenna-GPL/buildroot/package/wpa_supplicant/wpa_supplicant-1.1`
and its `wpa_supplicant-1.1.config`. All 26 active feature assignments remain,
including MADWIFI, WEXT, OpenSSL, the configured EAP methods, smartcard/PKCS12,
WPS/WPS2/ER, PMF and TDLS. No generic nl80211 backend was enabled and no smaller
crypto profile was substituted. Original WPS features are not the separate
F335 WPS changes.

The isolated source is `work/userspace/f344-wpa-madwifi/source`. Its only
functional source edit is the existing QTN hostapd port's `os_sleep` conversion
to `nanosleep` with EINTR handling for the noatomic uClibc environment. The
build replaces obsolete staging include/library paths with exact QTN shared
headers, the vendor MADWIFI headers and the isolated OpenSSL build.

OpenSSL 1.0.2d comes from the local GPL `download_backup` archive, SHA-256
`671c36487785628a703374c652ad2cebea45fa920ae5681515df25d9f2c9a8c8`, with the
vendor `openssl-1.0.2d.patch`. The Linux-ARC profile and algorithm configuration
are retained; static/no-assembly packaging and the existing noatomic sysroot
are used. Build-time metadata uses a fixed epoch. No source was downloaded.

The legacy parallel archive aggregation produced `libcrypto.a` members that
did not match their otherwise valid ARC ELF object files. A one-pass archive
build now uses the declared member set from the archive commands and engine
Makefile, in deterministic order, and verifies every member byte-for-byte.
Both final runs validate all 584 crypto and 50 SSL members. This is not a claim
of a general ARC compiler/archiver defect. The original failed outputs remain.

The second build was resumed after cancelling its obsolete automatic emulator
step. A/B source/object independence and final binary/archive equality are
retained and recorded. The canonical builder no longer invokes an emulator.

## Help and integration contract

Help files in the qualification directory are explicitly labelled:

- `wpa_supplicant-help.source-rendered.txt`: native rendering of the exact OEM
  `usage()` function and enabled driver metadata; no interface initialization.
- `wpa_cli-help.native.txt`: actual native CLI execution from the same source
  and feature profile. It is not execution of the ARC binary.

The OEM `-r` option is retained in both usage and parser and copied into
`global->repeater_mode`. No operational consumer of that field was found in
the supplied source; actual repeater topology is configured separately through
the driver. Accepting `-r` is not proof of repeater operation.

Use MADWIFI explicitly (`-Dmadwifi`); the preserved OEM driver array also
contains WEXT. `-b` selects the bridge and `-P` the owned PID file. With a private
configuration file, put the private `ctrl_interface` there: the documented
`-C` option applies only without `-c`. Do not assume it overrides a loaded file.
The CLI supports `-p <private-control-directory> -i wifi0` for the specific
owned instance; no global process killing is required.

Four native tests used synthetic Unix datagram peers: `STATUS`, `TERMINATE`,
`PING`, and a negative `FAIL` reply. All requests reached the selected private
socket. **The CLI also exits zero for `FAIL`**, so an exit code is insufficient;
check reply contents and actual driver/supplicant state.

The supplied MADWIFI scan method does not consume `params.freqs`; it sends
`SIOCSIWSCAN` with an otherwise empty request after SSID/IE setup. `scan_freq`
therefore is not an RF channel restriction. `freq_list` filters BSS selection,
not the scan itself. The F344 driver integration must impose/read back the
actual allowed-channel mask before activation.

`STATUS` reports BSSID, SSID, key management/ciphers and `wpa_state`, but not
the operating frequency. The `freq=` text elsewhere belongs to the BSS query.
Use actual driver frequency readback for acceptance. The fake `COMPLETED`
test response is a protocol fixture, not an association result.

No real STA, repeater, traffic or RF acceptance is claimed. Wi-Fi tests remain
deferred by the owner.
