# OpenMitraStar F192 Candidate

Fecha: 2026-09-01

## Estado

F192 corrige el falso estado `degraded` observado en F170 por una carrera de
arranque de `S34-ipv6-local-policy`. Es un candidato offline reproducible; no
se ha instalado en hardware.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-persistent-f192-ipv6-health-reconcile-from-f191-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `5,115,904`.
- SHA-256: `94b904333095b630edb0c0fcff458b4f2f9050211a36de5a005308c5d61d8bb0`.
- CRC32 candidato: `a9087030`.
- CRC32 slot completo: `b1dd8f56`.

## Cambio

- Espera IPv6 configurable y acotada por scope.
- Tres intentos tardios desde `S90-ready`.
- Limpieza del marcador degradado solo tras readback correcto.
- `GET /api/v1/status` expone los servicios degradados sin incluir logs ni
  secretos.
- UI `2.1.0` muestra la causa concreta del estado degradado.

Kernel, NAPI, multicast, radios, paquetes, SSH y layout MTD son byte-identicos
a F191.

## Evidencia

- Aparicion retardada de `br0/disable_ipv6`: PASS.
- Ausencia permanente del scope: falla de forma visible.
- 22 tests PASS con manifest presente.
- Clave privada SSH embebida: ausente por herencia verificada de F191.
- Hardware/cold boot: NOT_RUN.

