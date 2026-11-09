# OpenMitraStar F267 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.1.0-f267-radio-workbench-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5255168`
- Candidate SHA-256: `3fb0c5242558bd264f1ab41331681dceab2c829437d4b2f4a6a65fe6ab00f8a7`
- Full-slot CRC32: `69e4abff`
- Full-slot SHA-256: `d0796c595e8f6794b2fca50c619e186324056daf3f8028a9b2ab13acd3d54348`
- Bootbase TFTP write and full readback: PASS
- Protected `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5`: PASS / unchanged

Evidence:

- `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f267-device-bound\flash-one-shot-20260903T090926Z\result.json`
- `outputs/postflash/f267-device-20260903T090917Z/`
- `outputs/postflash/f267-radio2-expanded-20260903T091505Z/result.json`
- `outputs/postflash/f267-package-20260903-111703/status.json`

## Physical result

- Linux `5.10.260-openmitrastar-radiohw`: PASS
- SquashFS root, tmpfs `/run` and `/tmp`, read-only `/persist`: PASS
- SSH identity and management at `192.168.1.90`: PASS
- `br0`, `eth0`, `wlan0` and `wifi0`: PASS
- Realtek 2.4 GHz AP: PASS
- Quantenna 5 GHz AP boot path: PASS
- Signed package lifecycle in `/run`: PASS; `mtd5` unchanged
- Fatal kernel/MuC/QMAC markers: zero

## Radio workbench

F267 replaces decorative controls with values derived from the radio contract.
Every visible setting reports its current value, allowed range, write state,
backend, recommendation, effect and risk.

The 2.4 GHz transaction now supports:

- SSID;
- channel 1-13;
- 20/40 MHz bandwidth;
- SSID broadcast;
- client isolation;
- WMM;
- Short GI;
- beacon interval;
- DTIM period;
- maximum associated clients.

The physical expanded transaction changed all controls except SSID, verified
the resulting hostapd/driver state, restored the complete original state and
confirmed that 5 GHz did not change.

The 5 GHz page exposes the full current contract and advanced profile, but
dynamic writes remain disabled by default. F265 demonstrated that the old
WEXT/hostapd mutation sequence can remove Ethernet and SSH. F266/F267 keep the
boot-time 5 GHz AP unchanged and preserve UART trace points for later isolation.

DFS remains fail-closed. Channels 52-140 are visible for inspection, but are
not applicable until a native radar backend proves CAC, continuous detection,
channel evacuation and non-occupancy behavior.

## UI validation

- Foundation and integration tests: 35 PASS
- F267 builder tests: 3 PASS
- `SHA256SUMS`: PASS
- Desktop browser: no horizontal document overflow
- Mobile viewport 390x844: no horizontal document overflow
- Python and Node emulators agree that Quantenna mutation is unavailable
- UI version: `6.1.0`, build `78658c24772eb625`

## Remaining work

1. Isolate the failing Quantenna dynamic step using the F266/F267 UART markers.
2. Add write-only PSK rotation with redacted rollback storage.
3. Implement a measured automatic-channel engine; do not expose a fake action.
4. Add physical RSSI/PHY samples to the coverage view.
5. Run real-client throughput and long dual-radio soak after each datapath change.

