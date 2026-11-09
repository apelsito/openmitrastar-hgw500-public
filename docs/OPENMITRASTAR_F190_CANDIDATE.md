# OpenMitraStar F190 Candidate

Fecha: 2026-09-01

F190 elimina la clave privada Dropbear embebida de la imagen generica.

## Estado

- Candidato de laboratorio: SI.
- Candidato de release: NO.
- Hardware: NOT_RUN.
- Motivo del hold: la identidad es efimera hasta certificar `lyoko_store`.

## Artefacto

- Bytes: `5,115,904`.
- SHA-256: `5fa11ed78b2eef9266d26477f2999c84f64f70dd9c283dd84a0b25e81b927a0f`.
- CRC32 candidato: `bf851b5c`.
- CRC32 slot completo: `f3a37cf1`.

## Evidencia

- Ruta privada eliminada del diff SquashFS.
- Secuencia binaria exacta de la clave anterior ausente del SquashFS final.
- API `/api/v1/ssh` expone solo estado, puerto, persistencia y fingerprint.
- Si una clave persistida es invalida, SSH falla cerrado.
- Kernel, radios, datapath y paquetes son byte-identicos a F188.

