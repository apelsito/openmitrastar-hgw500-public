# OpenMitraStar F185 Candidate

Fecha: 2026-09-01

## Estado

F185 es un candidato offline reproducible. No esta instalado en el router; el
firmware fisico sigue siendo F170.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-persistent-f185-web-provenance-from-f184-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `5,111,808`
- SHA-256: `3ac3ffdbb4d7d2ccfce212de9cba9a3a61c16ea5da3a962e61a8a809f2fb74eb`
- CRC32 candidato: `f37ca6d5`
- CRC32 slot completo: `9d8adcdf`
- SHA-256 slot completo: `076af2d787dbbd50b8db89c566e774297554bcfa117630ba3a520bd2e6a46294`

## Cambio Unico

F185 conserva el kernel F172/F184 byte-identico y sustituye solamente siete
rutas de rootfs:

- identidad determinista de frontend;
- endpoint autenticado `GET /api/v1/frontend`;
- etiquetas de origen `Emulador` o `Router`;
- version UI `1.5.0` y build ID `f0adf5af5b71dfde`;
- skip-link, tabs ARIA, navegacion por teclado, foco visible y reduced motion.

No cambia radios, NAPI, DMA, paquetes, layout MTD ni almacenamiento.

## Evidencia

- Build repetido con el mismo SHA-256: PASS.
- `SHA256SUMS`: PASS.
- Suite F185 y Foundation congelada: 20 tests PASS.
- Podman: endpoint `/api/v1/frontend` PASS dentro del contenedor.
- Browser desktop y 390x844: PASS, sin overflow horizontal.
- Navegacion por flechas entre tabs: PASS.
- Hardware, boot y Wi-Fi: NOT_RUN.

## Promocion Fisica

El wrapper `tools/build_flash_test_f185_web_provenance.ps1` es dry-run por
defecto. Una ejecucion requiere autorizacion actual y escribe exclusivamente
`mtd4/linux_live`; el gate posterior valida Foundation, paquetes, capacidades,
identidad y hashes reales de los assets antes de ejecutar opcionalmente la
campana Wi-Fi F172.

