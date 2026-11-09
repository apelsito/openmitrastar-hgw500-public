# OpenMitraStar F187 Candidate

Fecha: 2026-09-01

## Estado

F187 es un candidato offline reproducible. El router fisico continua ejecutando
F170.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-persistent-f187-session-ui-from-f186-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `5,115,904`
- SHA-256: `649fba59d5154bfdaeb9c4e5cacf4f2f836bb2f095d057a943764e496d4dfbca`
- CRC32 candidato: `0634d190`
- CRC32 slot completo: `73fa64e7`
- SHA-256 slot completo: `7d9d3370db5de2fc81ba36a6e0f2e0cef9de3da58ac8715c1b33bc63f1bb468c`

## Cambio

- Login Lyoko servido sobre el backend de credenciales existente.
- `GET /api/v1/session` expone autenticacion, caducidad y politica de cookie.
- El endpoint no devuelve token, hash de cliente ni credenciales.
- Logout visible mediante el contrato existente `/logout.cgi`.
- HTML y CSS del login forman parte del build ID del frontend.
- UI `1.7.0`, build ID `f50b11ba9d4df057`.

Kernel, DTB, radios, datapath, paquetes y layout MTD son byte-identicos a F186.

## Evidencia

- 22 tests PASS con manifest y pipeline presentes.
- Build repetida con SHA-256 identico.
- `SHA256SUMS`: PASS.
- Login desktop y 320 px: PASS sin overflow.
- Dashboard muestra sesion activa, TTL y cookie HttpOnly/SameSite.
- Hardware, login real y expiracion real: NOT_RUN.

## Promocion

`tools/build_flash_test_f187_session_ui.ps1` es dry-run por defecto. Una
promocion requiere autorizacion exacta y escribe unicamente `mtd4/linux_live`.

