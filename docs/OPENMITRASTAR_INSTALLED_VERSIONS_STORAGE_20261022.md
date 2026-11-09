# HGW: versiones instaladas, fechas y almacenamiento

Verificado el 22 de octubre de 2026 mediante SSH fijado, metadatos de la
flash, registros DT decodificados y extracción de la raíz F367r9 exacta.
El firmware sigue siendo `lyoko-foundation-6.11.8-f367r9-transition-observation-device`,
Linux `5.10.260-openmitrastar-radiohw`, mismo boot
`5f513265-a294-4366-9567-e1d8af704b6b`. Las dos radios responden a sus controles;
esto no acredita asociación ni tráfico de clientes Wi-Fi.

## Inventario completo

- [Versiones y fechas](../outputs/inventory/installed-final-20261022T093747859049Z/VERSIONES.md).
- [CSV UTF-8 para Excel: 425 entradas](../outputs/inventory/installed-final-20261022T093747859049Z/installed-all.csv).
- [JSON detallado](../outputs/inventory/installed-final-20261022T093747859049Z/installed-all.json).
- [Validación de cobertura y CSV](../outputs/inventory/installed-final-20261022T093747859049Z/result.json).
- [Componentes, tamaños y candidatos separados](../outputs/inventory/router-components-20261022T092048336196Z/INVENTARIO.md).

Cobertura: 328 archivos regulares y 75 enlaces de F367r9, más 22 entradas de
paquetes RAM documentados. No es una lista de todos los logs, temporales,
procesos o páginas anónimas de memoria. Las rutas sensibles aparecen sin
contenido ni hashes de credenciales o calibración.

| Componente | Versión o identidad | Fecha demostrada de código/build | Instalación demostrada | Bytes de archivo |
|---|---|---|---|---:|
| Firmware completo | F367r9 / 6.11.8 | Integración del proyecto 2026 | Presente ahora; campaña documentada 22-09-2026 | 5.468.160 |
| Kernel comprimido | Linux 5.10.260, build #358 | Timestamp reproducible 21-09-2026 18:00 UTC | Dentro de F367r9 | 1.524.323 |
| BusyBox principal | 1.38.0 | Build embebido 20-08-2026 14:44:08 CEST | Dentro de F367r9 | 279.604 |
| BusyBox/pkgbox | 1.38.0 | Build embebido 02-09-2026 02:18:04 CEST | Dentro de F367r9; cuatro rutas idénticas | 238.624 únicos |
| Dropbear SSH | 2026.92 | Etiqueta de versión 2026 | Dentro de F367r9 | 247.428 |
| hostapd 2,4 GHz | 2.12-devel | Build proyecto 2026; fecha upstream sin demostrar | Dentro de F367r9 | 530.172 |
| hostapd_cli 2,4 GHz | 2.12-devel | Igual anterior | Dentro de F367r9 | 58.484 |
| hostapd 5 GHz | 0.8.x | Linaje OEM; reconstrucción proyecto 2026 | Dentro de F367r9 | 320.740 |
| hostapd-cli-qtn | 0.8.x | Igual anterior | Dentro de F367r9 | 50.444 |
| Servidor HTTP | mini_httpd 1.19/bhoc | Etiqueta 23-09-2004 | Dentro de F367r9 | 160.104 |
| Servidor HTTPS | mini_httpd 1.19 + OpenSSL 1.0.2d | HTTP 2004; OpenSSL 09-07-2015 | Dentro de F367r9 | 1.300.436 |
| iw | Versión no identificada en el binario | GCC 15.2.0 no determina versión de iw | Dentro de F367r9 | 155.108 |
| API / interfaz | v1 / 0.3.0-classic-dfs | Integración proyecto 2026 | Dentro de F367r9 | Detalle en CSV |
| Driver 2,4 GHz | rtl8192ee + rtlwifi/rtl_pci + mac80211/cfg80211 y crypto | Port 2026, ABI Linux 5.10.260 | 10 módulos en F367r9 | 1.074.396 total |
| Driver 5 GHz almacenado | qdrv 1.0 / wlan 0.9.3.3, revisión F367r9 | Port 2026, linaje OEM | 27 módulos en F367r9 | 1.769.272 total |
| qdrv 5 GHz activo | F365, SHA cfb1b5c4… | Port 2026 | RAM, activación 21-10-2026 | 685.332 |
| wlan 5 GHz activo | F365, SHA f4f6099b… | Port 2026 | RAM, activación 21-10-2026 | 629.180 |
| Control de LEDs | CLI revisión 2, SHA 0b2509b8… | Corrección 21-10-2026 | RAM desde 22-10-2026 00:11 CEST | 9.064 |
| Doom, episodio 1 y música original | WAD shareware 1.9; engine WASM con OPL_Delay corregido | Corrección del motor 22-10-2026 | RAM desde 00:11; música actualizada 11:32 CEST | 5.996.332 paquete |

Las fechas del código no son las fechas de instalación. El firmware conserva
archivos de versiones anteriores: la primera instalación individual de cada
uno no se ha demostrado. La fecha de campaña F367r9 tampoco prueba el segundo
exacto de instalación. Los timestamps deterministas del kernel/SquashFS no
son un reloj de instalación. Los campos desconocidos se mantienen desconocidos.

## Ocupación de la raíz instalada

| Grupo | Bytes sin comprimir |
|---|---:|
| Programas y scripts | 4.955.432 |
| Módulos 2,4 GHz | 1.074.396 |
| Módulos 5 GHz | 1.769.272 |
| Otros módulos | 57.944 |
| Firmware interno de radios | 1.450.941 |
| Web completa, incluido HTML interno | 1.222.665 |
| Configuración y metadatos | 87.512 |
| Total de archivos regulares | 10.618.162 |

