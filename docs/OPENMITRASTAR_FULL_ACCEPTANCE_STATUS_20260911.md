# HGW-500BNA-QCv2 A2: aceptación completa a 11 de septiembre de 2026

**Estado global: EN CURSO. No está demostrada una migración funcional al 100 %.**
F321 sí está instalado en `mtd4/linux_live`, arranca Linux
`5.10.260-openmitrastar-radiohw` y tiene comprobaciones actuales de gestión,
ambas radios en estado preparado y sesión HTTP autenticada. Eso no cierra los
ensayos físicos restantes ni convierte las pruebas de F314 en pruebas de F321.

Este documento se prepara exclusivamente leyendo archivos. El corte de estado
del equipo es la observación de **2026-09-11 09:13 UTC**; no se ha contactado con
el HGW, AELITA, UART ni otro dispositivo para elaborar esta matriz. Cada nuevo
ensayo debe conservar su fecha, imagen exacta y alcance por separado.

## Identidad y significado del estado

| Campo | Evidencia aceptada |
| --- | --- |
| Unidad | HGW-500BNA-QCv2 A2, gestión `192.168.1.90` |
| Versión observada | `lyoko-foundation-6.8.5-f321-classic-ui-f314-device` |
| Build | `ad60c8e1e49dfbbf`; UI `72dd5d1877544af9` |
| Imagen F321 | `5,337,088` bytes, SHA-256 `eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18` |
| Instalación | Ciclo `f321-direct-20260907T235105Z-b42111c6`; escritura y arranque desde mtd4 |
| Readback físico | CRC32 del slot completo `6ed8e483` y comparación de los `5,337,088` bytes de la candidata |
| SHA-256 del slot físico | No medido. El SHA del slot rellenado es un cálculo local y no se presenta como lectura del chip |
| Aceptación F321 | `PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION`, E01 |
| Recuperación disponible documentada | Restauración de la imagen exacta F314 en mtd4 mediante Bootbase, E05; mtd3 tiene un fallo de montaje documentado, E06 |

`ACTUAL` se limita al alcance de la observación fechada de F321. `HISTÓRICO`
pertenece a otra imagen o a una fecha anterior. `OFFLINE` acredita código,
artefactos o pruebas sin hardware. `PENDIENTE` no implica fallo del dispositivo;
significa que falta el ensayo de aceptación. `NO-GO` identifica un fallo o una
precondición incumplida que impide dar ese requisito por cerrado. No se calcula
un porcentaje mezclando estas categorías.

## Definition of done del port

La referencia es la lista de `AGENTS.md`. Se desglosa para evitar que un PASS de
control o de archivos oculte la ausencia de una prueba física.

