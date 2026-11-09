# OpenMitraStar — Manual de Operaciones de la Nave

> Historical draft. For the current F137 mission, use
> `docs/OPENMITRASTAR_HGW500_OPS.md` and
> `docs/OPENMITRASTAR_F137_CURRENT_STATE.md` as the canonical operating
> documents.

Version: `0.1-draft`  
Date: `2026-08-21`  
Target: `MitraStar HGW-500BNA-QCv2 A2`  
CPU: `ARC700 / ARCompact`  
Kernel target: `Linux 5.10.260-openmitrastar-radiohw`

This manual describes only behavior supported by source or hardware evidence.
`PROVEN` means observed on the real unit. `PORTED` means implemented and tested
offline but still requiring the stated hardware gate. `UNKNOWN` is intentionally
left unresolved rather than inferred from the enclosure label.

## 1. Safety and recovery boundary

- The physical flash is 16 MiB. `mtd6` is a logical view, not an additional
  physical partition.
- Preserve `mtd0` bootloader, both environment copies, `mtd3/linux_safety` and
  device calibration/data.
- Experimental Q3 images are RAM/TFTP-only until the complete promotion gate
  passes. A successful Linux boot or SSH login is not a flash authorization.
- Recovery path: USB-UART `115200 8N1` -> interrupt Bootbase -> TFTP candidate
  -> `iminfo` CRC -> `bootm`. Manual `ATGO` selects the preserved safety path.
- If exposed silicon becomes too hot to touch comfortably, power down and let
  it cool before continuing RF or stability tests.

## 2. Normal management plane

| Function | Current contract |
|---|---|
| Management IPv4 | `192.168.1.90/24` |
| Upstream gateway/DNS | `192.168.1.1` |
| Recovery/TFTP client | `192.168.1.200` |
| SSH | key-only, port 22 |
| HTTP | port 80 |
| HTTPS | port 443 only when an external mode-0600 PEM is supplied |
| OEM-compatible getinfo | port 16667 |
| Product role | L2 videobridge; no local DHCP/DNS/NAT/router firewall |

## 3. Radio state

### 2.4 GHz — Realtek

| Item | State |
|---|---|
| PCI device | `10ec:818b` |
| Driver | `rtl8192ee` |
| Interface | `wlan0` |
| Firmware | `rtlwifi/rtl8192eefw.bin` |
| Current lab SSID | `OpenMitraStar-Lab` |
| Security | WPA2-PSK / CCMP; secret is an external runtime input |
| Default lab channel | 1 / ES |
| Bridge | `br0` with `eth0` |

Operational healthy state requires all of:

```text
hostapd state=ENABLED
/sys/class/net/wlan0/carrier = 1
/sys/class/net/br0/brif/wlan0 exists
IRQ28 progresses
```

### 5 GHz — Quantenna

The RAM candidate uses `wifi0`, ES, channel 36, 80 MHz and an open diagnostic
SSID until association is proven. Secure WPA2, DFS and client-traffic
certification remain separate gates.

Healthy control-plane state requires:

```text
hostapd PONG
wifi0 carrier=1
IRQ8 progresses
no MuC exception / EV_TLB / QMACDie fatal marker
```

## 4. Front-panel LED map

| Physical/logical function | GPIO | Polarity | ON condition | Evidence/state |
|---|---:|---|---|---|
| Boot/alive lower green | 7 | active-high | asserted during early boot; cleared by product-ready | PROVEN |
| WLAN 2.4 GHz | 11 | **active-low** | `wlan0` running as AP | PROVEN physically on 2026-08-21 |
| WLAN 5 GHz | 1 | active-high | `wifi0` HOSTAP/RUN with carrier | PORTED; physical polarity still independently gated |
| WPS indication | shared WLAN LEDs | per-radio | blink/success/error state machine | BLOCKED, not yet ported |
| Ethernet | unknown/PHY-managed | unknown | link/activity | UNKNOWN |
| Enclosure IPTV/status label | unknown | unknown | unknown | UNKNOWN; do not relabel GPIO7 without evidence |

Critical 2.4 GHz physical proof:

```text
wlan0 hostapd=ENABLED, carrier=1
sysfs brightness=255 -> physical LED OFF
sysfs brightness=0   -> physical LED ON
```

Therefore GPIO11 must be declared active-low. Logical LED brightness remains
normal to userspace after the driver polarity fix: `255` means logically ON and
the driver writes the physical low level.

## 5. Rear controls

### Lower button beside Ethernet — Wi-Fi/RF enable

| Property | Contract |
|---|---|
| GPIO | 2 |
| Polarity | active-low |
| Physical identity | lower rear control beside Ethernet |
| Short release | OEM policy: no action |
| Stable hold | 5 seconds requests one persistent 2.4 GHz toggle |
| Debounce | press 50 ms; release must remain quiet for 500 ms |

This is not labelled as WPS. The current-unit configuration says
`monitorrfenable=1` and provides no active WPS configuration. A physical
actuation initially generated repeated release logs; the Linux 5.10 fix
coalesces the full actuation into one semantic event.

### WPS

Generic OEM sources assign GPIO4 both to a `5G WIFI Button` five-second toggle
record and to the non-Amber WPS fallback. The current unit does not provide an
explicit GPIO4 setting and no physical GPIO4 correlation exists. It therefore
remains unassigned and fail-closed. GPIO2 must not be repurposed as WPS.

### Reset button

| Hold time | Requested action |
|---|---|
| below 1 second | none |
| 1 to below 5 seconds | normal restart |
| 5 seconds or more | guarded factory-reset transaction, then restart |

Factory reset is userspace-controlled and must preserve bootloader,
environments, MAC, calibration, radio data, SSH host keys and Wi-Fi PSK. It is
refused unless persistence is read-write and a verified backup already exists.

## 6. LED diagnostics

Read logical state:

```sh
cat /sys/class/leds/openmitrastar:green:wlan2g/brightness
cat /sys/class/leds/openmitrastar:green:wlan5g/brightness
cat /sys/class/leds/topaz:stage0:alive/brightness
```

Do not infer physical polarity from the numeric value. The LED class exposes a
logical brightness; the driver translates it to the board-specific electrical
level.

## 7. Evidence checklist before declaring a radio functional

For each band require:

```text
driver and firmware loaded
interface present and running
AP control state enabled
physical LED matches logical state
client associates
client receives upstream DHCP configuration
DNS works
bidirectional traffic progresses
idle and burst traffic remain stable
no kernel/MuC exception
```

Visibility of an SSID alone is not a pass.

## 8. Current unfinished operations

- Validate the corrected GPIO11 active-low kernel in a fresh RAM boot.
- Verify one short GPIO2 operation produces exactly one no-action log.
- Verify one stable 5-second GPIO2 hold produces exactly one 2.4 GHz toggle.
- Physically map GPIO1/5 GHz and all enclosure labels.
- Implement and certify WPS separately.
- Certify 5 GHz association, traffic, WPA2 and DFS.
- Certify persistence, power-cycle and recovery before Q3 flash promotion.

## 9. Evidence locations

- `docs/HGW500_Q1_CONTROLS_PARITY_20260820.md`
- `outputs/kernel-port/hgw500-controls-active-low-20260821/`
- `work/mission-state/EVIDENCE_LEDGER.md`
- `work/mission-state/HARDWARE_STATE.json`
- `work/mission-state/MISSION_STATE.md`
