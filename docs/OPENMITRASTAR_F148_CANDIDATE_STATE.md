# OpenMitraStar F148 candidate state

Snapshot date: `2026-08-31 CEST`

## Installed state

- Physical target: `HGW-500BNA-QCv2 A2`.
- Persistent firmware: F147 in `mtd4/linux_live`.
- Kernel and SSH: Linux `5.10.260-openmitrastar-radiohw`, reachable at `192.168.1.90`.
- 2.4 GHz: operational baseline preserved.
- 5 GHz: SSID visibility and association proven; dynamic ARP remains intermittent.
- Safety: `mtd3/linux_safety` remains the manual UART rollback slot.

## Root cause addressed by F148

F147 contained a mixed module contract:

- `qdrv.ko` validates station node indices using bit `0x8000`.
- The embedded older `wlan.ko` stored the station node as raw `4/5` because its
  `BR_SUBPORT_MAP()` compatibility definition was identity.
- Consequently, an associated client with destination node `5` reached AuC as
  `dest_port=5`; qdrv rejected it as an unmapped node and fell back to VAP node
  `4`.

Binary verification:

- F147 `wlan.ko`: `ieee80211_idx_add` stores the raw index directly.
- F148 `wlan.ko`: `ieee80211_idx_add` executes `bset ...,0xf` before storing it.
- Expected runtime transition: `dest_port=5 node=4` becomes
  `dest_port=32773 node=5` for station node 5.

## F148 candidate

```text
file   work/mission-state/q3-persistent-composite-f148-5g-subport-map-pair-from-f147/build/openmitrastar-linux510-q3-persistent-f148-5g-subport-map-pair-from-f147-LZMA-OFFLINE-NO-FLASH.webformat.bin
bytes  4373867
sha256 9eb679bb6c4fb9cfb4a5cacf8bbcff2a2ce6c9c063d29f9f4d54b3d6262ac800
crc32  0a90afdd
slot   mtd4/linux_live only
```

Expected padded full-slot identity:

```text
sha256 b241bb7231353329ac3a4de202272c3f55505404ba797be1ff0e0e12e7ebd21d
crc32  da1e1db3
```

Module pair:

```text
qdrv.ko  600a6f98bb3151cf80755bd5132b8bc9a7460b86146557d57ba8c97568d5a581
wlan.ko  a750b273c0570c2ccfe0fce3f28a311d2e8e3b9f7d7ef9f7cd9ed48046065233
```

## Offline gates

- Clean 25-module build: PASS.
- F148 builder tests: 4/4 PASS.
- F148 operations contract tests: 3/3 PASS.
- SSH monitor regression tests: 2/2 PASS.
- Fixed initramfs layout and CPIO endpoint: PASS.
- SHA256SUMS: PASS.
- Bootbase image contract and slot-fit check: PASS.
- Flash dry-run: PASS, no hardware write performed.

## Flash and acceptance gate

The candidate is not flashed yet. Execution requires the exact acknowledgement:

```text
OPENMITRASTAR_Q3_F148_5G_SUBPORT_MAP_PAIR_FROM_F147_MTD4_FLASH_9EB679BB
```

After flash:

1. Verify protected partition hashes and exact `mtd4` prefix/full-slot readback.
2. Boot Linux 5.10 and verify SSH plus the 2.4 GHz baseline.
3. Start 5 GHz and require the F148 qdrv and wlan hashes.
4. Associate AELITA and verify `auc-submit` selects the client node.
5. Test dynamic ARP and bidirectional ICMP without a static neighbor entry.

