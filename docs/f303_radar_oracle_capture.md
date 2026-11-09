# F303 OEM radar oracle capture

Date: 2026-09-04  
Target: MitraStar `HGW-500BNA-QCv2 A2`  
Status: prepared offline; hardware execution not run

## Purpose

This workflow collects a bounded OEM radar-classifier oracle from the preserved
Linux 2.6.35 image in physical `mtd3/linux_safety`, then returns to the installed
F301 Linux 5.10 image in physical `mtd4/linux_live`.

It does not flash any image. It does not alter Bootbase environment variables.
The OEM slot is read into RAM by Bootbase and booted once with a transient
`init=/bin/sh` argument.

## Entrypoints

- `tools/f303_radar_oracle_capture.ps1`: preflight, UART state machine,
  evidence capture and recovery.
- `tools/f303_radar_oracle_evidence.py`: synthetic-vector validation,
  sanitization and SHA-256 manifest generation.
- `tools/test_f303_radar_oracle_capture.py`: offline regression suite.

Dry-run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\tools\f303_radar_oracle_capture.ps1
```

The dry-run performs local file reads only. It never enumerates or opens COM3,
contacts the router, changes a radio, reboots or accesses an MTD device.

Future physical execution requires the exact acknowledgement:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\tools\f303_radar_oracle_capture.ps1 `
  -Execute `
  -Ack OPENMITRASTAR_F303_RADAR_ORACLE_MTD3_TEMPORARY
```

## Immutable inputs

| Input | Expected SHA-256 |
|---|---|
| Installed F301 candidate | `4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262` |
| Preserved physical `mtd3` | `f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1` |
| OEM webformat reference | `f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f` |
| OEM `radar.ko` | `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332` |
| Proven historical ATGO boot log | `ef928a82ffe27f9a8b982d8a361dc490b13c3639267cc941ba9571ecd1cb88c8` |

The physical run additionally requires live F301 identity, pinned SSH host key,
COM3 availability, no active soak/gate and Bootbase values
`bootcmd=bootselect`, `bootselect=0`.

## Read-only boot design

The workflow deliberately avoids a normal OEM boot. A normal Linux 2.6 startup
mounts the data partition and creates a MiniFO overlay, which could modify
`mtd5`. Instead the runner performs:

```text
F301/mtd4
  -> normal reboot
  -> interrupt Bootbase
  -> spi_flash read mtd3 -> 0x83000000
  -> iminfo checksum
  -> transient setenv bootargs ${bootargs} init=/bin/sh
  -> bootm 0x83000000
```

There is no `saveenv`. The transient `setenv` disappears at the following
reset. The OEM shell mounts only `proc`, `sysfs` and tmpfs instances at `/tmp`,
`/var`, `/mnt/jffs2` and `/mnt/ccc`. It never runs `/etc/init.d/rcS`,
`mount_data_partition` or the OEM writable overlay.

Before loading the radar stack, and again after disabling it, the runner reads
MD5 values for physical `mtd0` through `mtd5`. All six values must be present
and identical. MD5 is used only as the hash available in OEM BusyBox for
before/after equality; the host generates SHA-256 for every retained evidence
file.

## Oracle sequence

The capture is deliberately bounded and uses a reviewed synthetic vector:

```text
start
  qdrv loads radar.ko and invokes radar_start
bandwidth
  iwpriv wifi0 radar_bw <20|40|80>
channel
  wifi0 remains down; select an EU non-weather DFS channel
enable
  echo enable:1 > /proc/radar
poll/detection
  tstart -> paired tdata words -> tend -> bounded wait
disable
  echo enable:0 > /proc/radar; wifi0 stays down
```

The default vector uses EU channel 100 and 80 MHz. Channels 116-128 are rejected
because they intersect the weather-radar band and require a 600-second CAC.
The script does not create an AP, enable hostapd or authorize data transmission.

The retained observations are limited to:

- stage and return-code markers;
- a small allowlist from `/proc/radar`;
- bounded radar/DFS/CAC/CSA kernel messages;
- before/after physical-partition hashes;
- generic Bootbase checksum and kernel-version lines;
- a SHA-256 of the complete in-memory UART byte stream.

The raw UART stream is never written to disk. Lines mentioning credentials,
keys, MAC addresses, serial identity or calibration are discarded even when
they otherwise match an allowed prefix.

## Return and recovery

The normal end path disables radar, keeps `wifi0` down and executes a forced
reset. Because the persistent environment was never changed, Bootbase selects
`mtd4/linux_live`; the runner requires the F301 kernel marker and exact release
identity over pinned SSH.

On failure:

1. Send UART SysRq reset.
2. Allow normal `bootselect=0` startup.
3. If a Bootbase prompt remains available, read physical `mtd4` to RAM,
   validate it with `iminfo` and boot it directly.
4. Require exact F301 SSH identity before reporting recovery success.

The recovery path contains only `spi_flash read`, `iminfo`, `bootm` and reset.
It contains no erase, program, MTD write, `saveenv`, `updatecrc`, `qtnboot` or
boot-environment persistence.

## Evidence layout

Each run uses a new immutable directory under `outputs/preflight/` or a supplied
empty output directory:

```text
plan.json
oracle-commands.json
events.jsonl                 execute only
uart-sanitized.log           execute only
result.json                  execute only
evidence-sha256.json
```

`result.json` is `PASS` only if the OEM sequence completes, all six MTD hashes
remain identical and exact F301 returns. A failed run records its phase and
recovery result without converting partial evidence into success.

## Current boundary

This tool prepares an OEM oracle capture; it does not claim a native DFS
detector. The returned vector/counters are input evidence for the later F303
classifier reconstruction. Actual RF radar certification still requires a
calibrated authorized test source and separate CAC, evacuation, CSA and NOP
gates.
