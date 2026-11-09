# OpenMitraStar F213 Movistar/F1 Router UX

Fecha: 2026-09-01

F213 rehace la experiencia de Lyoko como una consola de router inspirada en
OpenWrt y menus de configuracion de juego/F1: opciones grandes, selector de
banda, tabs y un inspector lateral para cada valor.

- Bytes: `5,201,920`.
- SHA-256: `2fe1dbbca0e5bb065ce4147b94c8ee74cc2683bfe35a4bcb4a61b7d59a90e333`.
- CRC32 candidato: `2e095812`.
- SHA-256 slot completo: `fe38f9692fd4c1777df6aaa409d0c6e6be8d5dde8eba040ac5d15fd2267f2fe5`.
- Rootfs headroom: `958,464` bytes.
- Validacion fisica: `NOT_RUN`.

## UX

- Identidad Movistar/Telefonica y producto Lyoko.
- Selector grande 2,4/5 GHz.
- Tabs General, Radio, Seguridad y Expert.
- Inspector con valores permitidos, recomendado, efecto al subir/bajar y
  riesgos.
- Controles pendientes visibles pero deshabilitados con estado real.
- Radar de cobertura declarado como modelo hasta recibir RSSI/PHY fisicos.
- Login inspirado en la ayuda OEM, con la ilustracion original sanitizada.

## Seguridad

- El firmware generico no contiene credencial web.
- Provisioning mediante hash SHA-256 privado y archivo runtime `0600`.
- Sesion temporal, HttpOnly, SameSite Strict, CSRF y bloqueo por cliente tras
  intentos fallidos.
- La credencial desbloquea toda la consola, no vistas parciales.

Tests: `25/25 PASS`. Browser desktop/movil: PASS. Cero errores de consola.
