# F367r7 — publicación coherente de los dos relojes

R7 conserva la política de admisión y todos los deadlines. Corrige únicamente
la publicación del tiempo restante y añade observación de los valores que
consumió el rechazo. No elige un reloj para permitir TX antes.

Imagen sellada `PASS_OFFLINE_F367R7_CLOCK_OBSERVATION_IMAGE`:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f367r7-fullimage-20260922T194138Z/result.json`.
5.468.160 bytes; SHA256
`5cd4118bc84061da24f917b99978477c85a405dba613743d6398ba2894a7e28c`.
Manifest SHA256
`3ce8489e85b0d0d9292932bd7b48086a880575e276fc6915dcbc1bc70ca433f4`.
Full-slot CRC32 `fa7d80ee`; Bootbase/slot-fit y dos repacks idénticos PASS.
Store `5d2ee646` y recuperación F365 `118901d4` conservados.

## Evidencia y límite de la atribución

R6 publicó correctamente la clasificación DFS52, adquirió28.588 jobs sin
errores y llegó a `quarantine_remaining_ms=0`. `PREPARE52` devolvió
`prepare-policy-clock-nop-or-transition`, antes de ABORT. La captura no
conservó jiffies, el deadline en ticks ni todos los booleanos del predicado.
Por tanto no mide una deriva física concreta ni identifica retrospectivamente
una de sus ramas. Root confirmó el retorno íntegro a F365.

El binario sellado y el kernel real usan HZ100. El qdrv suma180.000 ticks y
la resta firmada de32 bits maneja correctamente el wrap de INITIAL_JIFFIES.
La inconsistencia demostrada está entre dos consumidores: el estado de
cuarentena sólo consultaba nanosegundos, pero PREPARE exigía además el deadline
en jiffies. El productor ARC Timer0 periódico llama a `do_timer(1)` por evento
entregado; el reloj continuo Timer1 puede avanzar mientras no se entrega un
evento. La reproducción permite separar ambos valores sin asumir que una
pérdida concreta de eventos ocurrió en el HGW.

## Delta

Sólo cambia `qdrv_f367_control.inc`. `f367_ap_policy.h`,
`qdrv_f367_ap.inc`, el predicado PREPARE y los productores de plazos son
idénticos a R6. Para políticas inicializadas, cada tiempo publicado es:

`remaining_ms = max(ceil(ns_pendientes / 1ms), ceil(ticks_pendientes * 1000 / HZ))`

La resta de ticks usa el mismo criterio wrap-safe del guard. Se aplica a
cuarentena, CAC pendiente y NOP. `quarantine_active` permanece activo mientras
cualquiera de los dos relojes siga pendiente; la condición NOP ya exigía
ambos relojes y ahora su restante también los representa. Los deadlines
originales no se desplazan ni se renuevan.

Campos numéricos nuevos de snapshot:

- `policy_initialized`, `tick_hz`, `jiffies_u32`, `boot_until_ticks`,
  `cac_until_ticks`, `nop_until_ticks`, `nop_policy`.
- `quarantine_ns_remaining_ms`, `quarantine_tick_remaining_ms`.
- `cac_ns_remaining_ms`, `cac_tick_remaining_ms`.
- `nop_ns_remaining_ms`, `nop_tick_remaining_ms`.

`transition_prepared` y `switch_inflight` ya existían. Los plazos `_deadline_ms`
continúan representando el deadline de nanosegundos; los nuevos `_until_ticks`
exponen el segundo límite sin convertirlo en un deadline móvil.

Antes del rechazo agregado se emite `OMF367_POLICY_CLOCK_REJECT` con el
submotivo `uninitialized`, `boot-ticks`, `nop-ticks`, `boot-ns`, `nop-ns`,
`transition` o `unknown`. Incluye los valores de política, ticks/HZ, deadlines,
now y transición capturados bajo el lock del guard. No añade accesos MMIO.

## Comprobaciones afectadas

La reproducción R6
`outputs/preflight/f367r6-clock-contract-20260922T193202Z/result.json`
ejecuta las funciones reales del productor periódico del kernel y reproduce
el desacuerdo entre estado y PREPARE. Se conserva como evidencia del defecto.

`outputs/preflight/f367r7-clock-publication-20260922T193631Z/result.json`
pasa28 comprobaciones: HZ100, ancho32, wrap inicial y posterior, ticks
rezagados, nanosegundos rezagados, cero sólo al vencer ambos límites,
cuarentena/CAC/NOP, rechazo por transición y deadlines intactos. El mismo
replay se compila para ARC; no se presenta como una medición física.

`outputs/preflight/f367r7-clock-json-20260922T193916Z/result.json`
comprueba por separado los máximos legales de serialización:1.515 bytes frente
a PAGE_SIZE4096, JSON válido y canarios intactos. No repite el banco anterior.

El qdrv se compila dos veces y los bytes coinciden. Se resuelven1.980 imports
en41 módulos; el único import añadido es `__div64_32`, exportado por vmlinux.
El publisher estático R6, proveedor, engine, kernel/DT, supervisor y scripts
se conservan; el native helper sólo recibe el nuevo hash del qdrv.

La captura host conservará estos relojes desde el primer snapshot y el rechazo
antes de ABORT, sin deducir deriva ni modificar los horizontes de la campaña.
Quedan pendientes los gates físicos; no se declara CAC/NOP o release PASS.
