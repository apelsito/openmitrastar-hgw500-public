# F358: corrección NO_XIP y backend persistente inactivo

Estado: artefacto completo offline PASS, sin instalación ejecutada por este agente.
F357 queda conservado y NO-GO: contenía el registro de store defectuoso de F350.

Causa demostrada: physmap_flash_of_init aplica NO_XIP a las cinco vistas que
usan no-unaligned-direct-access. El nombre lyoko_store ya era correcto; el
sentinel se usaba incorrectamente como dirección física. F358 resuelve el
recurso DT real (único y de tamaño exacto), conserva NO_XIP y no expone point.
El test ejecuta el init physmap y map_rom antiguos/nuevos: reproduce ENODEV
anterior y verifica claim/read/release con el recurso correcto. Rechaza el
mismo nombre en una dirección equivocada. No se altera la política SPI.

Kernel #358, mismo release/config/DT; proveedor F356 y CLI F351 byteidénticos.
El supervisor sólo cambia el perfil uname esperado a #358. Tres casos nuevos
comprueban aceptación #358 y rechazo #350/#340 antes de abrir watchdog.
No se repite la batería completa SPI/radio. La segunda compilación ya estaba
en marcha y terminó idéntica durante el empaquetado, sin bloquear la entrega.

Imagen completa: dos composiciones idénticas, Bootbase PASS y sin solapar
store. Sólo ocho archivos del rootfs base F340 cambian (release, componentes
y catálogos/perfiles); init, radios, calibración e identidad permanecen iguales.
No autoload de backend, ARM de watchdog ni MMIO/escritura SPI automáticos.
Activación sólo en una campaña explícita. El fallback es el F340 exacto.

Resultado canónico: `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f358-fullimage-20260921T174614Z\result.json`
SHA-256 `4b8e694340956d8d75629c36e686326772354ca25e8728270a1e25a5ea5eccc9`.

Imagen `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f358-f340-config-backend-device-bound\openmitrastar-linux510-f358-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
5361664 bytes; SHA-256 `fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f`.

Manifest SHA-256 `b2c7a79796481b324b6ba4d4d84c82a6a017c96f2a6967bed3c03fe292845652`. Versión `lyoko-foundation-6.9.8-f358-config-backend-device`, build `bfc445a80d506df9`.

CRC de imagen `9bd4586c`; prefijo 0x5e0000 rellenado FF `df453410`; slot de referencia `4d006632`. La escritura normal debe preservar el store; el CRC de referencia no representa futuras modificaciones del journal.

Regresión: `outputs/preflight/f358-map-resource-20260921T173857Z/result.json`.
Kernel: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f358-flash-arbitration-20260921T173956Z/result.json`.
Supervisor: `outputs/kernel-port/f358-supervisor-20260921T174119Z/result.json`.
