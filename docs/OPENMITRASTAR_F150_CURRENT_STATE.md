# OpenMitraStar F150 current state

Snapshot date: `2026-08-31 18:03 CEST`

## Installed firmware

- Target: `HGW-500BNA-QCv2 A2`.
- Slot: physical `mtd4/linux_live` only.
- Kernel: `5.10.260-openmitrastar-radiohw`.
- Candidate bytes: `4374454`.
- Candidate SHA-256:
  `4e5ff1eaeca084cebc0f55ff853daf6709e6f6a951ba8ede53cfe218947bd48c`.
- Full-slot CRC32: `de411a32`.
- Full-slot SHA-256:
  `687e3e039ae3a9a60a1e8b8dfabd7a341c7d198445788400c6922fbf80e90826`.
- `mtd3/linux_safety` and all protected partitions were preserved.

Flash evidence:

`work/mission-state/q3-persistent-composite-f150-5g-autostart-enable-from-f149/build/flash-one-shot-20260831T155641Z/result.json`

## Demonstrated runtime state

- Persistent cold boot: PASS.
- Ethernet management and SSH at `192.168.1.90`: PASS.
- 2.4 GHz hostapd `state=ENABLED`: PASS.
- 5 GHz autonomous `rcS` start: PASS; no manual `om-radio5-start` invocation.
- `wifi0`, RF, carrier, hostapd control and 21 dBm readback: PASS.
- F148 matched qdrv/wlan module pair: PASS.
- AELITA association for 120 seconds: PASS, 24/24 connected samples.
- Dynamic ARP and client-to-router ICMP: PASS, 10/10 replies.
- Router RX/TX packet deltas and IRQ activity during association: PASS.
- Management remained reachable and AELITA restored its primary WiFi: PASS.
- Fatal MuC/MMU/kernel markers during the acceptance window: none.

Acceptance evidence:

`outputs/f3-certification/qtn-5g-f150-autostart-20260831-175914/`

## Root cause closed

The F147 module set mixed a qdrv that required mapped station indices with an
older wlan that stored raw indices. Downlink traffic for station node 5 reached
AuC as `dest_port=5 node=4`, falling back to the VAP node. F148/F150 use a
matched pair; live traces now show `dest_port=32773 node=5`, and dynamic ARP is
reliable in the completed acceptance run.

## Remaining product work

- The 5 GHz AP is intentionally still `open-lab` and isolated on
  `192.168.77.0/24`; WPA2 is not yet certified.
- DHCP, normal LAN bridge/forwarding policy, Internet path and OEM web-driven
  5 GHz configuration are not yet certified.
- DFS channels and regulatory behavior beyond the proven channel 36 path are
  unverified.
- Long-duration traffic/thermal soak and repeated cold-boot cycles remain.
- Two nonfatal Linux 5.10 sysfs compatibility warnings remain:
  `tqe_sem_en` uses mode `0700`, and `wps_button` advertises write permission
  without a store callback.

F150 is therefore the first persistent dual-radio functional checkpoint, not
the final OEM-equivalent release.

