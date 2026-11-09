# Linux 7.3 BASIC: primer arranque por UART

Fecha: 22 de octubre de 2026. Target: HGW-500BNA-QCv2 A2.
El propietario ha limitado el primer hito al arranque básico. Se aparcan
Realtek, Quantenna, Ethernet y PCI hasta aceptar la consola UART.

## Primer hito físico aceptado — 22 de octubre, 15:35 UTC

**PASS: Linux 7.3 básico ha arrancado en el HGW físico y responde por UART.**
Se ha ejecutado el artefacto sin compresión de 1966400 bytes, SHA256
`24a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb`.
Bootbase verificó el CRC RAM `0f700813` antes del único `bootm`.

La salida recibió Linux `7.3.0-openmitrastar-basic73` y el marker de PID1.
Una segunda captura del mismo arranque confirmó un nonce nuevo, uptime
175.83 → 176.14 segundos, Timer0 IRQ3 17589 → 17608, y UART IRQ16
65 → 86. El memtest de 1 MiB con dos patrones pasó.

Resultado de boot:
`outputs/rea/movistar-port-20261022T1327175411798Z/basic73-ram-continuation-v6/run-20261022T1532411338729Z/result.json`.
Ese recibo conserva su STOP por el parser de IRQ; no fue un crash del kernel.
La aceptación final está separada en
`outputs/rea/movistar-port-20261022T1327175411798Z/basic73-uart-acceptance-v7/run-20261022T1535387076279Z/result.json`.

El kernel queda ejecutándose únicamente en RAM. No se han escrito flash ni
bootenv. Ethernet y radios no están incluidos. Persistencia, cold boot,
soak largo y retorno manual después de este boot 7.3 siguen pendientes.
No apagar ni reiniciar para un simple status check; se perdería este arranque.
El objetivo completo permanece abierto. Las secciones inferiores conservan
las comprobaciones y los requisitos anteriores al ensayo.

## Resultado actual

El artefacto elegido para el primer ensayo RAM es ahora **v7 sin compresión**:
1966400 bytes, SHA256
`24a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb`,
CRC32 `0f700813`. Conserva exactamente el kernel e initramfs v6. El formato
Bootbase pasa en Windows; evita la discrepancia entre decodificadores ante la
cabecera LZMA de tamaño conocido con marcador final. La variante LZMA v6 queda
preservada como NO_GO para este ensayo. No se ha eximido ninguna comprobación.
La revisión del executor v1 encontró gaps de watchdog/fatal UART/PnP. El v2
los corrige y ha pasado revisión independiente; se conserva el v1 como
evidencia histórica y no se usa para el ensayo.

El kernel `7.3.0-openmitrastar-basic73` construye con ARC750D, MMU v2,
páginas de 8 KiB, caché, dos timers ARC y UART0. Dos compilaciones independientes
tienen idénticos kernel, configuración, DT e initramfs.

El resultado offline fue **BUILD PASS**. El ensayo posterior arriba acredita
boot físico, input UART, ticks y memtest acotado. El port completo sigue abierto.

- Kernel ELF: 2418080 bytes, SHA256
  `6c13ee940002b1e4512624e676cc158bc4dd3a51f7299592281fac52b39db220`.
- RAS RAM-only seleccionado sin compresión: 1966400 bytes, SHA256
  `24a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb`.
- CRC32 del RAS: `0f700813`.
- LOAD `0x8493a000`; ENTRY `0x8493e000`; kernel end `0x84b48000`.
- Payload raw: 1958208 bytes; staging propuesto `0x83000000`.
- CRC scratch propuesto: `0x84000000`; DDR end `0x88000000`.
- Cero símbolos sin resolver y cero SWAPE/LLOCK/SCOND en el kernel emitido.
- Header CRC, payload CRC y reproducción del RAS sin compresión: PASS offline.
- La preparación offline no abrió UART ni reinició. El ensayo posterior
  autorizado utilizó COM4 y Bootbase; no escribió flash ni bootenv.

Artefacto local seleccionado:
`outputs/rea/movistar-port-20261022T1327175411798Z/basic73-offline-v7-uncompressed/basic73-RAM-ONLY-NO-GO.ras.bin`.

Evidencias:
`basic73-offline-v6/result.json`, `paired-build-v6.json`,
`basic73-init-contract-v2.json` y `basic73-source-v6/SOURCE_MANIFEST.json`
en el mismo directorio de investigación.

## Qué se ha recuperado

La serie modifica 16 archivos upstream y restablece:

1. Perfil ARC750D en UP; atomics existentes sin LL/SC.
2. Byte-swap software y flags explícitos sin SWAPE/LLSC.
3. Bits PTE v2, registros y comandos TLB, BCR v2 y errata uTLB.
4. Operaciones CDU de caché v2; cálculo de geometría después de leer su tamaño.
5. Plataforma y DT Topaz mínimos; UART0 child hwirq16 / parent hwirq24.
6. Consola 8250 OF clásica, sin sondeos DW fuera de la ventana `0x20`.
7. Earlycon sin baud explícito: conserva el divisor inicial de Bootbase.
8. PID1 de syscalls directos; espera time64 syscall407 y respuesta a nonce.