| ID | Requisito | Estado al corte y evidencia fechada | Acción concreta para cerrarlo |
| --- | --- | --- | --- |
| D00 | Linux 5.10 instalado en el slot normal | **ACTUAL, alcance probado.** E01/E02, 11-09: versión, kernel, SquashFS y arranque desde mtd4. El resultado original del instalador sigue siendo STOP por su parser; la aceptación independiente lo reconcilia sin borrarlo | Conservar la imagen exacta y sus pruebas; no reflashear para corregir informes del host |
| D01 | Arranque persistente en frío repetible | **PARCIAL.** E01 prueba selección de mtd4 y arranque; sus límites excluyen ciclos de alimentación. F314 tiene arranque y reinicio normal históricos, E03; reiniciar por software no acredita un corte de alimentación | Preparar una campaña específica de arranques en frío de la imagen elegida, con captura completa, identidad de cada arranque, SSH/UI/radios y protección verificadas tras cada ciclo. Mantener recuperación física disponible |
| D02 | Estabilidad de SSH y Ethernet | **PARCIAL ACTUAL.** E02 pasa 27/27 a las 09:13 UTC. Hay otros postchecks F321 del 08-09, pero dos observaciones separadas no son un soak continuo | Medir pérdidas, disponibilidad de SSH/HTTP, contadores Ethernet/IRQ/colas y memoria durante carga y reconexión; probar cada puerto físico presente, sin asumir que un enlace valida todos |
| D03 | mtd3/linux_safety conservado y rollback probado | **NO-GO para boot de mtd3.** E06, 01-09: `RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE`, sin gestión ni SSH. Su CRC se conserva en E01. E05 prueba otra vía: F314 en mtd4 sin depender de SSH durante Bootbase | Mantener mtd3 intacto. Documentar y resolver explícitamente la diferencia entre la definición original y la vía de recuperación realmente disponible. Una reparación de mtd3 estaría fuera de la iteración normal de mtd4 y exige su propio plan; no usar ATGO como garantía de rescate |
| D04 | 2.4 GHz WPA2 y tráfico bidireccional útil | **HISTÓRICO PASS en F314; PENDIENTE en F321.** E04, 05-09: 32 MiB por sentido, salud del router y contadores WLAN correctos. F321 sólo tiene readiness actual | Reutilizar el runner 2G con identidad F321 y cliente físico fijados; exigir WPA2, bytes exactos por sentido, contadores RX/TX, salud de gestión, ausencia de errores nuevos y restauración del cliente |
| D05 | SSID de 5 GHz visible desde cliente real | **HISTÓRICO en F314; PENDIENTE en F321.** E03 acredita asociación real anterior; E02 no realiza un escaneo del cliente | Capturar un escaneo deliberado, fechado y redactado desde AELITA u otro cliente identificado, correlacionado con la imagen y canal actuales |
| D06 | 5 GHz AUTH/ASSOC/AUTHORIZED y tráfico bidireccional | **HISTÓRICO PASS en F314; PENDIENTE en F321.** E03, 05-09: WPA2/CCMP en canal 36, 32 MiB por sentido, 34.026/26.949 Mbps y 120 s sin desconexiones | Añadir un perfil F321 al runner 5G o un wrapper versionado; capturar estados de asociación/autorización, bytes por sentido y restauración. Un canal 36 operativo no demuestra DFS |
| D07 | Soak sin fatal ARC/QMAC/MuC/DMA/colas/térmico | **PARCIAL.** E02 pasa la búsqueda acotada de fatal; E03 tiene 120 s en F314. E07 consolida más de 6 h activas y 34 ciclos PASS de F301, con fallos de harness preservados. Ninguno es un soak F321 | Ejecutar un soak versionado de F321 tras los gates cortos, con duración fijada, carga por banda, reconexiones, contadores, memoria y registro de todos los huecos. Validar la fuente térmica real o registrar que no existe; no inventar temperatura |
| D08 | Calibración, regulación, identidad MAC y particiones protegidas | **PARCIAL, preservación probada en el ciclo.** E01 conserva CRC antes/después de mtd0/1/2/3/5; E02 valida identidad y credencial sin publicarlas; E08 preserva el payload de radio F314. No hay aceptación RF/DFS completa | Mantener comparación de archivos, dominio y tablas calibradas; añadir readback de los parámetros realmente aplicados durante las campañas de radio. Conservar siempre los límites de partición y redactar MAC/calibración/secretos |
| D09 | Manifiesto reproducible, hashes, recuperación y aceptación final | **PARCIAL.** E08 contiene build/repro/Bootbase y E01 reconcilia la instalación. Los flags de la candidata sellada y `release_eligible=false` no se cambian retrospectivamente | Reunir D01-D08 y los requisitos de producto en un manifiesto final nuevo, con versión exacta, resultados fechados, recuperación y limitaciones. Mantener originales fallidos y no declarar release completa mientras falten gates |

## CAC/DFS, persistencia y candidatos siguientes

