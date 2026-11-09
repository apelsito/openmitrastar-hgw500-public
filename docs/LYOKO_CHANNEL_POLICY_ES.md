# Lyoko channel policy for Spain

## Scope

This document defines what the HGW-500BNA UI may display, what the API may
stage and what the radio backend may actually transmit under the `ES` domain.
It is an engineering policy, not legal advice.

## Sources

- Spain CNAF UN-128: RLAN use in `5150-5250`, `5250-5350` and
  `5470-5725 MHz` under the applicable harmonized technical conditions:
  https://www.boe.es/diario_boe/txt.php?id=BOE-A-2023-14422
- Current CNAF publication (2026):
  https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-15661
- EU harmonization decision for 5 GHz WAS/RLAN, including DFS/TPC references:
  https://eur-lex.europa.eu/eli/dec/2005/513/oj/eng
- ETSI EN 301 893 DFS behavior and conformance requirements:
  https://www.etsi.org/deliver/etsi_en/301800_301899/301893/
- User investigation that identified the old HGU firmware/channel behavior:
  https://comunidad.movistar.es/discussions/soporte-fibra-optica/router-hgu-problema-de-firmware-/4170154

## 2.4 GHz

Lyoko exposes channels `1-13` under the ES regulatory domain.

- Channels `1`, `6` and `11` are recommendations for 20 MHz coexistence, not
  an artificial allow-list.
- Intermediate channels remain configurable.
- 40 MHz operation is allowed by the control contract, but must be benchmarked
  because overlapping networks can make it slower than 20 MHz.

## 5 GHz

| Channels | Lyoko class | Required behavior |
| --- | --- | --- |
| 36, 40, 44, 48 | immediate / non-DFS | ES domain and calibrated power table |
| 52, 56, 60, 64 | DFS | CAC before TX, continuous radar detection, channel evacuation and NOP |
| 100-140 | DFS | Same DFS behavior; 120/124/128 intersect the weather-radar sub-band |

The normal CAC policy is at least 60 seconds. The OEM Quantenna contract used
70 seconds. Channels intersecting `5600-5650 MHz` require a 600-second CAC.
After a radar event the affected channel is unavailable for 1,800 seconds.

## Developer acknowledgement

The UI acknowledgement is session-scoped and confirms only that the operator
understands the interruption and channel-move behavior. It never:

- changes the country from ES;
- disables radar detection;
- shortens CAC or NOP;
- bypasses the calibrated power table;
- makes an unavailable driver backend writable.

The API remains fail-closed. A DFS candidate is applicable only when all of
these are true:

1. the ES regulatory domain lists the channel;
2. the Quantenna hardware reports the channel for the selected bandwidth;
3. a native radar backend is continuously running;
4. TX remains disabled for the complete CAC;
5. radar causes an automatic channel move and NOP registration;
6. the transaction can verify the new state and roll back.

## Current F263 boundary

F263 exposes and documents the complete channel map in Developer mode. Channels
36-48 remain directly applicable. DFS channels remain selectable for inspection
but not applicable because Linux 5.10 still uses `qdrv_radar_compat`, which is a
fail-closed compatibility layer and not a radar detector.

This boundary is deliberate: Lyoko exposes the machine without pretending that
a checkbox can replace RF safety behavior.
