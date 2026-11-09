# OpenMitraStar F197 Common Radio Contract

Fecha: 2026-09-01

F197 introduce el primer contrato comun de control para los sectores Realtek
2,4 GHz y Quantenna 5 GHz. Es un cambio exclusivo de rootfs sobre F195; no
modifica kernel, modulos, firmware RF, DMA, colas, bridge, almacenamiento ni
politica SSH.

## Artefacto

- Bytes: `5,120,000`.
- SHA-256: `2b56fb9362c7027375c59ed364541691a5f43903de04e4c05b829adef24a0c19`.
- CRC32 candidato: `1af1d239`.
- SHA-256 slot completo: `8f92c2fbb348373f0b2b228db8859f2528cc055d17677cd14820493a6f10a297`.
- CRC32 slot completo: `cd937e3c`.
- Kernel LZMA: `ec029c052c3374d68e3e15c03353b487c12e12c3c431b6398b301877ef8f1d7c`.
- Validacion fisica: `NOT_RUN`.

## Contrato

`/usr/sbin/om-radioctl` normaliza para ambas radios:

- `identity`
- `capabilities`
- `status`
- `snapshot`
- `clients`
- `stage_config`
- `apply_config`
- `rollback_config`

La API ya no invoca directamente las herramientas especificas Realtek o
Quantenna. `restart_radio` falla de forma cerrada hasta que la recuperacion
acotada tenga certificacion fisica.

## Evidencia Offline

- Suite de contrato y Foundation: `18/18 PASS`.
- Sintaxis BusyBox/ash: PASS.
- Dos builds consecutivos: byte-identicos.
- `SHA256SUMS`: PASS.
- Bootbase y slot-fit: PASS.
- Acciones hardware: ninguna.

F197 no es una release ni esta autorizado para flash.
