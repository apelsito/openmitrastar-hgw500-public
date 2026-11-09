# OpenMitraStar F186 Candidate

Fecha: 2026-09-01

## Estado

F186 es un candidato offline reproducible. F170 continua instalado en el
router fisico.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-persistent-f186-navigation-shell-from-f185-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `5,115,904`
- SHA-256: `d4fe00a9dca9868251ea4e2964ee98349fb81ab6280d036141454af566191ca1`
- CRC32 candidato: `7679802a`
- CRC32 slot completo: `71422dd1`
- SHA-256 slot completo: `eadb5167b54390ef82ea00f891844afa5a13ffb6235341488714a01ad0f1069b`

## Cambio

- Shell de escritorio con sidebar y drawer movil.
- Areas estables: Inicio, Mi red, Wi-Fi, Sistema y Diagnostico.
- Modos Basico, Avanzado y Desarrollador como filtros de profundidad.
- Rutas hash estables.
- Carga parcial mediante `Promise.allSettled`.
- Formularios de radio precargados y staging exclusivo de campos modificados.
- Estados tecnicos principales humanizados.

Kernel, DTB, radios, paquetes y layout MTD son byte-identicos a F185.

## Evidencia

- 21 tests PASS con manifest presente.
- Build repetida con SHA-256 identico.
- `SHA256SUMS`: PASS.
- Browser desktop: PASS.
- Browser 390x844 y 320x568: PASS sin overflow horizontal.
- Drawer movil, rutas y modos: PASS.
- Consola del navegador: cero errores.
- Hardware: NOT_RUN.

## Gate Fisico

`tools/build_flash_test_f186_navigation_shell.ps1` permanece en dry-run por
defecto. Si se autoriza expresamente, escribe solo `mtd4/linux_live` y valida
despues Foundation, identidad de assets, paquetes, capacidades y la campana
Wi-Fi heredada de F172.

