# OpenMitraStar HGW-500BNA-QCv2 — operational procedures

Version: `1.0`  
Date: `2026-08-30`  
Scope: owner-authorized work on the single `HGW-500BNA-QCv2 A2` unit.

These procedures are the operational contract for completing the Linux 5.10
port. Historical documents remain useful evidence, but this file controls the
current F137 workflow.

## OPS-00 — start of shift

1. Confirm the target is `192.168.1.90`, not the gateway at `192.168.1.1`.
2. Read `AGENTS.md` and `docs/OPENMITRASTAR_F137_CURRENT_STATE.md`.
3. Inspect active PowerShell, Python, TFTP, SSH and COM3 users before taking
   ownership. Do not duplicate or interrupt a running hardware gate.
4. Check ping and TCP/22. If SSH is healthy, stay read-only and do not open
   UART merely for convenience.
5. Create a new timestamped evidence directory for every run.
6. Record facts as one of: offline, live control-plane, physical client,
   traffic, persistence, or recovery proof.

Minimum connectivity check:

```powershell
Test-Connection 192.168.1.90 -Count 1
Test-NetConnection 192.168.1.90 -Port 22
```

## OPS-01 — collect a read-only live baseline

Use `tools/ramssh_exec.py`; it tries the configured RAM credential path and
then the OpenSSH wrapper. Do not print secrets or client MACs.

Collect at minimum:

- `uname -r` and `/proc/cmdline`;
- `wlan0`/`wifi0` carrier and operstate;
- `wlan0` membership in `br0`;
- qdrv RF parameter;
- hostapd control `PONG`;
- IRQ8/IRQ10 and RX/TX counters;
- bounded dmesg fatal-marker search.

For 5 GHz association state use the existing redacted monitor:

```powershell
python tools\monitor_q3_ap_association_readonly.py `
  --host 192.168.1.90 `
  --duration-seconds 30 `
  --interval-seconds 5 `
  --output-dir outputs\handoff-live\f137-readonly-<date>
```

This operation must not reboot, flash, change radio parameters, collect client
MAC values, or write to the router.

## OPS-02 — verify pinned firmware artifacts

OEM input:

```powershell
Get-FileHash -Algorithm SHA256 `
  .\Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin
```

Expected SHA-256:
`f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f`.

F137:

```powershell
Get-FileHash -Algorithm SHA256 `
  .\work\tftp\omvl\openmitrastar-linux510-q3-persistent-f137-5g-post-hostapd-rearm-from-f136-LZMA-OFFLINE-NO-FLASH.webformat.bin
python -m pytest tools\test_f137_5g_post_hostapd_rearm_builder.py -q
```

Expected F137 SHA-256:
`eb25e4f728ddf0a041424a7c7ce828c21446581e0a133f222f69e8fc0717c445`.

Also require:

- candidate size `4,373,424` bytes;
- slot-fit true for `0x7a0000` bytes;
- Bootbase contract `PASS`;
- persistent entry contract `PASS`;
- manifest and SHA256SUMS consistent;
- provider input unchanged.

## OPS-03 — build the next Linux 5.10 candidate

1. Start from the latest accepted source image, currently F137.
2. State one hypothesis and one discriminating measurement.
3. Change one subsystem/variable. Preserve 2.4 GHz, Ethernet, SSH, partition
   layout and rollback unless the experiment explicitly targets one of them.
4. Generate a new version name; never overwrite F137 or the OEM image.
5. Emit the webformat image, decompressed payload, uImage, config, DTB,
   manifest, Bootbase contract, entry contract and SHA256SUMS.
6. Run the focused builder tests plus the relevant shared regression suite.
7. Mark the candidate `OFFLINE`, `RAM-ONLY`, or `FLASH-CANDIDATE`; never infer
   one status from another.

For the current blocker, do not build F138 until a real client scan establishes
whether the branch is visibility, association, or traffic.

## OPS-04 — RAM/TFTP experiment

Use RAM/TFTP for driver, queue, RF and association experiments when a complete
cold boot is not the variable under test.

Required gates:

- exact image path/hash/size pinned;
- COM3 ownership checked;
- temporary TFTP root and firewall scope restricted to the target;
- Bootbase `iminfo`/CRC accepted;
- Linux, SSH and management recovered;
- no MTD or bootenv writes;
- result captured under a new timestamped directory;
- TFTP listener and temporary firewall rule removed afterward.

If a RAM boot hangs after kernel handoff, do not assume Bootbase automatic
fallback will recover it. Use the proven UART recovery path.

## OPS-05 — persistent write to `mtd4/linux_live`

This is destructive and requires a fresh explicit user authorization. Before
the write, state in one line:

```text
target model/IP | exact image path | bytes | SHA-256 | mtd4 offset/size | rollback | reboot plan
```

Hard preconditions:

- exact target identity verified;
- candidate and manifest hashes match;
- candidate fits `mtd4`;
- Bootbase/entry contracts pass;
- current protected-partition attestation exists;
- `mtd3/linux_safety` rollback is available;
- UART recovery is available if normal boot fails;
- no other hardware process owns COM3/TFTP;
- the user has explicitly authorized this exact write.

