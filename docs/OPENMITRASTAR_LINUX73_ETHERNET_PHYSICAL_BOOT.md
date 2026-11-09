# Linux 7.3 Ethernet — arranque y tráfico físico aceptados

22 de octubre de 2026, aproximadamente 16:57 UTC / 18:57 Madrid.
Target único: HGW-500BNA-QCv2 A2.

**PASS: Linux `7.3.0-openmitrastar-eth73-v1` arranca en RAM, carga EMAC
y pasa ping y 12/12 ecos UDP entre el PC y eth0.** No se ha escrito flash
ni bootenv. El kernel de diagnóstico queda en RAM con eth0 activo y eth1
bajado. SSH no está incluido en este initramfs; UART sigue siendo el control.

## Artefacto probado

RAS sin compresión: `outputs/rea/movistar-port-20261022T1327175411798Z/eth73-ram-artifact-v3/eth73-RAM-ONLY.ras.bin`.

- 3.052.800 bytes; SHA256
  `513dc8d0a23e9aa8c8c1be90c2e9da090a4fae483ff6bbe20c836579f04e31b4`.
- CRC32 completo observado en Bootbase: `b6fdc394`.
- Payload: 3.044.608 bytes, SHA256
  `0475d6daf7a1c17a898021f241bb384b4ea642927b2ac7f1d97694832ac90ffd`.
- LOAD `0x8493a000`, ENTRY `0x84940000`, sttext `0x84940008`,
  kernel end `0x84c54000`, DDR final `0x88000000`.
- ELF: 4.463.340 bytes, SHA256
  `b6d391e8799201139e21ee514b34f0905ca4e7611621cd6c41bb93420bd55c1a`.
- PID1 syscall-only: 4.180 bytes, SHA256
  `541e99008a4ec2c5328095aaac3cdbc5f885b815f9e51405c280abcc8bdc8376`.
- EMAC SHA256
  `067f040165348edcdc3d125cf284f6921802cc3590909df9fe3772c0b9adf798`.

Dos compilaciones sobre copias nuevas de la baseline Ethernet coinciden
en ELF/config/DTB/raw/RAS. El driver es el módulo offline ya compilado
dos veces. Se verificaron init y módulo desde el CPIO incrustado en el ELF.
La nueva imagen activa DT y aplica la identidad del firmware privado de la
unidad; no imprime esa identidad ni la incorpora a fuentes compartidas.
No publica DT personalizado, ELF o firmware. La entrada cambió una página
por el tamaño mayor del initramfs; la cabecera se deriva del ELF nuevo.

## Ensayo físico y límites

COM4/FTDIAG41W2BL, guard exclusivo y receptor UART continuo. Antes de
esta campaña BASIC tenía nonce fresco y uptime3365.11. El primer encendido
manual perdió la ventana de Bootbase; el F367r9 conservado volvió a SSH
autenticado, boot `d7c2e443-1c42-4396-a1c1-5098435e7c09`, watchdog00000000.
Eso prueba un retorno a F367r9 tras BASIC; no prueba mtd3/linux_safety.

El usuario ordenó integración y prueba física y concedió autorización
total del port el22-10-2026. Esa autorización se conserva: no repetir
preguntas de permiso para las mismas acciones del target. Las comprobaciones
de artefacto y las particiones protegidas siguen vigentes.

Los intentos v1-v5 están preservados como fallos del host/transferencia.
Ninguno ejecutó bootm ETH73 ni flash. Se corrigió el lanzamiento de
PowerShell entre bytes/control YMODEM; el padre mantiene el lease y sus
checks, mientras RX/TX no bloquean el diálogo. v6 recibió 3.052.800bytes,
filesize2E9500/iminfo/CRC exacto y un único bootm a84940000.

Evidencia v6:

- Linux7.3/markerPID1/nonce input nuevo recibidos por UART.
- Memtest1MiB con dos patrones PASS; no memoria completa/caché proof.
- ETHLOAD=0 y módulo Live.
- eth0up/down, eth1up/down y reaperturaeth0 retornan0.
- Ping3peticiones PASS; el recibo registra el booleano validado por exit0
  y TTL.12payloadsUDP enviados desdePC.49 aHGW.90:9009 vuelven exactos.
- El HGW informa UDP_RECEIVED=12 y UDP_ECHOED=12.
- IRQ20 eth0:9→104; Timer0:2530→4540; UART16:64→221.
- eth0 RX1422bytes/13packets→8123bytes/84packets; TX0→1292bytes/17packets.
  ErroresRX/TX0; dropsRX1→3. No adjudicar esos drops a fallo sin más evidencia.
- Stats final:104NAPI,87RXwork,17TXdone; poll_napi_schedules0,
  poll_forced_napi0, RXrestart0 y quiescetimeouts0 en el intervalo capturado.
- Uptime3.37→49.49. No crash/timeout del ejecutor durante esta aceptación.

Una comprobación posterior, 17:01:33–17:02:03 UTC, recibió31/31pings
TTL64 durante30segundos, sin abrir UART ni reiniciar. Es continuidad
ICMP acotada, no soak largo. Recibo:
`outputs/rea/movistar-port-20261022T1327175411798Z/eth73-continuity-20261022T170100Z/result.json`.

El resultado acredita tráfico por eth0/MAC1/PHY3/hwirq20 con el conector
actual. eth1 sólo tiene aceptación de apertura/cierre; su conector y tráfico
no se probaron. No aceptar dual bridge, radio, SSH, persistencia, soak largo,
regulatorio, falloDMAreal o recoverymtd3 por este resultado.
Quarantine de timeout sigue reteniendo memoria y rechazando reopen; no
constituye recuperación por reset de un DMA bloqueado.

## Evidencias reproducibles

`outputs/rea/movistar-port-20261022T1327175411798Z/eth73-physical-trial-v6/`:
`result.json`, `uart-redacted.txt`, `network-counters.json`,
`ymodem-control-events.json`, `transfer-timing.jsonl`, `READY_POWER_CYCLE.json`.
`eth73-ram-artifact-v3/BUILD_RESULT.json` y `CONFIG.json` conservan identidad.
No rawUART, credenciales, PSKs o calibración se guardaron en estos logs.
El lease salió y UART fue liberada después del ensayo.

Fuentes/receta: `work/kernel-port/linux-7.3-ethernet-ram/`.
Antes de cambios físicos siguientes, registrar versión/artifact/acción
y comprobar el estado de esta unidad; no tratar el estado aquí como eterno.
El primer paso posterior es tráfico sostenido y segundo conector, sin
perder la aceptación del kernel/MMU/UART ya obtenida.