| Área / candidato | Estado comprobado | Evidencia y fecha | Acción concreta restante |
| --- | --- | --- | --- |
| F315, adquisición QT4 shadow | **OFFLINE; físico no ejecutado.** Sin callbacks ni autoridad de transmisión | `docs/OPENMITRASTAR_F315_CANDIDATE.md`, 05-09; hashes sellados | No reutilizar ciegamente su promotor antiguo. Usar un candidato nuevo sobre la UI vigente y un ejecutor revisado; demostrar adquisición temporal, progreso de muestras, cero callbacks y gestión estable |
| F322, shadow sobre F321 | **OFFLINE reproducible; no instalado.** Inicio desarmado, sin autoridad DFS | E09, 08-09; SHA `55145f55f904beb342dd67b39578a79fbc8a4d0bc68bae944402cab80e5f7f1a` | Preparar y revisar instalación/runtime/recuperación exactos. Primero validar arranque desarmado; después, en una fase acotada, progreso de adquisición y unload limpio. No confundir contadores o `backend_ready` con CAC o permiso TX |
| F316, radar con autoridad | **OFFLINE; aceptación RF no ejecutada** | `docs/OPENMITRASTAR_F316_CANDIDATE.md`, 05-09 | Tras shadow aceptado, validar clasificación, pérdida del detector, callbacks y concurrencia; demostrar CAC, evacuación, NOP y rollback con un procedimiento RF adecuado. Los vectores sintéticos no acreditan detección física |
| CAC, canales DFS, weather y TPC | **PENDIENTE / cerrado en F321 por el guard F314** | E03/E08 y `docs/LYOKO_CHANNEL_POLICY_ES.md` | Mantener los bloqueos hasta probar las condiciones del canal y ancho seleccionados. El panel puede explicar CAC/NOP, pero no habilitarlos por un temporizador local ni por apariencia de readiness |
| F317, optimización autónoma | **OFFLINE, observe-only; no instalado ni apply automático** | `docs/OPENMITRASTAR_F317_CANDIDATE.md`, 05-09 | Aceptar antes el backend físico de radio; medir CPU/RAM/gestión y estabilidad del observador. Sólo después validar decisiones y rollback antes de permitir aplicación automática |
| F318, journal persistente | **OFFLINE.** Core transaccional de dos eraseblocks; no backend MMIO ni escritura persistente | `docs/OPENMITRASTAR_F318_STORE_TRANSACTION_CORE.md`, 05-09 | Probar primero acceso seguro al controlador y restauración exacta de protección por bloque. Luego incorporar el proveedor en una candidata y realizar pruebas de interrupción de energía y recuperación del journal |
| F319, propiedad del controlador SPI | **HISTÓRICO PASS acotado**, 07-09 19:29 UTC: claim/map/unload, cero lecturas y cero escrituras | E10 | Conservar el resultado. No repetirlo como prueba de dirección MMIO, arbitraje eléctrico, opcodes SPI o persistencia: no midió esas propiedades |
| F320, lectura SPI controlada | **INSTALADO Y RESTAURADO; sonda no aceptada.** Boot/readback y platform PASS, pero `insmod` devolvió `Permission denied` sin salida de lectura aceptada; el harness registró además `Get-FileHash` no reconocido | E15, 07-09 21:04-21:09 UTC; final `FAIL_F320_EXACT_F314_RESTORED` | Analizar por separado el rechazo de carga y el fallo del harness antes de rediseñar el gate. Conservar el PASS de instalación y restauración F314 sin inventar PASS SPI. Cualquier nuevo ensayo requiere fuentes/imagen/ejecutor/recuperación ligados al baseline elegido y contingencia de hard halt; no cargar sondas ad hoc en F321 |
| Configuración guardada y restauración/factory reset | **NO aceptado completo en F321.** `/persist` sigue RO; existen helpers y contratos, pero presencia no demuestra persistencia | E02/E08; E12 para contrato de botones/reset | Probar lectura/rechazo seguro ahora; guardar/restaurar y reset persistente sólo cuando el backend de persistencia esté validado. No ejecutar un factory reset destructivo como prueba de presencia del botón |

## Paridad de producto y hardware fuera del PASS de UI

El HGW OEM documentado es un **Adaptador WiFi+ Dual / videobridge**. WAN/PPPoE,
NAT doméstico, VoIP/ATA y terminación IPTV no se convierten en deuda de este port
por llamarlo informalmente router. Su tráfico de clientes debe atravesar el
bridge hacia el HGU. La matriz OEM E13 determina qué comportamientos sí hay
que comparar; sus estados de agosto no describen la instalación actual.

