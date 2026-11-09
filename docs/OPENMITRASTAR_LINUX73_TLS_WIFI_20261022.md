# Linux 7.3: evidencia física de TLS, Wi-Fi, LYOKO y Doom

El objetivo completo continúa abierto: ambos Ethernet, 2,4/5 GHz, gestión
segura, Doom con música y controles, persistencia, soak y recuperación.
Limpieza y migración de AELITA están pospuestas.

Actualización del23octubre00:15CEST: eth0 pasaGET/POST65536TLS1.2/1.3 en v47,
con el cable movido y eth1 DOWN; eth1 ya había pasado por separado. El servidor
web corregido v42 entrega application/wasm; Doom y sesiónLYOKO vuelven a pasar
v43, sin fallback ni descarga duplicada. El uploader temporal se retiró v44.
v39terminóconAUTH/ASSOC/AUTHORIZED y segunda campañaTLS+restauraciónAELITA.
Prioridad indicada: radios2,4/5GHz; versiones/tamaños detallados en
OPENMITRASTAR_VERSIONES_TAMANOS_20261023.md. Las secciones inferiores conservan
la evidencia y límites de sus etapas anteriores.

Imagen aceptada en RAM: `radioeth73-events-RAM-ONLY.ras.bin`, 6.980.384 bytes,
SHA-256 `9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e`,
CRC32 físico `9657f794`. Kernel `7.3.0-openmitrastar-radio73-v1`.
v15 acredita YMODEM completo, contrato Bootbase, mapa/watchdog antes de un
único bootm, PID1, nonce, memtest, usuarios actuales y los 19 módulos Realtek.

## Resultados físicos

| Gate | Resultado y límite |
| --- | --- |
| eth1 TLS | GET y POST de65.536bytes exactos conTLS1.2/1.3; certificado y digest verificados. eth0 de esta imagen pendiente. |
| Wi-Fi 2,4GHz | AELITAv16: WPA2-Personal/canal1 y cuatro GET/POSTTLS1.2/1.3PASS. Router wlan0RX158556/TX170074bytes. |
| Autorización cliente | v39observa `[AUTH][ASSOC][AUTHORIZED][WMM][HT]`,wpa2 y contadores durante segunda campañaTLS; resultado final verificar. |
| LYOKO HTTPS | v28PASSlogin,Secure/HttpOnly/SameSiteStrictcookie,dashboard,API sesión/frontend,logout e invalidación. Configuración mutable y navegador completo pendientes. |
| Doom | v35PASSbrowserreal HTTPS: episodiooriginal,movimiento,disparo,táctil,audioPCM,música activada; sinrequests externos/WebSockets. Router sirveassets; juegoejecutaencliente. |
| SSH | v38PASSDropbear2026.94,ownerEd25519publickey,hostidentitypinned y comandoreadonlyLinux7.3. |
| Persistencia | CEROflash/bootenvwrites. RAMdiagnóstico,NOreleasepersistente. F367r9/protegidas/storeconservados; rollbackmtd3físicopendiente. |

Evidencia común: `outputs/rea/movistar-port-20261022T1327175411798Z/`.
Arranque: `radioeth73-events-physical-powercycle-v15/`.
TráficoEthernet: `radioeth73-events-https-upload-v20/`.
AP: `radioeth73-events-ap-v21/`; cliente inicial:
`work/aelita-preparation-20261022/wifi-tls-traffic-v16.json`.
SesiónLYOKO: `radioeth73-lyoko-auth-v28/`.
SSH: `dropbear73-ssh-v38/`.
Doomupload12assets: `outputs/doom/linux73-https-upload-v34/`.
Doombrowser/capturas: `outputs/doom/linux73-https-browser-v35/`.

## Correcciones y límites

EPOLL ausente causaba espera inválida y consumo CPU de uhttpd. Imagen events
habilita EPOLL/SIGNALFD/TIMERFD/EVENTFD con todos los archivos/módulos/DT iguales.
La prueba física confirma eventpoll y tráfico TLS. CredencialCRLF->LF
normalizada conservando64dígitos y permisos; no se cambió contraseña.
BINFMT_SCRIPT sigue desactivado: uhttpd usa configuración explícita de
intérprete para rutas API. Siguiente imagen debe integrar ese soporte.

UARTshell perdía líneas largas con diagnóstico/echo: consola quiet y escritura
de8bytes/20ms permitieron continuar. STOPs y errores previos permanecen
inmutables; no relabelar los recibos de lanzamiento como aceptación del gate.

DropbearSIGBUS capturado porptrace:BUS_ADRALN,dirección4000a5ce/PC20002740,
R_ARC_RELATIVE sobre literal de arranque. Cambiar linker-only-Wl,-pie porGCC-pie
seleccionaScrt1correcto;71objetos exactos,x2relocacionesalineadas,239628bytesSHA
23026d9cabd53cab1d9b7c5a78ef5c5be0e6842b7a81a1696af9949bf5974da0.
v36versionPASSpero-E/-snoexistenenbuildsinSyslog/passwordauth;v37flagscorrectos
y v38SSHfísicoPASS. No se habilitóemulacióndealineación.

Doom conservaZIPoriginal,fuentegzip,licencias,músicaoriginalyparchefuente.
WASMeb47045e...c20e/index5c8c0c99...facc exactos. ChromiumconfíaporSPKIespecífico;
noignore-allcertificates. MIMEwasmincorrectoproducefallbackArrayBufferysegunda
descarga; funciona,perooptimizaciónpendiente. PCMconmúsica/sfxsimultáneosno
es nueva aislaciónpista1/pista2;pruebaaisladahistóricaeraenHTTP5.10.

ResetBASIC7.3detieneCPU. SecuenciaTopaz5.10recuperadaenimagenseparada,x2
6980384bytesSHAa41505007c27e9b713ca23a487dbdefcd60312f7a3d9db8ad89535e168a75a0f,
95986archivoscomparados,soloreset.cdistinto,fixture6writes/barrera+3negativosPASS.
No cargada: reiniciofísicopendiente.

Quantenna5GHzsurveyv5:53/53Cunitscompilan contra kernel7.3reconstruidocon
layoutpaquetes/WEXT/I2C/GPIO/APIadaptadas. QDRV/WLANobjetoslinkPASS,
peroancillary/plataforma/HBM/TQE,exports/ABI/fixturessemánticos/radio/clientes
siguenpendientes. Todoslosdriversdebenrecompilarsejuntosconlayoutnuevo;
no cargarmódulos5.10niobjetossurveyenlaunidad.

Tamaño completo persistente sigue pendiente: co-pack previo6.955.008bytesXZ1MiB
excedíaventanarootfs4.587.520yfaltabacompletitud5GHz/control. Cola store y
protegidas no son espacio disponible. No flashear esta imagen RAM.
