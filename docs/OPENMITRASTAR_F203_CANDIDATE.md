# OpenMitraStar F203 Package Catalog

Fecha: 2026-09-01

F203 amplía `lyoko-pkg` sin añadir red, flash ni persistencia. El gestor puede
actualizar/verificar el catálogo inmutable, buscar, mostrar información,
resolver planes de dependencias e instalar dependencias antes del paquete
solicitado.

## Artefacto

- Bytes: `5,124,096`.
- SHA-256: `495b7eeb24f74498de6d7595b1cfcc6c069f1bdc923dea27dde1caf33ca95a20`.
- CRC32 candidato: `d13cd3a6`.
- SHA-256 slot completo: `d9f23593f4953f52a0b827f35dfddf2e756990f29df8adb9368834450efb901f`.
- CRC32 slot completo: `d58ecbea`.
- Kernel LZMA: `ec029c052c3374d68e3e15c03353b487c12e12c3c431b6398b301877ef8f1d7c`.
- Validacion fisica: `NOT_RUN`.

## Contrato

- dependencias por nombre exacto, profundidad maxima 16;
- ciclos y dependencias ausentes fallan cerrados;
- eliminacion bloqueada cuando otro paquete depende del objetivo;
- `update` verifica hashes de archivos y SHA del indice declarado por la
  metadata firmada durante build;
- la firma Ed25519 sigue siendo verificada durante el build, no en runtime;
- instalaciones exclusivamente bajo `/run/lyoko-packages`.

## Evidencia

- Suite combinada: `37/37 PASS`.
- Dos builds consecutivos byte-identicos.
- `SHA256SUMS`, Bootbase y slot-fit: PASS.
- Acciones hardware: ninguna.
