# OpenMitraStar F276 AELITA visibility

Date: 2026-09-03

## Result

A read-only physical scan from the authorized Windows test client AELITA
observed both F276 access points while preserving its existing connection:

- `OpenMitraStar-Lab`: visible, 2.4 GHz, channel 1, 91 percent signal.
- `MOVISTAR_PLUS_55CB`: visible, 5 GHz, channel 36, 94 percent signal.
- AELITA remained associated with its existing `MOVISTAR-WIFI6-A348` profile.
- Router-side lifecycle remained `ap-ready` for both radios.
- Router TX counters advanced over 20 seconds: `wlan0 +49`, `wifi0 +1`.
- Fatal kernel/radio marker count: zero.

Evidence:

- `outputs/postflash/dual-radio-visibility-20260903T123319Z/result.json`

The result file retains `ERROR_CAPTURE` because the first version of the
collector propagated `grep` exit code 1 when the fatal count was zero. Its
captured booleans and counters are valid; the collector was corrected before
the following run.

## Repeatability limitation

The corrected repeat at `20260903T123501Z` exited successfully but Windows
returned only the currently associated network in all six scans. Router-side
TX still advanced (`wlan0 +54`, `wifi0 +3`) and both radios remained
`ap-ready`, with zero fatal markers.

This establishes physical visibility of both F276 SSIDs at least once, but it
does not establish continuous scan visibility, fresh association or traffic on
this boot. Windows background scans while associated to A348 are therefore not
a sufficient standalone release gate.

## Reusable collector

`tools/capture_aelita_dual_radio_visibility_readonly.ps1` performs the bounded
read-only scan and router correlation without changing the client connection,
radio configuration or router state. It stores only target-SSID summary data;
neighbor scan details are not persisted.

## Next gate

When physical recovery is available:

1. Promote F277 through the guarded `mtd4/linux_live` TFTP pipeline.
2. Verify its exact no-op and channel-only plans against live WEXT mode.
3. Run `mode-write-same` with UART capture.
4. Only after that passes, perform a reversible client association and traffic
   gate while restoring AELITA to A348.

