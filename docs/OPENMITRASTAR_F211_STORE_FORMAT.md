# OpenMitraStar F211 Lyoko Store V1

Fecha: 2026-09-01

F211 define el formato persistente inicial de `lyoko_store` sin habilitar
escrituras en el router.

- Formato: JFFS2 little-endian.
- Tamaño: `0x1c0000` (`1,835,008` bytes).
- Eraseblock: `0x10000`, 28 bloques.
- Page size: `0x2000`, coherente con ARC 8 KiB.
- SHA-256: `d42427203214e3c304bb0f65c2586a0552d94f2a1a5abb23ab92ac0ab912d3b1`.
- Identidad privada: ausente.
- Runtime mount/write: desactivado.

El slot completo de análisis F209 + store mide `0x7a0000` y tiene SHA-256
`52420330c023e8c44e40d0fafe696377826bf344e73498c1535281253a081864`.
No está autorizado para flash.
