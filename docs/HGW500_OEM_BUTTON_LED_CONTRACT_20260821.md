# HGW-500BNA-QCv2 A2 OEM button and LED contract

Date: 2026-08-21

This document separates current-unit facts from generic GPL behavior and from
remaining electrical uncertainty. The immutable OEM inputs are:

| Input | SHA-256 |
|---|---|
| `usr/sbin/monitor_button` | `efcafebf78c12f11e8c0ede7f04c4cbe086b59c5c7ac74f24cc7081e07e587e0` |
| `sbin/monitor_wifi` | `ffbdb7d3bf3b099a106be532df02595c8eef20da7ace0b27d43bc27746aca734` |
| `usr/sbin/sys` | `75c89924ef6a1871a3bd50d996c6dcb51a1dae3d4ff81fde0444f70fc39a09f6` |
| `sbin/monitor_reset_device` | `40af0ae1d97d670ff17509a3fa9cfbb20fd965491babdf4c82e5b333312036ff` |
| `sbin/monitor_rfenable` | `7367ff06cc19774c748725e85053c26ed445d55afd4b828cce0d0c33f1a43568` |
| `scripts/start-helpers.sh` | `7c9171db5fd2feb5e6f8d8a2fb9e496701327e00c10db336c58be0684252749c` |
| `scripts/start-prod` | `af612d80aa52a393a049f4ae6e8bcd6fdee9b46e0db57d2500b15c6ce0fca16a` |
| `lib/librdmhandler.so` | `deda5e5c4d520447c2ca423e696d1080652c9805f098e612665510ad9cf0fd25` |

## Buttons and switches

### GPIO2 — 2.4 GHz Wi-Fi button

**PROVEN from the exact binary.** `monitor_button` constructs a record named
`2.4G WIFI Button` with GPIO `2`, released/previous level `1`, counter `0`,
threshold `0x0a`, and callback `0x10960`. The common loop calls
`qcsapi_led_get`, treats level zero as pressed, and sleeps `0x7a120 = 500000`
microseconds per full iteration.

- polarity: active-low;
- short release: no callback and no persistent action in `monitor_button`;
- long threshold: ten consecutive low samples, approximately five seconds;
- repeat behavior: a fired byte is set before invoking the callback, so one
  hold triggers exactly once; release resets the count and fired byte;
- long action: callback `0x10960` selects RDM object `0xda90`, flips byte 11 of
  the object selected as `Enable`, calls `rdmRequestSet`,
  `rdmApplySetObject`, `cccRdmDirectSave`, then deinitializes RDM;
- persistence: yes, explicitly through `cccRdmDirectSave`.

No current-unit evidence connects GPIO2 short release to WPS. The current unit
is on the non-Amber branch, proven below, so `monitor_rfenable` does not own
GPIO2 either.

### GPIO4 — combined 5 GHz toggle and qdrv WPS input

**PROVEN as two independent OEM currents.**

`monitor_button` constructs `5G WIFI Button` with GPIO `4`, released level
`1`, threshold `0x0a`, callback `0x10a28`, and the same 500 ms loop:

- short release in `monitor_button`: no action;
- at approximately five seconds: exactly one callback;
- callback: select RDM object `0x12ed0`, flip `Enable`, apply and save through
  the same `rdmApplySetObject` plus `cccRdmDirectSave` sequence;
- persistence: yes.

Separately, `start-helpers.sh` falls back to `wps_push_button_gpio=4` when the
parameter is absent. The live wireless configuration has no explicit WPS GPIO.
`start-prod` therefore calls `enable_wps_push_button 4 0`. The actual OEM UART
boot confirms the resolved current-unit branch:

```text
[   35.695000] WPS: push button GPIO pin 4
[   35.705000] WPS: monitored using polling
[   35.705000] WPS: active logic is low
```

The qdrv timer samples every `3*HZ/10` (300 ms). It records the falling edge
and acts on release:

- held less than ten seconds: `WPS_BUTTON_WIRELESS_EVENT` plus
  `WPS-BUTTON.indication`;
- held at least ten seconds: `WPS_BUTTON_DBGDUMP_EVENT` instead of WPS.

