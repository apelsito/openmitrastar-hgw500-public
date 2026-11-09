# OpenMitraStar F265 Full candidate

## Identity

- Runtime: `lyoko-foundation-6.0.2-f265-full-device`
- Bytes: `5251072`
- SHA-256: `c0ab6b1fd7d6c101551af6003edd7439d625d10cc1246218967524bdeacc121e`
- Full-slot CRC32: `32f7c200`
- Full-slot SHA-256: `d7caceefa004b3ae652fd6247ac2f58647e4c0fb07f34adda7d3262e1ba17910`
- Bootbase contract: PASS
- SHA256SUMS: PASS
- Normal write target: physical `mtd4/linux_live` only
- Preserved tail: `0x1c0000` bytes reserved for `lyoko_store`

## Full Lyoko contents

F265 is one integrated firmware, not a reduced or parallel UI branch. It
contains:

- Linux `5.10.260-openmitrastar-radiohw`, SquashFS-XZ and RX ring 256;
- Realtek and Quantenna runtime plus F258-F264 fixes;
- single Developer console with direct management routes;
- authenticated API v1, LED controls and hardware inventory;
- signed `lyoko-pkg` and constrained `opkg` compatibility;
- config-store API, exposed honestly as inactive until a boot consumer exists;
- complete ES channel documentation and a server-validated DFS acknowledgement.

## Radio correctness changes

- Realtek hostapd is restarted for channel/bandwidth changes; `reload` was
  physically proven insufficient.
- Existing non-width `ht_capab` flags are preserved when selecting 20/40 MHz.
- Quantenna bandwidth is read from the active driver before falling back to the
  imported OEM configuration.
- 5 GHz frequency decoding covers channels 36-140.
- Hostapd children and the rollback watchdog detach stdin from SSH.

## DFS policy

- Channels 36-48 are immediately applicable.
- Channels 52-140 are selectable and documented in Developer mode.
- The UI requires an explicit session acknowledgement.
- The API independently requires
  `X-OM-Regulatory-Ack: OPENMITRASTAR_ES_DFS_V1`.
- The transaction and qdrv control layers require both the disabled-by-default
  feature gate and `/sys/module/qtn_radar_native/parameters/ready=1`.
- Current result: DFS remains fail-closed until the native radar detector is
  implemented and physically validated.

## Validation

- Full source/emulator suite: 32/32 PASS
- Integrated F263-F265 suite: 44/44 PASS
- Shell and JavaScript syntax: PASS
- Desktop and 390 px mobile browser checks: PASS
- DFS acknowledgement and server rejection without radar: PASS
- Hardware boot: NOT RUN

## Promotion blocker

The installed F263 stopped responding after the radio transaction test. COM3
is present, but the running kernel did not accept SysRq. A physical power cycle
is required before F265 can be promoted through the prepared TFTP-first flow.

```powershell
.\tools\resume_f265_after_power_cycle.ps1 -Execute `
  -Ack OPENMITRASTAR_F265_CONTROL_TRUTH_C0AB6B1F
```
