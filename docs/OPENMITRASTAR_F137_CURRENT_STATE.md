# OpenMitraStar F137 — current state

> Superseded by `docs/OPENMITRASTAR_F163_CURRENT_STATE.md` on 2026-08-31.

Snapshot date: `2026-08-30 20:53 CEST`  
Target: `MitraStar HGW-500BNA-QCv2 A2`  
Mission: finish the persistent Linux 5.10 port.

## Executive state

| Area | State | Evidence class |
|---|---|---|
| Persistent boot | F137 boots Linux `5.10.260-openmitrastar-radiohw` from `mtd4/linux_live` | PASS |
| Management | Ping and TCP/22 reachable at `192.168.1.90`; authenticated read-only SSH works | PASS |
| Safety slot | `mtd3/linux_safety` preserved; manual UART `ATGO` rollback retained | PASS |
| Protected flash | F137 one-shot recorded `mtd0`, `mtd1`, `mtd2`, `mtd3`, and `mtd5` unchanged | PASS |
| 2.4 GHz | `wlan0` up, carrier 1, member of `br0`; earlier WPA2 association and IP traffic proven | OPERATIONAL |
| 5 GHz control plane | `wifi0` up, carrier 1, RF=1, hostapd `PONG`, IRQ activity observed | PASS |
| 5 GHz over-air/client | No associated station or packet movement in latest read-only window; prior probe shows `Tx-Power:0 dBm` | OPEN |
| Port completion | Blocked on 5 GHz visibility, association, traffic and soak | NOT DONE |

## F137 installed artifact

```text
file   work/tftp/omvl/openmitrastar-linux510-q3-persistent-f137-5g-post-hostapd-rearm-from-f136-LZMA-OFFLINE-NO-FLASH.webformat.bin
bytes  4373424
sha256 eb25e4f728ddf0a041424a7c7ce828c21446581e0a133f222f69e8fc0717c445
crc32  66252b47
slot   mtd4/linux_live
```

The flash transaction on `2026-08-28` passed candidate-prefix readback and
booted Linux 5.10 with TCP/22 ready. The full-slot readback SHA-256 was
`6a7b415e09ba25435fb7603cba7cb40423cd86bb25bf4045c370d46d4cfef8c7`.

Protected `mtd3/linux_safety` SHA-256 recorded by that transaction:

```text
f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1
```

## OEM immutable firmware

```text
file   Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin
bytes  6729728
sha256 f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f
```

This file is an immutable provider input. Its webformat hash is not expected
to equal the padded full-slot `mtd3` hash.

## Live read-only observations

The 2026-08-30 SSH snapshot returned:

```text
kernel           5.10.260-openmitrastar-radiohw
wlan0 carrier    1
wlan0 operstate  up
wlan0 in br0     yes
wifi0 carrier    1
wifi0 operstate  up
qdrv RF          1
wifi0 hostapd    PONG
```

The MAC-redacted F137 client monitor returned one healthy control-plane sample:

```text
station_count         0
authorized_count      0
AUTH/ASSOC events     0
wifi0 RX packets      0
wifi0 TX packets      0
fatal markers         none in the previous detailed gate
classification        NO_CLIENT_ATTEMPT_OBSERVED_BY_AP
```

The detailed post-flash radio probe from 2026-08-28 additionally recorded:

```text
ESSID       OpenMitraStar-5G-DIAG
mode        Master
frequency   5.18 GHz
channel     36
Tx-Power    0 dBm
carrier     1
RF          1
hostapd     PONG
```

`Tx-Power:0 dBm` is a blocker/diagnostic marker, not by itself proof that the
radio emits nothing. A deliberate nearby client scan and association attempt
is the next discriminating test.

## Immediate next gate

With a known client physically scanning beside the device:

```powershell
python tools\monitor_q3_ap_association_readonly.py `
  --host 192.168.1.90 `
  --duration-seconds 180 `
  --interval-seconds 5 `
  --output-dir outputs\f3-certification\qtn-5g-f137-client-gate
```

Decision:

- Visible and AUTH/ASSOC observed: continue through AUTHORIZED and isolated-L3
  bidirectional traffic.
- Visible but association fails: inspect auth/assoc reply path and hostapd/qdrv
  state without changing RF configuration.
- Invisible despite a deliberate nearby scan: inspect beacon completion,
  `queue_enabled=0`, TPC/CoC and the RF/management TX path; produce F138 as a
  one-variable diagnostic candidate.
- No deliberate client attempt: keep status `INCONCLUSIVE`; do not create a
  new firmware solely from zero counters.

## Canonical evidence

- `work/mission-state/q3-persistent-composite-f137-5g-post-hostapd-rearm-from-f136/build/manifest.json`
- `work/mission-state/q3-persistent-composite-f137-5g-post-hostapd-rearm-from-f136/build/bootbase-contract.json`
- `work/mission-state/q3-persistent-composite-f137-5g-post-hostapd-rearm-from-f136/build/flash-one-shot-20260828T130824Z/result.json`
- `outputs/postflash/f137-live-radio5-probe-latest.log`
- `outputs/postflash/f137-live-client-readonly-latest.json`
- `outputs/handoff-live/f137-readonly-20260830/`
