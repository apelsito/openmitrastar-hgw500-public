# OpenMitraStar F165 current state

Snapshot date: `2026-09-01`

## Installed firmware

- Target: `MitraStar HGW-500BNA-QCv2 A2`
- Kernel: `5.10.260-openmitrastar-radiohw`
- Physical slot: `mtd4/linux_live`
- Root filesystem: SquashFS-XZ, read-only
- Candidate size: `4,956,160` bytes (`0x4ba000`)
- Candidate SHA-256: `251b20b39142056ceb271298c726beeba4baef40a32921ac3c900637b74945f9`
- Candidate CRC32: `4a2ae5b2`
- Full-slot CRC32: `5123431d`
- Full-slot SHA-256: `8ce72a31e04962e99e3884ec53902951d89fa509891026b25c7050d388da315f`
- Rollback: preserved `mtd3/linux_safety`, manual UART `ATGO`
- Protected partitions: CRC32 unchanged before and after the write

Flash evidence:
`work/mission-state/q3-persistent-composite-f165-squashfs-exact-mtd/build/flash-one-shot-20260901T080803Z/result.json`

## F165 change

F165 changes only the Linux `physmap-core` size calculation for mappings
without GPIO address lines. The exact device-tree resource size is retained,
instead of rounding the non-power-of-two `rootfs_live` window down to 4 MiB.

Observed hardware result:

```text
physmap-flash 90960000.flash: [mem 0x90960000-0x90f7ffff]
mtd3: 00620000 00010000 "rootfs_live"
/dev/root on / type squashfs (ro,relatime)
```

`/run` and `/tmp` are tmpfs. `/persist` remains JFFS2 read-only.

## UART materialization

F165 was transferred without Ethernet/TFTP using U-Boot `loady` and YMODEM:

```text
RAM address:        0x83000000
Transferred bytes:  0x4ba000
RAM CRC32:          4a2ae5b2
Flash target:       0x007e0000 + 0x007a0000 (mtd4 only)
Readback CRC32:     5123431d
Prefix compare:     4,956,160 bytes identical
```

The transfer took about 959 seconds at 115200 baud and recovered from repeated
ACK timeouts. No environment or protected-partition write was performed.

Canonical command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_flash_test_lyoko.ps1 `
  -Execute -SkipBuild -Transport uart-ymodem -Port COM3
```

## Boot evidence

- Initial post-flash boot: PASS.
- Persistent UART reboot 2: PASS after waiting for the 2.4 GHz hostapd control socket.
- Persistent UART reboot 3: PASS.
- SSH, Ethernet management, SquashFS root, exact MTD window, 2.4 control plane,
  5 GHz control plane, `wifi0` bridge membership and 21 dBm 5 GHz report: PASS.
- One early reboot-2 sample queried 2.4 GHz before hostapd was ready; the gate now
  waits for `hostapd_cli ping == PONG` before evaluating `state=ENABLED`.

## Remaining acceptance work

- Repeat real-client bidirectional throughput on both bands under F165.
- The local Windows host currently has no visible WLAN adapter and `WlanSvc` is
  stopped, so client traffic certification was not repeated in this session.
- Run simultaneous dual-radio soak, DFS/CAC/radar, multicast, VLAN and IGMP.
- Continue EMAC RX/IRQ/NAPI work only after the F165 traffic baseline is recorded.

