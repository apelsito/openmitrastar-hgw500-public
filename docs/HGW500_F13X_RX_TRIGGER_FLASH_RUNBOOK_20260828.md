# HGW-500BNA-QCv2 F13x RX-Trigger Flash Runbook

Date: 2026-08-28

## Current Goal

Bring the HGW-500BNA-QCv2 forward on persistent Linux 5.10, keeping 2.4 GHz service and advancing the Quantenna 5 GHz port with reproducible flash/test cycles.

## Why This Runbook Exists

The older wait-powercycle wrappers could keep sending blind `space` / `ATGU` sequences when UART RX was silent. That made it hard to distinguish a missed Bootbase window from a physical UART/RX problem and could hold `COM3` for hours.

The F13x flow is now RX-gated by default:

- Listen on `COM3` without UART TX.
- Wait for the first real boot byte.
- Release/reopen UART for the existing Bootbase/ATGU flash helper.
- Abort if the flash helper sees no UART RX for the configured gate.
- Run post-flash SSH/radio evidence only after flash pass.

## Active Watcher

Current armed trigger:

```powershell
tools\arm_f13x_rx_trigger_flash.ps1 `
  -Profile F133 `
  -Port COM3 `
  -ServerIp 192.168.1.43 `
  -ClientIp 192.168.1.90 `
  -HostAddress 192.168.1.90 `
  -TriggerWaitSeconds 21600 `
  -NoRxAbortSeconds 180
```

Current trigger status:

```text
outputs\flash-watch\f13x-rx-trigger-f133-20260828-133054\trigger-status.json
```

Current postgate monitor:

```text
outputs\postflash\f13x-rx-trigger-monitor-f133-20260828-133409\monitor-status.json
```

## Status Command

Use:

```powershell
tools\status_f133_flash_watch.ps1 -Tail 80
```

Expected pre-power-cycle state:

```text
state=armed_waiting_for_first_rx
flashes=false
uart_tx_before_rx=false
```

## Physical Step

Power-cycle the router while the RX-trigger watcher is active.

Expected if UART RX is wired and Bootbase emits:

```text
first_rx_seen_starting_flash
OMQ3_F45_AUTOBREAK_TOPAZ_READY=1
OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1
```

Expected after Linux 5.10 boots:

```text
OMSSH_READY
```

Then the monitor runs:

```powershell
tools\post_flash_f13x_radio_gate.ps1 -Profile F133 -RunRadio5Start
```

## If It Stays Silent

If `trigger-status.json` stays at `armed_waiting_for_first_rx` and no `trigger-uart.log` appears after a physical power-cycle, the blocking layer is below firmware:

- wrong/missing board TX -> adapter RX path,
- missing common GND,
- adapter not actually connected to the boot UART,
- router not powered/booting,
- or boot UART disabled/silent in the current electrical setup.

Do not start another blind flash loop in that state. Fix physical RX evidence first.

## Candidates

F133:

```text
candidate=f133-5g-disable-hr-timer-from-f132
candidate_sha256=57fb4f87811957a55cea5da359daafb4520607b9651e7a78c11e6a032c1f00ae
expected_full_slot_crc32=e692b50c
current_live_crc32=d11c5cbd
```

F134 and F135 dry-run candidates exist and are parse/test validated, but are not flashed. Use them only after F133 evidence says the next cut should move from timer disable to RF-hold/core-hold isolation.

## Verification Performed

```text
python -m pytest -q .\tools\test_f13x_rx_trigger_flash.py .\tools\test_monitor_f13x_rx_trigger_then_postgate.py .\tools\test_f132_wait_powercycle_flash.py .\tools\test_f133_wait_powercycle_flash.py .\tools\test_f134_flash_wrapper.py .\tools\test_f135_flash_wrapper.py
21 passed
```

PowerShell parse passed for:

```text
tools\arm_f13x_rx_trigger_flash.ps1
tools\monitor_f13x_rx_trigger_then_postgate.ps1
tools\arm_f132_wait_powercycle_flash.ps1
tools\arm_f133_wait_powercycle_flash.ps1
tools\arm_f134_wait_powercycle_flash.ps1
tools\arm_f135_wait_powercycle_flash.ps1
tools\status_f133_flash_watch.ps1
```