| Capacidad | Estado honesto al corte | Evidencia disponible | Próximo ensayo o decisión |
| --- | --- | --- | --- |
| UI clásica, login, sesión y assets | **ACTUAL PASS acotado:** 12 hashes + 13 checks HTTP y 10 de sesión | E01/E02, 11-09; responsive/teclado en navegador local E08 | Recorrer la UI servida por el HGW en un navegador real, incluidas ambas bandas, formularios, errores y cancelación. Separar estos pasos de las pruebas ya hechas en emulador |
| Todos los controles de radio de la UI | **PARCIAL.** F314 pasó 14 controles Quantenna con apply/readback/rollback; F321 conserva su backend, pero no repitió esa matriz | E03/E08 | Perfil F321 para la matriz existente y pruebas materiales escogidas con snapshot exacto antes/después. No interpretar un campo visible como función habilitada |
| HTTPS/TLS | **OFFLINE en una integración separada; no instalado con F321** | `docs/OPENMITRASTAR_TLS_MODERNIZATION.md` y E08 | Versionar la integración TLS, verificar recursos/ABI y validar handshake, sesión, cookies y navegador en el dispositivo tras sus gates |
| Ethernet, bridge y modos AP/STA/repeater | **PARCIAL.** La gestión y readiness están actuales; tráfico AP tiene evidencia F314. No hay aceptación F321 de todos los puertos ni de los tres modos | E02/E03/E04/E13 | Inventariar puertos/modos reales; probar forwarding, DHCP/ARP/DNS/IPv4 y retorno a gestión por cada camino con rollback. No asumir NAT ni cambiar el HGU |
| VLAN y multicast/IGMP/IPTV transparente | **OFFLINE / PENDIENTE físico para F321** | E14; `docs/OPENMITRASTAR_F301_VLAN_GATE.md`; harness multicast presente en E08 | Rebasar runners exactos, verificar topología aislada y recuperación, y medir tagged/untagged, joins/leaves, MDB, flooding y unicast concurrente. La presencia de módulos no es tráfico PASS |
| LED 2.4/5 GHz, colores y ownership | **HISTÓRICO/PARCIAL.** Se observaron 2G, rojo/verde/naranja; GPIO1 y GPIO10 tienen límites de evidencia | E11, 21/22-08; controlador presente en E08 | Identificar físicamente cada ventana con snapshot/restore y observador. Probar la precedencia de estado de radio, actividad y WPS; no inventar un LED Power/Ethernet/IPTV por su nombre |
| Botones 2G, 5G/WPS, reset y switch RF | **CONTRATO OEM/offline; actuación física completa F321 pendiente** | E12, 20/21-08 | Identificar input y eventos primero; después probar ventanas de pulsación y una única acción por hold, con gestión preservada. Separar reset/reboot/factory reset y sus precondiciones de persistencia |
| Alimentación mecánica | **Sin mapeo software demostrado** | E12 | Identificar el control físico y usarlo sólo en una campaña de alimentación controlada. No añadir un supuesto driver de botón de power sin evidencia de placa |
| Temperatura y watchdog | **No validados en F321.** F173 registraba ausencia de sensor y watchdog expuestos; es evidencia histórica | `docs/OPENMITRASTAR_F173_HARDWARE_INVENTORY.md`, 01-09 | Inventario de lectura actual; si no hay sensor fiable, consignar temperatura desconocida o medir externamente. No prometer recuperación de un CPU detenido mediante un timeout del host |
| Drivers y firmware de coprocesadores | **Port funcional del host con dependencias binarias, no reimplementación libre del 100 %** | Inventario sellado E08: `rtl8192ee.ko`, `qdrv.ko`, `rtl8192eefw.bin`, `qtn_driver.qtn_ruby.0.bin`, `auc_driver.default.0.bin`, `auc_driver.nomu.0.bin`, `rdsp_driver.0.bin` | Preservar hashes, carga/ABI y calibración; distinguir bugs del host, driver y coprocesador. Eliminar o reimplementar blobs sería otro objetivo, no una condición implícita de que Linux 5.10 funcione |

