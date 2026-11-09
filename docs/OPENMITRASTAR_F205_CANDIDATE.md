# OpenMitraStar F205 Runtime Feed Signature

Fecha: 2026-09-01

F205 añade verificacion Ed25519 real del indice de paquetes en ARC700. Todos
los comandos que confian en el feed validan primero `Packages` con una clave
publica raw y firma raw inmutables.

## Artefacto

- Bytes: `5,144,576`.
- SHA-256: `1fa1f781f6c57c180e5a531a44be869d6415c4a1d975cfb3ed355c094e1bd37c`.
- CRC32 candidato: `0aef9c50`.
- SHA-256 slot completo: `0637b469286e52645f478b8233638cebb68eda72395df9e3315f03100c7476e5`.
- CRC32 slot completo: `32750e45`.
- Kernel: byte-identico a F203.
- Validacion fisica: `NOT_RUN`.

## Verificador

- Implementacion: Dropbear 2026.94 `dropbear_ed25519_verify`.
- Arquitectura: ARC700 v4 ABI, estatico.
- Bytes: `51,076`.
- SHA-256: `831ea6de598834222c6e6e597b13f297aeaf5d472a55de0a7535419e978442b7`.
- Instrucciones `llock/scond`: ausentes.
- Firma valida: PASS en build nativo.
- Indice manipulado: REJECTED.
- Firma manipulada: REJECTED.
- Clave publica incorrecta: REJECTED.
- Clave privada en firmware: no.

## Evidencia

- Suite combinada: `38/38 PASS`.
- Dos builds F205 byte-identicos.
- `SHA256SUMS`, Bootbase y slot-fit: PASS.
- Ejecucion del verificador ARC en hardware: `NOT_RUN`.