F137's historical guarded wrapper is:

```powershell
.\tools\arm_f137_5g_post_hostapd_rearm_flash.ps1
```

Without `-Execute` it is a dry run. Do not rerun its execute path merely
because it exists; F137 is already installed.

Post-write evidence must include candidate-prefix comparison, full-slot hash
or CRC, protected-partition hashes, kernel marker, network/SSH readiness and
the chosen rollback path.

## OPS-06 — rollback through `mtd3/linux_safety`

Preferred recovery selection is manual UART `ATGO` using the preserved safety
slot. Treat it as a deliberate recovery operation:

1. Stop all SSH/TFTP/watchers that could race the console.
2. Open the verified FTDI COM3 link at `115200 8N1`.
3. Capture the complete boot log.
4. Interrupt only at the known Bootbase prompt.
5. Use the already-proven manual safety selection; do not edit bootenv unless a
   separate, reviewed recovery plan requires it.
6. Verify OEM/safety boot and management before attempting another Linux 5.10
   candidate.

Bootbase fallback is not a watchdog: a kernel handoff hang may never return to
the loader.

## OPS-07 — SPI recovery, last resort

Use `recovery/HARDWARE_RECOVERY_RUNBOOK.md` as the detailed authority.

- Router PSU disconnected while CH341A is connected.
- Use 3.3 V only; never 5 V.
- Identify the exact SPI chip and voltage.
- Read the full physical 16 MiB chip at least twice and require identical
  hashes before any write.
- Reconstruct physical layout from `mtd0` through `mtd5` only.
- Never flash the historical `mtd0-mtd6` concatenation as a raw chip image.
- Restore the smallest proven damaged region, normally a Linux slot.
- Avoid `mtd0` and `mtd5` unless corruption is independently proven.

## OPS-08 — validate 2.4 GHz

The current F137 baseline must retain:

- `wlan0` present, up and carrier 1;
- hostapd enabled;
- `wlan0` in `br0` with `eth0`;
- WPA2 association from a physical client;
- router reachability and upstream traffic;
- useful packet/byte deltas and no queue/EMAC stall;
- IRQ20 and IRQ28 progress;
- stable reconnect and soak;
- GPIO11 active-low WLAN LED behavior.

Do not regress proven 2.4 GHz functionality while working on Quantenna 5 GHz.

## OPS-09 — finish the Quantenna 5 GHz gate

Current F137 control-plane prerequisites are present, but they are not product
proof. Run a deliberate physical-client window:

1. Place a known client close to the unit.
2. Start `monitor_q3_ap_association_readonly.py` for 120–180 seconds.
3. Scan for `OpenMitraStar-5G-DIAG` and record visible/not visible.
4. If visible, attempt association while the monitor is active.
5. Require AUTH, ASSOC, AUTHORIZED and station count > 0.
6. Prove RX and TX packet/byte deltas.
7. Prove bidirectional IPv4 on the isolated `192.168.77.0/24` path using the
   existing Aelita/oracle tooling when available.
8. Only after open diagnostic success, restore/certify WPA2 and then DFS.
9. Run a stability/thermal soak and confirm no ARC/QMAC/MuC fatal markers.

Interpretation matrix:

| Observation | Meaning | Next action |
|---|---|---|
| No client was told to scan | Inconclusive | Repeat with deliberate client action |
| Client scans, SSID invisible, AP sees probe requests | Beacon/reply TX path suspect | Trace beacon and management TX completion |
| Client scans, SSID invisible, AP sees no attempt | RF/visibility or client-band issue | Confirm client/channel then inspect RF/TPC/CoC |
| SSID visible, AUTH but no ASSOC | Authentication response/content path | Compare qdrv/hostapd events and TX completion |
| AUTHORIZED, no traffic | L3/TQE/bridge/data path | Keep isolated L3; inspect counters before bridging |
| Bidirectional traffic passes | Functional gate | Continue WPA2, DFS, cold-boot and soak certification |

Do not bridge `wifi0` into `br0` until isolated-L3 traffic is stable; an older
variant lost management during bridge activation.

## OPS-10 — evidence and release discipline

Every important operation records:

- UTC/local timestamp;
- target model and IP;
- artifact path, bytes and SHA-256;
- commands or script entrypoint;
- whether the router, UART, MTD, bootenv, network or radio was mutated;
- raw logs plus a small machine-readable result;
- explicit PASS/FAIL/INCONCLUSIVE classification;
- next discriminating test.

Never use `hostapd ENABLED`, carrier 1, `PONG`, an SSID name, or IRQ movement
alone as proof of usable Wi-Fi. Release status requires a real client and
bidirectional traffic.

## OPS-11 — final release gate

The port is release-complete only when the definition of done in `AGENTS.md`
is satisfied and a final bundle contains:

- immutable OEM firmware reference;
- final Linux 5.10 webformat image;
- SHA256SUMS and manifest;
- source/build provenance;
- flash and readback evidence;
- cold-boot and management evidence;
- 2.4 and 5 GHz client/traffic evidence;
- rollback and SPI recovery instructions;
- known limitations and explicit unresolved items.

