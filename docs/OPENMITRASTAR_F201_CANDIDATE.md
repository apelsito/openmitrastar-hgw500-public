# OpenMitraStar F201 Radio Contract UI

Fecha: 2026-09-01

F201 expone en Developer el contrato normalizado completo de ambos radios:
identidad, capacidades, ciclo de vida, estado e indicadores de interfaz. La
API usa `GET /api/v1/radios/{id}?view=contract` y no devuelve PSK, claves
privadas, identificadores de clientes ni calibracion.

## Artefacto

- Bytes: `5,124,096`.
- SHA-256: `1fc5d26b9a5d822da2201da7abcc38441441215b5e2dacd0b2acbf0dba00f707`.
- Kernel: byte-identico a F199.
- Validacion fisica: `NOT_RUN`.

## Evidencia Offline

- Foundation/API/radio contract: `19/19 PASS`.
- Sintaxis BusyBox/ash: PASS.
- Dos builds consecutivos byte-identicos.
- `SHA256SUMS`, Bootbase y slot-fit: PASS.
- Browser desktop `1280x720` y movil `390x844`: PASS sin overflow.
- Stage, reload, apply, reload y rollback desde UI: PASS.
- Consola del navegador: cero warnings y cero errors.
- Acciones hardware: ninguna.

F201 conserva la transaccion v2 de F199 y deja `restart_radio` bloqueado hasta
que exista recuperacion fisica certificada.