## Herramientas existentes y límites antes de reutilizarlas

Se han inspeccionado sus fuentes; **no se han ejecutado**. Que una herramienta
se llame `readonly`, `cold` o `preflight` no acredita por sí solo su alcance.

| Gate | Herramienta existente | Capacidad y adaptación necesaria |
| --- | --- | --- |
| Estado de plataforma/UI | `tools/post_flash_f214_device_gate.py`, `tools/post_flash_f321_ui_gate.py`, `tools/verify_f321_authenticated_http.py` | Son los checks reutilizados en E02. Fijar versión, SSH conocido y directorio nuevo; el último crea y cierra una sesión HTTP |
| Visibilidad 2G/5G | `tools/capture_aelita_dual_radio_visibility_readonly.ps1`, `tools/monitor_q3_ap_association_readonly.py` | El primero consulta el escaneo de AELITA y contadores; el segundo observa AP sin provocar asociación. Revisar target/identidad/redacción y SSID reales antes de reutilizar |
| Tráfico 2G | `tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py` y `tools/run_aelita_2g_wpa2_runtime_psk_once_ssh_v2.py` | Reutilizan el flujo físico con SSH fijado, 32 MiB y restauración del cliente. No son file-only: la asociación del cliente y su tráfico cambian durante el gate |
| Tráfico 5G | `tools/run_f293_5g_aelita_traffic_ssh_v2.py` sobre `tools/run_f293_5g_aelita_traffic.py` | El catálogo inspeccionado llega a F314; falta perfil F321. Rechaza otra versión y exige 120-600 s de observación; crear wrapper/perfil y tests sin falsear la identidad instalada |
| Soak de ambas bandas | `tools/run_f301_sequential_dual_radio_soak_ssh_v2.py`, `tools/f310_soak_runner.py` | Fijan versiones, hashes, planes y profiles antiguos. Rebasar en wrapper F321; reutilizar continuidad/deduplicación y recuperación, no cambiar resultados históricos. E07 es una cadena de tiempo activo, no seis horas continuas sin incidentes del harness |
| Arranque en frío | No hay un runner F321 de power-cycle aceptado en esta revisión | `tools/run_product_cold_irq28_ioss_ap_gate.ps1` es un experimento RAM antiguo con uploads/módulos y target por defecto distinto; no sirve como certificación fría de F321. Crear campaña exacta sin repetir un flash para cada arranque |
| Matriz Quantenna | `tools/run_f314_qtn_control_matrix_gate.py` | 14 controles históricos con rollback; rebasar sólo la identidad/artefacto y mantener los bloqueos de canal/ancho/TPC mientras falte radar |
| LEDs | `tools/run_frontpanel_led_identification_gate.ps1` | Acepta `ExpectedVersion` y `KnownHostsPath`, pero usa F222 por defecto. Snapshot/restore y pasos de 1-3 s; necesita observador físico para color/ventana |
| Botones | `tools/om_buttond.c`, contratos E12 | La implementación no sustituye una prueba física de timing ni autoriza reset. Diseñar el gate por eventos y acciones permitidas; comprobar qué consumidor está realmente instalado |
| Multicast y VLAN | `tools/run_f310_multicast_igmp_physical.py`, `tools/f310_vlan_gate.py` | Fijan F310. Requieren plan/topología/recuperación propios; VLAN puede afectar el enlace del controlador y usa un guard UART. No ejecutar bajo apariencia de inventario |
| Recuperación | `tools/rollback_f321_to_f314_mtd4.ps1`, `tools/f319_recovery_guard.ps1` | El contrato histórico F321 y su snapshot quedan sellados. Fuentes modificadas necesitan nueva revisión antes de una nueva acción física; no restaurar sólo para mejorar un status |

