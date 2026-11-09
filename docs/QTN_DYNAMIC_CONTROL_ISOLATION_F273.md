# Quantenna dynamic-control isolation through F273

Date: 2026-09-03

## Proven physical boundary

Installed F272 keeps the 5 GHz AP available while dynamic mutation remains
disabled. The F270 step runner has physically proved these same-value actions:

- `rf-write-same`: PASS;
- `interface-up-same`: PASS;
- SSH and both APs remained available;
- no fatal kernel, MuC, QMAC or alignment marker appeared.

## Why `mode` is the next discriminator

The legacy private ioctl reaches `ieee80211_ioctl_setmode()`. A truly identical
media selection returns before the media-change callback. A real change can:

- reset WME state and rate tables;
- move the current/designed channel;
- call the driver channel setter;
- send PHY mode, TX A-MSDU and aggregation parameters to qdrv/MuC;
- update the AP beacon;
- force station reassociation.

The qdrv parameter path allocates a host ioctl plus coherent DMA arguments,
sends the hostlink request and releases those buffers. This is materially more
dangerous than reopening the already-open RF gate or raising an already-up
interface.

Relevant source:

- `work/linux510-radio-port/quantenna-v6-scheduler-diag/wlan/if_media.c`
- `work/linux510-radio-port/quantenna-v6-scheduler-diag/wlan/ieee80211_wireless.c`
- `work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_wlan.c`
- `work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_hostlink.c`

## F273 design

F273 adds `om-qtnctl plan <config-file>`. It reads current SSID, channel and
bandwidth and reports the exact differences and required classes of operation.
It does not require the dynamic-write feature gate and performs no mutation.

F273 also adds a fast path for an exact no-op apply. When all requested values
match current state it returns verified success without stopping hostapd-qtn,
writing WEXT values or sending new MuC configuration.

Dynamic 5 GHz writes remain disabled by default. F273 is an offline candidate;
the installed baseline remains F272.

