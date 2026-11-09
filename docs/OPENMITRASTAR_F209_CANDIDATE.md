# OpenMitraStar F209 Storage API

Fecha: 2026-09-01

F209 añade observabilidad read-only del split de almacenamiento F207 mediante
`GET /api/v1/storage` y un panel Advanced.

- Bytes: `5,144,576`.
- SHA-256: `7f3e7575f3ad35c32d1581dc57a19c1b434533b2e6f7a704e936910351095ba8`.
- CRC32 candidato: `cfa79316`.
- SHA-256 slot completo: `c17f2d13f0a7bdb5c8b043dbbc91e72ca09f954724b08215a2c756fde6a84273`.
- CRC32 slot completo: `fe941ebe`.
- Validacion fisica: `NOT_RUN`.

La API expone geometria rootfs/store, mount state, resultado del probe SPI y
politica de escritura. No contiene rutas para montar, formatear, borrar o
escribir. El kernel, DTB y probe son byte-identicos a F207.

Tests offline: `20/20 PASS`. Dos builds byte-identicos y `SHA256SUMS` PASS.