El PID1 mide 2344 bytes. La libc estática descartada contenía LL/SC; no se usa
en el candidato final. La API time32 también se descartó: syscall101 era un
stub con `COMPAT_32BIT_TIME=n`. El syscall407 está presente y se observa
`mov r8,407` antes de trap0 en la assembly final.

Comandos de la consola: help, status, cpuinfo, interrupts, meminfo, memtest,
`echo TOKEN`. El token admite caracteres alfanuméricos y guion. Memtest
ejercita 1 MiB del BSS propio de PID1 con dos patrones; no es una prueba de toda
la RAM ni de coherencia DMA.

## Fuente y reproducción

Fuente upstream: v7.3, commit `c03c1a14507dfaf8b856c2608f9ac216021fc222`.
Archive SHA256:
`87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953`.

Fuentes, patch, plantilla de config y receta en
`work/kernel-port/linux-7.3-basic/`. El patch completo se aplica sin fuzz.
La receta Linux/WSL recibe archive/toolchain/output explícitos y exige un
directorio nuevo. `--plan-only` comprueba inputs sin construir ni acceder
a hardware.

La rama privada `port/linux-7.3` del repo Realtek conserva este soporte de
plataforma bajo `kernel/basic-linux-7.3/`. main, los originales y la baseline
5.10 permanecen separados. El driver 7.3 no está integrado en BASIC.

## Baseline físico y retorno

Lectura SSH autenticada el 22 de octubre a las 14:26 UTC: mismo boot
`5f513265-a294-4366-9567-e1d8af704b6b`, F367r9 y Linux5.10.260.
CPU family0x33, 500 MHz, MMUv2/8KiB/JTLB128x2, I-cache16KiB/2ways,
D-cache16KiB/4ways, líneas32B. Esa geometría no activa aliasing VIPT.
El reloj UART125MHz sigue siendo contrato histórico de DT, no medición nueva.

FTDIAG41W2BL aparece como COM4. Enumerarlo no abre el puerto ni demuestra
binding físico al HGW. Los viejos defaultsCOM3 no se reutilizan.

El retorno previsto de una prueba RAM es power-cycle manual al slot persistido
mtd4, condicionado a verificar en Bootbase `bootcmd=bootselect` y
`bootselect=0` antes del handoff. No se cambia ni se guarda bootenv.
mtd3/linux_safety no constituye recuperación probada. Reboot/power-cycle
descarta Doom y el paquete activo de 5 GHz que están en RAM.

## Gate pendiente

El executor v2 ha pasado revisión independiente sobre el manifiesto de fuentes
SHA256 `725215ffca1ac64afa2260d337e78cf9f13729b958e52a3785d863702fe96348`.
Las 22 pruebas simuladas y los casos independientes de watchdog, fatal UART,
lease y cola de RX pasan. El preflight real del archivo v7 sin compresión pasa
en Windows. Recibo: `outputs/rea/movistar-port-20261022T1327175411798Z/basic73-independent-executor-review-v2/REVIEW.json`.
El siguiente paso requiere autorización exacta de un único reinicio y ensayo
RAM con COM4, más aceptación de la contingencia manual. Boot físico UNRUN.

Preparar y revisar un executor para una única prueba con:

- Binding entre SSH autenticado y UART mediante nonce y lease exclusiva.
- Entrada controlada a Bootbase tras un reboot autorizado.
- Lecturas frescas de ruta de boot, legacy map y watchdog inactivo.
- Una transferencia RAM YMODEM; filesize, iminfo y CRC exactos antes de bootm.
- Captura continua; identidad Linux7.3, PID1, prompt y nonce de input nuevo.
- Uptime/tick UART y memtest acotado.
- Fail-stop y power-cycle manual si se cuelga; sin reintento automático.
- Ninguna escritura flash, TFTP, bootenv persistente o uso del loader OEM
  antiguo sin quiesce.

La autoridad específica del artefacto y las acciones físicas se resuelve antes
de abrir UART/reiniciar. No se deriva de la compilación ni del hash.

## Contraste estático del cargador OEM

El binario Bootbase decodificado coincide con el LZMA contenido en el mtd0
original verificado. Su SHA256 es
`20ab45412b973478aa49a3daa31851a49f0deeaa09d07213479b0c3ee7af5f07`.
La traza acotada de su ensamblador confirma la selección de payload en
cabecera+0x2000 para imagen kernel y la rama de copia para compresión cero.
El dispatch Linux apunta a `0x8802cbc4`; la secuencia final toma el entry
del header y transfiere el control mediante un salto indirecto.

Para el candidato seleccionado, el rango de origen es
`0x83002000..0x831e0140`, y el destino `0x8493a000..0x84b18140`.
No se superponen con el scratch CRC `0x84000000`. Esto confirma coherencia
estática del formato y los intervalos; no ejecuta el cargador ni demuestra
caché, estado heredado, consola, temporizadores o retorno físico.

Evidencia: `outputs/rea/movistar-port-20261022T1327175411798Z/bootbase-static-ram-trace-20261022T150400Z/result.json`.
El auditor `work/kernel-port/linux-7.3-basic/audit_bootbase_ram.py` recibe todos
los archivos explícitamente y rechaza cambios de identidad en dump, binario
decodificado, ensamblador o imagen RAM. Las cinco comprobaciones pasan.

