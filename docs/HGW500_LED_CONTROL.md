# HGW-500BNA-QCv2 front-panel LEDs

Date: 2026-08-21  
Updated: 2026-08-22 — lower red, green and orange physically observed on the current unit.  
Scope: OpenMitraStar Linux 5.10, RAM/offline integration only. No flash action.

## Result

The enclosure has three visible indicator windows but five independently
addressable LED channels:

| Window/channel | GPIO | Linux LED class | Current evidence |
|---|---:|---|---|
| Wi-Fi 2.4 GHz/WPS | 11 | `openmitrastar:green:wlan2g` | Physical active-low behavior proven on A2 hardware. |
| Wi-Fi 5 GHz/WPS | 1 | `openmitrastar:green:wlan5g` | OEM active-high table and carrier policy proven; final physical observation remains a gate. |
| Lower `signalB` | 10 | `openmitrastar:panel:signalb` | Exact OEM channel; no independent visible colour confirmed on 2026-08-22 sweep. |
| Lower `signalG` / boot-green | 9 | `openmitrastar:panel:signalg`; boot alias `topaz:stage0:alive` | Physical green confirmed on 2026-08-22 sweep; current boot/alive policy uses this channel until `S90-ready`. |
| Lower `signalR` | 7 | `openmitrastar:panel:signalr` | Physical red confirmed on 2026-08-22 sweep. |

The OEM names `signalB`, `signalG` and `signalR` describe the three logical
channels of the lower multicolour window. A 2026-08-22 physical sweep on the
current unit confirmed the useful visible product colours as red, green and
orange. Orange is produced by enabling the confirmed red and green channels
together. The `signalB` channel remains a logical GPIO10 channel, but no useful
independent visible blue/white colour was confirmed in that sweep.

## Simple control

OpenMitraStar installs `/usr/sbin/om-ledctl`:

```sh
om-ledctl list
om-ledctl status
om-ledctl set wifi2g on
om-ledctl set wifi2g off
om-ledctl set wifi5g on
om-ledctl set wifi5g off
```

The lower indicator remains behind an explicit diagnostic flag for manual
writes. Red, green and orange are physically correlated on the current unit;
GPIO10/`signalB` is still not correlated to a useful independent visible colour.

```sh
om-ledctl --diagnostic set signalb on
om-ledctl --diagnostic set signalg on
om-ledctl --diagnostic set signalr on
om-ledctl --diagnostic color amber   # product-visible orange on this unit
om-ledctl --diagnostic color off
```

`identify` cycles all five channels and restores every previous brightness
value, even when interrupted:

```sh
om-ledctl --diagnostic identify 2
```

The sequence first tests the five independent channels, then the lower-window
presets `blue`, `green`, `red`, `amber`, `cyan`, `magenta` and `white`. On this
unit, `amber` is the useful product-visible orange produced by GPIO7+GPIO9.
Record any later GPIO10-only observation separately; do not infer it from the
orange alias.

## OEM state machines

### Wi-Fi 2.4 GHz — GPIO11

- interface enabled: steady on;
- interface disabled: off;
- WPS shares the same window;
- physical polarity on A2 is proven active-low.

### Wi-Fi 5 GHz — GPIO1

The OEM WLAN writer runs first and its WPS writer runs afterwards:

- associated without counter changes: steady on;
- traffic: blink every 500 ms;
- WPS/WPA handshake without association: blink every 250 ms;
- WPS in progress: blink every 500 ms;
- WPS success: on;
- disabled or unknown radio mode: off.

This ordering matters: WPS can replace the WLAN/traffic indication during the
same monitor iteration.

### Lower `signalG` — GPIO9

The OEM uses this channel for WPS message error, overlap, timeout or unknown
state. On the current non-Amber firmware branch it is cleared after roughly 20
seconds.

### Lower `signalR` — GPIO7

The OEM quality policy is:

- quality `>=100`: on;
- quality `30..99`: 500 ms blink;
- quality `<30`: off;
- interface disabled or undefined: off.

OpenMitraStar previously used GPIO7 during boot before the physical colour
sweep. Current product parity uses GPIO9 for the green boot/alive indication,
so GPIO7 is free to remain the red lower diagnostic/product channel.

On the current unit this channel is physically visible as the lower red LED.

### Lower orange — GPIO7 + GPIO9

The current unit shows a useful lower orange indication when the red GPIO7
channel and green GPIO9 channel are asserted together. Treat this as a product
alias, not as a separate hardware channel.

### Lower `signalB` — GPIO10

The OEM table contains the channel. Generic non-RGMII logic would encode AP as
on, STA as off and unknown mode as blinking. This unit uses the RGMII build,
where that autonomous updater is compiled out, so another boot/manufacturing
writer may leave its last state.

## Writers and precedence

| Channel | Writers |
|---|---|
| GPIO11 | Linux netdevice notifier; manual `om-ledctl`; OEM RDM/WPS on stock firmware. |
| GPIO1 | Linux netdevice notifier; manual `om-ledctl`; OEM WLAN writer followed by WPS writer. |
| GPIO10 | Manual `om-ledctl`; OEM `sys ledtest`; possible boot/manufacturing writer. |
| GPIO9 | Linux boot/alive policy until `S90-ready`; manual `om-ledctl`; OEM WPS-error monitor. |
| GPIO7 | Manual `om-ledctl`; OEM quality monitor. |

Manual state is not persistent. A later network event or reboot may restore the
automatic owner. `identify` avoids leaving stale state by restoring its initial
snapshot.

## Automatic ownership

- GPIO11 follows the `wlan0` AP state through the kernel netdevice notifier.
- GPIO1 follows `wifi0` running, carrier and operational state.
- GPIO9 is asserted during early boot as the green boot indicator and cleared by `S90-ready`.
- Manual writes are temporary and may be replaced by the corresponding state
  machine on its next event.

## Why this is not Python

The target exposes only about 55 MiB of the high-DDR Linux window and uses an
ARC700/uClibc userspace. The current Q3 image is 4,321,911 bytes in a 7,995,392
byte slot, but flash fit alone is not the useful criterion: CPython would add a
large interpreter/stdlib, RAM pressure and a new cross-ABI maintenance surface.

The complete LED controller is a BusyBox `ash` script. It has no added runtime
library, starts immediately and is easy to audit. A narrowly built MicroPython
could fit later, but it is not justified for GPIO/LED control.

## Safety

- The controller writes only LED-class `brightness` files.
- It contains no MTD, flash, bootloader, calibration or persistent-config path.
- Unverified lower-channel operations require `--diagnostic`.
- `identify` snapshots and restores the previous values.
