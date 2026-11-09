# Linux 7.3 y software actual: integración offline del 22 de octubre de 2026

El objetivo mantiene la interfaz de configuración estilo Movistar/LYOKO y
renueva sus componentes internos. Web exclusivamente HTTPS con TLS actual,
SSH moderno permitido y requerido. No abrir HTTP, TFTP o Telnet. La carga RAM
sigue por UART/YMODEM. OEM y recuperación se conservan en sus particiones;
firmware interno de radio y calibración siguen siendo dependencias físicas.

El propietario ha autorizado probar los dos conectores Ethernet y 2,4 GHz y
flashear la imagen completa aceptada. La autorización no elimina los contratos
de imagen exacta, geometría, readback de protegidas/store y rollback. Doom con
música original, controles táctiles/inglés y las demás funciones deben caber
en el conjunto final; una variante RAM sin esos recursos no es el release.

## Resultados nuevos, todavía sin ejecución física

Evidencias locales copiadas bajo
`../outputs/rea/movistar-port-20261022T1327175411798Z/current-userland-offline-20261022T1919Z/`.

| Componente | Resultado offline |
| --- | --- |
| Linux 7.3 + PCIe/Realtek | Kernel y 19 módulos en dos builds iguales, imports resueltos, sin SWAPE/LLOCK/SCOND. ELF 5029296 bytes, SHA b13f22156a871719b7a713a8fef614b67f37687596995d919940f48e4b252cd8. |
| libc uClibc-ng 1.0.59 | Shared/static sin LLOCK/SCOND, kernel-assisted cmpxchg; EN/ES/UTF-8, C99math, utmp y netlink/resolver para herramientas completas. Shared 534536 bytes, loader 25572. |
| BusyBox 1.38.0 | Build con herramientas amplias y sin listeners HTTP/TFTP/Telnet; 984332 bytes, dinámico, sin instrucciones prohibidas. Release upstream de pruebas; todavía requiere ejecución de applets/scripts. |
| Dropbear 2026.94 | 239624 bytes, autenticación por clave, primitivas antiguas desactivadas, sin instrucciones prohibidas. Negociación física pendiente. |
| hostapd 2.12 | 628288 bytes, backend wolfSSL, WPA2/WPA3/OWE/WPS compilados; ninguna asociación ni WPS ejecutada. |
| iw 6.17 | 199020 bytes, libnl-tiny, compilado sin instrucciones prohibidas. |
| uhttpd de 2026-10-19 | Build ARC actual, CGI y HTTPS; adaptación X-OM-CSRF para contrato LYOKO. TLS/CGI físico pendiente. |
| wolfSSL 5.9.4 | Perfil combinado web/WPA con TLSX y RFC5746 indication; 946612 bytes, sin instrucciones prohibidas. TLS 1.2/1.3 y rechazo de versiones antiguas pendientes de ensayo. |
| Ethernet MAC-init + diagnóstico TX | Dos módulos iguales de 27808 bytes, 80 imports; nueva inicialización OEM local y diagnóstico pasivo, tests previos aprobados. Recuperación eth1 física pendiente. |

El kernel añade COMPAT_32BIT_TIME/POSIX_TIMERS porque los binarios de usuario
necesitan esas llamadas; el BASIC sólo usaba syscalls time64 directos. CMAC
se añade como módulo. CPU750D, MMUv2/8KiB, UP y ausencia de LLOCK/SCOND se
mantienen. DT conserva identidad Ethernet del propietario sólo en build privado.

La libc anterior del toolchain introducía 26 instrucciones LLOCK/SCOND incluso
en un hello. Se reconstruyó con CONFIG_ARC_HAS_ATOMICS desactivado. Los locales
del host de build estaban ausentes: se generaron en una ruta aislada y se
ejecutó locale_headers serialmente bajo make4.3. No se eliminaron ES ni UTF-8.
Los intentos fallidos y sus logs se conservan. La dependencia añadida a gen_ldc
no solucionaba la causa y se revirtió. C99math corrige el enlace __signbit.

libubox actual usa helpers __atomic_fetch_and_4/__atomic_fetch_or_4. La libatomic
del toolchain contenía 100 instrucciones prohibidas. Un adaptador limitado a
32 bits/UP utiliza el mismo syscall arc_usr_cmpxchg y barreras SYNC. Fixture
compilada de los bucles reales: 360033 checks y 320000 operaciones concurrentes
con CAS host; backend ARC compila sin imports/instrucciones prohibidas. Esto
no prueba el syscall en la placa. No usar como atomics SMP.

REA inspect_binary_layout rechazó hostapd ARC32 porque ese perfil sólo acepta
ELF64 little-endian. Se continuó con readelf/objdump/nm del toolchain exacto;
no se presenta el rechazo como análisis REA aprobado.

## RAM y producto final

La imagen RAM nueva está en preparación con kernel, Ethernet, Realtek, firmware,
regdb firmado verificado con certificado compilado, programas actuales y
consola de diagnóstico. Carga radio/AP/HTTPS/SSH explícita, sin autostart radio.
Usa una clave/certificado TLS de laboratorio y configuración WPA2 privada.
No es una imagen flash de producto y todavía no ha arrancado físicamente.

La preparación detectó falta de memcpy en PID1 y una incompatibilidad de símbolo
TLSX entre perfil web y WPA. Ambas se corrigieron antes de generar imagen;
se valida la resolución completa de imports de usuario y las bibliotecas
packaged. Cada intento mantiene su resultado separado.

Los archivos se construyen en
`/home/rea/openmitrastar-linux73-20261022T135100Z/` dentro de REA-Linux. Sources
y recetas nuevas están en `../work/kernel-port/linux-7.3-radioeth-ram-v1/`.
No hubo apertura UART, reinicio, cambio radio, flash ni bootenv en este trabajo.

## Doom y SquashFS

Configuración histórica probada: SquashFS XZ/128KiB, con rootfs read-only y
runtime writable en RAM. F373 combinado daba 7782400 bytes, excediendo la
ventana histórica 4587520 bytes. El firmware prefix permitido es 6160384 bytes;
la cola store dentro de mtd4 se conserva. No utilizar mtd3/mtd5 o mtd6 lógico
como espacio extra.

Se midió orientativamente el WAD original extraído: XZ 1360580 bytes frente
al ZIP redistribuido de 2450688. El contenido fuente agregado tiene potencial
de otra compresión, pero esto aún no es un co-pack ni una nueva equivalencia
validada de la entrega. Mantener archivo original íntegro, licencias, fuentes,
música y controles; medir la imagen completa y ejecutar el navegador por HTTPS
antes de afirmar que cabe o que Doom sigue funcionando.

Toybox 0.8.15 se ha obtenido para comparar; su shell sigue en pending/default-off.
No se ha medido un binario ARC comparable ni ejecutado los scripts LYOKO con ella.
La comparación y decisión definitiva siguen abiertas.
