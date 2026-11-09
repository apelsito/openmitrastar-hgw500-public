# Linux 7.3 BASIC: UART-first HGW500 bring-up

> Public source snapshot. [Scope, provenance and verification](docs/PUBLIC_SNAPSHOT.md).

Primer objetivo acordado: arrancar Linux 7.3 y llegar a PID1 interactivo por
UART. El candidato incorpora CPU750D/MMUv2/caché, RAM, IRQ, timers y UART.
Realtek, Quantenna, Ethernet, PCI, MTD y watchdog están desactivados.

## Estado verificado el 22 de octubre de 2026

El hito físico se aceptó a las 15:35 UTC: Linux
`7.3.0-openmitrastar-basic73`, PID1 y nonce UART nuevo; avance de uptime,
Timer0 y UART; memtest de 1 MiB con dos patrones PASS. RAM-only, sin flash
ni bootenv persistente. Véase `docs/OPENMITRASTAR_LINUX73_BASIC_BOOT.md`
en el workspace y `PHYSICAL_BOOT_RESULT.json` en el repositorio privado.
Las notas de prueba pendiente inferiores describen la preparación histórica.

- BUILD_PASS, dos compilaciones completas con kernel/config/DT/initramfs idénticos.
- Kernel SHA256: `6c13ee940002b1e4512624e676cc158bc4dd3a51f7299592281fac52b39db220`.
- ELF2.418.080bytes; payload raw1.958.208bytes.
- RAS seleccionado para prueba RAM sin compresión: 1.966.400 bytes,
  SHA256 `24a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb`,
  CRC32 `0f700813`.
- Sin símbolos sin resolver; cero instrucciones SWAPE/LLOCK/SCOND en kernel.
- Entry `0x8493e000`, res_service salta a stext `0x8493e008`.
- Carga `0x8493a000`; end `0x84b48000`; RAM final `0x88000000`.
- Bootbase header/payload CRC y empaquetado sin compresión pasan offline.
  La variante LZMA v6 queda descartada para este ensayo por la discrepancia
  entre decodificadores ante tamaño conocido y marcador final.
- PID1 syscall-only2344bytes, SHA256
  `9380f5c7b85231ae9320fc70b7b6a922316978c61f69d473907271168ca36194`.
- API espera time64 syscall407; función kernel presente; número407 confirmado
  en ensamblador. libc estática quedó excluida porque contenía LL/SC.
- Consola earlycon conserva divisor Bootbase; consola normal DT125MHz.
- Fuente compuesta modifica16archivos de Linux upstream.
- UART/input/tick/memtest físico: PASS. Recovery físico de esta prueba: UNRUN.

El boot físico acredita el primer hito; persistencia, retorno manual y soak
no están aceptados. La igualdad offline, por sí sola, no prueba arranque.

## Insumos y reproducción

Upstream `v7.3`, commit
`c03c1a14507dfaf8b856c2608f9ac216021fc222`.
Tarball SHA256
`87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953`.

`basic73.patch` SHA256
`d36ed090cdcb9470eb301933c066b2c7cde12de3af5c1cf3d02d9a7509088192`.
Se aplica sin fuzz a upstream. `overlay/` y `SOURCE_MANIFEST.json` retienen
los16archivos finales. `basic73.config.template` permite solo la sustitución
de ruta `@INITRAMFS_LIST@`. La receta conserva el perfil resolvedUP y
PREEMPT_VOLUNTARY, sin preemption forzosa; no lo presenta como PREEMPT_NONE.

`build.py` trabaja en Linux/WSL, requiere tarball y toolchain explícitos,
crea un directorio nuevo y ejecuta dos builds. Plan sin escribir:

La receta conserva el basename original de PID1 antes de compilar; ELF
incluye ese nombre en `STT_FILE`. Sin él, cambia el hash de la tabla de
símbolos aunque `.text` y `.rodata` coincidan. Ahora exige el hash aceptado.

```sh
python3 build.py --archive /path/linux-7.3.tar.xz --toolchain /path/arc-toolchain --output /path/new-build --plan-only
```

El kernel mínimo no usa el árbol completo históricoF358. Este nuevo candidato
se reconstruye desde upstream7.3 y overlay. El repoRealtek conserva la
baseline5.10 y añade esta fase de plataforma sin modificar el driver original.

`pack_ram.py` regenera el artefacto RAM exacto desde el ELF sellado y una
plantilla OEM local indicada explícitamente. Verifica hashes, secciones ELF,
entry, RAM e initramfs/PID1; no ejecuta código ni modifica sus entradas.
`--check-only` calcula y verifica el resultado sin escribirlo. La regeneración
del ELF v6 produce el RAS v7 con SHA256 idéntico. Las seis comprobaciones
offline incluyen rechazo de corrupción y direcciones fuera de RAM.

## Prueba física pendiente

Ruta prevista: UART FTDIAG41W2BL/COM4, captura continua, binding a SSH
autenticadoF367r9, un reboot autorizado a Bootbase, lectura fresh de bootcmd
y bootselect, RAM loadYMODEM `0x83000000`, filesize/iminfo/CRC scratch
`0x84000000`, una sola entradaBootbase al kernel. No TFTP ni flash.

Se comprobarán:
1. Linux7.3 visible en salida nueva.
2. Marker `OPENMITRASTAR_BASIC73_PID1_REACHED` y prompt.
3. `echo TOKEN` devuelve `BASIC73_NONCE=TOKEN` exacto.
4. `status` y uptime creciente prueban que el kernel sigue vivo.
5. `interrupts` acredita ticks/inputUART.
6. `memtest` ejecuta dos patrones1MiB del propioBSS dePID1.

Un panic/hang detiene el intento; el candidato no lleva watchdog. Powercycle
manual pierdeRAM y debería volver al F367r9 persistido solo siBootbase sigue
en bootcmd=bootselect/bootselect=0. Leer y verificar ese estado antes debootm.
mtd3/linux_safety no es recuperación probada. No tocar bootenv ni particiones
protegidas. Reboot también descarta Doom/paquete5GHz activos enRAM.

El executor y la autorización del artefacto/acción se revisan aparte.
Ningún script de esta carpeta abre UART, reinicia ni escribe firmware.

`audit_bootbase_ram.py` contrasta una traza estática finita del cargador OEM
con los archivos locales que se le indiquen. El dump, binario decodificado,
ensamblador e imagen deben coincidir con sus hashes. La traza confirma
payload RAS en +0x2000, copia de la imagen sin compresión y salto al entry.
No ejecuta Bootbase ni demuestra un boot.

