# OpenMitraStar F194 Safety Slot

Fecha: 2026-09-01

## Problema Demostrado

La imagen conservada actualmente en `mtd3/linux_safety` tiene CRC valido y
arranca Linux 2.6.35.12, pero termina en:

```text
VFS: Unable to mount root fs on unknown-block(3,2)
```

Por tanto, la recuperacion actual es `RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE`.

## Solucion F194

F194 reconstruye exactamente el kernel F170 con NAPI 64 y modifica una sola
variable funcional: el DTB mapea el rootfs dentro del slot fisico mtd3.

- rootfs safety: `0x901c0000 + 0x00620000`;
- dispositivo raiz: `31:3`;
- rootfs: byte-identico a F170;
- boot environment: sin cambios.

La build de control con el DTB live produjo exactamente el SHA-256 del kernel
F170, demostrando que la variante safety parte del mismo codigo binario.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-recovery-f194-safety-slot-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `4,964,352`.
- SHA-256: `231f01b44667e90accae4cf1b0561c72dcf66e8ccd86e57bd0f6728f21e4399e`.
- Slot completo SHA-256: `c158c65dbc921acf43cbd2f4ffd8c51b6d52e754a09fc100135d006855a4a698`.
- Slot completo CRC32: `05934f74`.

## Contrato Bootbase

La simulacion usa un entorno CRC-valido con `bootselect=1`, F194 como
`linux_safety` y F170 como `linux_live`:

- slot seleccionado: `linux_safety`;
- handoff: `linux_safety`;
- fallback: `linux_live`;
- contrato: PASS.

Esto no demuestra ejecucion ARC ni autoriza escritura.

## Seguridad

- `candidate_eligible=false`.
- `flash_supported=false`.
- Cualquier escritura en mtd3 requiere una autorizacion de recovery separada.
- Durante esa operacion mtd0, mtd1, mtd2, mtd4 y mtd5 deben permanecer iguales.

## Contrato De Provisioning

El contrato offline se encuentra en
`outputs/recovery/f194-provisioning-contract-20260901/contract.json`.

Todas las comprobaciones locales pasan, pero su estado permanece
`WAITING_EXPLICIT_EXCEPTION_AUTHORIZATION`. No contiene ejecutor y no realizo
UART, reboot, flash ni cambios de boot environment.