El cliente documentado **AELITA**, Windows y dirección histórica `192.168.1.63`,
demostró WPA2 2.4 GHz y WPA2/CCMP 802.11ac en 5 GHz el 05-09. Eso acredita
capacidad física anterior, no disponibilidad ni rutas de control hoy. Antes de
la campaña se debe comprobar SSH, perfil de restauración, interfaz, la ruta del
servidor de 32 MiB y el watchdog del cliente. La dirección histórica del
controlador `192.168.1.43:8008` es una entrada a validar, no un endpoint vivo
deducido de los scripts. No se necesita publicar contraseñas o MAC de clientes.

## Orden de ejecución propuesto

1. Cerrar el perfil F321 de los runners y la preflight de cliente/servidor;
   hacer primero visibilidad y tráfico corto de ambas bandas sobre la imagen
   instalada, preservando la gestión y restauración de AELITA.
2. Validar navegador real y controles materiales de UI; después soak acotado y
   campaña de arranques en frío, sin confundir una con otra.
3. Llevar F322 desde reproducibilidad offline a su campaña desarmada y después
   a adquisición shadow. No adelantar autoridad DFS, CAC ni TPC.
4. Resolver por campañas distintas el backend de persistencia y la recuperación
   que exige la definición final; conservar el fallo de mtd3 y el alcance real
   del rescate F314. Validar después botones/reset persistente y demás paridad.
5. Emitir aceptación final sólo cuando cada requisito aplicable tenga pruebas
   correlacionadas con la imagen final. Ni la UI, ni un análisis de seguridad,
   ni un manifiesto reproducible reemplazan estos ensayos físicos.

## Ajuste pequeño propuesto para el audit histórico

`tools/audit_lyoko_full_liberation.py` **no se modifica en esta tarea**. Su campo
`installed_firmware` deduce F319 del último gate F319 aceptado, aunque su scope
advierte que no consulta posteriores imágenes o rollbacks. El informe fijo
`outputs/audit/lyoko-full-liberation-20260905.json` no debe usarse como estado
actual del equipo.

Una actualización acotada podría:

- Renombrar ese campo a `last_accepted_legacy_probe_firmware` y mantener F319
  con su fecha/alcance; evitar que parezca una lectura viva.
- Aceptar explícitamente un `--acceptance-record` F321, verificar schema,
  candidata, snapshot y hashes de la evidencia con el reconciliador existente,
  y añadir `last_accepted_firmware_record` con versión, fecha y alcance. La
  ausencia o fallo de ese documento debe producir `UNKNOWN`, nunca inferir
  que F319 vuelve a estar instalado.
- Añadir el hito UI/gestión F321 como aceptación acotada; conservar DFS,
  persistencia, mtd3 y validación final pendientes, con `overall_status=IN_PROGRESS`.
- Escribir un snapshot nuevo con timestamp; conservar los informes anteriores
  y no reetiquetar sus resultados ni los manifests de candidatos.

## Evidencia consultada

Todas las rutas sin unidad parten de `/workspace/user-home\Desktop\MitraStar`.
Los JSON fuente conservan sus timestamps originales, algunos expresados con
offset `+02:00`; las horas resumidas arriba se normalizan a UTC.

