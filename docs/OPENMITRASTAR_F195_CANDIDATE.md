# OpenMitraStar F195 Candidate

Fecha: 2026-09-01

F195 integra el gestor de paquetes endurecido sobre F192.

## Artefacto

- Bytes: `5,120,000`.
- SHA-256: `0ea0c703059ebddad9e955f95698d2870a9b8b9205c6c9d5069affddb2f63607`.
- CRC32 candidato: `bc14414c`.
- CRC32 slot completo: `d890e553`.

## Seguridad De Paquetes

- Limite de 16 MiB descomprimidos y 1024 entradas.
- Rechazo de traversal, rutas duplicadas y nombres inseguros.
- Rechazo de symlinks, hardlinks, dispositivos y permisos privilegiados.
- Fuentes de receta enlazadas simbolicamente rechazadas.
- Metadatos de control sin inyeccion de nuevas lineas.
- Activacion atomica dentro de `/run/lyoko-packages`.
- Feed firmado durante build y paquete verificado por SHA-256 en runtime.
- Sin descargas de red ni instalacion persistente.

## Evidencia

- 30 tests PASS, incluidos paquetes adversariales y ejecucion runtime en WSL.
- Build reproducible.
- Clave privada SSH embebida ausente.
- Kernel y radios byte-identicos a F192.
- Hardware: NOT_RUN.