SquashFS reduce esa raíz a 3.895.296 bytes. Esa raíz ya está incluida en la
imagen de 5.468.160 bytes: no se suman. Los bytes individuales comprimidos no
son una asignación de flash; SquashFS comparte fragmentos y deduplica contenido.

## Mapa físico de la NOR

La referencia de volcado físico validada cubre 16.777.216 bytes, 16 MiB.
Linux muestra cinco vistas ROM de esta misma NOR. El nombre del chip en los
documentos de sonda es Macronix MX25L12836E; esta consulta no volvió a leer
el JEDEC y no convierte ese nombre histórico en una identificación nueva.

| Región física | Inicio | Final exclusivo | Capacidad | Uso |
|---|---|---|---:|---|
| uboot | 0x000000 | 0x020000 | 128 KiB | Bootbase protegido |
| uboot_env | 0x020000 | 0x030000 | 64 KiB | Entorno protegido |
| uboot_env_bak | 0x030000 | 0x040000 | 64 KiB | Entorno redundante protegido |
| linux_safety | 0x040000 | 0x7e0000 | 7,625 MiB | OEM preservado; recuperación de gestión aún no validada |
| linux_live | 0x7e0000 | 0xf80000 | 7,625 MiB | Firmware Linux 5.10 y store |
| data | 0xf80000 | 0x1000000 | 512 KiB | Datos OEM preservados; /persist solo lectura |

Dentro de linux_live se reparten 1,5 MiB para cabecera/kernel, 4,375 MiB para
rootfs y 1,75 MiB para lyoko_store. Son subdivisiones; no se suman otra vez
al total físico. El firmware actual ocupa 5,215 MiB del prefijo de 5,875 MiB.
El journal/store de 1,75 MiB no es capacidad libre.

## Vistas actuales de Linux

| Dispositivo visible | Nombre | Offset físico | Capacidad |
|---|---|---|---:|
| mtd0 | uboot_env | 0x020000 | 64 KiB |
| mtd1 | uboot_env_bak | 0x030000 | 64 KiB |
| mtd2 | data | 0xf80000 | 512 KiB |
| mtd3 | rootfs_live | 0x960000 | 4,375 MiB |
| mtd4 | lyoko_store | 0xdc0000 | 1,75 MiB |

Estos índices no corresponden a los mismos números del mapa físico OEM.
Todas las vistas actuales declaran tipo ROM y flags0; no se han unido ni
reparticionado. Ningún disco adicional, eMMC, SD o almacenamiento USB aparece
en `/proc/partitions` o como bloque no-MTD en esta observación. Eso no prueba
que la placa no tenga otro recurso aún sin driver; solo delimita lo expuesto.

Evidencia: [consulta SSH](../outputs/storage/hgw-readonly-20261022T093109419362Z/stdout.txt)
y [registros DT decodificados](../outputs/storage/hgw-dt-reg-20261022T093404035766Z/result.json).
La primera consulta terminó en una opción `od` no soportada; quedó registrada
como incompleta y se corrigió sin cambiar hardware.

## RAM y tmpfs

Linux informa MemTotal51.976 KiB (aproximadamente50,76 MiB utilizables),
MemAvailable10.360 KiB en la observación y SwapTotal0. El DT reserva para Linux
una ventana alta DDR de0x036c6000 bytes; no representa toda la RAM física de la
placa. La DDR baja permanece fuera del uso del kernel y puede pertenecer a
radios/coprocesadores; no se reclama ni convierte en almacenamiento persistente.

`/run` limita su tmpfs a8 MiB y `/tmp` a4 MiB. El tmpfs separado de Doom tiene
otro límite8 MiB. Son límites de asignación sobre la misma RAM, no memorias
añadidas. `/www` y `/usr/sbin/om-ledctl` son binds de ese tmpfs y no duplican
sus datos. La música añade otro WASM en `/tmp`; el original se conserva debajo
del bind. Estos archivos se pierden al reiniciar.

## Unir almacenamiento y modernizar

Crear una vista de regiones físicas disjuntas puede cambiar el espacio
direccionable, pero no crea bytes nuevos. Unir rootfs y store reutilizaría
los mismos7,625 MiB de linux_live y desplazaría datos existentes. Unir safety
y live necesitaría modificar la región OEM preservada y el diseño de rollback;
esa región no es espacio disponible en el alcance vigente. Dos alias de la
misma región no pueden sumarse. Cualquier almacenamiento realmente adicional
requiere identificar dispositivo, controlador y capacidad antes de diseñar uso.

El candidato F373 completo medido excede la ventana de rootfs por3.194.880 bytes.
La sustitución TLS por el ensayo wolfSSL5.9.2 ahorra352 KiB reales en un repack
controlado de F372 y no está instalada. Esa reducción no resuelve por sí sola
el déficit. [Medición TLS](OPENMITRASTAR_TLS_SIZE_MEASURED_20261022.md).

F368–F373 siguen siendo candidatos/estudios offline y no la instalación actual.
La música sí está instalada en RAM y verificada por HTTP, OPL y PCM:
[prueba real](../outputs/doom/music-http-20261022-r1/result.json).
No se han flasheado particiones, cambiado bootenv ni reiniciado el HGW en este
inventario. El port completo aún necesita cliente/tráfico, persistencia,
recuperación y aceptación física.
