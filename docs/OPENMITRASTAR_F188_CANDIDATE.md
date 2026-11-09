# OpenMitraStar F188 Candidate

Fecha: 2026-09-01

## Estado

F188 es un candidato offline reproducible. F170 continua instalado en el
router fisico.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-persistent-f188-diagnostics-ui-from-f187-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `5,115,904`
- SHA-256: `aac1993994d6796b4a88caf1f5c21f601baec620b09b2c16c6dfa745c78a1f69`
- CRC32 candidato: `67619862`
- CRC32 slot completo: `e624d906`
- SHA-256 slot completo: `94b706db211d007f52d67a476cd9b0a38c6081f15ff196826b94f288ec60bd00`

## Cambio

- Nueve metricas legibles para IRQ, NAPI, `NO_RX_DESC`, reinicios RX y TQE.
- Deltas calculados entre refrescos dentro del navegador.
- Estado visual: muestra base, sin nuevos stalls, presion RX o fallo fatal.
- JSON tecnico conservado como detalle opcional.
- UI `1.8.0`, build ID `0f0088bd98bb51c4`.

Kernel, DTB, drivers, paquetes, sesion y layout MTD son byte-identicos a F187.

## Evidencia

- 23 tests PASS con manifest y pipeline presentes.
- Build repetida con SHA-256 identico.
- `SHA256SUMS`: PASS.
- Browser: nueve metricas, baseline y segundo refresco sin nuevos stalls.
- Consola del navegador: cero errores.
- Hardware: NOT_RUN.

El wrapper `tools/build_flash_test_f188_diagnostics_ui.ps1` es dry-run por
defecto y solo admite `mtd4/linux_live` tras autorizacion exacta.

