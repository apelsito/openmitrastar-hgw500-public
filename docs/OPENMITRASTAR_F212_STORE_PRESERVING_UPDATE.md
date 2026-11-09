# OpenMitraStar F212 Store-Preserving Update

Fecha: 2026-09-01

F212 simula una actualización realista sobre la disposición física verificada
de 16 MiB. Parte de F207 con el store JFFS2 F211 inicializado y actualiza el
prefijo a F209.

## Contrato

- Offset físico `mtd4`: `0x7e0000`.
- Prefijo borrable/escribible: `0x5e0000` (`6,160,384` bytes).
- Tail preservado: `0x1c0000` (`1,835,008` bytes).
- Un borrado completo de `mtd4` queda prohibido tras inicializar el store.
- Reset del store requiere backup y autorización separada.

## Resultado

- Firmware nuevo exacto: PASS.
- Espacio libre del prefijo a `0xFF`: PASS.
- `lyoko_store` preservado byte a byte: PASS.
- `mtd3`, `mtd5`, bootloader y environments preservados: PASS.
- Ejecutores emitidos: ninguno.
- Acciones hardware: ninguna.