Combined exact behavior:

| Physical GPIO4 hold | `monitor_button` current | qdrv current on release |
|---|---|---|
| brief, `<5 s` | no toggle | WPS wireless event |
| `5 s` to `<10 s` | toggle/persist 5 GHz once at ~5 s | WPS wireless event on release |
| `>=10 s` | toggle/persist 5 GHz once at ~5 s | debug-dump event on release |

The five-second toggle does **not** unload qdrv before release:

1. the RDM WLAN setter contains `call_qcsapi enable_interface %s %d`;
2. `libqcsapi` `local_interface_enable` performs `SIOCGIFFLAGS` (`0x8913`)
   and `SIOCSIFFLAGS` (`0x8914`), changing interface flags rather than
   removing the VAP or module;
3. qdrv `vnet_stop()` stops IEEE80211/NAPI/queue but does not call
   `qdrv_wps_button_exit()`;
4. WPS polling is removed only in `qdrv_vap_exit_muc_done()` after the last
   VAP is deleted.

Thus the overlapping five-second toggle and release event are genuine OEM
behavior, not mutually exclusive interpretations.

### GPIO5 — reset

**PROVEN from exact start script and binary/GPL-matching call path.**

`start-helpers.sh` fixes `reset_device_gpio=5`; `start-prod` launches
`monitor_reset_device 5 0`, so the input is active-low. The callback samples
once per second:

- released before accumulating one complete sample: no action;
- accumulated count `1..4`: reboot on release;
- accumulated count `>=5`: run
  `/scripts/restore_default_config -nr -ip`, then reboot;
- if continuously held, the guard completes after the bounded counter and
  chooses factory reset.

Factory reset and reboot are persistent/destructive OEM actions. OpenMitraStar
keeps them behind its managed-config backup transaction instead of copying the
OEM raw action blindly.

### GPIO12 — RF-enable switch

**PROVEN current-unit branch.** The generic non-Amber assignment is GPIO12;
Amber would replace it with GPIO2 and WPS with GPIO1. The live OEM boot resolves
WPS to GPIO4, proving the non-Amber branch for this unit. `start-prod` launches
`monitor_rfenable 12 1` because `monitorrfenable=1` in the live configuration.

`monitor_rfenable` reads the pin, treats high as RF enabled, calls both the
remote `rfenable` RPC when available and local `qcsapi_wifi_rfenable(onoff)`,
then blocks until the next electrical transition. This is state-following,
not short/long-press logic, and it does not persist an RDM value.

### Mechanical power control

**UNKNOWN / not software-mapped.** No OEM GPIO/button monitor found in this
firmware controls input power. Do not model the mechanical power control as a
Linux key without new board evidence.

## LED channels

### Visible boot sequence

**USER-OBSERVED on the original firmware, 2026-08-21.** During power-up the
lower visible indicator lights green and turns off when startup finishes. Red
and yellow/amber were not observed in normal OEM operation. This is strong
evidence for the externally visible sequence, but it does not by itself
identify which of GPIO7/GPIO9/GPIO10 produces that physical color: the exact
`sys` table names and selector classes do not establish the PCB channel wiring.
OpenMitraStar originally implemented this with GPIO7 before the physical colour
sweep. The current product-parity direction is to drive GPIO9 active-low for
the visible green boot/alive indication, then clear it in `S90-ready`.

**USER-OBSERVED on OpenMitraStar diagnostics, 2026-08-22.** A later controlled
lower-window sweep on the current unit confirmed visible red, green and
orange. The current OpenMitraStar product mapping records GPIO7/`signalR` as
red, GPIO9/`signalG` as green, and orange/amber as GPIO7+GPIO9. GPIO10/`signalB`
remains an OEM logical channel without a useful independently visible colour
confirmed.

The exact `sys` binary constructs five 22-byte LED definitions. The names and
logical on values are proven by disassembly; these logical values pass through
the OEM LED abstraction and must not automatically be treated as PCB voltage
polarity.

