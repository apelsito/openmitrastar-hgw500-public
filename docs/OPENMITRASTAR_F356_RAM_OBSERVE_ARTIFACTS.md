# F356: arranque RAM para una observación ID/status/security

Preparado el 21 de septiembre de 2026. PASS offline, 43 comprobaciones; ninguna
operación de hardware ejecutada por el preparador. No es una imagen flash.

Se empaqueta el kernel F350 ya reproducido, sin recompilar kernel/config/DT.
Su identidad real es `#350 @1790006400`, release
`5.10.260-openmitrastar-radiohw`; conserva el DT F340 y utiliza su rootfs
persistente read-only. RAS con payload en 0x2000 y uImage compacto contienen
exactamente el mismo kernel, comprimido dos veces con resultado idéntico.

Memoria: staging 0x83000000; scratch CRC 0x84000000; load 0x8493a000;
entry 0x8493e000; fin kernel 0x84d02000; DDR end 0x88000000. El contrato
Bootbase, CRCs y round-trip LZMA pasan. No se incluye ni modifica rootfs.

## Componentes y contrato

- Supervisor nuevo `om-watchdog-supervisor-f356`: exige uname release/version
  exactos y conserva DT/driver/sysfs f340. Inspección publica
  `kernel_profile_verified=1` y `required_kernel_version=#350 @1790006400`.
  F340 original validaba el marcador, no uname: F356 añade esa comprobación.
  Rechaza #340 antes de abrir watchdog. Mantiene wire/schema IPC F340
  compatibles; esa versión de protocolo no representa el kernel en ejecución.
  No autoarm; 20 pruebas de policy y 13 IPC/profile con backend fake PASS.
- Proveedor nuevo `qtn_f356_journal.ko`, versión 356: RDID debe ser c22018
  antes de SCUR2B o cualquier escritura CONTROL. ID compartido E/F, sin afirmar
  `exact_part_verified`. Cinco IDs desconocidos/ilegibles no generan escritura;
  cleanup parcial no repite snapshot ni deja ownership de tarea retenido.
- Ante cambio de ID al cerrar, conserva el snapshot parcial que produjo el
  rechazo y pone en cuarentena si no puede confirmar el estado inicial. El
  módulo anterior 170333Z/bundle170552Z queda histórico, no debe ejecutarse.
- Después de OBSERVE y release/quarantine emite una sola línea numérica:
  `OMF356 observe rc=... id=... control=... status=... security=... valid=... claimed=... quarantined=...`.
  No hace lecturas adicionales ni expone payload. `valid` es máscara de campos
  leídos: ID1/CONTROL2/STATUS4/SECURITY8; no certifica identidad E/F. Los fallos
  nunca se convierten en PASS ni permiten unload.
- ABI/nodo F350 de 4180 bytes, compatible con F351. Parámetros de esta campaña:
  `allow_hw=1 allow_program=0`; una única llamada CLI `observe`. No SAVE,
  WREN, PP, D8 ni cambios de protección. La lectura SCUR sí utiliza cambios
  temporales de CONTROL, con restauración y footer READ_ID verificados.
- F351 y ram-insmod-qtn se copian byteidénticos. El cargador recibe todos los
  parámetros en argv2 y ejecuta una sola finit_module, sin fallback.

El executor/plan pertenecen al otro agente. Su política coordinada es no hacer
rmmod ante cualquier fallo/timeout/observación parcial: CEASE, reset y retorno
F340 read-only. Sólo una respuesta completa validada permite unload. Los
helpers persistentes, F350/F351 previos y F354 quedan intactos.

La aceptación F354 sólo prueba SPI_CONTROL=00000004 y el mapa legacy; no
identifica flash ni acepta el transporte de ID/security. La primera observación
F356 física permanece UNRUN en esta cualificación. No se demuestra recuperación
ante CPU/bus halt; no se prepara F343 ni se hacen pruebas Wi-Fi/AELITA.

## Artefactos finales

- Bundle: `outputs\kernel-port\f356-observe-ram-20260921T171309Z\result.json`
  SHA-256 `5ae7ad32f718da536787cb1008450a24ce4551861245ca3c64a5ebcf89fe7d0f`.
- Cualificación: `outputs\preflight\f356-artifacts-qualified-20260921T171418Z\result.json`
  SHA-256 `18dfc4ff9f52c83fe6df89534630df535300ddc7f72645509523b08a2057c292`.
- RAS: `/workspace/user-home\Desktop\MitraStar\outputs\kernel-port\f356-observe-ram-20260921T171309Z\a\F356-OBSERVE-RAM-ONLY.ras.bin`
  SHA-256 `b4753dc8f2cbb0847011e7f3241a58d8dcb6d4c2fc18c12296f9f8b7161621d0`, 1532255 bytes.
- Proveedor: `/workspace/user-home\Desktop\MitraStar\outputs\kernel-port\f356-observe-ram-20260921T171309Z\qtn_f356_journal.ko`
  SHA-256 `ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4`, 20192 bytes.
- Supervisor: `/workspace/user-home\Desktop\MitraStar\outputs\kernel-port\f356-observe-ram-20260921T171309Z\om-watchdog-supervisor-f356`
  SHA-256 `3cb43d1686626c0df99fbce43912db6df54553da5bfb07fba820a8e5cf9062a5`, 33720 bytes.
- CLI: `/workspace/user-home\Desktop\MitraStar\outputs\kernel-port\f356-observe-ram-20260921T171309Z\om-journal-cli`
  SHA-256 `dee84fd30d41734e52d4627418028a1d15cd64db87cca1bc3eef261aacb0edef`, 25524 bytes.
- Loader: `/workspace/user-home\Desktop\MitraStar\outputs\kernel-port\f356-observe-ram-20260921T171309Z\ram-insmod-qtn`
  SHA-256 `8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6`, 816 bytes.
