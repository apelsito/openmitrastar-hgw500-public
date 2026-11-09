# Lyoko API Gap

Fecha: 2026-09-01

## Disponible Ahora

| Endpoint | Estado | Limite |
|---|---|---|
| `GET /api/v1/status` | Disponible | Salud, memoria, carga y CSRF |
| `GET /api/v1/network` | Solo lectura | Bridge y contadores, sin MAC |
| `GET /api/v1/radios/{2g,5g}` | Disponible | Configuracion no secreta |
| `GET /api/v1/clients` | Parcial | Solo conteos redactados |
| `GET /api/v1/hardware` | Solo lectura | Botones, LEDs, IRQ y disponibilidad |
| `GET /api/v1/diagnostics` | Solo lectura | EMAC, IRQ, NAPI y TQE |
| `GET /api/v1/privacy` | Disponible | Politica machine-readable |
| `GET /api/v1/firmware` | Solo lectura | Slots y version; sin escritura |
| `GET /api/v1/packages` | Parcial | Inventario; runtime no certificado |
| `GET /api/v1/capabilities` | Disponible | Gate central de funciones |
| `GET /api/v1/frontend` | Disponible en 1.5-dev | Procedencia y hashes de UI |
| `PATCH /api/v1/radios/{id}` | Bloqueado por feature gate | Solo staging validado |
| `POST /api/v1/config/{apply,rollback}` | Bloqueado por feature gate | Confirmacion y CSRF obligatorios |

## Endpoints Necesarios

| Contrato propuesto | Requisito previo |
|---|---|
| `GET/POST /api/v1/session` | Login Lyoko y rate limiting |
| `DELETE /api/v1/session` | Logout y revocacion |
| `PATCH /api/v1/radios/{id}/security` | PSK write-only y reautenticacion |
| `GET /api/v1/radios/5g/station` | Certificacion de modo STA |
| `GET/PATCH /api/v1/network/management` | Recovery ante cambio de IP |
| `GET/PATCH /api/v1/radios/{id}/ssids` | Multi-SSID probado por driver |
| `GET/PATCH /api/v1/radios/{id}/acl` | Anti-lockout y aliases |
| `POST /api/v1/radios/{id}/wps` | WPS opt-in y temporizador |
| `POST /api/v1/config/export` | Formato versionado y redactado |
| `POST /api/v1/config/import` | Firma, compatibilidad y rollback |
| `POST /api/v1/system/reset` | Contrato de preservacion de particiones |
| `POST /api/v1/firmware/stage` | Solo validacion en RAM inicialmente |
| `POST /api/v1/support/bundle` | Allowlist y escaneo de secretos |
| `GET/PATCH /api/v1/network/vlans` | Kernel y trafico real certificados |
| `GET/PATCH /api/v1/network/multicast` | IGMP/MLD/MDB certificados |

## Contratos Prohibidos

- Lectura de PSK o contrasena administrativa.
- Lectura de claves privadas, calibracion o MAC completa de clientes.
- Acceso web generico a `/dev/mtd*`, SPI, Bootbase o comandos arbitrarios.
- Escritura de `mtd0`, `mtd1`, `mtd2`, `mtd3` o `mtd5`.
- Activar controles porque una opcion exista en la web OEM sin backend probado.