| Logical name | GPIO | class | OEM logical on | Evidence status |
|---|---:|---:|---:|---|
| `wlan2.4GB` | 11 | 4 | 1 | exact `sys` table |
| `wlan5GB` | 1 | 4 | 0 | exact `sys` table |
| `signalB` | 10 | 4 | 1 | exact `sys` table |
| `signalG` | 9 | 1 | 0 | exact `sys` table |
| `signalR` | 7 | 2 | 0 | exact `sys` table |

`signalB/G/R` are the three channels of the lower multicolor indicator. The
class values align with the `sys ledtest` blue/green/red selector masks, but
the final visible color from simultaneous channels is recorded from board-level
observation, not inferred from the OEM class names alone.

### GPIO11 — 2.4 GHz WLAN/WPS LED

- exact OEM identity: `wlan2.4GB`, GPIO11;
- exact `monitor_wifi` startup: `qcsapi_led_set(11, 1)`, with the adjacent
  error string `WLAN 2.4GHz WPS LED`;
- exact WLAN RDM handler contains `sys ledctl wlan2.4GB on` and `off` for the
  2.4 GHz enable path;
- physical A2 polarity: **active-low**, proven on Linux 5.10 RAM-only:
  electrical level 1 was physically off and level 0 physically on.

The apparent disagreement with OEM logical value `1` is the reason logical
API state and direct electrical polarity are recorded separately.

### GPIO1 — 5 GHz WLAN and WPS LED

The exact `monitor_wifi` `.data` table has both WPS and WLAN entries on GPIO1,
active logical state `1`, blink interval 500 ms. The exact binary contains the
RGMII traffic branch (`Cannot get interface counter`), so the relevant WLAN
state machine is:

- associated/no counter change: steady on;
- traffic counter change: blink at 500 ms;
- no association during WPS or WPA handshake: blink at 250 ms;
- otherwise: steady on;
- interface disabled/mode undefined: off.

WPS is a second writer to the same GPIO1 and runs after WLAN in each update:

- initial/error/timeout/overlap/unknown: WPS LED off;
- in progress: blink at 500 ms;
- success: on.

Therefore GPIO1 is a shared state machine, not two independent LEDs.

### GPIO9 — WPS error channel (`signalG`)

The exact monitor table maps WPS error to GPIO9 with active logical state 1.
Message error, overlap, timeout or unknown turns it on. On this non-Amber build
the timeout is `80` fast updates at 250 ms, i.e. approximately 20 seconds,
after which the channel and WPS state are turned off.

### GPIO7 — quality channel (`signalR`)

The exact monitor table maps quality to GPIO7 with active logical state 1 and
500 ms blink. Current RFIC ID is 4, while `CHIPID_DUAL` is 2, so this path is
active:

- maximum link quality `>=100`: on;
- `30..99`: blink;
- `<30`: off;
- interface disabled/mode undefined: off.

The lower LED is also reused by OpenMitraStar as its early boot/alive channel.
Its visible on-until-ready/off sequence matches the OEM behavior reported by
the owner, while the exact OEM boot writer and physical RGB channel remain
unproven. Do not conflate that boot phase with the OEM runtime quality writer.

### GPIO10 — mode/blue channel (`signalB`)

The exact table contains GPIO10 as the mode channel, logical active state 0.
Generic non-RGMII code would show AP=on, STA=off and unknown=blink. The exact
binary is built with the RGMII traffic branch, which compile-time excludes the
mode updater. Therefore the table entry is proven, but an autonomous OEM
runtime transition from `monitor_wifi` is not; this channel may retain boot,
manufacturing-test or another service's state.

## Implementation consequence

The minimum faithful Linux 5.10 delta is:

1. keep GPIO11 active-low from physical evidence;
2. keep GPIO2 short release inert and five-second persistent 2.4 GHz toggle;
3. configure qdrv WPS GPIO4 active-low before VAP creation;
4. independently count ten 500 ms GPIO4 samples and request one persistent
   5 GHz toggle, without suppressing qdrv's release event;
5. keep GPIO12 as a separate state-following RF-enable control;
6. reproduce LED state machines only where the exact writer and polarity are
   known; do not infer electrical polarity from OEM logical values.