| ID | Fuente local | Fecha / límite |
| --- | --- | --- |
| E01 | `outputs/postflash/f321-acceptance-20260911T091500Z/result.json` | 11-09; SHA-256 `7795bda97bc87e597677b779715bc0acede2e78ddbdd6fee370a376ce09f8f21`; reconciliación file-only, no nueva prueba física |
| E02 | `outputs/postflash/f321-independent-20260911T091309Z/platform/status.json`, `outputs/postflash/f321-independent-20260911T091309Z/ui/result.json`, `outputs/postflash/f321-independent-20260911T091309Z/authenticated-http/result.json` | 11-09 09:13 UTC; alcance exacto de checks en cada JSON |
| E03 | `docs/OPENMITRASTAR_F314_CURRENT_STATE.md`; `outputs/f3-certification/f314-5g-aelita-traffic-20260905/result-20260905T112942Z.json`; `outputs/flash-watch/f314-detached-watchdog-20260905T100618Z/qtn-control-matrix/result-20260905T112006Z.json` | 05-09; F314 histórico, no F321 actual |
| E04 | `outputs/f3-certification/f314-realtek-2g-20260905/summary.json` | 05-09 11:30-11:31 UTC; ambos sentidos y router health PASS |
| E05 | `outputs/recovery/f319-f314-rehearsal-detached-20260907T111355Z/run/result.json` | 07-09; `PASS_F314_RESTORE_WITHOUT_SSH_IN_BOOTBASE`, límites de hard halt/erase parcial conservados |
| E06 | `outputs/recovery/mtd3-current-evidence-20260901/result.json` | 01-09; fallo de montaje, `recovery_ready=false` |
| E07 | `outputs/soak/f301-soak-chain-final-20260904T191917Z/summary.json`, `outputs/soak/f301-soak-chain-final-20260904T191917Z/summary.md` | 04-09; F301, 34 ciclos, 22,101.813 s activos y tres fallos recuperados del harness |
| E08 | `docs/OPENMITRASTAR_F321_CLASSIC_UI_CANDIDATE.md`, `docs/OPENMITRASTAR_LYOKO_UI_RESTORATION.md`; `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/rootfs-inventory.json` | Paquete/build 07-09; evidencia de instalación 07/08-09 y postchecks 11-09. El inventario identifica cambios de UI y preserva 430 entradas |
| E09 | `docs/OPENMITRASTAR_F322_SHADOW_CANDIDATE.md`; `outputs/preflight/f322-shadow-repro-20260908T000424Z/result.json` | 08-09; `OFFLINE_REPRODUCIBLE_PASS_NO_GO_PHYSICAL` |
| E10 | `outputs/preflight/f319-runtime-probe-20260907T192754Z/result.json`; `docs/OPENMITRASTAR_F319_SPI_OWNER_PROBE.md` | 07-09 19:29 UTC; claim/map/unload, cero accesos |
| E11 | `docs/HGW500_LED_CONTROL.md`; `docs/OPENMITRASTAR_FRONTPANEL_LED_GATE.md` | Observaciones 21/22-08 y gate histórico; no sweep F321 nuevo |
| E12 | `docs/HGW500_OEM_BUTTON_LED_CONTRACT_20260821.md`; `docs/HGW500_Q1_CONTROLS_PARITY_20260820.md` | Contrato 20/21-08 y límites de actuación física pendientes |
| E13 | `docs/HGW500BNA_QCV2_OEM_MOVISTAR_PARITY_MATRIX.md` | Corte OEM 18-08; referencia de alcance, no dashboard de estado actual |
| E14 | `docs/LYOKO_NETWORK_CERTIFICATION.md`; `docs/OPENMITRASTAR_F301_VLAN_GATE.md` | Topología y contratos históricos; no ejecución F321 inferida |
| E15 | `outputs/flash-watch/f320-promotion-detached-20260907T210022594Z/run/result.json`; subdirectorios `f320-install`, `postflash-f320`, `runtime`, `f314-restore` y `postrestore-f314` del mismo ciclo | 07-09: instalación/readback PASS 21:04:54 UTC, plataforma F320 PASS 21:05:07, intento de sonda no aceptado, restauración exacta F314 PASS 21:09:24 y plataforma PASS 21:09:37 |

Los documentos antiguos de operaciones y reverse engineering contienen
baselines F137/F170 o afirmaciones anteriores al port real. Se usan para
localizar contratos y herramientas, no para declarar instalado ese firmware
ni para ignorar evidencia posterior. El encabezado offline/no-run de
`docs/OPENMITRASTAR_F320_SPI_CONTROL_READ.md` también es anterior al intento
físico E15; no prevalece sobre sus resultados conservados. Rigen `AGENTS.md`, la misión actual y la
evidencia fechada del artefacto elegido. Esta matriz tampoco autoriza por sí
misma abrir COM3, cambiar radios, cortar alimentación o escribir flash.
