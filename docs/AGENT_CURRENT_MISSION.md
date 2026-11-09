## 23 de octubre de 2026: R2 abierta programada y operativa

Continuidad de construcción local cerrada:
outputs/releases/linux73-doom-open-r2-source-inputs-20261023-v1/.
SOURCE_INPUTS.json fija receta, herramientas, configuración y 3.010 entradas
del kernel localizadas en 1.452 registros del compilador; 202 archivos/enlaces
públicos del root. Cero fuentes referenciadas sin localizar.
Sólo lectura de archivos: no nueva compilación, pruebas ni acceso al dispositivo.
Es continuidad del árbol local existente, no prueba de reconstrucción portable.
Claves/credenciales excluidas. Enlace desde docs/OPENMITRASTAR_DOOM_OPEN_R2_20261023.md.

Última corrección del propietario aplicada: SSID "wanna play Doom" abierto,
sin contraseña Wi-Fi. La ruta / conserva Movistar/LYOKO y su autenticación;
/Doom redirige al juego. No sustituir la administración por el juego.

Imagen R2 escrita en mtd4: 6.062.800 bytes, SHA256
500b617b659f3b2c8ed075ed493f721ad112ef2fc6245df9422ec9462feab2b9.
CRC imagen e303de32; fullslot 952b0ee4. Un erase/program de prefix,
bytecompare exacto, store/protegidas conservados, cero bootenv writes.
Boot desde readback de flash PASS: PID1 exacto, AP abierto ENABLED,
DHCP y HTTPS automáticos. Sesiónexec66936 terminal y UART/guard cerrados.
Recibo outputs/rea/radio73-doom-open-r2-flash-physical-20261023-v1/result.json.
Entrega outputs/releases/linux73-doom-open-r2-programmed-20261023-v1/manifest.json.

Dirección común Wi-Fi/Ethernet: https://192.168.1.90/ para LYOKO,
https://192.168.1.90/Doom para jugar. WLAN conserva subnet192.168.73.0/24;
DHCP da IP automática y hostroute192.168.1.90/32 vía192.168.73.1.
Cliente real probó red abierta, DHCP y ambas rutas con TLS fijado:
outputs/rea/doom-open-client-common90-v3.json (antes del program R2).
Comprobación final HTTPS sobre R2 PASS: raíz login LYOKO, redirects Doom,
página exacta y APIadministrativa sin sesión403.
Propietario confirmó ejecución del juego en iPhone real; controles difíciles,
mejora futura. Los assets/motor de juego no cambiaron en R2.

No confundir el coldboot anterior con R2: un encendido normal se probó
sólo con la imagen precedente. R2 coldpowercycle posterior UNRUN.
5GHz, configuración editable persistente, soak/repetibilidad y rollback
físico siguen pendientes. No más pruebas/acciones hardware sin indicación.
No enviar mensajes ni despertar el otro chat de 5GHz.

## 23 de octubre de 2026: encendido normal desde flash confirmado

El propietario autorizó expresamente un apagado de cinco segundos y encendido
normal tras la escritura. Captura pasiva sin teclas/comandos UART ni escrituras.
Resultado PASS_NORMAL_COLD_BOOT_FLASH_AUTOSTART_AP_AND_DOOM_HTTPS:
outputs/rea/radio73-normal-coldboot-20261023-v1/result.json.
Bootbase normal no interrumpido, boot_id nuevo, kernel7.3/producto/PID1exactos,
AP2,4ENABLED ES1 y páginaDoomHTTPS hash exacto. Kernelobservado18,36s;
SSH/AP/HTTPSDoom listos33,469s desde primer outputBootbase, no desde el
instante exacto del interruptor. Una observación de encendido normal,
no repetibilidad/soak completo. UARTcerrada. No volver a probar sin indicación.
5GHz/configpersistente/soak/rollback físicos siguen pendientes del goal completo.

## 23 de octubre de 2026: Linux7.3/2,4GHz/Doom escrito y operativo

Escritura final completada: un erase y un program del firmwareprefixmtd4,
6.063.274B SHAc2d39eb2a2fa19d31e75376435956d90eb5529340e09ced827d9b6e0f20e699d.
Bytecompare exacto, fullslotCRCa0898e79; store/protegidas CRC conservados.
Readbackmtd4→RAM/CRC/bootm y SSHpin+PID1exacto+APENABLED+HTTPSDoom PASS.
Final outputs/rea/radio73-2g-doom-flash-final-20261023-v1/result.json.
Detalle docs/OPENMITRASTAR_LINUX73_FLASHED_2G_DOOM_20261023.md.

Sesiónexec63003 TERMINAL; child7980 ausente; COM4cerrada y guardreleased.
Original installer STOP por marcadorPID1UART mezclado con initmem; conservarlo.
Su campo agregado flash_writes0 es default incorrecto: writer separado/steps
prueban un program completo. Recoverynonce falló tras kernelhandoff;
NO hubo restauración/segunda escritura. Candidato operativo permanece.
NO reiniciar ni flashear por ese STOP antiguo.

Propietario prohíbe nuevas pruebas/campañas/ensayos. Sólo se hizo comprobación
final mínima de operación. Coldpoweron posterior NO observado; no tiempo
dearranque medido. 5GHzpendiente, configchangesRAM, storeconservado.
Objetivocompleto sigue abierto. No más accioneshardware ahora.

## 23 de octubre de 2026: escritura final 2,4GHz/Doom autorizada y en curso

Última indicación del propietario: terminar la transferencia actual, escribir
esta versión y dejarla funcionando. No hacer nuevas campañas de tráfico,
ensayos, cambios de firmware ni pruebas de 5GHz. Sólo lectura/comparación
de la escritura final y comprobación necesaria de arranque y servicios.
El objetivo general se conserva, pero 5GHz queda pendiente para después.
No enviar mensajes ni despertar «Reconstruye el driver 5GHz con REA».

Imagen exacta autorizada y probada en RAM:
6.063.274 bytes, SHA256
c2d39eb2a2fa19d31e75376435956d90eb5529340e09ced827d9b6e0f20e699d,
CRC32 a05df7ce, entry851b6000, load8493a000. Kernel7.3,
flatCPIO263entradas, encoderLZMAoriginal, dos builds idénticos.
Arranqueautónomo SSH/HTTPS/AP2,4/DHCP y DoomXZ físicos PASS;
UARTprompttimeout quedó STOP separado, reconciliado por PID1 exacto/SSH.
Cliente WPA2 recibió192.168.73.20 sinIPmanual y cuatroTLSGETPOST PASS.
AuthLYOKO PASS; Doomdesktop/touch/movimiento/disparo/PCMdesdeHGWHTTPS PASS.

Plan outputs/rea/radio73-2g-doom-flash-plan-20261023-v1/plan.json.
Gate work/kernel-port/linux-7.3-2g-autostart-flash-v1.
Proceso de escritura se lanzó con sesiónunifiedexec63003: consultar primero
ese handle y el proceso/recibo antes de reiniciar cualquier operación.
Evidencia outputs/rea/radio73-2g-doom-flash-physical-20261023-v1.
PREWRITE_BASELINE confirma firmwareF367r9/fullCRC4fa4640f y store5d2ee646,
particiones protegidas ligadas a copias exactas. RAMstaging no sobrevivió el
powercycle; se está transfiriendo por YMODEM otra vez antes de escribir.
No afirmar flash completa hasta leer writer/readback/result y arranque.
Único destino firmwareprefixmtd4 offset7e0000+5e0000; store/protegidas
y bootenv permanecen fuera de escritura. Si el gate falla, inspeccionar
estado exacto, comando en vuelo y recuperación antes de más acciones.

## 23 de octubre de 2026: Doom XZ medido; radios siguen prioridad

Actualización posterior al inventario: propuesta del propietario xzwasm
probada localmente. Conjunto jugable1.963.925B; SquashFS aislado1.933.312B.
Desktop/touch/movimiento/disparo/PCM e integridad PASS; HGW no modificado.
Fuentes y ZIPDOS siguen conservados en el candidato completo. La variante
de2MB los excluye de la imagen medida y requiere resolver su distribución
antes de promoverla. Detalle: docs/OPENMITRASTAR_DOOM_XZWASM_20261023.md.
RecetaR2 preparada, pareja final pendiente; no build/compiler activo.

## 23 de octubre de 2026, 00:15 CEST: ambos Ethernet probados; prioridad radios

Última indicación del propietario: presentar versiones y tamaños para decidir
qué abordar primero, priorizando 2,4 y 5 GHz. La optimización de Doom queda
pendiente. Inventario: docs/OPENMITRASTAR_VERSIONES_TAMANOS_20261023.md.
No eliminar archivos ni cambiar versiones únicamente para reducir tamaño.

El HGW conserva el kernel events7.3 en RAM. Tras la respuesta tardía «done» al
cambio de cable, v46 activó eth0 y dejó eth1 DOWN, sin reboot ni bootenv/flash.
SSH con identidad fijada a192.168.1.90 confirma kernel7.3, eth0carrier1 y el
mismo arranque. v47 acredita los cuatro GET/POST de65.536bytes mediante
TLS1.2/TLS1.3 con certificado/hash exactos. eth1 pasó esos mismos gates antes;
ambos conectores están probados por separado, sin demostrar bridge simultáneo.
El recibo general v47 conserva INCOMPLETE por su supuesto erróneo de que toda
página de login200 es acceso abierto. No relabelarlo: la aceptación de sesión
LYOKO está separada en v28/v43. No revertir el puerto al cable anterior sin motivo.

v39 ya terminó:32observaciones,8conAUTH/ASSOC/AUTHORIZED/WMM/HT; segunda
campaña de cliente WPA2+4GET/POSTTLS PASS y AELITA restaurada. No cliente
temporal, capturaUART ni gate físico activo quedan pendientes de esa campaña.
Actual servidorHTTPS443: /run/uhttpd73-wasm, PID2296 observado en v42,
42.912bytes SHA43a0fea8072cfd725ae5803bc7fc4bfd94bb734d8a321b8490945d9563c62d1c.
MIMEapplication/wasm, v43Doomdesktop/touch/audioPASS con un único fetchWASM y
sesiónLYOKOHTTPS PASS. v44retiró sólo el uploader temporal y servidor8443.
SSH2026.94 sigue probado. EntrypointBINFMT_SCRIPT y normalizaciónLF deben
integrarse en el próximo artefacto reproducible.

La tarea independiente «Reconstruye el driver 5GHz con REA» está activa y
produce R22SRAM; reutilizar sus recibos y no competir editando sus fuentes.
R20selectorprivado y R22candidate con74C/22módulosx2idénticos/importsPASS;
admisiónSRAM de placa/mapping/writers/reset/TQE físico siguen pendientes.
REAfocusOEMhal_reset devuelve advertencias de decodificador; clearsram no
localizado por nombre. Ese recibo es parcial, no mapa universal de escritores.

Nueva medida v45 conserva Doom11archivos, usuarios y22módulos5GHz: raíz
XZ1MiB7.303.168bytes, excede sola elprefix6.160.384bytes en1.142.784.
También faltan los3carriers5GHz(1.374.513bytes sin comprimir), kernel y servicios
persistentescompletos. No presentar v45como composición release ni ajuste
definitivo. ZIPDOS2.450.688B+fuentesgzip913.704B explican parte del costeDoom;
WASM2.291.176B->XZ500.048B/WAD4.196.020B->XZ1.360.580B son medidas
independientes, no alternativa empaquetada o equivalencia de entrega aprobada.
CEROflash/bootenvwrites; firmwareOEM/protegidas/store conservados.

## 22Oct2026 21:37 UTC: Linux7.3RAM+WiFiTLS+LYOKO+Doom+SSH physically proved

CurrentimageeventsSHA9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e,
6980384bytesCRC9657f794acceptedv15YMODEM/onebootm/nonce/PID1/memtest/19modules.
eth1TLS1.2/1.3GET/POST65536PASS;eth0thisimagepending. APv21ENABLED ESchannel1.
AELITAv16WPA2/TLSfourGETPOSTexactPASS,originalprofile/DHCPrestored. v39repeat
clientcampaigncurrentlyrunning(hostsession35231),read-onlySSHstationobservation
session72194alreadycapturesAUTH/ASSOC/AUTHORIZED/WMM/HT+wpa2andcounters;wait
forfinalrestore/receiptswithoutrestartingdevice. Cleanup/migrationpostponed.

LYOKOv28PASSlogin/SecureHttpOnlySameSiteStrictcookie/dashboard/session/frontend/
logoutinvalidates. RuntimehashCRLF->LFsamevalue+explicituhttpdAPIinterpreters;
futureartifactmustintegrateBINFMT_SCRIPTandLFprovisioning. uhttpdPID289 HTTPSonly.
Doomv35PASSactualHTTPSbrowserdesktop+touch/movement/fire/actualPCM;
outputs/doom/linux73-https-browser-v35/result.json. OriginalZIP/music/source/
licensesretained,x12assetTLSuploadv34PASS. AssetsRAM,persistenceNO_GO.
WrongWASMmimecausesfallback/duplicatefetch;correctbeforefinalimage.

DropbearSIGBUSrootcauseptraceprovedunalignedstartupR_ARC_RELATIVEby-Wl,-pie;
correctGCC-piex2SHA23026d9cabd53cab1d9b7c5a78ef5c5be0e6842b7a81a1696af9949bf5974da0,
239628bytes. Correctbuildflags(no-E/-s)launchedv37;v38PASSpinnedEd25519SSHcommand
at.91. Usework/kernel-port/ssh_radio73.pyread-onlyfirst;noUARTstatuswhenSSHhealthy.
Kernel29minupatv38;noautoload5GHz/persistentchanges.

TopazresetseparatepairedRAMa4150500...75a0favailableoffline,physicalresetUNRUN.
Quantenna5Gv5realkernelcontext53/53units+objectslink,butplatform/HBM/TQE/ancillary/
exports/ABI/semanticfixtures+radio/client/persistenceunrun. No5GHz7.3claim.
ZEROflash/bootenvwrites;protected/store/F367r9preserved. mtd3rollbackandcomplete
flashfit/releasepending. Fullcheckpoint:docs/OPENMITRASTAR_LINUX73_TLS_WIFI_20261022.md.

## 22Oct2026 20:42 UTC: radio/client accepted; HTTPS events image waiting for power-cycle

Latest owner scope remains Linux7.3, both Ethernet, 2.4/5GHz, secure LYOKO
management and complete Doom; AELITA cleanup/migration are postponed.

The secure RAM image SHA256868f35367375613d97a51ff73d036c2d4b16b8c5aca4d6a4a09b5f2cac3d2
did boot: same-boot v4 accepted current userspace, Ethernet and all19radio
modules; APv9 accepted hostapd ENABLED/ES/channel1. AELITA scan saw the test
SSID and v6 observed WPA2-Personal association. Initial remote executor had an
ACL error and failed to stop later stdin lines: retain both stdout/stderr;
association observation is valid but the entire client executor is not clean
PASS. Router AUTH/ASSOC/AUTHORIZED correlation and useful WiFi traffic remain
pending. HTTPS failed because CONFIG_EPOLL and related event syscalls were
absent. uhttpd was stopped with SIGSTOP. Dropbear CHILD_STATUS=7 remains an
undetermined SIGBUS; do not assume unaligned fault without signal/registers.

AELITA restoration was reconciled at20:34:49UTC over pinned wired SSH(.93).
Original WiFi profile observed, temporary test profile/private input/scheduled
task absent. Receipt: work/aelita-preparation-20261022/wifi-restore-explicit-v10.json.
No cleanup/migration of user data was performed.

New paired RAM image enables only EPOLL/SIGNALFD/TIMERFD/EVENTFD, with all
initramfs/userland/modules/DT unchanged:6980384bytes SHA
9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e,
CRC9657f794. Private CONFIG/BUILD_RESULT/image under
.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/
radioeth73-events-ram-20261022T2036Z. Bootbase offline contract and exact pins
PASS; retained7parser+4writer and3actual-new-flow fake tests PASS.

Physical events-v11 synchronized current kernel/freshnonce, sent one authorized
RAM reboot, then timed out with no Bootbase/transfer/handoff. UART observed
"reboot: Restarting system"; source arch/arc/kernel/reset.c currently calls
machine_halt() rather than Topaz reset. The previous5.10 overlay contains the
Topaz watchdog/sysctl reset sequence, but it was not imported to BASIC7.3.
This is a port gap; v11 is STOP, not a new image boot or HTTPS proof. Record:
outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-v11/.
Router is halted pending owner power-cycle; do not claim current radio uptime.

v12 binds exact v11STOP/image and has UARTCOM4 capture armed for owner
power-cycle (session71883 at20:41UTC); no software reset in this continuation.
Question is pending. Verify live progress before reusing. Guard/source pins,
YMODEM bounded writes, CRC, prehandoff map/watchdog and nonce remain required.
ZEROflash/bootenvwrites; F367r9/mtd3/protected partitions/store unchanged.
Physical mtd3rollback and complete persistent release still pending.

## Secure combined RAM image built; UART transfer recovery waiting for power-cycle

22Oct2026: paired secure radioeth73 RAM image now built and final package
qualified:6964000bytes SHA256868f35367375613d97a51ff73d036c2d4b16b8c5aca4d6a4a09b5f2cac3d2,
CRCdf2ab962,load8493a000,entry84ca4000,end85010000. Receipt under
/home/rea/openmitrastar-linux73-20261022T135100Z/radioeth73-secure-ram-finish-v3.
Private Windows artifact: .openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/
radioeth73-secure-ram-20261022T1934Z/radioeth73-secure-RAM-ONLY.ras.bin.
CPIO7293440bytes/246entries,19module order/dependencies/private0600 modes/DT
embedding and entry qualified. Exact BootbaseRAM contractPASS. Final image has
current libc1.0.59+BusyBox1.38+Dropbear2026.94+hostapd2.12+iw6.17+uhttpd2026+
wolfSSL5.9.4;HTTPS443/SSH22 explicit-only. No UDPecho/HTTP/TFTP/Telnet listener.
No physical acceptance of this image and not a complete flash release.

Physical-v1 captured fresh ETH73 nonce and owner power-cycle, Bootbase route0,
watchdog0/map-qualified,then loady. Python writer blocked in pySerial
GetOverlappedResult(TRUE) during a YMODEM data write. Observed exact stack with
py-spy(no locals); killed exact child51932 and parent36272 exited/released guard.
No bootm/flash/bootenv. HOST_WRITER_CONTAINMENT.json records the event separately;
original partial output preserved. It is host serial failure, not kernel crash.

Versioned bounded overlapped writer uses event wait/cancel/GetOverlappedResult
FALSE;4fake cases verify completion, cancellation and quarantined buffer. V2
recovery got no receiver/prompt within15s, stopped without sending CAN or loady.
V3 captured active fresh guard/COM4 waiting for owner power-cycle, session18082,
parent23736 started19:38:51UTC. Latest pending physical action asks owner to
power-cycle again with Ethernet/UART unchanged. Do not infer last answered first
powercycle as completion of the second request. Inspect live process/session.
V3uses same exact RAM image; no new generic approval required.

Whole co-pack measurement with modern diagnosticroot+completeDoom/archive/source/
originalmusic: XZ128KiB7122944bytes;XZ1MiB6955008bytes. Both exceed historical
rootfswindow4587520; these are measurements of diagnosticroot, not full persistent
product or physical acceptance. All game/source/licenses retained. Size optimization
remains necessary; protected/store/mtd6 are not capacity. See
docs/OPENMITRASTAR_LINUX73_CURRENT_SOFTWARE_20261022.md.

## Latest owner correction: Movistar-style LYOKO, secure current stack and Doom fit

Owner explicitly retains the current Movistar-style LYOKO configuration UI and
requests lightweight modern secure web components under it. Preserve its controls,
layout and identity; do not remove the existing UI merely because its style is
Movistar. HTTPS/TLS and modern SSH are authorized and required. Earlier strict
TLS-only/noSSH interpretation below is superseded. No cleartextHTTP/TFTP/Telnet
listeners or new plainUDPecho traffic. Local UART/YMODEM remains the RAM loader.
SSL means current TLS here: do not enable obsolete SSL protocols.

Owner requests best current efficient components, compare BusyBox vsToybox by
actual applet coverage/size/resource use instead of replacing by name. Keep prior
SquashFS progress: current proven packing is XZ/128KiB; compare alternatives with
whole-image bytes/runtime before promotion. Doom, original music, touch/English
wrapper, LED/timing and all requested functions must fit the complete flash image.
Do not drop them to claim fit. Existing F373 complete SquashFS is7,782,400bytes,
over old rootfs window by3,194,880; earlier TLS-size saving does not solve this.
New composition must measure kernel/rootfs/slot and preserve all protected areas.

New2026source acquisition completed for11components, no physical access.
uClibc-ng1.0.59 now builds shared/static with CONFIG_ARC_HAS_ATOMICS disabled,
C99math and EN/ES UTF-8 locales. Exact18ELF/archive checks no SWAPE/LLOCK/SCOND;
new libc518100bytes, loader25572; hello119876bytes linked, not executed physically.
Receipt: /home/rea/openmitrastar-linux73-20261022T135100Z/libc2026-qualified-v1/result.json.
Initial failed builds kept. Host needed isolated glibc2.39 locale sources and
serial locale_headers under make4.3; adding a gen_ldc dependency alone did not
solve missing host locales and was reverted. C99math fixes __signbit link.
Current uhttpd/wolfSSL5.9.4 shared build now running in modern-web-arc750-v1.
Toybox0.8.15 comparison source acquired; its shell is pending/default-off, so
do not substitute it for qualified BusyBox shell without actual script tests.
Composite driver/PID1/HTTPS and full Doom co-pack still pending. SSH stays required.

## Owner scope correction: current userland and HTTPS/TLS only - 2026-10-22

Owner ordered reuse of the Linux5.10 port, RAM acceptance of both Ethernet
connectors and2.4GHz, then flashing the accepted complete image. Authority
persists; no repeat generic approval. Exact flash artifact/contract/readback/
protected partition/rollback gates still required. OEM recovery remains intact.
Owner rejects the OEM application/web stack and requests current2026 software,
HTTPS/TLS exclusively. New listeners and traffic tests must not use plainHTTP,
TFTP,Telnet or plainUDPecho. UART/YMODEM remains local RAM transfer. Do not
include SSH listener in this strictHTTPS/TLS candidate. Radio calibration and
chip-required firmware are hardware dependencies, not OEM management services.

work/kernel-port/linux-7.3-radioeth-ram-v1 has source-only composite driver:
MAC-init-v3 plus passive TX sysfs diagnostics. Actual diagnostic fixture262cases/
72728checks PASS; reset regression28cases/48153checks PASS. PID1 proposal is
being corrected to remove UDP/SSH and integrate a current HTTPS server and TLS
traffic tests. It is not built, packaged or installed. Safe extracted old static
BusyBox/hostapd/iw/Dropbear verified without forbidden instructions; these are
references, not approved final current software. Old TLS trial retains mini_httpd
1.19 and wolfSSL5.9.2; do not relabel it modern or install as final replacement.
Current userland sources pinned for new builds: uClibc-ng1.0.59, wolfSSL5.9.4,
uhttpd2026-10-19, libubox2026-10-08, ustream2026-07-08, hostapd2.12,
BusyBox1.38.0(testing release); libnl-tiny latest pinned2025-12-02 dependency.

Current toolchain libc still adds26LLOCK/SCOND to a compiled hello. Historical
patched sysroot distro was removed. Kernel already implements arc_usr_cmpxchg;
build new userland libc with CONFIG_ARC_HAS_ATOMICS disabled before linking
new services. No new physical action or flash occurred during this work.

## Linux 7.3 radio2g offline pair and Ethernet MAC-init v3 - 2026-10-22

See [current radio2g and Ethernet v3 evidence](OPENMITRASTAR_LINUX73_RADIO2G_OFFLINE_V1.md).
Radio73 kernel plus18modules passed independent paired builds/import/ARC checks;
physical PCIe/wiphy/AP/client/traffic UNRUN. Signed regdb is enabled in actual
config. Ethernet is absent from that kernel package. Current physical evidence
is reset-v2 RAM boot: eth0 bounded2018/2018UDP accepted earlier; eth1 alone has
carrier/RX but repeats TX WaitEOT after9completions. Local stop reset succeeded
and reopen succeeded, then TX stalled again. No SSH in RAM image; UART released.
No new hardware observation in this reconciliation; do not claim current uptime.

OEM code confirms12localMACregister settings omitted from reset-v2. New
work/kernel-port/linux-7.3-ethernet-macinit-v3 initializes them before TX/RX;
root cause remains hypothesis. Actual fixture256cases/134400checks and3compiled
negative controls PASS; retained reset lifecycle28cases/48153checks PASS. Module
twice identical against copied sealed radio73 context,26372bytes SHA528e1862dbbf
391f33e62c5bd9a2dfe7325439aca23fdeaa01c364f96786bbf0;80imports resolved/no
SWAPE/LLOCK/SCOND. No physical use, integrated image or TX recovery claim.
Next:read-only TX diagnostics, explicit radioload initramfs/firmware/regdb,
integrated paired RAM image/Bootbase contracts, then authorized physical trial.
ZERO new UART/reboot/radio/flash/bootenv operations. Protected images preserved.
Radio73 source package and offline receipts pushed to private Realtek repository
on port/linux-7.3, verified remote head a924ed874ba925c1b9fb2e42cbb2ef2e59d74e5d.
No firmware binaries, unit MAC, PSK or calibration committed. Original references
and Linux5.10 branch preserved. Source portable full rebuild still UNRUN.

## Linux 7.3 Ethernet physical boot/traffic accepted - 2026-10-22

Owner ordered immediate integration/test and then granted total authority
for this target's port. Do not repeat approval for authorized same-scope
testing/resets; keep artifact/partition/recovery gates. On22Oct~16:57UTC,
ETH73RAMimage3052800bytesSHA513dc8d0a23e9aa8c8c1be90c2e9da090a4fae483ff6bbe
20c836579f04e31b4 booted physically after exactBootbaseCRCb6fdc394,load8493a000,
entry84940000. Linux7.3.0-openmitrastar-eth73-v1/PID1/freshnonce/memtestPASS.
Driverload0,eth0up/down,eth1up/down,eth0reopen0; pingPASS and12/12UDPechoPASS.
IRQ20 9->104; actualNAPI104/RX87/TX17; noforcedpollNAPI/restart/quiescetimeout
inthiscapture. ZEROflash/bootenvwrites. ETH73RAMleft running eth0UP,eth1DOWN;
UARTreleased, noSSH included. OriginalF367r9stillpersistent. Manualreturnfrom
BASICtoF367r9 was pinnedSSHverified duringfirstwindowmiss; mtd3notrecoveryproof.
v1-v5hostfailuresremainimmutable; finalv6resultPASS_ETH73_PHYSICAL_BOOT_DRIVER_AND_TRAFFIC.
Exactartifact/pairedbuild/CPIO/physicalreceipt in outputs/rea/
movistar-port-20261022T1327175411798Z/eth73-ram-artifact-v3 and
eth73-physical-trial-v6. docs/OPENMITRASTAR_LINUX73_ETHERNET_PHYSICAL_BOOT.md
stateslimits. Next:trafficsoak/secondconnector,physicalmappinganddualbridge;
radios/SSH/persistence/recoveryremainUNRUN. Currentfiles outrank oldofflineNO_GO.

## Linux 7.3 Ethernet v1 paired offline build - 2026-10-22

After accepting BASIC, offline Ethernet integration now builds kernel and
module twice identically: ELF4455148bytes SHA3c173455469c84ed46664a9f3b36b80d
fd112ab77b77cc1f755413cbb2a6e19a; EMAC25808bytes
SHA067f040165348edcdc3d125cf284f6921802cc3590909df9fe3772c0b9adf798.
80imports resolve; no SWAPE/LLOCK/SCOND. CPU750D/MMUv2/8KiB,
UP/PREEMPT_NONE via ETH73 selecting ARCH_NO_PREEMPT; no radios/PCI/MTD.
F374r3APIadaptation plus hwirq/domain validation, direct19/20gates,
Topazdma-ranges and timeoutquarantine. Failed stop pins DMA memory and
refuses reopen; it does not recover the hung engine. Worker RTNLtrylock
serializes with stop.18lifecyclecases18340checks and60RXcases48606checksPASS;
4compiled/executedmutationsreject.95978upstreamfilesverified; embeddedDT
equals sidecar inbothELFs. No new device access; no RAS created. DT Ethernet
disabled, module separate, PID1 BASIC does not load/configure networking.
Therefore OFFLINEPASS/NO_GO_HARDWARE. See
docs/OPENMITRASTAR_LINUX73_ETHERNET_OFFLINE_V1.md and work/kernel-port/
linux-7.3-ethernet-v1. Next:diagnosticinitramfs/DTidentity/moduleintegration,
fullworker/probe/removeandresourcefixtures, newbuild/packagecontracts, then
resolve exact physical authority. Existing BASIC physicalboot remains accepted;
its current runtime was not refreshed. No reboot/statusUART inferred.

## Linux 7.3 BASIC physical UART boot accepted - 2026-10-22

Owner narrowed the first milestone to kernel BASIC UART, without networking
or radios, then authorized the RAM trial. At 15:35 UTC, the physical HGW passed
Linux7.3 version/PID1, fresh nonce input, growing uptime, Timer0/UART IRQ counters
and a bounded1MiB two-pattern userspace memtest. The kernel is
7.3.0-openmitrastar-basic73, RAM-only, left running. Exact RAS1966400bytes,
SHA25624a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb.
Bootbase observed CRC0f700813 before the only kernel handoff. No flash or
persistent bootenv writes. Prior host parser STOPs remain immutable and are
not kernel crashes. F367r9 remains the preserved persistent image; its RAM
overlays were lost during the controlled reboot. Do not reboot for status.
UART is the observed FTDIAG41W2BL onCOM4. Ethernet/Realtek/Quantenna are absent
from BASIC; persistent7.3/cold boot/long soak/manual return are unrun.
See docs/OPENMITRASTAR_LINUX73_BASIC_BOOT.md and final physical receipt
outputs/rea/movistar-port-20261022T1327175411798Z/basic73-uart-acceptance-v7/
run-20261022T1535387076279Z/result.json. Finish accepting/documenting this
milestone before advancing to driver integration. New hardware actions retain
their applicable artifact, review, ownership and authorization gates.

## 5 GHz AMSDU20 full typed closure offline qualified - 2026-10-22

Afterexecutor recovery,20entrycandidate full7moduleclosure passed116freshC
compilations,x2identical modules,209priorVAPfields offsets/widths unchanged,
typedflag3081usespadding,sizeVAP3084/qdrv_vap3540unchanged. MainQDRV18byte-
identical;WLAN630312aa00ffd4...c2c02 with4semanticbodies+7exactdiagnostics,
allothercode/data/symbol/RELAresiduals pass. Fiveancillaryproviders F152original
hashmanifestbound operationalallbytes/symbols/RELAexact;srcversionaddition
declared.1511inputpins,7negativechecks and independentfinalreview PASS.
Table586=18functional records+2faithfullyunsupported,24OEMgaps. No aggregation,
throughput,RF/client/persistence/rollback/release evidence. See
outputs/rea/driver5g-ops-20261022-twenty-full-qualification-r1/result.json.
Beaconr9 all7modulesx2built+jointexports resolved; globaldeltaqualification
stillpending. TQE R2 boundedproviderofflinequal171cases+12negative/independent
review; retainedledger/recovery/foreignbank/HBM/physical gates remain.

## 5 GHz executor recovered;18-entry pair offline qualified - 2026-10-22

Owner explicitly requested continuing through errors. REA-Linux was terminated,
then the shared WSL VM restarted to restore its disconnected disk; passwd/id,
rootmount/space and pinned ARC15.2.0 compiler verified. No router/flash/UART/radio
operation occurred. Full18pair now passes106Ccompiles,x2 identicalmodules:
QDRV684772f79e2836...a913;WLAN630136ce526cf5...09cc.2224inputpins,actual
privateABI30556/u830553,allresidualcode/data/RELA,7faultchecks and independent
review PASS.16functional records+2faithfulunsupported,26OEMtablegaps.
See outputs/rea/driver5g-ops-20261022-eighteen-pair-sealed-20261022T175000Z-r1.

AMSDU20 source typedVAPflag/default1/actualADDBApredicate recovered with OEM
and MuC evidence. All209priorVAPfields unchanged;newflag3081 usesoldpadding,
VAP3084 andQDRVvap3540 unchanged. Three changed units ARCsyntaxPASS; complete
7moduleheaderclosurex2 inprogress. Beaconr9 source fullchain/lifetime fixture
PASS and changedunitsARCcompilePASS;full7moduleclosureinprogress. Neither new
closure is qualified or installed. TQEboundedproviderpair compiledoffline but
delta/retention/foreignwriter/runtimerecovery remainseparate. No releaseclaim.

## Quantenna 5 GHz REA recovery and private source repository - 2026-10-22

Owner requested REA/full source recovery, exact comments and private GitHub.
Repository repos/openmitrastar-hgw500-quantenna-5ghz-driver is private on
apelsito GitHub, verified pushed checkpoint48e5286. Full original GPL firmware
tree pinned116a8b0;46770files/598076127bytes; radio/port snapshot separate.
Original comments/copyright/line endings preserved. Full Git C/C++ catalog:
35018files/1331535comments/104725712rawbytes; allrecordhashes replayPASS.
Ownerlocalfirmware/modules/secrets/calibration excluded fromGit.

ExactOEM private WEXT607 vsF365566:563matching/44missing/3added. REA recovered
complete OEMset/get/assignedQDRVgetter evidence. Sevenentry completepair now
offline qualifiedx2: QDRV684108 dd8f29a1...fad06; WLAN629496461c23d2...aec92.
2208pins/alloutsidegetterbytes+RELA+symbols/data/BSS/stringsPASS;327681actual
function/ARCchecks+5negativeparsedmodulechecksPASS.37OEMgaps remain.
Fourteenentryfullpair nowOFFLINEqualifiedx2 after106Ccompiles/noobjectreuse:
QDRV6847563e76821b...cf06; WLAN62998446075f1f...cb79.12operations+2faithful
unsupportedresponses,30OEMgaps.7faultchecks/independentreviewPASS; finalr5
binds17evidenceinputs/fixtures.1502hostpins refreshed,718Linuxonlypreviously
verifiedunchangednotfreshWindowsclaim. Further15/17/19sourcebranchesremain
unqualified. Fifteenpair nowOFFLINEqualified:QDRV14unchanged,38WLANcompiles,
629896byteseac8c063...f946. Actual464caseARCwriteoffset19488/width4 proven,
131074sourcechecks/7faultchecksPASS; separateoffsetcompilerUNRUNWSLerror.
13operations+2unsupported,29OEMgaps. PreservefailclosedDFS, F355retentionand
TQEarbitrajeNO_GO.

Standalone repositoryTQE buildx2BYTEPASS35552 bd5ab101...635f. Standalone WLAN
buildx2 nowPASS6291807b0e504e...f8dc0, alloperational959functions/9543RELA/2250
symbolsmatch; onlysrcversiondelta declared. See repo evidence/portable-wlan-
20261022-r3. PriorWSLdiscovery/memory/0x8007274cfailures preserved; scopefix
testedbynewWLANbuild, noWSLreset/routeroperation performed.

HTTPSonlyclientdesktop10,168B actualbrowserPASS(notes/Snake/windows/HTTPrefusal),
notinstalledonHGW. Commentviewerclientchunks<=10000recordspassesHTTPSbrowser
decompression/search, noexternalrequests. NoDocker/nativegraphicsinstalled.
Nohardware/UART/SSH/radio/bootenv/flashaccess performedbythiswork.
See docs/OPENMITRASTAR_DRIVER5G_REA_RECOVERY_20261022.md for exactbounds.

## Ethernet REA and F374r3 offline correction - 2026-10-22

Owner requested complete Ethernet REA to improve the Linux5.10 port. Three
subagents contributed source/build, coverage and independent candidate reviews.
OEM emac/emaclib/switch_emac and F352 executable bytes are fully preserved and
linearly decoded with exact pinned ARC objdump byte checks. Pseudocode remains
partial: OEM non-NOP body gaps are20/118/8bytes; F352/F374r3 have none but13
warning functions each. All original STT_FUNC starts are represented; stripped
local OEM names are source-correlated candidates, not recovered identities.
See docs/OPENMITRASTAR_ETHERNET_REA_F374R3_20261022.md and the final coverage
outputs/rea/ethernet-full-20261022T132851Z/final-r3-coverage/REPORT.md.

F352 full-module baseline reconstructed twice byte-exact24544bytes SHA
41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e.
F374r3 now prevents RX descriptor rearm on quiesce timeout, counts failed attempts
separately, restores controls and IRQ0 to supported0x111 for the active worker.
Two complete24768byte builds match SHA
d1a0fbb05b876855454f65519a0ecc64c20106c1c437174e2519281f99f46eed.
Final build outputs/rea/ethernet-f374-build-20261022T135845610793Z/result.json
checks38function bodies34unchanged,9data sections,40NOP gap bytes and77imports.
60cases/48678checksPASS and independent replay; six negative gate mutations reject.
Final review outputs/rea/ethernet-r3-final-review-20261022T1401144672462Z/REVIEW.md.

OFFLINE_PASS; NO_GO_INSTALL. Inherited ndo_stop/remove/open-failure DMA lifetime
remains unresolved; full worker and physical boot/ports/traffic/soak/rollback
gates UNRUN. No reset, module installation, router/SSH/UART/radio access, flash
or reboot occurred. This is not complete Ethernet parity or a release result.
Only pinned UP/PREEMPT_NONE is in the candidate's scope. Existing live state
was not refreshed by this offline task. Some historical build objects vanished
during the run; exact sealed baseline substitutions are documented rather than
restoring or replacing historical evidence. No Codex or installed REA changed.

## Execution recovered; music installed; inventory/storage refreshed - 2026-10-22

Owner requested a complete technical ZIP handoff. Delivered locally under
outputs/handoffs/hgw500-linux510-complete-20261022T125241562008Z/
OpenMitraStar-HGW500-Linux510-Handoff.zip,211566919bytes,
SHA256ca3685b195394ae88020757eefe4b5bedf8c690f113aaed975be22ecb0873381.
3308payload files checked bySHA/ZIPCRC. Includes bothradio binaries/sources,
sanitized installedfiles,currentRAMoverlays,toolchain/kernelarchive/buildcontext,
audits,fixtures,REAevidence andrecoverylimits. Notflashable; no privatekeys,
PSKs/calibration/rawMTD/store/personalizedfullimages. EXCLUSIONS explicit.
CompletepatchedF358kernelsource missing, exact2Grebuild remainsUNPROVEN.
No file sent; no hardwaremutations. See LEEME_ENTREGA.md beside ZIP.

Complete owner-facing inventory and storage map:
docs/OPENMITRASTAR_INSTALLED_VERSIONS_STORAGE_20261022.md;
UTF8 CSV425entries outputs/inventory/installed-final-20261022T093747859049Z.
403firmwarereference entries+22recordedRAMpackage entries; notallvolatilefiles.
Dates distinguish embeddedsource/buildtime, Sept22campaign and actualRAMinstalls.

Local execution recovered after desktop host failure. Pinned SSH confirms same
F367r9 boot5f513265-a294-4366-9567-e1d8af704b6b, controls2gENABLED/5gPONG/RF1,
watchdog00000000/fatal0. PC192.168.1.49 nowinterface16; old18hardwareplans stale.
AELITA .63:22 source-bound timeout; client/traffic still UNRUN, not WiFi failure.
Currentcapture outputs/current-state/hgw-resume-20261022T092441413571Z.

Original Doomepisode1 music installed inRAM: both patchedWASM eb47045e...c20e
andEnglishindex5c8c0c99...efacc verifiedHTTP. ActualoriginalOPL audioPCM and
movement/firePASS outputs/doom/music-http-20261022-r1/result.json; noexternalmusic.
Config-onlyOPLvariant hangs and isNO_GO; originaldelaystartupfix changes1/2631
WASMfunctions. See docs/OPENMITRASTAR_DOOM_ORIGINAL_MUSIC_20261022.md.
No reboots/flash/radiochanges; previousWASM/index preserved underRAM bindmounts.

Fullcomponent inventory outputs/inventory/router-components-20261022T092048336196Z.
ActualTLStrial re-pack saving352KiB, not raw837052bytes; sourceF372unchanged.
See docs/OPENMITRASTAR_TLS_SIZE_MEASURED_20261022.md. NotinstalledorHTTPSaccepted.
StorageRO outputs/storage/hgw-readonly-20261022T093109419362Z and decodedDT
hgw-dt-reg-20261022T093404035766Z: one16MiBphysicalNOR layout,5ROM logicalviews,
noadditionalblockdisk. rootfs0x960000+0x460000/store0xdc0000+0x1c0000 disjoint.
Tmpfs/www/LEDviews shareRAM not extra storage. Never sum overlappingMTD orclaim
OEM/protected/store as unused capacity. Ownership/recoverygates unchanged.

TQEbounded-admission prototype progressed offline:38cases245checksPASS, but
baselinefullmodule/arbitrajeuniversal remainNO_GO_MODULE; notloadedorpackaged.
See docs/OPENMITRASTAR_TQE_BOUNDED_ADMISSION_PROTOTYPE_20261022.md.

## English episode1 and persistent integration attempt - 2026-10-22

Owner requested EnglishUI/fullgame then explicitly narrowed back to original
sharewareepisode1 ONLY with easycontrols. Englishpage is live on /Doom and
routerbrowserPASS including movement/fire/touch; no fullgamepicker installed.
IndexSHAf05c849f945e56f4250a7800e627a732e9711746465c8359d5cfeb270d5baa33.
Evidence outputs/doom/router-english-test-20261022-r1/result.json.
Owner requests persistent firmware with Doom/LED. Actual F373co-rootfs twice
measured7,782,400bytes vs4,587,520window: excess3,194,880bytes. NO_GO_SLOT_FIT,
no flashfile created; RAMinstallation remains. Existing drivers/auth/management
catalogs preserved. Do not reclaimjournal/protected space or removefeatures tofit.
See latest docs/OPENMITRASTAR_F373_DOOM_LED_INTEGRATION.md when available and
privateanalysis f373-doom-led-* result; current evidence is measured, not estimate.

## Doom and LED CLI installed in RAM - 2026-10-22

Owner authorized installation and requested hidden /Doom route on managementIP.
Actual physicalrouter HTTPassetsPASS and browsergamePASS: E1M1 movement/fire
and actualtouchgestures, no externalrequests/WebSockets/JSerrors. LEDCLIfix is
now bindmounted and verified on target, brightness unchanged. Port80mini_httpd
alone restarted for newwebroot. SameF367r9 boot/APs/store/config/fatal0 preserved.
Installed for thisboot only, NOTpersistent. No reboot/UART/flash/bootenv/radiochange.
Boot timingrcS and F372firmware remain uninstalled; recoverygates unresolved.
Owner asked if powercycle needed: explicitly told no, keep powered for currentRAM.
See docs/OPENMITRASTAR_DOOM_RAM_INSTALLED_20261022.md.

## Owner parks Wi-Fi test; LED and boot work - 2026-10-21

Owner declined Wi-Fi testing today; prior "does not appear" reply is not a
performed client scan or established visibility failure. No further mobile
prompt/idle capture is needed. Client/traffic gates remain UNRUN.
Current pinnedSSH confirms sameF367r9 boot, bothAP controls healthy, fatal0.
WiFi LED requests255; lowerB/G/R andstage0 requests0. Physical cause of owner's
lower lights remains unknown; cached LED class values are not electrical proof.
New offlineLED CLI fixes stage0/boot mapping and exact restore/signal failures:
25fakechecksPASS plus actual targetash list/status read-onlyPASS. Not installed.
New rcS timing-only candidate preserves original behavior in three fake service
cases; no physical speed improvement claimed. SealedF372 and oldplan unchanged.
See docs/OPENMITRASTAR_LED_BOOT_PROGRESS_20261021.md.

F372 install decision core is now offline-tested:23fake unittest methodsPASS,
finalcoreSHA38d36343aca72aff0f58be0def83ae98d10bb53896764293659e418eeea3ecdf.
Evidence outputs/preflight/f372-core-tests-20261021T214200Z-r7-cached/result.json.
Originalsource hashes/plan checked real initially/finally; repeated originals
memoized only in simulations, newcore/receipts still hashed. CLI remains file-only;
no production factory provenance or cross-run single-use admission mechanism yet.
Recovery/owner exactimage/physicalreadbacks unresolved; no physicalGO inferred.
See docs/OPENMITRASTAR_F372_INSTALL_CORE_OFFLINE.md and immutable review
outputs/preflight/f372-core-review-20261021T215805665824Z/result.json.

## Installation preparation and iPhone window - 2026-10-21

F372 now has a file-only install contract: outputs/preflight/
f372-install-20261021T195348642022Z/plan.json, 298 source pins and21faultchecks.
No physical executor or write is admitted: exact owner artifact authority,
fresh recovery and physical readback gates remain pending. The preserved mtd3
record remains historical rootfs/management NO_GO, not verified ATGO recovery.
F372 postboot control verifier has140offlinefaultchecks and reads92runtimehashes;
it never substitutes for client/traffic/coldboot/recovery/release acceptance.
See docs/OPENMITRASTAR_F372_INSTALL_PREPARATION.md.

Owner offered iPhone18Pro. Actual AP SSID MOVISTAR_PLUS_55CB; five-minute SSH
window sampled50times, AP/control/bridge/watchdog preserved and fatal0.
No client association or WLAN5RX traffic was observed. Owner Wi-Fi outcome
reply is pending; this is inconclusive, not a proven client rejection/failure.
Exact F365 radio modules remain active in RAM on installed F367r9, same boot.
No flash/reboot/bootenv write occurred during this preparation.

## Live resume - 2026-10-21

The physical HGW is reachable again by pinned SSH at192.168.1.90, from existing
PC192.168.1.49/Ethernet18. The owner moved the cable to the connector observed as
eth0. Original FTDI AG41W2BL now enumerates COM4. BootID is
5f513265-a294-4366-9567-e1d8af704b6b; installed image remains F367r9/#358 Linux5.10.

A normal non-DFS5GHz AP is running from exact F365 qdrv/wlan modules in RAM,
channel36/80, RF1/carrier1/hostapdPONG; SSH and2.4GHz remain healthy, fatal0,
watchdog00000000. No firmware/bootenv write or reboot occurred. Original R9
quarantine is intact. This RAM activation disappears on reboot; it does not
qualify persistent5GHz, client traffic or final release. AELITA TCP22 was absent;
owner mobile client test is pending.

REA ARC700 analysis and F368r2 descriptor-quarantine correction are implemented
offline. F368 original is NO_GO after reproduced stale-ACK hazard. F368r2 has
16cases/80checks and two identical703624-byte modules; it is NOT installed.
F369 now packages this qdrv offline in two identical5468160-byte full images,
SHA256d803af79949e4d0bb26791c8f234976f66a2934d724c01ed4b4d0486f067250e,
Bootbase/slotfitPASS. See docs/OPENMITRASTAR_F369_STORE38_CANDIDATE.md.
F369 retains diagnostic activation; it is NOT a product5GHz auto-start release.
Image installation/physical acceptance remain pending. The owner accepts flashing between gated
iterations; safe hot reload is not required. OEM-to-5.10 demo remains future work.

F370 is now a complete qualified module on exact F365 lineage: two identical
686144-byte qdrv modules, SHA256
d5e1f58303eaaa02123e0cf6352bd40c40df3027be300d2a1143b07f54a05dae.
The full baseline comparison covers831functions/14034RELA/1932symbols and
allocated data; 369imports/15exports and four0444uint counters are verified.
See docs/OPENMITRASTAR_F370_COMPLETE_MODULE_20261021.md.
F371/F372 full images are prepared offline, both5382144bytes. F372 packages
F370 normal-start measurement, imageSHA256
e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9.
Neither newimage nor F370 is installed; client/traffic/persistence gates UNRUN.
See docs/OPENMITRASTAR_F372_AUC_TQE_OBSERVATION_IMAGE.md.
Correction: live head -n and tail -n work; they were not missing. F371 helpers
are not proven necessary. Only head -c is unsupported, affecting an inherited
configuration transaction ID path. Current QDRV line diagnostics are valid.
A fresh61-second read-only dual-radio control observation passed on sameboot. TX BA remains disabled by the
current baseline; performance and full legal functionality are not accepted.
The owner cannot run the mobile client test now; no client/traffic PASS claimed.

Read docs/OPENMITRASTAR_REA_RADIO_STATUS_20261021.md for current evidence/limits.
Older September recovery plans bind COM3 or historical host indices; do not
execute them unchanged against today's COM4. Current physical partition views
are logical ROM views, not permission to write their same-numbered devices.

# OpenMitraStar current-work handoff

## Ready offline; blocked on physical HGW restart - 2026-09-23 08:33 UTC

The current recovery preparation is complete. The HGW still does not answer:
source-bound TCP22 failed at08:33UTC; TCP80/443 and the20-second UART/empty-line
probe also failed earlier this morning. No fresh Linux or Bootbase identity is
available. No hardware operation is running, and the original quarantine lease
remains intact. F365 is NOT restored and DFS/port completion is NOT claimed.
The HGW-only10-second power cycle was already requested once; no confirmation has
arrived. Do not repeat that request or start another flash/serial reset blindly.

Use this sealed recovery plan after a fresh, verified quiescent R9 boot:
`outputs/preflight/r9-return-host17-20260923T083056Z/plan.json`, SHA256
`43c3fd8de34c675501168e86180df1b46e45bf60b99024d78e0fa59745d60b18`.
Runner: `tools/run_f367r9_return_f365_host17.ps1`; procedure:
`docs/OPENMITRASTAR_R9_HOST17_RETURN.md`. It preserves the parent quarantine until
the exact F365 return and all readbacks pass. It uses only one qualified SSH
reboot and no serial-reset fallback, radio experiment or new firmware candidate.

The root host observation proves that the existing permission differs only by
Ethernet index18 becoming17; GUID, PnP, IP/direct route and every permission/profile
property are pinned without changing any rule, IP or route:
`outputs/preflight/r9-host17-observation-20260923T082938Z/result.json`, SHA256
`f71c4f90df7a2d32986a702eb8f4d3a5a700694ae50c8c4e7f01e080bd43e212`.
The older 08:12 plan is historical and must not be executed on this host.

The separate host recovery revision2 is also OFFLINE ready for a future new
continuous capture; its contract and27-test result are recorded below and in
`work/mission-state/R9_RECOVERY_PENDING.json`. It cannot resume the closed R9 UART.
The complete original DFS and port goal remains pending. After the owner action,
start from live evidence rather than these historical image/boot assumptions.

## Recovery preparation update - 2026-09-23 08:20 UTC

The renewed root console probe still received zero bytes, including Ctrl-U+CR;
`/workspace/OpenMitraStar/f367-recovery/r9-console-resume-20260923T082045Z/result.json`
confirms the parent lease is unchanged, the child/port are closed, and no BREAK,
reboot or flash occurred. TCP22/80/443 also do not respond. The previously requested
HGW-only power cycle is still unconfirmed; do not repeat the request.

Host recovery revision2 is implemented and OFFLINE qualified (27 tests):
`outputs/preflight/f367-host-recovery-r2-20260923T080937Z/result.json`, SHA256
`235c451f6147533bdd4837a2f4bbc6f65a260f4c5d0c133e22680875d61e5b09`.
It is for a new continuous capture; it cannot authorize recovery of the closed R9
capture. The immediate F365 return instead reuses UART2 and one fresh SSH reboot.

An offline F365 return plan exists, but do NOT execute the 08:12 plan yet:
Windows now selects Ethernet index17 for192.168.1.49/24, while that plan and its
historical firewall/network guards bind index18. The current adapter is pinned in
`R9_RECOVERY_PENDING.json`. The recovery-plan agent prepares a read-only observation
and a narrowly updated binding; no firewall rule, IP or route may be changed.
This current index change does not explain the earlier R9 failure: its original
index18 guards passed at that time. Keep all historical plans and results intact.

## Current: recovery unproven; owner power cycle pending - 2026-09-23 08:01 UTC

R9 is NOT active and F365 has NOT been restored. Its final result is
`/workspace/OpenMitraStar/f367-campaign/f367r9-campaign-20260922T224919Z-91a7595c/result.json`,
SHA256 `2ed7d2c75142a9ca3176302d4cb14c11d52d76dec056d6295a8ce7fd131b38d3`.
It ended `FAILED_RECOVERY_UNPROVEN_NO_RETRY`: SSH failed during initial quarantine,
before any DFS transition or R9 trace. Last sample:11,109 jobs,0 errors,1,089s
quarantine still pending. The physical cause is unknown. The recovery then failed
with `uart_window_overflow` before BREAK/b or a recovery write was attempted.
Session16184 and all its children closed; UART is closed, no flash was in flight,
but watchdog state is unproven and the original parent lease remains retained.
Do not clear that lease merely because its owner PID has ended.

Root performed one reviewed console observation under the same mutexes and a child
lease, preserving the parent. It received0 bytes in20s including one Ctrl-U+CR
probe; no BREAK, reset, flash or bootenv write occurred. Result:
`/workspace/OpenMitraStar/f367-recovery/r9-console-20260922T232256Z/result.json`.
An HGW-only power cycle with10s off and USB/UART/Ethernet left connected was already
requested once. There is no confirmation yet; do not repeat the request.

The Codex execution helper subsequently failed to start, preventing state updates.
Execution is available again on this resume; TCP22 at192.168.1.90 still fails.
Authoritative pending state is `work/mission-state/R9_RECOVERY_PENDING.json`.
Next work is offline: correct continuous UART epoch/autoboot recovery handling and
prepare a gated return to the exact F365 image after fresh identity/quiescence.
No new firmware experiment, blind lease deletion or unproven SysRq is authorized
by this pending state. Keep the complete DFS/port objective; temperature and
performance remain parked. Hardware recovery is the sole critical blocker.

## R9 sole physical campaign active - 2026-09-22 22:49 UTC

Root session16184 owns
`/workspace/OpenMitraStar/f367-campaign/f367r9-campaign-20260922T224919Z-91a7595c`.
Plan: `outputs/preflight/f367r9-campaign-20260922T224746Z/plan.json`.
Plan SHA256: `178f62662d01d20388f5e029bd54e452f45a84ce67829b4d0d5eecb1d46f13fa`.
640 source files plus the plan are frozen. UART nonce binding passed. Follow this
operation; do not compete with UART, lease, flash, watchdog or client activity,
and do not edit pinned files. The R9 image is5,468,160bytes, SHA256
`6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440`,
full-slot CRC4fa4640f. Mandatory return remains F365118901d4/store5d2ee646.

R9 is diagnostic only. It preserves the operational branches, return values,
admission and all CAC/NOP/HEALTH/watchdog deadlines. It adds bounded observations
of CSA, channel/hostlink waits, the actual shared calstate used by the wait,
clock/IRQ context and getter/snapshot boundaries. No inaccessible MuC global is
invented. qdrv was built twice identically; wlan was built once, with provenance
checked against the R8 peer.41 modules/1,981 imports resolve. Two image repacks
match; this does not claim a complete release rebuild from source.

The host remains R8 with R7 clock capture, V3 transport, phase2, UART2 and AELITA.
No previous bank was rerun. Collect this run's actual transition trace before
choosing a fix. CAC/client/NOP/RF and full port acceptance remain unproven.

## Next step: one bounded R9 transition capture - 2026-09-22 UTC

R8 remains closed and F365 verified at the boot below; no hardware owner is active.
The completed causal replay is
`outputs/preflight/f367r8-csa-hostlink-20260922T220822Z/result.json`
(SHA256 c95dcb4947b7930c100b8671e8df8e0be97e182d10d94cb4003a967258c61ab9).
It covers8 cases/13 assertions using actual CSA/channel/hostlink functions. DEFAULT
calstate is3, with a51-tick missing-ACK limit; calstate1 gives5001 ticks. IRQs remain
enabled and locks are released, but the wait does not sleep. Frozen jiffies stall
it only in the injected condition. None of this proves R8's physical reset cause.

The missing live calstate/caller/ACK/readback boundary cannot be reconstructed from
R8. Root therefore proceeds with one narrowly versioned R9 observation image, not a
blind R8 repeat or a claimed fix: bounded before/after markers around CSA/channel,
38/17/35 when applicable, radar context/readiness, getters and snapshot; safe clock,
IRQ/softirq and calstate observations. No policy, admission, CAC/NOP, watchdog,
HEALTH or operational deadline changes; no bypass of the normal CSA path.
Integrator owns caller/radar/controller integration; campaign agent implements the
agreed hostlink/peer-CSA trace transforms and then binds the exact new plan.
Only changed-module linking/composition, trace-specific checks and the fresh physical
gate are needed. Wait for the concrete artifact and plan; no R9 hardware run exists yet.

## R8 closed with F365; causal analysis split offline - 2026-09-22 22:00 UTC

R8 `result.json` is `FAIL_F367_WITH_F365_RETURN`, `control_timeout_enter-dfs`.
F365 platform27 passed22:00:59UTC; returned boot
`442a393d-5fdd-4652-8bbb-e559f0adbab5`.
Journal/configuration and protected CRCs match before/after; Ethernet, inactive
watchdog and containment pass. Session98034 closed exit1, UART is closed and the
lease is absent. No hardware operation is active. Reuse the immutable result and
partial command-return evidence indexed in `work/mission-state/GATES_BY_SHA.json`.

The reset cause remains unproven. Integrator owns the request/OCAC/readiness
interleaving analysis; campaign agent independently traces/reproduces the CSA
timer -> qdrv_set_channel -> hostlink/locks/ACK wait path. Context/radar/readiness
has no radar_start or synchronous *_sync joins on the traced path; that is source
evidence, not proof of the physical cause. A remaining candidate is synchronous
hostlink wait in softirq using jiffies and a calstate-dependent timeout multiplier.
Do not describe that hypothesis as confirmed, extend timeouts, bypass CSA/readback,
or create/reflash another image before a concrete cause and correction are ready.
MODE/FILTER/CHANNEL rc0 prove accepted commands, not actual52/20 readback or CAC.
DFS remains first; temperature/performance stay parked. AELITA tests were not reached.

## R8 commands accepted; reset before readback; return active - 2026-09-22 21:55 UTC

Root session98034 remains the sole hardware owner and is restoring F365.
Do not compete with its UART/lease/flash/watchdog or edit435 pinned inputs.
R8 `control/20260922T215455923643Z-enter-dfs.json` timed out after30.015s.
PREPARE52/TXoff passed (UARTseq9633); MODE11ac, FILTER20 and CHANNEL52 each returned0.
There was no subsequent CONTEXT_READBACK or ENTER_DFS marker. The exact blocking
getter/snapshot operation and the cause of the reset remain unproven.
Last diagnosis UARTseq9659 at host52507187ms was beacon release generation1647;
the U-Boot banner at52515593ms proves a reset8.406s later, not its cause.
STOP then returned255 after8.047s without a CEASE acknowledgement. No preserved
panic/HEALTH_FAIL/fault proves the cause. Final containment/return is still pending.

Integrator is analysing the actual post-channel getters/snapshot and CSA timer
callback through channel/context/readiness for a concrete lock/atomicity defect.
Do not repeat R8 unchanged, extend deadlines or bypass the readback. Previous mode,
clock, publication, lock and ACK fixes remain passed; no CAC/client/NOP acceptance
has been achieved. Acquisition reached29,111 jobs without recorded errors before
the transition. The campaign agent extracted local evidence only; root owns recovery.

## R8 sole physical campaign active - 2026-09-22 21:16 UTC

Root session98034 owns
`/workspace/OpenMitraStar/f367-campaign/f367r8-campaign-20260922T211614Z-acd0ba24`.
Plan `outputs/preflight/f367r8-campaign-20260922T211554Z/plan.json`, SHA256
`dbf0d1b3f673ef401907a2af1a2f296ce406bfa43ba17997b347082a63ee4eaa`.
435 sources plus plan frozen; UART nonce binding passed. Follow this operation,
never compete with its UART/lease/flash/watchdog/client path or edit pinned files.
Image SHA256 `7b65b3e66e5d5aafb3db25c0f0622503e4f38a7c1a56f50b97ff2c1969d6d234`,
5,468,160bytes, fullslot3da398dc; mandatory F365118901d4/store5d2ee646 return.

R8 changes the controller and four metadata/catalogue files only. The OEM setter
uses11ac, getter remains11ac20. Each mode/filter/channel command is issued once,
with safe rc markers; cached channel52/20 readback may complete asynchronously,
so it is observed within5s without changing any watchdog/CAC/NOP horizon.
Fault flags are checked before PASS.11 actual OEM parser/ifmedia/BW/getter checks
and5 helper cases pass (delayed success, timeout, late, fault, mode rejection).
Existing modules, native helper, R7 clocks/capture, V3/phase2/UART2/AELITA and prior
banks are reused. No CAC/client/NOP acceptance is claimed until this run proves it.

## R7 closed with verified F365; R8 setter correction resumed - 2026-09-22 20:59 UTC

R7 result is `FAIL_F367_WITH_F365_RETURN`, `control_failed_enter-dfs`.
Return platform27 passed at20:27:28UTC. F365 boot is
`7046ec00-d1d5-432f-83d7-67c475d98d47`; journal/configuration/Ethernet and containment
are verified. Session49831 has closed exit1, UART is closed, no lease remains,
no flash is in flight and no watchdog remains armed. These were checked on resume.
The R7 UART/clock evidence and its physical PREPARE52 PASS are indexed by SHA in
`work/mission-state/GATES_BY_SHA.json`; do not repeat the solved clock gate alone.

Integrator resumed the narrow R8 correction of the mode setter after interruption;
no R8 artifact or active build existed on resume. Campaign agent prepares only the
new binding and launcher against its forthcoming exact artifact and this F365
return. Preserve R7 files and all successful tests. Existing R7 host clock capture,
V3 observer, phase2, UART2 and AELITA dispatcher remain the qualified host path.
No new hardware operation is active. DFS/CAC remains first; temperature/performance
remain parked. Native acquisition is proven, but CAC/client/radarRF/NOP acceptance
has not yet been achieved.

## R7 PREPARE passed; mode20 failed; F365 return active - 2026-09-22 20:22 UTC

The existing root session49831 is restoring F365; do not compete with its lease,
UART, flash, watchdog or modify the415 pinned inputs until it closes.
R7 accepted PREPARE52: UART sequence9563 records
`OMF367_PREPARE target=52 bandwidth=20 tx-off-command=confirmed`, after ACK26.
Both quarantine clocks elapsed, 28,467 acquisition jobs and zero errors; no NOP
or transition was pending. Clock publication and PREPARE gates are now physically
passed. CAC has not begun and AELITA has not been switched to HGW.

Next command failed: `control/20260922T202157246996Z-enter-dfs.json` records
`OMF367_ERROR reason=mode20`, rc1/no timeout, after1.656s. The sealed helper calls
`iwpriv wifi0 mode 11ac20`; its stdout/stderr were discarded, so physical errno is
unknown. The real OEM parser accepts `11ac`, while its getter reports `11ac20`.
Integrator is reproducing that setter/getter mismatch and the subsequent actual
OEM command path before a narrow new shell revision. Do not repeat R7 unchanged,
weaken any timer/guard, or rebuild unchanged modules. DOTH/TPC commands returned
success by script flow, but no post-command readback was reached.

## R7 sole physical campaign active - 2026-09-22 19:44 UTC

Root session49831 owns
`/workspace/OpenMitraStar/f367-campaign/f367r7-campaign-20260922T194414Z-dbc07031`.
Plan `outputs/preflight/f367r7-campaign-20260922T194355Z/plan.json`, SHA256
`730e276d8f2c76ba1a06f3105d308673b0b739ebc327ae734ffea070fa727c3e`.
415 sources plus plan are frozen. UART nonce binding passed. Follow this process;
do not start another UART/flash/watchdog/client operation or modify pinned inputs.
Image SHA256 `5cd4118bc84061da24f917b99978477c85a405dba613743d6398ba2894a7e28c`,
5,468,160bytes, fullslot fa7d80ee; exact F365118901d4/store5d2ee646 return retained.
R7 changes only conservative clock publication and discriminating fields plus
bindings/metadata. PREPARE predicates and all deadline producers remain unchanged.
The28 clock checks and maximum1515/4096-byte JSON check pass; prior banks reused.
`clock-progress.json`/`clock-snapshots.jsonl` preserve paired clocks from the first
sample, while the original phase2/V3/UART2/dispatcher and horizons are unchanged.
No CAC/client/NOP acceptance is yet claimed.

## R6 closed with F365 return; R7 clock publication in progress - 2026-09-22 19:29 UTC

Root session36391 has ended. The sole physical operation is closed:
`/workspace/OpenMitraStar/f367-campaign/f367r6-campaign-20260922T184618Z-44555a4f/result.json`
is `FAIL_F367_WITH_F365_RETURN`, `control_failed_enter-dfs`.
F365 returned at boot `bdaa516c-f61f-4f0a-bd94-c243f8c4ecdb`, platform27 PASS,
with journal/configuration/Ethernet and containment verified. UART is closed,
no flash is in flight, no watchdog remains armed and no lease retention is required.

R6 physically passed the real OEM publication and readback of channel52 active/DFS,
including the readback immediately before PREPARE. Native acquisition reached
28,588 jobs with zero errors and no readonly retries. The displayed1800s quarantine
elapsed, but PREPARE52 rejected with `prepare-policy-clock-nop-or-transition`,
errno -16. This is before CAC or client testing. Cleanup ACK26 follows the rejection.

The source proves that remaining time was published from ktime alone, while
PREPARE requires both the ktime and jiffies deadlines. The offline actual-producer
replay reproduces this mismatch and passes u32 wrap; physical clock drift is NOT
measured by R6. Its snapshot lacks the discriminating paired-clock/transition fields.
Integrator is preparing R7: conservative remaining=max(ticks,ns), paired-clock and
exact rejection fields, with admission predicates, timers and horizons unchanged.
Campaign agent prepares only the corresponding host capture and exact new plan.
Do not repeat R6 unchanged or weaken either clock guard. Reuse prior publication,
static-helper, ACK, lock, observerV3, phase2 and UART2 evidence by SHA.
Temperature and performance remain parked; AELITA has not been switched to HGW.

## F367r6 static-helper campaign active - 2026-09-22 18:46 UTC

Root session36391 owns the sole hardware operation:
`/workspace/OpenMitraStar/f367-campaign/f367r6-campaign-20260922T184618Z-44555a4f`.
Plan `outputs/preflight/f367r6-campaign-20260922T184513Z/plan.json`, SHA256
`2de3fc2b646a7d0afc10bcef27887930ea7b73af28c892ca55abac216d365605`.
266sources+plan frozen. Do not compete with UART/flash/watchdog/client activity.
Image dfcf24b67d4494608c0228fcf69895748309222bde9849678808872e3986a332,
5,464,064bytes/fullslote98fe8f2; exact F365118901d4/store5d2ee646 return preserved.
Direct nonce binding passed; normal guarded execution is in progress.

This image changes only the target-proved static helper and metadata from R5.
R5 host/regulatory publication/readback, observerV3, phase2, UART2, dispatcher
and every timer/guard are reused. No previous bank was rerun. First physical
gate is actual PROFILE_PUBLISHED plus52 active/DFS readback before quarantine;
then the unchanged CAC/client/software-radar/NOP campaign and F365 return.
Follow this run, not older consumed plans or the failed dynamic R5 image.

R6 has now physically passed publication and initial readback. The activation
receipt `control/20260922T185346326470Z-activate.json` exits0 in45.610s and records
one OEM_SUBIO14 publication of52, DFS/PASSIVE1 and active_mask_unchanged1.
`regulatory-publication.json` is PASS_CAPTURED_OEM_PROFILE_PUBLICATION;
`regulatory-initial-readback.json` is PASS_INITIAL_TARGET52_READBACK with
present/active/DFS1, radar0 and publication-window closed after native start.
The live campaign is in boot-quarantine on36/BW80 with acquisition running and
no recorded errors. CAC/client/NOP remain pending; do not interrupt or duplicate.

## F367r6 static-helper image sealed; new campaign plan pending

Private `analysis/f367r6-fullimage-20260922T184150Z/result.json` is
`PASS_OFFLINE_F367R6_STATIC_PROFILE_IMAGE`.
Image5,464,064bytes, SHA256
`dfcf24b67d4494608c0228fcf69895748309222bde9849678808872e3986a332`;
manifestf5c9c2ab463cb4a754db6d6db4323a5ee16ba5f3f42204eaca019429c550ff01;
fullslote98fe8f2/prefix39823816, store5d2ee646/F365118901d4 unchanged.
Exactly helper+four metadata/catalogue files change from R5. Source/header,
qdrv/provider/engine/kernel/DT/supervisor and all shell logic remain identical.
The extracted helper is static and its exact binary already passed root's
invalid-argument execution probe on the HGW; publication/CAC are still unrun.

Campaign agent is binding the next exact plan. No physical operation is active.
Last accepted F365 boot is1f93e581-5e61-478c-a647-9d1ea6bcd22e. Reuse successful
evidence; never reflash the R5 image with unavailable dynamic dependencies.

## R5 helper loader absent; static R6 helper passes target execution - 2026-09-22 18:40 UTC

Root session47422 closed exit1. R5 result:
`/workspace/OpenMitraStar/f367-campaign/f367r5-campaign-20260922T182530Z-4dae16f0/result.json`,
`FAIL_F367_WITH_F365_RETURN`, `control_failed_activate`.
All19 installed hashes passed, but exec reported om-f367-dfs-profile not found.
The image contains that ELF; its PT_INTERP /lib/ld-uClibc.so.0 and required
libc.so.0 are absent. This is an image dependency defect, not radar failure.
No regulatory publication/readback, native start, CAC or client test occurred.
F365 returned at boot `1f93e581-5e61-478c-a647-9d1ea6bcd22e` with platform27,
store/configuration/Ethernet/containment PASS; no owner/flash remains active.

Integrator built the exact same C/header source statically with the proven
noatomic sysroot. Helper25,524bytes SHA
`f7c678995b205577690502351504e54268cb5ffcbf1c5010cadeab3162063f92`;
no PT_INTERP/PT_DYNAMIC/DT_NEEDED/llock/scond, two identical builds.
Root executed this exact helper in a new private RAM fixture using the invalid
argument probe, which exits before kernel/state/socket/radio operations.
PASS/RC0, expected helper exit1/errno22, no stderr; fixture removed.
Receipt `outputs/handoff-live/f367r6-static-probe-20260922T183941Z/result.json`,
SHAa700450d7f2ada90973472c40f8980a5312299d95ba3e29b25eede5a6f387636.
The integrator is composing R6, changing only helper linkage and metadata;
regulatory logic/tests, qdrv, provider, timers and all prior PASS are reused.
No further R5 installation; next gate requires the new R6 artifact and plan.

## F367r5 regulatory publication campaign active - 2026-09-22 18:25 UTC

Root session47422 owns the sole physical operation:
`/workspace/OpenMitraStar/f367-campaign/f367r5-campaign-20260922T182530Z-4dae16f0`.
Plan `outputs/preflight/f367r5-campaign-20260922T182355Z/plan.json`, SHA256
`dab054c8f54911feb7f7e630d31431061a72fb43e944a98d23d42a30fcd98263`.
247sources+plan frozen. Do not compete with UART/flash/watchdog/client activity;
follow this run's result, semantic UART2 and host-observation receipts.
Image9a4364491804a3bc6cddc43a5970b39ee94efc93f30583532aebcd3ccc4753d1,
5,464,064bytes/fullslot131f097e/prefix67c86213. F365118901d4/store5d2ee646 remain
the exact mandatory return/preservation targets. Direct nonce binding passed.

R5 uses the real OEM subio14 int{52} producer exactly once before native enable;
GETCHANLIST/GETCHANINFO verify an identical32-byte active mask and unchanged
records except DFS/PASSIVE added to52. Initial host gate checks target52
present/active/DFS1 and radar0 before the long wait. Readback repeats before
PREPARE without re-publication. This is not the MARKDFS test parameter and does
not change NOP, power, country, active channels or CAC.21 producer/lookup/sysfs
checks and3 real-helper routes pass offline;3 host receipt/readback delta checks
and default launchers pass. Prior V3/fase/lock/ACK/driver/engine evidence is reused.
No physical classification/CAC/client/NOP acceptance is claimed until this run.

## Full quarantine passed; required DFS classification missing; F365 safe - 2026-09-22 17:31 UTC

Root session87456 closed exit1. Result:
`/workspace/OpenMitraStar/f367-campaign/f367r4-observe-v3-20260922T164636Z-35e95209/result.json`,
`FAIL_F367_WITH_F365_RETURN`, `control_failed_enter-dfs`.
R4 completed initial1800s quarantine with27,398 jobs, zero hardware/engine/control
faults and no readonly retries. First PREPARE52 returned1 in1.437s, before CAC.
No AELITA Wi-Fi change or client/NOP test occurred. STOP/CEASE and return succeeded.
Current accepted F365 boot: `cd2b1c61-a4a2-49d6-8c99-cc3b2302a0d0`; platform27,
store/configuration/Ethernet/containment PASS. No active lease/flash;218pins released.

The deterministic missing step is the OEM publication of ic_chan_dfs_required:
region alone does not mark52 DFS when that mask is empty. The current helper
never invokes SIOCDEV_SUBIO_SET_MARK_DFS_CHAN; default52 lacks CHAN_DFS and the
PREPARE guard rejects. The exact NULL-versus-unmarked rejection branch was not
logged, so do not invent it. Integrator continues a new narrow implementation
through the real regulatory producer, preserving active-channel capability,
calibration, ES, NOP and all timers; no test MARKDFS/CAC bypass or synthetic flag.
Actual52 active+DFS readback must pass during bootstrap before the long quarantine.
No further unchanged R4 runs until this configuration defect is corrected.
Reuse all prior PASS by SHA. Root alone performs any next hardware gate.

## V3 completes quarantine; PREPARE52 classification gap found; return in progress

Root session87456 / `f367r4-observe-v3-20260922T164636Z-35e95209` completed the
full1800-second initial quarantine with27,398 native jobs, zero errors/faults
and zero readonly retries. The first enter-dfs at17:25:23UTC returned1 in1.437s,
without timeout: `OMF367_ERROR reason=prepare52`; CEASE/STOP were accepted.
Failure is `control_failed_enter-dfs`. No CAC/client/DFS transmission followed.
The original runner is restoring F365; do not compete with its hardware lease.

Integrator traced a deterministic omitted OEM configuration step. Region21317
sets country724 and invokes mark_dfs, but CHAN_DFS is added only for channels
already in ic_chan_dfs_required. The actual native helper and enter-dfs never
publish that required-channel classification through
SIOCDEV_SUBIO_SET_MARK_DFS_CHAN. The default52 record lacks CHAN_DFS. PREPARE52
refuses absent/inactive/mode-filtered or unclassified52; the captured receipt
does not distinguish its NULL versus !CHAN_DFS branch. Do not assume MMIO/ACK
failure or remove the admission check.

Next correction is narrowly scoped to the real OEM regulatory producer and
readback of supported/active52 classified DFS before PREPARE, preserving ES,
calibration, NOP and all timers. No test MARKDFS/CAC shortcuts or synthetic
flags. Integrator is locating the existing userspace interface; all218 current
pins and R4 artifacts remain unchanged while return is active.

## R4 readonly-observation guard V3 campaign active - 2026-09-22 16:46 UTC

Root session87456 owns the sole physical operation:
`/workspace/OpenMitraStar/f367-campaign/f367r4-observe-v3-20260922T164636Z-35e95209`.
Plan `outputs/preflight/f367r4-observe-v3-20260922T164511Z/plan.json`, SHA256
`80e9f59fd994135a80be384d53479c4b434722c63ad220aca825363fda16cfbd`.
218sources+plan frozen; do not compete with this UART/flash/watchdog/client run.
Exact R4 D8ea image,5,459,968bytes/fullslotf21df41c, remains unchanged;
F365118901d4/store5d2ee646 are the verified return/preservation targets.

Host-only V3 adds typed redacted guard receipts and at most one retry of a
complete readonly state/owner sample after a contained local guard timeout.
It discards partial state and repeats all guards/epoch checks. Real guard
rejections, source/identity/route faults, mutations and uncontained processes
are not retried. All existing phase/session/CAC/NOP deadlines remain bounded
and unchanged. Six focused tests and both default commands passed offline.
Source review confirmed thread-local operation scopes and no nested retry;
unavailable SSH process provenance is recorded as unknown rather than guessed.
Follow this process; starting it is not CAC/client/NOP acceptance.

## Read-only host guard timeout; firmware stayed healthy; F365 returned - 2026-09-22 16:32 UTC

Root session6029 closed exit1. Result:
`/workspace/OpenMitraStar/f367-campaign/f367r4-phase-v2-20260922T155328Z-78b94a41/result.json`,
`FAIL_F367_WITH_F365_RETURN`, `TimeoutExpired`.
During initial quarantine the last snapshot had14,334 jobs, zero hardware,
engine/control/TX faults; owner remained active with the same absolute deadline.
STOP/CEASE succeeded. No CAC/DFS entry/client/NOP trial was reached.

The exception is strongly localized to the30-second PowerShell context guard:
it is the only sampling call that propagates raw subprocess.TimeoutExpired;
SSH status/owner timeouts are translated to named Failure values. The37-second
gap fits sleep5+hashing+guard30, but no receipt identifies the exact PS subcommand.
Do not label this a radio/firmware failure or shorten any kernel timer.

F365 returned at boot `66b4b270-7e58-467a-8e51-7b002970e2c3`, platform27,
store/configuration/Ethernet and containment PASS, no pending flash/owner.
208sources+plan released; old plan consumed. Campaign agent is preparing a new
host-only observation wrapper: typed redacted receipts and at most one contained
timeout retry of a complete readonly sample with fresh guards/epoch validation.
No retry of mutations/flash/control or failed identity/hash/route checks, and
no deadline extension. FirmwareR4 D8ea and its qualification remain unchanged.

## R4 campaign with phase-aware host gate active - 2026-09-22 15:53 UTC

Root session6029 owns the sole physical operation:
`/workspace/OpenMitraStar/f367-campaign/f367r4-phase-v2-20260922T155328Z-78b94a41`.
New plan `outputs/preflight/f367r4-phase-v2-20260922T155028Z/plan.json`, SHA256
`adb70a34b0fc9c3120798bd7a19cfc4347a192d223b151bb1a1ef35d844ec061`.
208sources+plan are frozen; do not compete with this UART/flash/watchdog/client
operation. Firmware is the exact same R4 D8ea image,5,459,968bytes/fullslotf21df41c;
no binary, timer or runtime setting was changed for the host correction.

Only the initial36/BW80 phase before any confirmed DFS entry permits DOTH/TPC0,
with no CAC/NOP/injection history and mandatory configured/ES/EU/live acquisition.
After helper enter-dfs returns verified success, flags1 remain mandatory including
fallback36/NOP. READY/generation may be0 on nonDFS36; valid CAC and DFS TX still
require readiness and a positive generation. Source proves the fallback path
preserves DOTH/TPC. Six affected host tests and default CLI checks PASS; unchanged
campaign timers/rejections/client code are reused. Exact F365 return remains
mandatory. Follow this run's progress.json and campaign-progress.json.

The phase-aware run has now passed activation and entered boot-quarantine.
Observed at hostmonotonic31440937ms: channel36/BW80, configured/ES/EU1,
DOTH/TPC0 as expected before DFS, native511jobs with zero errors/control/TX
faults, quarantine1754383ms remaining. The owner continues the actual30-minute
startup quarantine before entering52/CAC; no CAC or client result yet.
This is ongoing hardware work, not a reason to start another task or test.

## R4 activation passes; host phase predicate corrected next; F365 safe - 2026-09-22 15:41 UTC

Root session7567 closed exit1. Immutable result:
`/workspace/OpenMitraStar/f367-campaign/f367r4-campaign-20260922T152707Z-9f9627a7/result.json`,
`FAIL_F367_WITH_F365_RETURN`, error `regulatory_context_changed`.
ACK17/26 normalization and full activation passed; initial36/80 snapshot has
native289jobs, hardware ready/started, zero errors and verified active owner.
The global host predicate wrongly demanded DOTH/TPC1 before enter-dfs.
Firmware already stages them in the correct order before channel52/readback.
No new firmware is required for this correction.

F365 returned at boot `cc25fdd6-25da-45f9-bf1f-5ddd61920475`; platform27,
store/configuration/Ethernet and containment PASS. No flash/owner remains active;
198sources+plan released, and the prior one-use plan is consumed.

Campaign agent is preparing new host files/plan with phase-aware validation.
Initial36/80 can retain DOTH/TPC0 and authority-ready/generation0, while ES/EU,
configured state and live fault-free acquisition remain required. Channel52,
CAC and DFS TX must retain all strict controls/readiness. Integrator is confirming
the exact producer behavior of DOTH/TPC on fallback36/NOP before any additional
host invariant is imposed. Reuse R4 image D8ea and existing PASS by SHA; no rebuild.

## F367r4 physical campaign active - 2026-09-22 15:27 UTC

Root session7567 owns the sole hardware operation:
`/workspace/OpenMitraStar/f367-campaign/f367r4-campaign-20260922T152707Z-9f9627a7`.
Plan `outputs/preflight/f367r4-campaign-20260922T152045Z/plan.json`, exact SHA256
`1fbdb0beb6e2cab23f0d3b36395d5590daac44d5c86beda6dfb0585b0154551e`
(cab23, not cabb23).198sources+plan frozen; do not compete or modify them.
Candidate d8ea968d3bebfb81725a862b345a8c443b20f16501bfdb1db96435eb4903c805,
5,459,968bytes/fullslotf21df41c; F365118901d4/store5d2ee646 preserved.

Earlier preflight session35168 at15:22 failed its UART nonce observation before
worker launch, plan consumption, reboot or flash. It released all resources.
Read-only SSH confirmed the same F365 boot, active ttyS0 and healthy unique COM3.
One fresh retry of the unconsumed plan passed the unchanged exact nonce binding;
no timeout/identity guard was relaxed and no USB/device reset was used. The
current process has printed its run directory and continues the normal campaign.
Watch the existing result/semantic UART2; do not start another run.

R4 activation has now passed in36.625s: confirmed ACK17/26 raw1→0, active owner,
native acquisition289jobs and zero pipeline/control/TX faults. The first
native-and-quarantine snapshot is36/BW80 with configured/EU/ES1, DOTH/TPC0,
provider_ready0/generation0. The host stopped with `regulatory_context_changed`
because its predicate required DOTH/TPC too early. Runtime setters exist and
match their actual producers: enter-dfs does PREPARE52/TXoff, DOTH1, TPC1,
mode/filter/channel52 and readback. NonDFS36 intentionally disables detection
authority while diagnostic acquisition stays live. No firmware change is needed.
Campaign agent is correcting only host phase validation in new files: initial
36/80 may retain those defaults; ES/EU and live acquisition remain mandatory,
and DFS52/CAC/service require controls/ready as defined. Do not weaken globally.
STOP/CEASE succeeded; the original runner is returning F365. No CAC or client
connection happened and no new hardware run may begin before this one closes.

## F367r4 confirmed-ACK candidate sealed; campaign plan pending

Private result `analysis/f367r4-fullimage-20260922T151701Z/result.json` is
`PASS_OFFLINE_F367R4_HOSTLINK_ACK_IMAGE`.
Image5,459,968bytes, SHA256
`d8ea968d3bebfb81725a862b345a8c443b20f16501bfdb1db96435eb4903c805`;
manifest49212304d4ee05b3f9899ad6baedd1609dd1d17a41b785da8aba21618c98ef25;
fullslotf21df41c/prefix7b848f5f, unchanged store5d2ee646/F365118901d4.

Only qdrv_hostlink.c behavior changes: selected channel17/deferred35/XMIT26
callers receive zero only for completed DONE without ERR. Negative returns,
ERR2/3, pending timeout and dead-MAC without publication remain failures.
Other callers retain their raw bitmasks and ownership/retention behavior.
The physical cmd38 trace was preceding context, not itself proof that opcode38
was the failing request. The failing XMIT consumer's raw1 is independently
preserved.23 focused actual producer/consumer checks pass; root reviewed the
negative-return and completion guard. qdrv doublebuild/import qualification PASS;
provider/kernel/engine/supervisor and R3 shell logic are reused (loader hash bound
to the new qdrv). No extra radio or regulatory change.

Campaign agent is binding the new exact plan; no hardware run is currently active.
Last accepted F365 boot is8bcb8b5e-a012-434b-855c-57150a540fb2. Execute only the new
sealed plan with full UART2 capture and mandatory verified F365 return.

## F367r3 advances through VAP; hostlink ACK mismatch found; F365 returned - 2026-09-22 15:02 UTC

Root session30024 closed exit1. Result:
`/workspace/OpenMitraStar/f367-campaign/f367r3-campaign-20260922T144531Z-57498cc6/result.json`,
`FAIL_F367_WITH_F365_RETURN`, transport error `control_timeout_activate`.
Actual ARM/preamble/keeper ACK/module-load/core-start/VAP phases passed; lock
cleanup and protected preamble are physically demonstrated. The next failure,
in radio-nondfs, is HLcmd38 status0/rc1, then xmit-stop-unconfirmed and
channel-command fault with TX admission closed. The keeper reacts afterward.
Native-radar, CAC, AELITA connection/traffic and NOP were not reached.

Source identifies completion bitmask DONE=1/ERR=2, incorrectly consumed by the
new `if(rc)` error checks. The dead-MAC early path also returns1 without sending,
so blind acceptance is forbidden. Integrator is preparing the next minimal
version to normalize confirmed completion only for channel/direct/deferred/XMIT,
retaining all real failures and other API conventions. No unchanged R3 retry.

F365 returned at boot `8bcb8b5e-a012-434b-855c-57150a540fb2` with platform27,
store/configuration/Ethernet and containment PASS. No flash/owner remains active;
181sources+plan released. All historical results remain immutable and the ledger
records startup success separately from the later radio failure.

## F367r3 physical campaign active - 2026-09-22 14:45 UTC

Root session30024 owns the only hardware operation:
`/workspace/OpenMitraStar/f367-campaign/f367r3-campaign-20260922T144531Z-57498cc6`.
Plan `outputs/preflight/f367r3-campaign-20260922T144408Z/plan.json`, SHA256
`ae5e407e7b2f566c77a2480ae5b273cae2660632cff50ab0e803ad1d9ef7f1d8`.
181sources+plan are frozen. Do not compete with UART/flash/watchdog/AELITA;
follow the existing process and its new semantic UART2 capture.
Candidatea9d6283c383f65a0f02ea37c7624910b461e6e48adbf49c678b274af34b3f53c,
5,459,968bytes/fullslot3def6860; returnF365118901d4 and store5d2ee646.
This new candidate fixes the unavailable-rmdir lock lifecycle and retains the
protected preamble. Actual target cleanup and existing offline PASS are reused.
The campaign still requires real bootstrap/CAC/client/NOP evidence and automatic
F365 return; starting it is not physical acceptance.

This run has passed the previous blocking path: ARM, preamble, fresh keeper ACK,
module-load, core-start and VAP creation; it reaches radio-nondfs. The first fault
is now HL command38 status0/rc1 (UARTseq1753), then
`OMF338DFS xmit-stop-unconfirmed rc=1 action=deny-reenable` and
`OMF367_FAULT reason=channel-command error=1 tx-admission=closed` atseq1756.
HEALTH_FAIL/control_fault and keeper exit follow as reactions. Native-radar/CAC
and AELITA traffic were not reached. Do not treat rc1 as errno or as success
without checking the producer ABI. Integrator is doing that bounded source review.
Activate hit240s transport timeout; the original runner is restoring F365.
Do not interrupt it or modify its181frozen sources.

Producer review has established QTN_HLINK_RC_DONE=1 and ERR=2: the owned ioctl
sender returns this completion bitmask after waiting. The new `if(rc)` consumers
mistake a valid DONE for failure. The dead-MAC early path also returns1 without
publication, so accepting all raw1 values would be unsafe. Integrator is preparing
a new minimal producer adaptation for channel/direct/deferred/XMIT only:
confirmed DONE without ERR becomes0, while dead-MAC/timeout/ERR remain failures.
The rest of the hostlink API must keep its existing return convention.

## F367r3 owned-lock correction sealed; final campaign plan pending

New result: private `analysis/f367r3-fullimage-20260922T143805Z/result.json`,
`PASS_OFFLINE_F367R3_OWNED_LOCK_IMAGE`.
Image5,459,968bytes, SHA256
`a9d6283c383f65a0f02ea37c7624910b461e6e48adbf49c678b274af34b3f53c`;
manifest22d3ee5485ca30606b79981ec7b7ab6ab70c4874a2f9d9d1db58620ca9a5289e;
fullslot3def6860/prefix1389675d, unchanged store5d2ee646 and F365118901d4.
Only stage lock lifecycle changes from R2; R2 protected preamble, all binaries,
HEALTH5s, total90min, CAC70 and NOP1800 are unchanged.
Exact lock release passed on HGW's ash;8 affected IPC tests cover no-rmdir PATH,
12 concurrent HEALTH calls, ownership/symlink/foreign-entry protection and rm
failure returning74. Existing successful gates are reused by SHA.

dfs_physical_campaign is binding a new plan with semantic UART R2 and the
qualified client dispatcher. No F367r3 physical run is active yet. Do not use
the old F367 or the physically incompatible F367r2. Root will execute the new
plan when sealed and always return to exact verified F365.

## Concrete lock-cleanup dependency found; do not flash F367r2 - 2026-09-22 14:26 UTC

Root confirmed through pinned HGW SSH, read-only: `rmdir` is not found and
`/bin/busybox rmdir --help` reports `rmdir: applet not found`. Both F367 and
F367r2 stage scripts acquire `ipc-lock` with mkdir but their EXIT trap invokes
rmdir and suppresses its failure. The directory remains after BEGIN and blocks
keeper/verify lock acquisition. This is a concrete missing target dependency;
the delayed-keeper reproduction did not cover it.

Do not flash F367r2 SHA d106f448...: composition remains offline PASS, but target
lock-cleanup compatibility is NO_GO. No F367r2 plan was sealed or executed.
Integrator is preparing F367r3, retaining R2 protection and changing only the
owned private lock cleanup using target-supported operations with explicit
failure. Tests must omit rmdir and cover actual IPC/concurrent lock behavior.
Campaign preparation waits for the new immutable image; no repeated banks or
binary builds. F365 remains the last accepted image, with no active hardware job.
The dated capability receipt is under `outputs/handoff-live/f367-rmdir-capability-*`
and is linked from `work/mission-state/GATES_BY_SHA.json`.

At14:33UTC root executed the exact new release_lock function under the HGW's
`/bin/ash`, only on a new private test directory. PASS/RC0/no stderr; the fixture
was removed and no watchdog/radio/MTD/preexisting data were touched.
Receipt `outputs/handoff-live/f367r3-lock-probe-20260922T143309Z/result.json`,
SHA b211f67850e14413837f6a2c6ebc9292f139dceba7bae3d3cbf4f66f7f4f5ea5.
The exact probe SHA is3f6184f1080e6e9f8a212a16a58f4ed58ac96823c5bc76366effdc13a6446eca.
Integrator can compose the new R3 after its affected IPC/concurrency checks;
do not repeat the successful target capability probe.

## F367r2 protection correction sealed; new plan being bound - 2026-09-22 14:20 UTC

No physical owner/lease or hardware campaign was active on this refresh.
F367r2 is sealed at private `analysis/f367r2-fullimage-20260922T134401Z/result.json`:
`PASS_OFFLINE_F367R2_PROTECTED_PREAMBLE_IMAGE`,5,459,968bytes, SHA256
`d106f448ba0bff1b4a7d2eaa28434cc36f518ce8c4fd17e5312a9a080a2c08ed`;
manifestc2ba47c911d135bfdfcfc317cac6182025a3f5fff13da0cbef9aed2360d1d659,
fullslot12ff8ce9/store5d2ee646. This is a new shell revision, not another
unchanged F367 retry. Kernel/qdrv/provider/engine/supervisors are identical.

The actual old helper prefix with delayed keeper reproduces the same refusal
while its30-second phase is still valid; the new prefix passes that case and
rejects a missing keeper. Readonly preamble now has its own30-second phase,
foreground HEALTH checkpoints and a required fresh keeper ACK before module-load.
HEALTH5s, module-load30s, total90min, CAC70/NOP1800 remain unchanged.
This proves a protection gap, not the unique cause of physical keeper delay.
Detailed source/test bindings: `docs/OPENMITRASTAR_F367R2_PROTECTED_PREAMBLE.md`.

dfs_physical_campaign is binding the new exact plan with full UART R2 capture,
the qualified AELITA dispatcher and mandatory F365 return. Root alone will run it
when sealed; reuse existing PASS by SHA and do not rebuild tested binaries.
Current last verified F365 boot remains86c21b2b-91ac-4c48-84fd-48d387083b42.

## Exact bootstrap refusal captured; F365 safe again - 2026-09-22 13:25 UTC

Root session95770 closed exit1. Result:
`/workspace/OpenMitraStar/f367-campaign/f367-capture-r2-20260922T130816Z-c6771b0b/result.json`,
`FAIL_F367_WITH_F365_RETURN`, `control_timeout_activate`.
Semantic UART sequence1217 preserves the actual reason:
`OMRADIO5_REFUSED reason=f367-watchdog-not-protecting-module-load`.
This is the first module-load watchdog verify; literal phase names agree.
Expiry of HEALTH5s is not yet proved. Integrator is reproducing the actual helper
preamble with IPCv2 and the initial state lacking qdrv/provider, omitted by the
earlier test. Keep guards, HEALTH and CAC/NOP timers intact in the correction.

F365 returned with platform27/store/configuration/Ethernet/containment PASS;
current boot `86c21b2b-91ac-4c48-84fd-48d387083b42`. No flash or owner is active;
160sources+plan released. No AELITA Wi-Fi change, CAC or NOP test occurred.
The one-use repeat is consumed: do not repeat unchanged F367 again. Next artifact
must incorporate a demonstrated bootstrap correction and reuse prior PASS inputs.
Root remains the only physical operator. Existing acceptance of R3 acquisition
remains valid; temperature/performance are still parked.

## One F367 repeat with corrected UART capture active - 2026-09-22 13:08 UTC

Root session95770 owns the sole physical operation:
`/workspace/OpenMitraStar/f367-campaign/f367-capture-r2-20260922T130816Z-c6771b0b`.
One-use plan `outputs/preflight/f367-capture-r2-20260922T130600Z/plan.json`, SHA256
`eaccfd2b512357f6c4b0b4d268b311c541e8f1c3b7e72c96ec507c81c658f886`.
The160sources+plan are frozen. Follow this process; never rerun its consumed plan
or start competing hardware work. The only new input is host UART capture:
`uart-semantic-r2.jsonl` preserves redacted bootstrap refusal/OMF367/guard evidence
before the old filter. Incomplete capture cannot produce PASS.

Image F367 remains exactly SHA447f94aa1be95b1ba52a47d206978bc8a359e3c57e7435d475a3e49b9cb28aa0,
5,455,872bytes/fullslot6f77010f. Existing firmware qualification is reused;
no rebuild or repeated firmware test bank. Actual F365 baseline before this run:
boot19f112a8-ae00-4c10-b6b2-21059aa35582, fullslot118901d4/store5d2ee646.
Return to exact F365 remains mandatory. Do not infer the prior refusal from
redacted lengths/hashes. This single repetition obtains the missing reason;
no further unchanged retries are authorized by this plan.

The new capture has now preserved the exact refusal at semantic sequence1217:
`OMRADIO5_REFUSED reason=f367-watchdog-not-protecting-module-load`, host monotonic
21406046ms. The failure is the first watchdog verification before module load.
Integrator is preparing a new revision of the bootstrap protection contract,
distinguishing expired HEALTH lease from an invalid verification; retain HEALTH5s,
guard checks and all CAC/NOP deadlines. Do not change the active160source pins.
The same F367 image must not be retried again after this diagnostic repeat.

## F367 stopped before CAC; F365 returned safely - 2026-09-22 12:57 UTC

Root session79469 closed exit1. Its immutable result is
`/workspace/OpenMitraStar/f367-campaign/f367-campaign-20260922T124015Z-42362ab0/result.json`:
`FAIL_F367_WITH_F365_RETURN`, error `control_timeout_activate`.
F367 installation, boot and client read-only preflight passed. Activation emitted
ARM_ACK, BEGIN module-load and `OMF367_ERROR reason=native-bootstrap`.
UART observed reboot19.235s after phase start and a fresh prompt26.188s after;
SSH waited for EOF until its210-second timeout. Bootstrap refusal and SSH shutdown
are separate findings. The exact refusal text was redacted by the old UART layer;
do not reconstruct it from line lengths/hashes or attribute a hardware fault.
No CAC, client Wi-Fi change, software radar or NOP trial occurred.

F365 returned at boot `19f112a8-ae00-4c10-b6b2-21059aa35582` with platform27,
store/configuration/Ethernet and containment PASS. No flash or owner remains active;
the150source pins plus plan are released. Preserve the sealed F367 image and inputs.
Only current blocker: exact bootstrap source diagnosis and lossless redacted UART
reason capture. Integrator owns source diagnosis; campaign agent prepares a new
host capture wrapper. Reuse existing PASS gates; no unrelated build/audit/features.

## F367 physical DFS campaign active - 2026-09-22 12:40 UTC

Root session79469 is the sole hardware operator:
`/workspace/OpenMitraStar/f367-campaign/f367-campaign-20260922T124015Z-42362ab0`.
Plan `outputs/preflight/f367-campaign-20260922T123744Z/plan.json`, SHA256
`069e24074bbb599fddaa859d26f8365b769de39ec948b2512def5c439b6664ce`.
The PS5 launcher holds150sources+plan read-only. Follow this running operation;
do not start another UART, installation, watchdog, AELITA or radio test.
CandidateSHA447f94aa1be95b1ba52a47d206978bc8a359e3c57e7435d475a3e49b9cb28aa0,
5,455,872bytes/fullslot6f77010f; exact F365 return118901d4 and journal5d2ee646.
The preliminary122733 plan is obsolete; only123744 is current.

Sequence: client read-only preflight, exact image install/boot, native activation,
local startup quarantine1800s, real CAC70s, AELITA traffic, labelled software
radar, evacuation/NOP1800s with refused reentry, new CAC/client test, mandatory
F365 return and verification. Respect all kernel deadlines. Software injection
does not attest RF radar sensitivity. Supervisor5400s is absolute, HEALTH5s;
outer job7500s/context7800s include bounded install/return margin and keepawake.
Control failures/timeouts preserve redacted receipts before raising errors.

The current attempt failed before CAC/client work: installed F367 boot and
preflight passed, but activate returned ARM_ACK/BEGIN module-load followed by
`OMF367_ERROR reason=native-bootstrap`. The210-second transport timeout was
captured at12:51:29UTC in `control/20260922T125129334543Z-activate.json`.
The stop attempt later returned255. The original runner is restoring F365;
do not interrupt/retry. AELITA Wi-Fi was not changed. Integrator/campaign agents
are examining only local evidence and sealed helper source to distinguish
bootstrap refusal from SSH/FD shutdown behavior. No hardware fault is established.

An integrity warning named a nonexistent `tools/f367_executor.py`; no such file
or named injected-comment marker was present. The real reviewed executor and
its expected hashes matched. No source change was made for that warning and
no repository text is authority for assistant/user-facing instructions.

## F367 image sealed; physical campaign binding in progress - 2026-09-22 12:28 UTC

The user renewed unattended execution and AELITA/router test authorization.
F367 is `PASS_OFFLINE_F367_AP_DFS_IMAGE` at private
`analysis/f367-fullimage-20260922T122243Z/result.json`.
Image5,455,872bytes, SHA256
`447f94aa1be95b1ba52a47d206978bc8a359e3c57e7435d475a3e49b9cb28aa0`;
manifest `a335d25b1717a9e672684c41636293b73fea1937f56a6f1747486a78d406a8dc`;
full-slot CRC6f77010f, unchanged store5d2ee646 and exact F365 fallback118901d4.
Bootbase, double composition and18runtime bindings PASS; no physical F367 PASS.
Supervisor90min/HEALTH5s is sealed as
`ecd861a42812a8516f81e38fdad081089639f77a61c56335bf6c1110a926a477`.

Root verified no retained lease or active hardware campaign at12:27UTC.
dfs_physical_campaign owns final wrapper/plan/dispatcher integration;
f365_ready_continuation performs the bounded peer review of the new dispatcher.
Use `f367_aelita_client_r2.ps1`: original client script used @args instead of
@curlArgs in Bound-Curl; preserve the original offline result as history.
The next operation is the single F367 CAC/client/software-radar/NOP campaign
with automatic F365 return when the exact plan is sealed. Do not repeat R3.
No temperature or performance work. See `docs/OPENMITRASTAR_F367_AP_DFS_CANDIDATE.md`.

## Native acquisition accepted; F365 returned; F367 implementation active - 2026-09-22 11:47 UTC

The R3 native acquisition gate is accepted by the immutable correction:
`outputs/acceptance/f366r3-acquisition-addendum-20260922T114659Z/result.json`,
SHA256 `9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87`.
Status `PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM`.
The original campaign `FAIL_F366_WITH_F365_RETURN` is preserved unchanged:
its sole error was the evaluator confusing START_ATTEMPT with actual API entry.
The helper extracted from the exact sealed image proves setter235/80 before
the API; live guard admits80, then the real API marker appears.20 samples,
jobs20 to358 (+338), hardware_ready=1/started=1, no pipeline errors.
ready=0/callbacks=0 is intentional compiled/load authority0, not failed acquisition.
No repeat flash was performed to correct the evaluator.

Root session36806 closed exit1 because of that original evaluator outcome.
Actual reset was observed and F365 returned with platform27, store/config/ETH,
disabled thermal state and containment PASS. Current F365 boot is
`4b8201d8-96ba-481d-a7ca-e10d5e86000e`; no retained physical lease or flash in flight.
All136 open plan/source handles have closed. Preserve their historical contents.

One next blocker: functional F367 AP DFS control. Offline dfs_current_integration
owns qdrv/provider/channel52-BW20-filter20/CAC70/TX/NOP1800 and composition;
dfs_physical_campaign owns the bounded long supervisor/health/deadline/physical
runner. They coordinate disjoint files, and root remains sole hardware operator.
Authority-enabled composition must bind this acquisition proof and the new exact
supervisor; no physical F367 candidate is ready yet. Initial1800-second quarantine
remains conservative local policy while persisted NOP is not integrated.
No CAC/NOP/RF-radar/client/traffic/release acceptance follows from acquisition.

AELITA wired control `.63`/Ethernet6 and main-router Wi-Fi internet reference
are ready. Offline client bundle is
`outputs/preflight/f367-aelita-20260922T113429Z/result.json`, SHA256
`a9b563b137d87f39c51a31f0f5c6e0186f44c60f1d215a82c4c6a115b2b0ab0e`;
image/proof binding and root integration remain pending. Temperature/performance
remain parked. Existing results are indexed in `work/mission-state/GATES_BY_SHA.json`.

## F366r3 acquisition active - 2026-09-22 11:30 UTC

Root session36806 owns the only hardware operation:
`/workspace/OpenMitraStar/f366-acquisition/f366r3-acquisition-20260922T113036Z-f847269a`.
Plan `outputs/preflight/f366r3-acquisition-20260922T112913Z/plan.json`, SHA256
`4690a4d0f21aa6f3ad062ce9da38ec130e6024fd972c2b026e0fab9305a9b154`.
The PS5 wrapper holds135sources plus the plan open read-only throughout the run.
Candidate `ca66ddf07a6a1ef4470a77ca85c4151354e9d7dd831abc7e5f02c1a53a8b5d2d`,
5,451,776 bytes; full-slot CRC94ddd37e; exact F365 return CRC118901d4;
journal CRC5d2ee646. No other UART, flash, watchdog or HGW radio work may run.
Follow the existing process/result; do not restart or interfere with it.

Live acquisition completed20 samples with338 additional completed jobs,
hardware_ready=1, started=1, applied/request generation7/7, callbacks=0 and no
recorded pipeline faults. Guard UART admitted AP36/radar-filter80 before the
single real native API entry. The preliminary evaluator reports only
`radar_filter_not_before_enable`: it mistakes the earlier START_ATTEMPT helper
intent marker for actual API entry. The sealed loader sets235/80 before
`control_set`; the campaign agent is preparing a separate source/event-bound
correction, preserving the original FAIL result. Do not reflash unchanged R3
to repair this evaluator. Exact F365 return is still in progress; no overall
PASS or F367 build authorization from this provisional observation alone.

`work/mission-state/GATES_BY_SHA.json` indexes the existing results by image SHA.
Reuse unchanged PASS inputs. The one current blocker is observable native
acquisition with authority0; F367 higher functionality remains unbuilt/disabled.
AELITA `.63` wired SSH is verified with strong-host send/receive; its current
Wi-Fi `.50` has a source-bound HTTPS200 reference through the main router:
`outputs/handoff-live/aelita-wired-and-internet-reference-20260922T112644Z/result.json`.

## F366r3 ready offline; AELITA wired control recovered - 2026-09-22 11:25 UTC

F365 remains the accepted live baseline; no HGW hardware run is active yet.
F366r3 is sealed at private `analysis/f366r3-fullimage-20260922T112259Z/result.json`:
5,451,776 bytes, SHA256 `ca66ddf07a6a1ef4470a77ca85c4151354e9d7dd831abc7e5f02c1a53a8b5d2d`,
full-slot CRC `94ddd37e`, unchanged journal CRC `5d2ee646`. Root is preparing
the exact acquisition/always-F365-return plan. The new revision restores the OEM
RADAR_BW235/80 setter before native enable and records numeric RAM guard reasons.
`ic_radar_bw` is radar-filter configuration, not the operating channel width.
No native acquisition or DFS acceptance PASS is claimed yet.

AELITA SSH recovered at Wi-Fi `.50`. The earlier ICS/DHCP repair rollback failed
with HRESULT0x80040201; it must not be reported as successful. A subsequent
non-destructive ActiveStore-only alias `.63` on Ethernet6 became Preferred and
passed pinned-key SSH identity/local-address/interface verification:
`outputs/handoff-live/aelita-wired-probe-complete-20260922T112443Z/result.json`.
The keep marker was written only after that wired proof. Remote stage is
`/workspace/user-home/AppData/Local/Temp/openmitrastar-wired-probe-20260922T112418Z`.
The alias is temporary until reboot/explicit cleanup; Wi-Fi/profile and other
addresses remain unchanged. Use `.63` for control during later Wi-Fi testing,
with canonical historical pinned SSH keys; `.50` is the original Wi-Fi route.
No further user SSH-recovery action is needed at this point.

R2 reset review confirmed an observation false negative: the existing matcher
missed `Info: Quantenna U-Boot` 7.922s after CEASE. New offline R3 observer records
the same UART bytes without adding commands or I/O. This corrects observation;
R2 acquisition remains FAIL and no RF radar detection is proved.

## F366r2 closed; native activation guard rejected, F365 operating again

`/workspace/OpenMitraStar/f366-acquisition/f366r2-acquisition-20260922T103601Z-339fcd03/result.json`
is `FAIL_F366_WITH_F365_RETURN`. Session7782 ended1; F365 return platform27,
configuration/store/ETH and containment pass, no flash in flight or retained lease.
Current returned boot: `bbe5034f-d8a8-44fc-9433-7851e4ff6bcb`.128pins released.
The result reports zero reset signatures/watchdog_reset_observed=false, with no
software_recovery flag or serial recovery command. Fresh Bootbase and inactive
watchdog were observed; the capture agent is checking this observation discrepancy.
Do not call that a proven watchdog failure or pass without the additional review.

Actual UART captured `qdrv_control_input_serialized: ERROR - Failed to execute
command "radar" (10)` and `control-native-radar-enable-reply`.10 is the command
table index, not errno. Source shows this handler returns negative only from the
new guard; the void radar-enable API is not reached on that path. Investigate
native_wlan/opmode/current-channel/radar-bandwidth contract, not a guessed hardware
fault. Integrator prepares the next minimal revision with concrete guard evidence;
F367 operational DFS remains blocked on successful acquisition.

DFS remains the first objective. AELITA SSH recovery is still pending the user's
source-scoped firewall/start-service command after the Ethernet adjustment;
temperature work remains parked. No HGW hardware campaign is active at this point.

## F366r2 native-start trial active - 2026-09-22 10:36 UTC

Root session7782 runs the second acquisition trial:
`/workspace/OpenMitraStar/f366-acquisition/f366r2-acquisition-20260922T103601Z-339fcd03`.
Plan: `outputs/preflight/f366r2-acquisition-20260922T103420Z/plan.json`,
SHA5f435c556124d46fe3042fbb788b15a519a87dd3ef708f31768a838e19094ea5.
All128sources frozen. Exact candidate SHA
c260249e2633e6e90b775ea51c25b68b1771ff3f340f54f652ef967e83fcbb07,
5451776bytes, full-slot CRC64db5015; automatic F365 return CRC118901d4;
store remains CRC5d2ee646. One exact native radar enable in AP36/BW80, authority0,
bounded watchdog, capture revision2. Do not run competing HGW hardware work.

AELITA remains reachable at layer2 and WinRM5985, but SSH is unavailable after
the Ethernet repair attempt. Default WinRM credentials were rejected by the
client's TrustedHosts policy; no TrustedHosts/security relaxation was made.
The user has a concise request to start sshd and add an SSH rule restricted to
controller192.168.1.49. Wait for recovery before further client network changes.
No AELITA SSID change or Wi-Fi client test has been attempted yet.

## DFS first: F366 acquisition failed safely; F366r2 ready, client SSH recovery pending

F366 run `/workspace/OpenMitraStar/f366-acquisition/f366-acquisition-20260922T095127Z-2149c8c9/result.json`
closed with `FAIL_F366_WITH_F365_RETURN`. Provider/engine loaded, but started/ready/
dirty/polls/jobs stayed0 in20samples. Source investigation found the missing
`radar enable eu` call and the sequential guard that would reject it after VAP.
This was not evidence of a hardware failure. F365 returned via watchdog with
platform27PASS, store/config/ETH preserved, no owner armed and all helpers closed.
Session1692 ended1;117pins are released. Boot: `ca1efdbd-fdfb-4c2b-a89e-8c786487bba8`.

F366r2 image is offline PASS at private
`analysis/f366r2-fullimage-20260922T101619Z/result.json`:5451776bytes,
SHAc260249e2633e6e90b775ea51c25b68b1771ff3f340f54f652ef967e83fcbb07,
full-slot CRC64db5015. It permits one exact diagnostic radar-enable after VAP,
waits for asynchronous readiness/first job, and keeps authority0/ch36/BW80.
Campaign agent is binding a new plan with capture_revision2 and complete redacted
stdout/stderr/UART evidence. F367 AP/CAC/NOP work remains offline and blocked on
real successful acquisition; no CAC/NOP shortening or DFS authority bypass.

AELITA was located by its previously pinned SSH host key at192.168.1.50 (Wi-Fi17).
Windows computer name is APELSITO, account aelita; this differs from local APPLESITO.
Ethernet6 had duplicate192.168.1.36 and orphaned ICS private192.168.137.1, Public
profile while the existing SSH firewall rule applied only to Private. Read-only
evidence: `outputs/handoff-live/aelita-control-routing-20260922T095330Z/result.json`.
The wired repair backed up state and armed SYSTEM rollback after3minutes, kept
Wi-Fi settings untouched, disabled orphaned Ethernet sharing and requested DHCP.
DHCP did not become ready within35s. Result:
`outputs/handoff-live/aelita-wired-repair-20260922T101939Z/result.json`.
Remote backup/task: `/workspace/user-home\AppData\Local\Temp\openmitrastar-wired-20260922T101847Z`,
`OpenMitraStar-Wired-Rollback-20260922T101847Z`. No keep marker was written.
SSH subsequently became unreachable; client .50 still answers ARP and WinRM5985.
Do not assume rollback succeeded or alter the client further blindly. A user
question requests starting sshd and a source-scoped SSH firewall rule. Core HGW
DFS work can continue independently while client access is recovered.

## Current priority: finish DFS; AELITA and Wi-Fi/internet tests authorized

The user explicitly made DFS the first objective and confirmed that AELITA is
available again, connected by Ethernet to the same internet-providing switch.
Wi-Fi/client and internet tests are now authorized. Preserve AELITA's wired
management while using Wi-Fi for the test path; the main router may be used as a
connection/reference, but its configuration is not in the mutation scope.
Temperature work is parked. Do not replay the former Wi-Fi deferral.

F365 installation completed PASS:
`/workspace/OpenMitraStar/f365-evidence/f365-install-20260922T092314Z-5d42e11f/result.json`.
Platform27, Ethernet identity, config/journal and cached diagnostic revision365
pass; sensor still disabled with no sensor MMIO. Boot
`19976fc4-d962-4c51-8c0d-f526b9d1a016`, kernel #358; full-slot CRC118901d4,
store CRC5d2ee646. Session49135 ended0, no hardware job/owner remains active,
94pins released. No F365 sensor activation has been run.

New offline agents: dfs_current_integration composes F366 native DFS on this
F365 baseline, preserving F355 lifetime/thermal/Ethernet/persistence; agent
dfs_physical_campaign owns the new root-executed acquisition/guardian/return
runner and subsequent CAC/NOP/client plan. Both are offline only. First F366
acquisition is non-DFS36/80 with authority0; later functional DFS gates must be
real and must preserve regulatory timing/transmission restrictions. Classifier
injection is not RF radar detection. Root remains the only physical operator.
The heartbeat prompt is updated to this DFS-first priority and current test scope.

## F365 data diagnostics installation active - 2026-09-22 09:23 UTC

Root session49135 is installing F365 using the accepted F364r3 fallback.
Plan: `outputs/preflight/f365-install-20260922T092141Z/plan.json`,
SHA5916674167d33bc617fc2bf0214f4978186b02c7ffe4100be775da77e1fcddb9.
All94source pins are frozen. Candidate full-slot CRC118901d4, fallback F364r3
CRCd7a19077, preserved sequence2 store CRC5d2ee646. No competing hardware access.
Kernel/DT/qdrv are unchanged; only the sensor diagnostics and matching helper/
catalog metadata differ. Install acceptance reads cached data only, never enables
or samples the sensor. A separate bounded activation follows after installation.

Post-F364 healthy network reference was also captured without mutations:
`outputs/handoff-live/f364-network-reference-20260922T092159Z/result.json`.
It is a reference for the unresolved intermittent management-loss issue, not a
root-cause determination or a completed stability soak.

## F364r3 accepted with stable Ethernet verification - 2026-09-22 09:21 UTC

Installation PASS: `/workspace/OpenMitraStar/f364-evidence/f364-install-20260922T091253Z-c2ba449c/result.json`.
Platform27, stable DT/netdev/IRQ/bridge/carrier checks, config and journal pass.
Boot `633bea1d-6732-42f7-968c-f82b96468f72`; full-slot CRCd7a19077; store CRC5d2ee646.
Session25364 ended0; hardware lease/UART/awake hold closed,87pins released.
The connected management port passed1MiB each direction with matching hashes:
`outputs/handoff-live/f364-management-stream-20260922T092114Z/result.json`.
Second physical connector and simultaneous forwarding remain untested.

The earlier loss of Ethernet while Linux/RX remained active is an unresolved soak
issue, not a proven driver regression. A source review found no evidence sufficient
to choose an L3/bridge drift or driver-stall patch. Keep that uncertainty explicit.
F365 image is already offline PASS; the offline continuation agent now binds its
installer to this accepted F364r3 result. Root remains sole hardware operator.
Temperature remains ETIMEDOUT/unaccepted and Wi-Fi/client tests remain deferred.

## 2026-09-22 09:13 UTC: management recovered, corrected F364 installation active

After the user's request to continue, SSH still timed out. Fresh UART output then
identified the live F352 eth0/eth1 driver on the expected HGW, despite loss of
network management. One serial BREAK+b reboot recovered F363r2 autonomously:
`outputs/handoff-live/hgw-serial-recovery-20260922T091008Z/result.json`.
SysRq dispatch/reset/new Linux/SSH ready all confirmed, watchdog inactive;
boot `7984b1ad-84d8-4461-9374-322b14ca9d56`. No flash or Bootbase commands in recovery.
The earlier narrow-signature attempt sent no BREAK or b and is not a reboot.

The stable Ethernet verifier passed live on F363r2, using bound DT properties,
driver/IRQ/bridge/carrier rather than a dmesg message:
`outputs/handoff-live/f364-stable-ethernet-20260922T091229Z/result.json`.
eth0=MAC1/PHY3/IRQ20 without carrier; eth1=MAC0/PHY1/IRQ19 with carrier.

Heartbeat `continuar-port-hgw-linux-5-10` is ACTIVE again.
Root session25364 now runs the prepared F364r3 installation with an awake hold:
`outputs/preflight/f364-install-20260922T085231Z/plan.json`,
SHA971d3d1a9c5e013b9e1bb5486c4c58e35596c9c2801589c75a6a8f729eadf4c0.
All87pins frozen; candidate full-slot CRCd7a19077, fallback F363r2 CRCb8f8acc1,
store CRC5d2ee646. Do not start competing hardware work or interrupt a write.
F365 image/templates remain ready offline and await actual F364 acceptance.

## 2026-09-22: verifier corrected; hardware unreachable, continuation paused

The F364r3 attempt ended with `ethernet_dt_probe_mapping`: platform27, watchdog,
store and config had passed, but the old Ethernet checker required a historical
printk string in dmesg. The missing string does not establish a hardware failure.
The automatic F363r2 return completed: boot `4900bcf2-d0d7-4579-8ac6-8b352d439431`,
platform27PASS, preserved store, no flash in flight and all handles contained.
Session34589 ended1 because acceptance failed; no hardware job remains active.

New `tools/f364_ethernet_identity.py` checks each bound netdev, parent DT node,
DT property hashes, live IRQ, bridge membership and carrier; no dmesg dependency.
Existing recovery code is untouched. Six targeted identity checks plus the seven
existing F364 checks pass. The generator also preserves the correction.
Ready plan: `outputs/preflight/f364-install-20260922T085231Z/plan.json`,
SHA971d3d1a9c5e013b9e1bb5486c4c58e35596c9c2801589c75a6a8f729eadf4c0,
87pins, exact F364r3 image unchanged. This plan has NOT been executed.

Current connectivity observations: PC Ethernet18 is Up at1Gbps,192.168.1.49/24,
but SSH to192.168.1.90 timed out twice. Exact FTDI PnP device is present asCOM3.
Win32_SerialPort alone missed it; use the existing PnP fallback, not that incomplete
query, for presence. Passive recovery RX observed zero bytes for20seconds, sent
zero UART bytes, requested no reboot, and closed the port/lease. No flash today.
Evidence: `outputs/handoff-live/hgw-recovery-rx-20260922T085045Z/result.json` and
`outputs/handoff-live/hgw-resume-connectivity-20260922T085416Z/result.json`.
Do not claim that the device is powered off or still running: its current state
is unverified. An input question about power/cabling is pending with the user.

Heartbeat `continuar-port-hgw-linux-5-10` is PAUSED under its explicit stop-on-user-
dependency policy. Resume after the user clarifies/restores device connectivity;
begin with a fresh read-only SSH identity and do not repeat completed builds.
F365 image remains offline PASS at private `analysis/f365-fullimage-20260921T215511Z/result.json`.
Its derivation preserves the stable Ethernet import; F365 templates still await
a corrected physical F364 acceptance. Temperature remains ETIMEDOUT/unaccepted.
Current file-only audit: `outputs/audit/hgw-full-port-20260922T085450Z/result.json`.

## Active F364r3 lifetime installation - 2026-09-21 21:48 UTC

The instrumented sensor campaign closed safely: `FAIL_SENSOR_WITH_F363_RETURN`,
with exact `cat: read error: Connection timed out` (ETIMEDOUT inferred from the
message). Activation succeeded, but no valid temperature sample was produced.
Evidence: `/workspace/OpenMitraStar/f363-temperature-activation/f363-sensor-20260921T214213Z-12cff874/result.json`.
F363r2 returned autonomously via watchdog, platform27PASS and journal intact;
boot `0b06b631-4fc1-4bd1-8d37-ac544c655560`. Session85340 is closed, no owner armed.

Root now installs the independent F364r3 lifetime fix in session34589.
Directory: `/workspace/OpenMitraStar/f364-evidence/f364-install-20260921T214843Z-41c33dfa`.
Plan: `outputs/preflight/f364-install-20260921T214046Z/plan.json`,
SHA4ec18c628e437495a732095ca56d2144756b09b4ff6ffb99462b7045881f1ddb.
All84pins are frozen; candidate full-slot CRCd7a19077, fallback F363r2 CRCb8f8acc1,
unchanged sequence2 store CRC5d2ee646. Do not run competing hardware operations.

F365 now means temperature DATA diagnostics, not the postponed auto-start idea.
Watchdog and image agents prepare it offline on F364r3: cache first/last DATA,
poll count, elapsed time and errno from the reads already performed, with separate
hwmon/legacy records. No additional sensor MMIO, no mask/timeout/protocol change,
and explicit activation remains required. No F365 hardware authority or success
is implied by those offline files.

## Active instrumented sensor diagnostic - 2026-09-21 21:42 UTC

Root session85340 runs the instrumented one-activation campaign on unchanged F363r2.
Directory: `/workspace/OpenMitraStar/f363-temperature-activation/f363-sensor-20260921T214213Z-12cff874`.
Plan: `outputs/preflight/f363-temperature-activation-20260921T214010Z/plan.json`,
SHAdc130c4a84edcd3b7f34e5a6a22a9b5e5464f3525fa4845d849f522ca2b23fcd.
All85pins are frozen. The only new behavior is capturing the known sysfs cat stderr
before CEASE/reset; no extra sensor reads after an error, no flash or RF operation.
Do not interrupt a possibly armed owner or run competing hardware access.

F364r3 installation plan is ready but must wait for this campaign to close:
`outputs/preflight/f364-install-20260921T214046Z/plan.json`,
SHA4ec18c628e437495a732095ca56d2144756b09b4ff6ffb99462b7045881f1ddb.
It accepts only the proven safe inactive F363r2 return and retains the failed
temperature status explicitly; temperature is not an acceptance prerequisite for
its unrelated lifetime fix. Sensor completion and F365 remain open.

## Sensor activated but first sample failed; F363r2 returned safely

`/workspace/OpenMitraStar/f363-temperature-activation/f363-sensor-20260921T213150Z-f83f8f12/result.json`
is `FAIL_SENSOR_WITH_F363_RETURN`, error `sensor_sample_failed`.
The single activation succeeded (enabled1/attempted1/error0), but the first
temp1_input read failed and no valid samples were recorded. Temperature acceptance
remains OPEN. The earlier helper discarded cat stderr during reboot, so a new
userspace-only diagnostic will capture that exact error before another controlled
single activation. Do not repeat the old plan or guess the failing errno.

CEASE and watchdog-driven autonomous return succeeded without software fallback.
F363r2 platform27PASS, journal preserved, software sensor state inactive again;
boot `04fad133-90b7-4886-b98b-d3ed4686712e`. Session25473 ended1 because sampling
failed; no watchdog owner remains armed, UART/lease/helpers are contained and79pins
are released. The hardware agent prepares stderr diagnostics and the watchdog
agent reviews only the relevant sensor/OEM error paths. No hardware job is active.

F364r3 may be installed independently once a safe inactive F363r2 return is bound;
its identical inactive sensor does not require successful temperature acceptance.
Keep the FAIL sensor result explicit in that plan. F365 automatic activation stays
postponed until the actual sensor read issue is resolved.

## Active F363r2 sensor campaign - 2026-09-21 21:31 UTC

Root session25473 is running the single sensor activation with the existing
bounded watchdog owner and automatic reboot; do not interrupt a possibly armed owner.
Directory: `/workspace/OpenMitraStar/f363-temperature-activation/f363-sensor-20260921T213150Z-f83f8f12`.
Plan: `outputs/preflight/f363-temperature-activation-20260921T213105Z/plan.json`,
SHA052454ab0160ebd2d8a668b751811da2b381227aa55771c93a6bb4ef2c0bdd92.
All79pins are frozen, including F363 bindings. One experimental_enable write,
three independent sample pairs, CEASE and autonomous F363r2 return are planned.
No flash, RF, Bootbase command or repeated sensor activation is allowed in this run.
Do not start another hardware job until result and launcher containment close.

## F363r2 installed PASS; sensor activation preparing

Corrected installation passed:
`/workspace/OpenMitraStar/f363-evidence/f363-install-20260921T212301Z-7ea2a551/result.json`.
Platform27PASS including radio5 startup, both Ethernet netdevs and unchanged journal.
Boot ID `27fff22f-78ea-4196-bdb2-7c29c00ca6d1`; full-slot CRCb8f8acc1;
store CRC5d2ee646, slotB/sequence2. Sensor is registered but cached inactive0/0/-19.
Session7254 ended0, UART/lease/awake hold closed and80pins released.
Root is preparing the separate sensor campaign from this accepted result.
The sensor context/test fixture now bind the exact F363r2 product string.
F364r3 remains offline only until the sensor campaign returns successfully.

## Active corrected F363r2 installation - 2026-09-21 21:23 UTC

The original F363 attempt completed with `FAILED_F363_WITH_F362_AND_PRESERVED_JOURNAL`.
Its automatic return is PASS: F362 platform27, serial BREAK+b recovery, store intact,
boot `26e22e0c-d113-4240-aca9-e5f8c8235cd2`, helpers/port/lease closed. Session99507 ended1
because the candidate failed; recovery itself succeeded. No sensor activation occurred.

Root now runs corrected F363r2 installation in session7254 with awake hold.
Plan: `outputs/preflight/f363-install-20260921T212217Z/plan.json`,
SHA17949f41927dcd866b97bd1ae28c35765c9d663a7d4ce5a808abf155f1bd368d.
All80pins are frozen again. Candidate image SHAbe5073c2e3fca5b4a214513f3c7aeee42b463b760b8213bf55c12a6ccbc2c075,
full-slot CRCb8f8acc1; exact F362 fallback CRC1a6e28c0; store CRC5d2ee646.
This changes the radio-start admission of the legitimate S16-preloaded sensor;
kernel/DT/modules are unchanged. Do not run competing hardware access.

The only current F364 candidate is F364r3, private
`analysis/f364r3-fullimage-20260921T212001Z/result.json`, image SHA
ee6b7d09fd9e2dc5e0009d6756910510409ae13fb17108089a4caf7043056a15,
full-slot CRCd7a19077. Original F364 and F364r2 are NO_GO. F364r3 still awaits
F363r2 installation and the separate sensor activation/return acceptance.

## F363 failed startup acceptance; automatic F362 restoration active

F363 physical attempt `f363-install-20260921T210511Z-7e8c7914` passed writing,
readback, Linux boot and SSH/Ethernet, but platform acceptance failed: boot degraded,
radio5 stopped and wifi0 absent from br0. Radio2, API and protected storage checks
passed; no fatal marker was seen. The sensor was NOT activated or sampled.
Root session99507 is restoring F362 automatically (stage restore-f362 observed).
Do not interrupt or access the hardware concurrently. The final return result is
still pending;80source pins remain frozen until that session closes.
Watchdog agent diagnoses the F363 failure offline. F364r2 fixes its own startup
hash defect but still depends on this failed F363 baseline: do not install it
until that dependency is corrected. F365 preparation is postponed.

## F364 original image is NO_GO - correction pending

Do not install or seal a plan using F364 image SHA
`1e2d07de0aaee45295b7cd27e5418898d7ceeaa7a2e4060391f0695092da2857`
or `analysis/f364-fullimage-20260921T205724Z/result.json`.
Its radio-start helper retained the F363 qdrv hash and would reject the replaced
F364 module. The image agent is producing a new immutable corrected artifact;
the original is retained as failed qualification evidence. No F364 hardware action
was performed. Root's `f364_management_stream_probe.py` also needs binding to the
new image before use. F363's corresponding startup hash is correct and unaffected.

## Active F363 installation - 2026-09-21 21:05 UTC

Root session99507 runs the F363 installer with an awake hold.
Directory: `/workspace/OpenMitraStar/f363-evidence/f363-install-20260921T210511Z-7e8c7914`.
Plan: `outputs/preflight/f363-install-20260921T210430Z/plan.json`,
SHA6662675812ead958b27088169e183e942bedd7e9ee1b0552103ef1173e85d5f6.
All80source pins are frozen. Candidate F363 full-slot CRC2a855242, fallback F362
full-slot CRC1a6e28c0, preserved sequence2 store CRC5d2ee646.
Only physical mtd4 prefix writes are allowed; no sensor activation/RF during install.
Do not interfere with UART/lease/write or claim installation before final result.
F364 final offline image is already available at private
`analysis/f364-fullimage-20260921T205724Z/result.json`; its installer will be bound
after the F363 install and separate sensor activation/return result.

## F363 temperature image complete offline — 2026-09-21

Final result: private `analysis/f363-fullimage-20260921T204859Z/result.json`,
SHA `9948197f20c1875af08d39f9884c1a5321ae06c4f36ae25e845a716bf3d652cd`.
Image directory `firmware/f363-f362-temperature-diagnostic-device-bound`;
5,382,144 bytes, SHA `c8d49e9d44ff86e5045d4a28aa2e0a90dd68e8bb89c7fc3104f0b874e37ea26d`.
Manifest SHA `d16e034887c9c8f47c50352b71ec82126fa9108c79bf560ded64988c49a2e6c6`.
Product `lyoko-foundation-6.9.11-f363-temperature-diagnostic-device`, kernel #358,
F340 watchdog marker/supervisor preserved. Bootbase, prefix fit, two complete
compositions and catalog/inventory checks pass. Prefix CRC `da4b82d7`; full-slot
CRC with the preserved sequence-2 journal `2a855242`; store remains SHA fcbeb5ab...
and CRC `5d2ee646`. Exact F362 is the fallback.

Components: `/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/result.json`
(SHA `5036e7a5980a22c81c08506c1a77ba1af7ec3ceeeab69393e2d0bfdbb6d7bdf3`).
The F339 core/table/protocol is unchanged; only CONFIG_HWMON=m, resource split,
explicit activation wrapper and qdrv error guard are integrated. Cached default
state is enabled0/activation_attempted0/activation_error-19, with zero sensor MMIO.
Initial post-install checks must not read temp1_input/interval or enable it.
Physical activation is a separate root-owned F363 campaign; no new RF/WPS test.

qdrv retains the actual F321/F362 profile. The rebuilt WPS function uses the
correct kernel ABI offsets; the thermal worker has its guard. The apparent extra
qdrv_wlan_exit difference was only the WARN source-line immediate9170→9177,
verified against identical source and all other normalized code bytes. No exit
behavior change or F355 integration is included. See
`docs/OPENMITRASTAR_F363_TEMPERATURE_DIAGNOSTIC.md` for exact boundaries.

All F363 build processes owned by watchdog_linux510_port have completed. The
installer agent has received final image/manifest/module bindings; F364 has been
reactivated with the real F363 component and image results. Do not use historical
component202114Z or first image204653Z. No F363 hardware action was performed by
this agent. F362 remains the last accepted physical baseline until root records
an F363 installation result; root remains the sole hardware operator.

## Unattended continuation active

Heartbeat checkpoint 2026-09-21 20:37 UTC: no physical job or lease was active.
F363 build `/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z`
is running (host Python36816, WSL37652 at observation); kernel, hwmon and first
sensor build are produced, qdrv comparison and complete image are still pending.
The earlier202114Z build was abandoned after the NTFS build-location issue;
preserve it as historical evidence and do not consume it as PASS.
F363 installer templates are ready but unsealed. The hardware agent also prepares
`f363_sensor_*` for one guarded temperature activation after installation; this is
a F363 test campaign, not firmwareF364. F364 is reserved for the lifetime fix.
F364 source-combination preparation is complete and its builders await real F363
component/image PASS; watchdog agent will reactivate that agent when inputs exist.
No new firmware was installed during this checkpoint. Continue from actual build
results without repeating F362 installation/traffic or existing component suites.

Heartbeat `continuar-port-hgw-linux-5-10` is ACTIVE on this same task every10minutes.
It continues the previously authorized work and reports meaningful changes only;
the old F301/F306 automation remains PAUSED on its separate task.
At this handoff no physical job is running. F362 is the accepted installed baseline.
`watchdog_linux510_port` is building F363 temperature components/image offline;
`hardware_parity_inventory` has prepared F363 installer templates and must bind real
candidate hashes before sealing; `f362_image_fast` is preparing F364 lifetime-fix
integration on the actual F363 sources/image without touching its build inputs.
Root remains sole physical operator. Check agent/process state and preserve their
frozen inputs before continuing. Do not infer installation from an offline build.

## Current accepted baseline: F362 dual Ethernet installed and active-port traffic PASS

F362 installation completed with `PASS_F362_PRESERVED_JOURNAL`:
`/workspace/OpenMitraStar/f362-evidence/f362-install-20260921T201238Z-d650b1af/result.json`.
The exact image was read back and compared; protected partitions and sequence2
store are unchanged. Platform27PASS; both F352 netdevs belong to br0, with
eth0=MAC1/PHY3/IRQ20 (no carrier) and eth1=MAC0/PHY1/IRQ19 (carrier).
Boot ID: `a1365d73-9c70-48a9-ae6d-a06f6029e223`; kernel remains `#358 @1790006400`.
Source=journal, slotB/sequence2, active configuration SHA073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9.
F362 full-slot CRC1a6e28c0; store CRC5d2ee646 and SHA fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873.

One1MiBstream per direction over the connected management Ethernet passed with
matching hashes, unchanged boot, and no new RX/TX errors:
`outputs/handoff-live/f362-management-stream-20260921T202006Z/result.json`.
This proves the active eth1 management link; second-connector traffic and simultaneous
forwarding are not tested. Session26662 ended0, helpers/UART/lease/awake hold closed;
no hardware job remains active and73pins are unfrozen.

Next: F363 temperature diagnostic integration is being prepared offline, preserving
F362 and the committed journal. Its sensor activation must remain explicit; no
physical clock/conversion qualification is claimed from source-only evidence.
Wi-Fi/client/RF tests remain deferred. Full port status remains IN_PROGRESS.
Audit including active-port traffic: `outputs/audit/hgw-full-port-20260921T202305Z/result.json`.

## Active F362 installation - 2026-09-21 20:12 UTC

Root session26662 is running the exact F362 installer, with temporary awake hold.
Evidence: `/workspace/OpenMitraStar/f362-evidence/f362-install-20260921T201238Z-d650b1af/`.
Plan: `outputs/preflight/f362-install-20260921T201143Z/plan.json`,
SHA57501957cf30853b5b1e2f7b935430ca1aafea2cca0b1b516ab98c0e0ed735cb.
Its73source pins are frozen. The earlier201046Zplan is superseded and unused.
Candidate F362 SHA9582b92f1c68ec192ee14c55ba9ab69015749cc69ecde392bd6ad3392d105f2b;
full-slot CRC1a6e28c0, preserved sequence2 store CRC5d2ee646, fallbackF361 CRC815b9440.
Only the physical mtd4 prefix may be written. No competing hardware access or
interruption during erase/write. No installed/success claim until result.json and
launcher completion. Wi-Fi/client testing remains deferred.

## Current checkpoint: F362 image ready, physical UART recovery PASS

The single real serial BREAK+b recovery test passed on F361, without flash or
Bootbase commands. Evidence:
`/workspace/OpenMitraStar/f362-uart-evidence/f362-uart-20260921T200416Z-9cbb58e8/result.json`.
It observed SysRq dispatch and a fresh autonomous boot, then ready/journal
sequence2 with unchanged active configuration hash and inactive watchdog.
Current boot ID: `1d095c9b-425d-4c33-ba6a-c1cd42f11594`.
Session35562 exited0; serial reader/port, helpers, lease and awake hold closed.
This proves the responsive-kernel serial recovery path, not hard CPU/bus lock recovery.

F362 dual Ethernet image is offline PASS, 5,390,336 bytes,
SHA9582b92f1c68ec192ee14c55ba9ab69015749cc69ecde392bd6ad3392d105f2b.
Private result: `analysis/f362-fullimage-20260921T200242Z/result.json`.
Candidate full-slot CRC1a6e28c0 includes preserved sequence2 store CRC5d2ee646;
exact F361 fallback full-slot CRC815b9440. Physical installation remains pending.
Root is sole hardware operator; hardware agent prepares the installer offline.
Wi-Fi/client tests remain deferred. No changes to protected partitions or boot environment.

## Current accepted baseline: F361, normal SAVE and autonomous reboot PASS

F361 is installed from image SHA0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af.
Installation: `/workspace/OpenMitraStar/f361-evidence/f361-install-20260921T192436Z-34833167/result.json`,
SHA311a95e2a7a57237502ae28cb9ecd6b9f1f56c0c7417f349680b4762e6366d37;
platform27PASS, saved journal preserved and loaded automatically.

Normal production helper commit then passed, without ARM or automatic reboot:
`outputs/handoff-live/f361-normal-save-20260921T193655Z/result.json`.
Latest record is DD/slot1/sequence2, same 586-byte config SHA073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9.
Private complete store backup:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f361-store-seq2-20260921T193734Z/store.bin`,
SHAfcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873.
Current store CRC5d2ee646; F361 prefix CRC4cb7f99e; current full-slot CRC815b9440.
Do not reuse earlier sequence1 store/full-slot CRC assumptions.

Autonomous reboot (one SSH sysrq reboot, NO UART or Bootbase commands) passed:
`outputs/handoff-live/f361-autoboot-20260921T194036Z/result.json`.
Boot-ready, source=journal, sequence2, unchanged active config hash. Current boot ID
`be54167a-52f9-456b-b2ed-a6e7270255d3`. This is a normal reset, not a power-cycle test.
No hardware jobs remain active; sessions18717/68440 closed and pins are unfrozen.

Next F362 work: integrate only the qualified F352 dual Ethernet driver/DT/helper,
preserving the committed store and F361 fallback. Prepare/test supported UART
BREAK then b recovery before risking loss of SSH with a changed Ethernet driver.
Root remains sole hardware operator; all agents are offline. No new temperature,
WPS or radio changes in this image. Wi-Fi/client tests remain deferred.
F361 persists22managed settings; advanced/derived5GHz fields remain outside that scope.

## Active F361 normal configuration persistence installation - 2026-09-21 19:24 UTC

Root run: `/workspace/OpenMitraStar/f361-evidence/f361-install-20260921T192436Z-34833167/`.
Session **18717**, outer PID **34244**, temporary awake hold active; 83 pins frozen.
Plan `outputs/preflight/f361-install-20260921T192310Z/plan.json`, SHA-256
`102190fb0b1011b075f8b86b21b064336fa41b0ff945b469ac5b5d49420d4aca`.
Candidate F361: 5,378,048 bytes, SHA0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af.
Only physical mtd4 prefix is written. Preserve existing journal SHAa7620cf8f6a8a8764e082e524c1968915e0ad4b6810be939522deed67b0302a8,
store CRC31bf4416; candidate full-slot CRCedca3610, fallback F358 with journal CRC3e8db0dc.
The installer checks journal after erase and after boot, then F361_READY/source=journal,
slotA/sequence1, regenerated active.conf SHA073747... and backend parameters Y/Y.
No normal SAVE or boot path arms the watchdog or reboots automatically; no radio tests.
Do not interrupt an erase/write or run competing hardware access. No F361 installed
claim until this campaign completes; exact F358 fallback keeps the same journal.

## Current checkpoint: F360 real SAVE and retention PASS

`/workspace/OpenMitraStar/f360-evidence/f360-save-20260921T183947Z-b2328b27/result.json`
records **PASS_F360_CONFIG_SAVED_AND_PERSISTED**. The unchanged current config,
586 bytes / 26 keys, SHA073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9,
was saved once to DC slot0 sequence1, read back, and found byte-identical in a
private MTD-ROM capture after controlled reset and F358 boot. DD remains FF.
Firmware-prefix CRCdf453410 and all protected CRCs are unchanged; new store
CRC31bf4416, full-slot CRC3e8db0dc. Do not use the obsolete FF/full-slot4d006632
assumption in any later firmware update or return check.

Installed firmware remains F358, kernel #358, current boot ID
`9b3f258b-a9e8-49f2-a0bf-22c4ce1db14f`, platform27PASS, watchdog inactive.
Session11160 ended; UART, lease, children and awake hold are closed. No hardware
job is active and the96source pins are unfrozen. No radio/settings values changed.

This establishes real storage persistence, not yet automatic application of
saved settings at boot. F361 now integrates the journal into the real managed
configuration boot/load/save path, reading by MTD ROM at boot and retaining
fallback on invalid data without erase/format. The next installer must preserve
the committed journal and compute image+store CRCs rather than assuming FF.
Wi-Fi/client tests remain deferred. The full Linux5.10 port is still in progress.

## Active F360 first configuration SAVE - 2026-09-21 18:39 UTC

Root run: `/workspace/OpenMitraStar/f360-evidence/f360-save-20260921T183947Z-b2328b27/`.
Session **11160**, outer PID **34980**, awake hold active; 96 source pins frozen.
Plan `outputs/preflight/f360-save-20260921T183854Z/plan.json`, SHA-256
`a51e615604607331c4e623476feab801ff548030b3fb4d82d2c3e961454aec33`.
One SAVE of unchanged current active.conf (586 bytes), one LOAD/readback,
controlled reset and F358 return, then private MTD-ROM capture to prove retention.
Expected slot0/sequence1/DC CRC df278ed3, store CRC31bf4416, full-slot CRC3e8db0dc;
firmware-prefix CRCdf453410 and protected partitions must remain unchanged.
The former full-slot CRC4d006632 is no longer the success expectation after SAVE.
No automatic re-erase or second SAVE on failure. Do not interrupt a possible
program/erase or run another hardware operation. No Wi-Fi/settings changes.

## Current state: F358 installed, F359 identification PASS, first SAVE preparing

F358 installation completed successfully in
`/workspace/OpenMitraStar/f358-evidence/f358-install-20260921T175118Z-31a39fbd/result.json`
(SHA `3540e48cf0d0c7bd9bf8fd15a2029f7b0b95cb6c29ea8162c2fb5d6c1ac3d49f`).
Image bytes were compared, protected partitions/store preserved, platform 27/27.

F359 then observed the real flash successfully:
`/workspace/OpenMitraStar/f359-evidence/f359-observe-20260921T180806Z-10cd4f98/result.json`
(SHA `3fc6c70a53bfec5894a2b57f33ec53cf0708f8f429e76debdf33e62776182037`).
RDID c22018, control 4, status 0, security 0, common-BP0 supported. Exact 35F/36E
marking remains unknown but is unnecessary for the qualified common command path.
Clean release/unload, planned watchdog reset and F358 return passed; platform 27/27,
slot CRC 4d006632, watchdog inactive. Current boot ID:
`8267c82b-8332-4f70-9419-8fdbf31a361d`. Sessions 86623 and 22028 ended, UART/leases/
awake holds closed. No hardware campaign is active; all prior source pins unfrozen.

F360 prepares one real SAVE of the unchanged current managed configuration,
586 bytes / 26 keys, SHA `073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9`.
Private contract: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f360-config-contract-20260921T182515Z/manifest.json`.
Real F342 generation expects DC slot0 sequence1; DC CRC df278ed3, store CRC31bf4416,
new full-slot CRC3e8db0dc, unchanged firmware-prefix CRCdf453410. Do NOT require the
old full-slot CRC after the legitimate store write. No automatic erase or second
SAVE on failure: preserve the partial journal and backup, stop, return to unchanged
F358, and diagnose. F358 does not autoload/consume the backend on boot yet.
No configuration values, Wi-Fi behavior or management settings have been changed.

## Active F358 persistent installation - 2026-09-21 17:51 UTC

Root run: `/workspace/OpenMitraStar/f358-evidence/f358-install-20260921T175118Z-31a39fbd/`.
Session **86623**, outer root PID **25896**, temporary awake hold active.
Plan: `outputs/preflight/f358-install-20260921T175018Z/plan.json`, SHA-256
`4c17ad8d989cfa1e696ec277080d2ce0c7e997d5928db43d58312dba123c86f6`.
Its 75 source pins are frozen. Wrapper forces Windows PowerShell 5.1.

Candidate F358 is 5,361,664 bytes, SHA-256
`fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f`.
Target only physical mtd4/linux_live, erase prefix 0x7e0000+0x5e0000;
preserve store and mtd0/1/2/3/5. Exact F340 is the automatic fallback.
Do not interrupt a possible erase/write or open another UART/SSH campaign.
No backend autoload/ARM/programming at boot and no Wi-Fi/AELITA tests.
Do not claim F358 installed until readback, boot and management gates finish.

## Current checkpoint: F356 returned to F340; F358 fixes NO_XIP registration

F356 run `/workspace/OpenMitraStar/f356-evidence/f356-observe-20260921T172425Z-4e534b88/`
finished **FAIL_OBSERVE_WITH_F340_RETURN**. The RAM kernel #350 passed all 27
platform checks. OBSERVE returned ENODEV (-19), valid-mask zero, before sampling
ID/control/status/security. No flash programming occurred. The driver had no
claim or quarantine left. Root `root-return-acceptance.json` accepts the return;
result SHA-256 is `0311e0b2c0f144d37180604d2e98af73364601b70d1da9c50c25d45f3f775c0e`.

Installed/running baseline remains F340, new boot ID
`eeea6368-c6f8-4030-bcbe-ebeb5b11534c`. Return platform passes 27/27; protected
CRCs and full-slot `2aa26ca6` are unchanged. Watchdog inactive. Session 6809,
UART, lease, helpers and awake hold are closed; the 99 pins are unfrozen.

Confirmed cause: the real DT uses `no-unaligned-direct-access`, so physmap sets
`map.phys=NO_XIP`. F350 classified guards using that sentinel as a physical
address, leaving the views unguarded and the store unregistered. The name was
correct. Core is preparing F358 to resolve the actual DT resource while
preserving NO_XIP, indirect reads and disabled point mappings. The only new
regression check targets that real pipeline; unchanged suites are not rerun.

F357 full backend image was built but remains **NO_GO** because it contains
the affected F350 kernel. Next physical action is the corrected full F358 image,
with F340 fallback, following the owner's request for more flashing and fewer
repeated checks. No more F356 RAM attempts. All agents remain hardware-free;
root is the sole physical operator. Wi-Fi/AELITA tests remain deferred.

## Active F356 RAM observation - 2026-09-21 17:24 UTC

Root run: `/workspace/OpenMitraStar/f356-evidence/f356-observe-20260921T172425Z-4e534b88/`.
Session **6809**, Windows PowerShell 5.1 PID **21196**, temporary awake hold active.
Plan: `outputs/preflight/f356-windows-launch-20260921T172409Z/plan.json`, SHA-256
`74bdcb1d7142f4132ce123f3cf47116d412d7d5eb2846481a6a5c523290578e3`.
The same 99 source pins and 65 tests as plan 171932Z are frozen. No retesting
or new component changes were introduced by the launch envelope.

The first PowerShell 7 launch failed before starting the executor because of
DateTime conversion. Its prelaunch-failure.json is in the previous 172133Z run;
F340 boot ID was unchanged, no provider was loaded, and the lease was released.
The corrected launch uses the already-tested Windows PowerShell 5.1 runtime.

Scope: RAM kernel #350, programming-disabled F356 provider, exactly one OBSERVE
of ID/status/security, then controlled return to F340. No flash programming,
Wi-Fi/AELITA tests or deliberate CPU fault. Root remains the sole operator.
The owner has requested faster physical progress and fewer repeated checks;
reuse unchanged qualification and keep only necessary image/recovery gates.

## Current physical checkpoint: F354 PASS, F340 healthy - 2026-09-21 16:50 UTC

`outputs/handoff-live/f354-passive-20260921T164639Z-3afe11b8/result.json`
records **PASS_F354_PASSIVE_CONTROL_READ_AND_F340_RETURN**, SHA-256
`478099ad7875da93fc1ea05ef06373c71e2d3d800bf77b3c873fb26526d1573b`.
Root `root-acceptance.json` passes 15/15. The exact F347 module observed Linux
SYSCTL map `00007fbf` and SPI_CONTROL `00000004`: one read each, zero writes,
four UART markers, successful unload. These are raw register observations,
not flash-part identification or acceptance of a write provider.

Planned watchdog CEASE/reset and direct F340 return completed. Five protected
CRCs and slot `2aa26ca6` are unchanged; platform 27/27, watchdog inactive.
Current verified boot ID: `2ae319b4-05c7-4752-9b9c-46deebf1327d`.
Session 70093 exited zero; UART, lease, helpers and temporary awake hold are
closed. No physical job is active, and the 93 source pins are unfrozen.

F356 is being prepared offline: RAM boot of the exact F350 kernel, a supervisor
that validates that kernel, and one journal-provider OBSERVE operation with
programming disabled. The provider is being copied to F356 to reject an
unexpected RDID before any vendor security-register command; F350 artifacts
remain immutable. No F356 hardware operation is authorized by this document.
Root retains the existing owner scope and must verify the concrete artifact
and applicable execution gates. F355 independently fixes qdrv lifetime offline.

## Active F354 corrected-loader SPI observation - 2026-09-21 16:46 UTC

Root run: `outputs/handoff-live/f354-passive-20260921T164639Z-3afe11b8/`.
Tool session **70093**, root PowerShell PID **28484**, temporary awake hold active.
Plan `outputs/preflight/f354-passive-20260921T164435Z/plan.json`, SHA-256
`ae10485d3c4b957652e4e8eb6d2b22a7267972a748126321eaa4cc98deab077c`;
70 offline tests and 93 frozen source pins. Root review:
`outputs/preflight/f354-root-review-20260921T164558Z/result.json`.

Uses exact existing RAM loader to pass `execute_read=1` in one finit_module,
same F347 observer and F340 watchdog owner. Two passive register reads only,
then CEASE/reset and read-only return. No flash write, TFTP, Wi-Fi/AELITA or
deliberate CPU fault. Do not repeat the observer or open competing UART/SSH
operations. Live state may change to Bootbase during controlled cleanup.
F355 continues offline in its own directory; all shared F354 inputs are frozen.

## Current checkpoint: F349 failed in loader response, F340 recovered

`outputs/handoff-live/f349-passive-20260921T162050Z-0cb97d7b/result.json`
is **FAIL_PROBE_WITH_F340_RETURN**, error `probe_fields`. Its original result
is immutable and does not prove an SPI_CONTROL observation or a hardware fault.
The independent return review is `root-return-acceptance.json` in that directory:
12/12 checks, protected CRCs unchanged, slot CRC `2aa26ca6`, platform 27/27,
watchdog inactive. Current verified boot ID:
`4703e018-c53f-4b03-8b64-eda8adb9a15e`, kernel `#340 @1790006400`.
Session 49964 ended; UART, lease, helpers and temporary awake hold are closed.

Read-only loader evidence is under `outputs/handoff-live/f349-loader-identity-20260921T162837Z/`.
The installed BusyBox SHA is `537b409a13db65380cebff31a24b2cfe8d9ebe38678b35fe6c205db080c5773d`.
Its exact disassembly passes an empty module-parameter string: `execute_read=1`
did not reach the F347 init. A separate negative load without parameters returned
the expected EACCES, without opening UART/arming watchdog or changing boot ID:
`outputs/handoff-live/f349-loader-negative-20260921T162706Z/result.json`.
F354 is being prepared with the already-included single-syscall RAM loader;
no new active SPI observation has started. Do not reuse the consumed F349 plan.

F344 components are delivered offline with incomplete mode-transition parity:
`outputs/handoff/f344-mode-components-20260921T162648Z/manifest.json`.
F350 provider qualification and F351 CLI are complete offline. F352 dual-port
Ethernet packaging and F353 reset/ownership analysis are being closed.
Wi-Fi/AELITA remains USER_DEFERRED; F343 remains rejected/no-retry.

C: temporarily reached zero free bytes and truncated the F352 builder; the agent
restored that builder atomically and verified its other recorded inputs. C:
was subsequently observed with about 1.45 GB free. WSL disks are on D:, not C:.
The attempted cache relocation was blocked by automatic policy and did not run;
no compression or cache deletion was executed. New writes require a free-space
check. Do not attribute the returned free space to a cleanup performed here.

## Active F349 passive SPI observation - 2026-09-21 16:20 UTC

Root campaign: `outputs/handoff-live/f349-passive-20260921T162050Z-0cb97d7b/`.
Tool session **49964**, root PowerShell PID **3564**, temporary awake hold active.
Plan: `outputs/preflight/f349-passive-20260921T161933Z/plan.json`, SHA-256
`4414d69c7107814533490a0d681a63dfb534c9839542248f661ea13cdd504243`.
Its 68 sources are frozen. The new plan passes 52 offline tests, including
the two-second host UART-drain wait identified in independent review.
Root review: `outputs/preflight/f349-root-review-20260921T162025Z/result.json`.

This operation performs one SYSCTL-map read and one SPI_CONTROL read with
zero SPI writes, then an explicit watchdog CEASE/reset and read-only F340
return. No deliberate CPU fault, Wi-Fi/AELITA test, TFTP, flash write or
persistent boot-environment change is included. F340 remains the installed
image; live execution may be in Linux or Bootbase until acceptance completes.
Do not open another UART session or kill a possibly armed watchdog owner.

Offline progress: F350 kernel and bounded common-BP0 journal provider pass
`outputs/preflight/f350-qualified-20260921T161419Z/result.json`. F351 CLI,
F344 modes and F352 simultaneous Ethernet support remain in progress.

## Current installed baseline: F340, F346 physical installation PASS

`outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/result.json`
records **PASS_F340_PERSISTENT_WATCHDOG_BASELINE**. F340 is installed in
physical mtd4/linux_live and has booted as `#340 @1790006400`, marker
`F340_WATCHDOG_BASELINE`, boot ID `d6ae3305-d867-4c4b-ac1e-42a2dccf7113`.
All 5,349,376 candidate bytes were compared; full-slot CRC is `2aa26ca6`.
Protected partitions and store CRCs are unchanged. Platform passes 27/27.
The watchdog driver is registered, inactive, control EN=0 and ready for an
explicit owner operation. No watchdog ARM or Wi-Fi/RF/client test occurred.

Root session 20321 ended successfully. Helpers, UART, lease and temporary
awake hold are closed; no physical campaign is currently active. Do not use
an F321-only status/flash guard as if F321 were still running. The exact F321
backup remains the fallback, but F340 is now the verified running baseline.
Cold-power-cycle acceptance is not implied by this boot/readback result.

F341 DFS image remains uninstalled/USER_DEFERRED; F343 deliberate CPU-stop
preparation remains rejected/no-retry. The pending physical flash-part question,
F344 modes work and F348 reader-arbitration work remain open.

## Active F346 firmware installation - 2026-09-21 15:19 UTC

Root has started the reviewed F340 installation with exact F321 rollback:
`outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/`.
Tool session **20321**, outer PID **29428**, parent PowerShell PID **5752**.
Plan: `outputs/preflight/f346-install-20260921T150921Z/plan.json`;
review: `outputs/preflight/f346-readonly-review-20260921T151634Z/result.json`.
The 56 source pins are frozen while this runs. Root owns the physical actions;
no other agent may access HGW/UART or modify those sources. The process-local
awake hold is active. Do not interrupt a possible erase/write. Use run files
and the live worker status, not an assumption that starting means success.

Target is only physical mtd4/linux_live, erase prefix 0x5e0000. Preserve store
and protected partitions. F340 is the watchdog baseline; no watchdog ARM,
DFS acquisition or Wi-Fi/RF/client tests belong to this installation.
The currently executing system may be F321, Bootbase, or F340; do not claim
F340 installed/accepted until the result and readback/platform gates prove it.

## Current work checkpoint - 2026-09-21 15:04 UTC and later offline work

Fresh read-only SSH still identifies the same healthy F321 boot:
`outputs/handoff-live/f321-before-f346-20260921T150446Z/result.json`.
No hardware campaign is currently active. F346 is being prepared/reviewed to
install exact F340 (persistent watchdog baseline) with a single exact F321
rollback. It has NOT been executed. Root remains the only physical operator.

Completed offline components since the watchdog test:

- F341 full native DFS diagnostic image: `outputs/preflight/f341-fullimage-20260921T135223Z/result.json`.
  It remains **NO_GO_HW_WIFI_DEFERRED**, without DFS callback/TX authority.
- F342 4 KiB configuration journal: `outputs/kernel-port/f342-config-journal-20260921T141638Z/result.json`;
  read-only review `outputs/preflight/f342-readonly-review-20260921T141855Z/result.json`.
  The real SPI provider is still absent.
- F344 vendor MADWIFI supplicant and CLI: `outputs/userspace/f344-wpa-final-20260921T145403Z/manifest.json`;
  reproducible complete OEM profile. ARC execution and Wi-Fi acceptance are unrun.
  AP/STA/repeater driver/workflow integration is still in progress.
- F345 SPI packet encoder: `outputs/kernel-port/f345-protocol-20260921T141539Z/result.json`.
  Both flash profiles are encoded; no MMIO transport or persistent writes.
- F347 unchanged passive F320 SPI-control observer rebuilt for F340:
  `outputs/kernel-port/f347-passive-spi-control-20260921T145647Z/result.json`.
  It has NOT been loaded or executed; it is not a deliberate CPU-fault test.

The owner has a pending text question about the physical flash marking
(MX25L12835F versus MX25L12836E). Official Macronix documents confirm that
their individual-protection commands differ despite the common JEDEC ID.
Do not pick a profile from a GPL table label or an old memory note. Sources
and the exact unresolved transport boundary are in `docs/OPENMITRASTAR_F345_FLASH_PROTOCOL.md`.

F346's reviewed Bootbase write/erase branch binding is
`outputs/preflight/f346-bootbase-paths-20260921T144707Z/result.json`.
Its scope is those exact branches, not every Bootbase/board-startup action.
The separate `unlock_hw` branch is not allowed by the installer.

Current delegation: hardware_parity_inventory prepares F346; watchdog_linux510_port
implements F344 modes; dfs_core_audit prepares F348 common ROM-reader arbitration
offline after delivering the supplicant. The F343 rejection and the owner's
Wi-Fi/AELITA deferral below remain applicable.

## F343 deliberate CPU-stop preparation blocked

The F343 agent was automatically stopped with a possible cybersecurity-risk
rejection while preparing a deliberate CPU-halt watchdog test. No F343
hardware test was executed. Do not retry or disguise the same trigger through
another agent/tool. Continue ordinary port implementation and preserve the
limited F336 cessation evidence. CPU/bus-halt recovery remains unverified.
The owner has been told the concrete reason; no new permission was requested.

## Current result - watchdog cessation and F321 return pass, 13:48 UTC

F336 attempt 3 completed `CESSATION_RESET_AND_F321_RETURN_OBSERVED`:
`outputs/handoff-live/f336-ram-20260921T133950Z-51c6016b/result.json`.
After 25 explicit pets, the open-descriptor cessation produced 42 decreasing
counter samples and a UART-observed reset 8766-8782 ms after the last pet.
No software fallback, negative verdict, close-before-reset or fatal marker
was observed. Post-reset watchdog was inactive; before/after flash CRC is
`6ed8e483`. The exact F321 returned and platform passes 27/27 at 13:48:53 UTC.
Both tool sessions 69460 and 81495 ended; UART, helpers, lease and temporary
awake hold are closed. No physical operation is currently active.

This proves the observed cessation/reset/return sequence, not CPU/bus-halt
recovery, full-chip reset, or release acceptance. F340 watchdog full image,
F339 internal-temperature driver and F341 DFS integration are offline work.
Wi-Fi/RF/client acceptance remains explicitly USER_DEFERRED.

## Active F336 third attempt - 2026-09-21 13:39 UTC

Root is executing `outputs/preflight/f336-executor-20260921T133902Z/plan.json`
after the marker/SSH/autoboot fixes and 56 offline checks. Evidence directory:
`outputs/handoff-live/f336-ram-20260921T133950Z-51c6016b/`.
Tool session 69460, outer PID 28940, parent PID 17304. Source pins are frozen,
root owns UART, and the process-local awake hold is active. No flash writes.
Watchdog ARM has NOT been sent; wait for `F336_RAM_INSPECT_PASS`, then root
may issue ARM in this same session. Do not start another physical operation.
Wi-Fi/RF/client tests remain USER_DEFERRED; this is only the watchdog gate.

## Current verified state - 2026-09-21 13:38 UTC

Direct UART recovery succeeded: F321 is running again and platform checks
pass 27/27 at 13:37:22 UTC. Evidence is
`outputs/recovery/f336-bootbase-20260921T133521Z-9177a1ee/result.json` and
`platform-verified/status.json`. Root session 79776 is finished; UART,
helpers, lease and awake hold are closed. No firmware write was performed.
F336's previous failures remain failures; its watchdog experiment is unrun.

The F336 probe now also passes a real ARC negative inspection from RAM on
F321, without opening a watchdog: `outputs/handoff-live/f336-probe-negative-20260921T133802Z/`.
The final 75,212-byte F338 service passes all 398 math selftest checks on
real F321: `outputs/handoff-live/f338-ram-math-20260921T133822Z/`.
All temporary files were removed. Prepare the corrected F336 third attempt;
the owner still defers Wi-Fi/RF/client testing.

## Direct F321 recovery active - 2026-09-21 13:35 UTC

Fresh owned UART observation confirmed ZHAL at 13:33; the port and lease
were closed afterwards. Root now runs the direct F321 read/boot recovery:
`outputs/recovery/f336-bootbase-20260921T133521Z-9177a1ee/`.
Plan: `outputs/preflight/f336-direct-recovery-20260921T133432Z/plan.json`.
Tool session 79776, outer PID 17592, parent PID 16224. This has its own
lease, exact FTDI identity and fresh Bootbase echo nonce; it does not claim
a fresh SSH nonce. No flash writes, reboot requests or watchdog experiment.
Sources are frozen. Root remains the only physical operator. A kernel banner
is only boot evidence; run the separate platform gate after the return.

## Recovery required - 2026-09-21 13:30 UTC

F336 attempt 2 ended `FAILED_UART_CAPTURE`; session 43599 and all owned
helpers/UART are contained and the lease was released. NO flash writes and
NO watchdog ARM occurred. F321 remains in flash; its return is NOT verified.
Pinned SSH now times out. Root must recover through a fresh owned UART lease
and the direct F321 read/CRC/bootm contract; do not ask for another power cycle
before trying the available software recovery.

The diagnostic RAM kernel did boot as `#336`, and root's read-only SSH saw
`Topaz DesignWare watchdog`, inactive, nowayout=1. The runner's identity read
failed because F321 has no `tr`. Its subsequent recovery hit a second host
bug: re-enabling autoboot interception reprocessed the old UART buffer and
exhausted its event limit. Fix marker parsing with raw cat plus host NUL
handling; fence autoboot events to bytes received after its activation.
Preserve `outputs/handoff-live/f336-ram-20260921T132233Z-03826f49/result.json`.

## Owner steering - Wi-Fi testing deferred on 2026-09-21

The owner replied: "No wifi tests de momento que no quiero conectar aelita".
Do not contact AELITA again or run Wi-Fi/RF/client acceptance tests until this
deferral is lifted. Continue the full port implementation and offline checks.
F339 temperature and the already active F336 watchdog RAM test remain in
scope. F341 acquisition/radio execution must be marked USER_DEFERRED, never
counted as physical acceptance. The owner did not cancel the full port.

## Active F336 second attempt - 2026-09-21 13:22 UTC

Root is now executing the corrected RAM-only plan
`outputs/preflight/f336-executor-20260921T132136Z/plan.json`.
Evidence directory: `outputs/handoff-live/f336-ram-20260921T132233Z-03826f49/`.
Tool session 43599, outer PID 26656, parent PID 26312. Sources are frozen,
root owns UART, no other physical job may run. The watchdog is not yet armed;
the executor must publish `F336_RAM_INSPECT_PASS` before root sends ARM in
this same session. There are no flash-write commands in this campaign.
Do not describe the running system as F321 while it may be in Bootbase/RAM.

## Current physical state - 2026-09-21 13:20 UTC

F321 has returned and passes platform 27/27 after the first F336 attempt.
`outputs/handoff-live/f336-ram-20260921T131641Z-9e5f6ff2/result.json`
records `FAILED` with `ssh_deadline`: the reboot reached fresh Bootbase, but
the old SSH connection timed out before the controller accepted its UART
evidence. The bounded recovery directly read/CRC-checked/booted F321. No F336
RAM kernel was loaded, no watchdog was armed, no flash write was issued.
`return-platform/status.json` records the 27/27 PASS at 13:20:28 UTC.
All children and UART are contained, root session 8831 is finished and the
temporary awake hold ended. No physical run is active. Correct the reboot
wait with new-prompt evidence, qualify a new plan, then retry the RAM test.

## Historical physical run - 2026-09-21 13:16 UTC

Root is running the reviewed F336 RAM-only watchdog campaign:
`outputs/handoff-live/f336-ram-20260921T131641Z-9e5f6ff2/`.
Root tool session 8831, outer PID 29092, parent PowerShell PID 25560.
The source plan is `outputs/preflight/f336-executor-20260921T131512Z/plan.json`.
No firmware write is part of this run. F321 remains the flash baseline, but
current execution may be Bootbase or the RAM kernel: do not claim the live
system is F321 until the run proves its return. Root owns UART exclusively.
All sources pinned by this plan are frozen while it runs. First phase is
RAM boot plus unarmed inspection; root will issue ARM only after observing
the passing inspection in this same session. Do not start another physical job.

F338 math now passes 398 checks on real F321 Linux from RAM; its kernel/UAPI
integration continues offline. See the session checkpoint for exact evidence.

## Latest physical outcome - 2026-09-21 12:05 UTC

**Exact F321 is restored and platform checks pass 27/27.** After the owner
power-cycled the HGW, the fresh recovery verified a new pristine F334 boot and
new F334 SSH/UART binding, then restored F321 with full candidate comparison,
slot CRC and protected-partition verification. Its result is
`outputs/recovery/f334-after-reset-20260921T120202Z-fd02977b/result.json`:
`PASS_EXACT_F321_RESTORED_AFTER_FRESH_RESET`. Helpers are contained, the lease
is released, and no hardware campaign is currently running. No new capture
was performed. The historical F334 failure below remains a failure.

Current work continues on the complete native OEM DFS pipeline and WPS. Before
another acquisition attempt, prepare continuous UART evidence and physically
validate watchdog recovery, preferably with a RAM-only kernel while leaving
stable F321 flash intact. The owner has already granted implementation/flash
authority; do not ask again for routine authorized steps. Fresh hardware and
artifact gates still apply. See the session checkpoint for current agent roles.


## Historical capture stop — 2026-09-21 11:39 UTC

**The last verified installed image is F334; F321 was NOT restored in the
latest campaign.** F334 flash/readback and platform 27/27 passed in
`outputs/flash-watch/f325-ethernet-20260921T113155Z-ea9253f2/`.
The capture request then failed, with `arm_attempted=true` and no POST-arm
observation. Its effective MMIO/arming state is unknown. The automatic F321
return failed during reboot before its writer/transfer; UART capture was empty
and a separate root SSH check timed out.

The campaign and its helper processes have stopped, the lease was released,
and no write is in progress. The user has been asked to power-cycle only the
HGW. Do not repeat the consumed launcher or the same blind arm request.
After a new clean F334 boot, use a separately qualified fresh recovery wrapper
with current SSH/UART binding and a new lease to restore exact F321. Do not
forge/reuse old borrowed contexts. Existing owner authorization remains valid.

The earlier F326 attempt did restore F321 successfully, but that is historical.
See [the current session checkpoint](OPENMITRASTAR_2026_09_21_PORT_SESSION.md)
for authoritative run locations and continuing offline work.

## Owner-directed full OEM parity — 2026-09-21

The owner explicitly requested completion of DFS and then clarified the
objective: port every existing HGW function to Linux 5.10.260 first, with
improvements deferred, flash authorized and unattended execution preferred.
The intended kernel version remains **5.10.260-openmitrastar-radiohw**.
This is continuing implementation authority, not proof that a future artifact
or physical gate has passed. Preserve the exact artifact, device identity,
protected-partition, readback and recovery checks for every installation.

Fresh pinned SSH at 09:51:29 UTC identifies F321, build
`ad60c8e1e49dfbbf`; the platform gate at 09:54 UTC passes 27/27:
`outputs/handoff-live/dfs-platform-20260921T095423Z/status.json`.
This is current control-plane evidence, not current client/RF acceptance.
The first read-only probe failed on host CRLF encoding; its separate failure
is preserved and the succeeding probe used byte input.

The actual host link changed: `192.168.1.49/24`, interface 18, alias `Ethernet`,
Realtek Gaming GbE Family Controller. Interface 17 is now the VirtualBox
host-only adapter and must not be used as the old physical Ethernet binding.
COM3 still identifies the expected FTDI adapter. No host addresses/routes were
changed. The F326/F321 images and UART backend remain unchanged.

The new exact Ethernet executor review is
`outputs/preflight/f326-network-20260921T0953Z/ethernet-executor-review.json`,
SHA-256 `5e69879afd75128cedca0a03525b5d00d013ac6e22b60fb289e8967642e64e01`.
Its 83 sources are frozen; 645/645 Ethernet tests pass and the existing 205
effective UART passes remain bound. The old review/snapshot and the initial
643-pass/2-fixture-failure result are preserved.

The new launcher is
`outputs/launchers/f326-network-20260921T0953Z/launch.ps1`, SHA-256
`3f7e5b869c9e6874bf6221e966f853ce226710eeb7169fedb209d33696ae5142`.
Use `outputs/preflight/f326-network-20260921T0953Z/launcher-ready.json` as
the authoritative exact launcher binding; do not use the old desktop command.
One normal RunAs request on 21 September ended at 10:01:34 UTC with
`ELEVATION_DID_NOT_START`. Windows reported cancellation, which does not prove
a human clicked Cancel. No elevated execution claim, physical attempt, UART,
reboot, capture or flash was reached. The complete result is
`outputs/launchers/f326-network-20260921T0953Z/uac-20260921T095932370Z.json`.
Do not silently retry or bypass Windows elevation.

A later read-only inspection found an **existing enforced Allow rule** for the
exact Python312 UDP executable on the active Public profile. The synthetic
HGW transfer in
`outputs/preflight/f326-existing-tftp-probe-20260921T102246Z/result.json` passes
on both sides with no firewall change or elevation. The executor is being
qualified for an explicit `existing-permission` mode that uses this already
granted permission and never creates/removes a rule or requests elevation.
Require its new source review before execution; the managed-rule review above
does not qualify later source changes. Detailed continuing-work evidence is
in [the session checkpoint](OPENMITRASTAR_2026_09_21_PORT_SESSION.md).

The functional inventory and its source hashes are
`outputs/port-parity/hgw500-20260921T095258Z/PARITY.md` and `sources.json`.
Work continues on the DFS lifecycle/consumer integration (F327), reuse of the
exact OEM classifier with an ARC/5.10 compatibility layer (F328), and the
hardware watchdog port (F329). These are implementation tracks, not installed
firmware or accepted RF behavior. Inspect each new manifest before reusing it.

The remaining parity scope includes persistent configuration, OEM AP/STA/
repeater and WPS behavior, both Ethernet paths, multicast/VLAN/IPv6 forwarding,
and the proven on-board peripherals. Do not add DSL/ONT/voice/router features
merely because generic BSP sources contain them: this target is a videobridge.

## Resume checkpoint — 2026-09-19 12:16 UTC

F321 is currently verified through pinned read-only SSH at 12:10:28 UTC and a
fresh platform gate passes 27/27 in
`outputs/handoff-live/f326-resume-readonly-20260919T121028Z/`.
The later F325 attempt `outputs/flash-watch/f325-ethernet-20260919T112602Z-bd1b0cae`
**did write and verify F325**, then failed its platform gate because three
radio-start catalogue entries were stale. Its original result is
`FAIL_F325_EXACT_F321_RESTORED`; the nested exact F321 rollback is
`PASS_EXACT_F321_RESTORED`, with writer, containment, firewall cleanup and lease
release proved. Capture was not reached. Preserve those original reports.

F326 repairs the catalogue over exact F321 while retaining the same F325
single-boot diagnostic module, 20-second software deadline and mandatory F321
return. The image is independently reproducible, 5,320,704 bytes, SHA-256
`7500036d0c7215a74d509b39419f65463efbd575b18d15703b3d05312262a767`.
The final executor has 205 effective UART passes (the original one-failure
report and exact passing rerun are preserved) and 639/639 final Ethernet and
capture passes. Review:
`outputs/preflight/f326-executor-20260919T114805Z/ethernet-executor-review.json`,
SHA-256 `9c14f41d4842f88989a4e4ad117e39ff713415ec7ff14df4d98502ae52ad1cdd`.
Its 83 bound sources are frozen in `final-source-snapshot/`; file-only
`final-plan.json` is `OFFLINE_READY_FRESH_PHYSICAL_GATES_PENDING`.

The user-facing desktop command `HGW F326 - prueba y retorno F321.cmd` invokes
`outputs/launchers/f326-oneclick-20260919T1214Z/launch.ps1`. It uses normal Windows
UAC, fixed artifact/review/network/ACK bindings, fresh evidence and a one-use
execution claim. Its default is file-only planning. At this checkpoint it has
not requested UAC or performed hardware actions; the user will initiate it
from the desktop. Read [F326 diagnostic](OPENMITRASTAR_F326_ARTIFACT_CATALOG_DIAGNOSTIC.md).
Any future operator must inspect the launch directory for newer live results
before using this historical checkpoint or attempting another campaign.

## Resume checkpoint — 2026-09-19 11:18 UTC

The owner resumed with `vamo0`. Pinned SSH confirmed F321 and the exact COM3
adapter/current Ethernet index 17 were present. Attempt
`outputs/flash-watch/f325-ethernet-20260919T105347Z-0929157e` passed the complete
transfer, byte count, filesize and iminfo checks, then stopped in the UART CRC
exchange. It never reached erase/write. The original UartFailure lost partial
RX/cause details, so a checksum mismatch or failed hardware is not established.
UART Ctrl-C recovery returned the interpreter prompt and normal boot; F321
passed 27/27 at 11:07:15 UTC. Capture was never armed.

The UART adapter now preserves bounded, sanitized exchange diagnostics and
avoids reconfiguring identical timeout values. Command/address/deadline/CRC
acceptance semantics are unchanged. 241 directed tests and 607 composition
tests pass. This has not yet been physically exercised.
Latest review:
`outputs/preflight/f325-executor-adaptation-20260919T0012/ethernet-executor-review-v4.json`,
SHA-256 `cf7334d4c7be915117d44f3081811d6aa3d3c04ce0d7bf68d1ba8ddb82958c4e`;
sources are frozen beside it in `uart-diagnostic-source-snapshot/`.

The prepared next launch in
`outputs/flash-watch/f325-parent-20260919T111630Z/launch.ps1` did NOT start:
Windows returned `El usuario ha cancelado la operación` for elevation.
See its `launch-result.json`. No hardware action was performed by that launch.
The firmware GO remains valid; resolve the actual Windows elevation before
retrying, and keep the usual fresh identity/lease/readback/recovery gates.

## Last verified state — 2026-09-19 01:04 UTC

**F321 is running; F325 is not installed and capture was not armed.** Two F325
Ethernet attempts completed the network transfer but stopped before any erase
or write on host-parser incompatibilities. The first was followed by an owner
power-cycle; the second was recovered through UART, with F321 platform PASS
27/27 at 00:51:13 UTC and pinned SSH F321 identity again at 01:04:24 UTC.

Progress-backspace, vendor transfer-count and `filesize=0x...` parsing are now
fixed and qualified: 165 UART/backend tests and 578 Ethernet/capture tests pass.
Final executor review is
`outputs/preflight/f325-executor-adaptation-20260919T0012/ethernet-executor-review-v3.json`,
SHA-256 `6dabbde21d43fb509dd4acdea23c425e59c7be61a49202e13cac5717bc9f03d3`.
Its 81 source files are frozen in `final-source-snapshot/` beside it. The final
file-only plan passes; a further physical attempt has not been performed.

The owner requested unattended operation and went to sleep. F321 was left
operational while offline corrections were completed. The diagnostic still
has a possible BB/MMIO hard-halt path and no remote power-control mechanism.
Preserve the existing GO for this exact image and scope, while refreshing the
actual recovery availability before a new physical campaign.

Read [F325 diagnostic](OPENMITRASTAR_F325_SINGLE_BOOT_DIAGNOSTIC.md) and
[Bootbase prompt recovery](OPENMITRASTAR_BOOTBASE_PROMPT_RECOVERY.md).
Never send an empty line/Ctrl-U+CR to recover a prompt after a repeatable
command: it can repeat TFTP. Ctrl-C recovery is restricted to a proven
pre-erase RAM-transfer state, never an uncertain flash operation.

## F325 diagnostic preparation — 2026-09-19

The owner approved the proposed single-boot capture and exact F321 return,
confirmed UART/power access, and requested subagents. F325 is now built and
independently reproducible; no flash has yet been performed at this checkpoint.
See [F325 single-boot diagnostic](OPENMITRASTAR_F325_SINGLE_BOOT_DIAGNOSTIC.md)
for image hash/size, the software-deadline limitation and mandatory recovery.
The final executor review must include the last capture-reader/deadline changes
before execution. F324's in-place hardware-restoration blocker below remains
valid; F325 does not claim to solve it or enable DFS transmission.

## Latest owner-directed DFS checkpoint — 2026-09-19 CEST

The owner powered on the HGW and requested stepwise status, then prioritized
DFS/CAC/WPS and instructed `go a eso y a flash` for the DFS acquisition
lifecycle correction. Pinned SSH at 2026-09-18 23:23 UTC observed exact F321,
build `ad60c8e1e49dfbbf`; the read-only platform gate passed 27/27 at 23:23:32 UTC.
Evidence: `outputs/handoff-live/hgw-start-readonly-20260918T232321Z/platform/status.json`.
This is not a new flash, repeated-cold-boot, client-traffic or DFS acceptance.

Source review found the current F322 acquisition guard's
`NO_GO_ARM_CLEANUP_CONTRACT`: software disarm does not halt/restore capture
hardware, and its BB reader reference is not exclusive producer ownership.
New F324 portable lifecycle code passes 21 simulated failure/restore cases and
builds reproducibly for ARC700. **No QT4 hardware adapter or firmware image is
created, and no flash has been performed.** The blocker is a missing verified
hardware quiesce/restore primitive, not missing owner intent.

Read [F324 lifecycle](OPENMITRASTAR_F324_RADAR_LIFECYCLE.md) before resuming.
Keep F322 disarmed. Do not turn quiet counters, an RX-option name, or a model
PASS into physical stop evidence. Existing F323/F321 permissions and historical
records below are retained; they do not identify a future DFS artifact.

## Prior F323 transport checkpoint

Mission recorded on 2026-09-05; last read-only SSH observation at 2026-09-11
20:44 UTC and offline Ethernet preparation through 20:48 UTC; F323 is not installed. The owner power-cycled
the HGW after the latest abort; F321 is running again and passed 27/27 platform
checks. No further bulk UART upload is permitted without resolving the path.
Verify the installed image and newer local evidence
before acting. Paths and commands use the workspace root. Applicable AGENTS.md
hardware boundaries remain mandatory.

## Immediate mission

**Current execution boundary:** the owner returned home with `ya estoy`, then
explicitly approved the proposed TFTP plaintext LAN transfer, scoped temporary
firewall and volatile Bootbase network settings. The network authorization is
`outputs/authorizations/f323-ethernet-20260911T215738Z/authorization.json`, SHA-256
`827f7d628cd89344e10fe8d7be39dd7b657f57291a35c45788b5e3f536bceaa4`.
Do not ask for this or the existing exact F323/F321 firmware approval again.
This consent does not replace fresh UART identity/ownership or readback gates.
Reusable native transport components pass 111 focused offline
tests; see `outputs/preflight/f323-ethernet-native-20260911T204832Z/result.json`.
The complete parent promoter, scoped firewall/UDP return path and conditional
recovery integration are being completed for the now-authorized `.249`/interface15
to `.90` scope. Qualify them and revalidate physical identity/ownership before use.
Do not repeat completed suites, build another image, or start another unchanged
UART upload merely to keep an automatic goal continuation busy.

Complete Lyoko Full Liberation while preserving installed F321 and the exact
F314 recovery artifact:

1. **F321 is installed in physical `mtd4/linux_live`**. The authorized cycle
   `outputs/flash-watch/f321-direct-20260907T235105Z-b42111c6` wrote the exact
   `5,337,088`-byte candidate, SHA-256
   `eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`.
   Its UART record proves full-slot CRC32 `6ed8e483`, equality of all candidate
   bytes, unchanged protected-partition CRCs and boot selection from mtd4.
   Hardware SHA-256 was not measured. The original promoter result remains
   `STOP_NO_AUTOMATIC_RETRY`: its boot parser incorrectly treated a Linux PCI
   `BAR 0: failed to assign` warning as a Bootbase failure after writing.
   Independent pinned SSH and HTTP checks at 2026-09-11 09:13 UTC report
   `lyoko-foundation-6.8.5-f321-classic-ui-f314-device`, build
   `ad60c8e1e49dfbbf`, on Linux `5.10.260-openmitrastar-radiohw`.
   Platform checks pass 27/27; the UI gate verifies 12 installed file hashes and
   13 public HTTP/authentication checks; authenticated HTTP passes 10/10,
   including login, exact dashboard/bundle bytes and logout invalidation.
   Both radio control planes are ready and the bounded fatal search passes.
   Evidence is in `outputs/postflash/f321-independent-20260911T091309Z/` under
   `platform/status.json`, `ui/result.json` and `authenticated-http/result.json`.
   File-only reconciliation at
   `outputs/postflash/f321-acceptance-20260911T091500Z/result.json` reports
   `PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION`, binding the executed source
   snapshot, physical transcript and these separately dated device checks.
   Those checks do not establish repeated cold boot, browser JavaScript on the
   device, HTTPS/TLS, fresh client association/traffic or DFS RF acceptance.
   A separate physical-browser smoke test on 2026-09-11 then proved JavaScript
   mount, real-data navigation, classic branding and login/logout, but exposed
   two compatibility defects: config/store HTTP 502 from the target grep's BRE
   parser, and a legacy radio-status alias rejected by the DFS observation UI.
   Their corrections first passed 36 focused source tests; the browser evidence
   is in `docs/OPENMITRASTAR_F321_BROWSER_ACCEPTANCE.md`.
   **F323 now integrates both corrections offline over exact F321**, with
   image SHA-256 `9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11`.
   Its two builds are byte-identical, Bootbase passes and 46 additional focused
   contract/package tests pass. Its exact executor is now reviewed offline:
   `outputs/preflight/f323-executor-20260911T150647Z/executor-review.json`, SHA-256
   `43c3ba71ea2fa2dba0ff1d3ec0a7a645cdfbe179968280eeb0e92e1c22a31d36`,
   with 148 passing tests, 69 subtests and 40 source files snapshotted.
   The owner explicitly authorized this exact F323 action and controlled F321
   recovery with `SI AUTORIZO`; the record is
   `outputs/authorizations/f323-20260911T153634Z/authorization.json`.
   The guarded attempt `outputs/flash-watch/f323-direct-20260911T153844Z-5e485259`
   passed binding/reboot but stopped in YMODEM at 3,529,728/5,361,664 bytes,
   before the flash backend, erase or write. Its original
   `STOP_NO_AUTOMATIC_RETRY` result is preserved. All helper processes exited.
   The owner power-cycled only the HGW without moving the UART. Pinned SSH at
   15:57 UTC observed F321 again; the 16:00 UTC platform gate passed 27/27.
   See the attempt's `preerase-failure-audit.json` and
   `outputs/recovery/f323-preerase-f321-20260911T155752Z/platform/status.json`.
   The receiver-driven loader then completed and verified the entire image in
   RAM in `outputs/flash-watch/f323-direct-20260911T163406Z-448aeb9e` (CRC32
   `81cec636`). Its backend stopped before opening UART or any erase/write:
   PowerShell 7 converted the context's JSON dates to DateTime, whereas the
   PowerShell 5 parent emitted strings. The strict validator refused them.
   The owner again power-cycled only the HGW; F321 passed 27/27 platform checks
   at 17:02 UTC. Both original STOP results remain unchanged.
   The date parser now preserves strings explicitly without relaxing UTC/TTL
   checks. Latest qualified executor:
   `outputs/preflight/f323-cross-shell-20260911T170200Z/executor-review.json`,
   SHA-256 `28c80273383067d833e02f47e65596c1291d3c6baffd86ef89525025bc0bc2d9`,
   with 185 passing tests, including real PS5/PS7 roundtrips. Earlier executor
   reviews do not qualify the modified sources. The same exact-image owner
   authorization remains valid; a fresh attempt still requires all live gates.
   The next guarded attempt,
   `outputs/flash-watch/f323-direct-20260911T171046Z-40cbacfd`, stopped at
   4,597,760 bytes when RX returned `0xaa` during an ACK wait. The new loader
   aborted immediately, before RAM-integrity PASS or any flash backend call.
   All helpers terminated and no erase/write was reached. Pinned SSH at 17:24
   UTC timed out. See its `preerase-link-failure-audit.json`.
   Do not run a fourth identical UART upload. First recover the unchanged F321
   boot, then investigate transfer-path integrity or prepare a separately
   validated transport change. Do not treat this as missing authorization or
   as a reason to rebuild the unchanged F323 image.
   Recovery is now observed: pinned SSH at 18:01 UTC identified F321 with a new
   uptime; `outputs/recovery/f323-link-abort-f321-20260911T180151Z/platform/status.json`
   passed 27/27 at 18:08 UTC. A new bounded Linux-console-to-host UART receive
   diagnostic is being prepared in `tools/hgw_uart_rx_integrity_probe.ps1`;
   it must not reboot, send host UART commands, write firmware or claim that
   a short RX window certifies host TX, Bootbase or a complete YMODEM transfer.
   That diagnostic now has a physical result: initial windows were contaminated
   by periodic `OMEMAC poll` console messages. A quiet-console window received
   exactly 32,768 ACK/C bytes with the expected SHA-256, zero unexpected payload
   bytes and zero serial error events. The temporary console-display change was
   restored to `7 4 1 7` and independently checked; F321 remained reachable.
   See `docs/OPENMITRASTAR_UART_RX_DIAGNOSIS_2026-09-11.md` and
   `outputs/uart-diagnostics/hgw-rx-quiet-20260911T185337Z/result.json`.
   This is not clearance for a fourth identical YMODEM upload. Keep F321 running
   and validate an alternative bulk-transfer strategy with its applicable gates.
   Ethernet preparation is now offline-tested: a scoped one-file/one-client
   server and file-only plan passed 122/122 focused tests, including a synthetic
   full-size transfer. See `docs/OPENMITRASTAR_F323_ETHERNET_PREPARATION.md` and
   `outputs/preflight/f323-ethernet-preparation-20260911T191417Z/plan/result.json`.
   The observed source is PC `192.168.1.249`, interface 15, also carrying the PC
   default route; isolation is not demonstrated. No LAN listener, firewall,
   address/route change or hardware action was performed. The existing F323/F321
   firmware authorization is retained and hash-bound; private-image plaintext
   LAN exposure, any temporary firewall rule and volatile Bootbase network
   settings still require a separate owner decision. The exact Ethernet
   executor, UDP return path and conditional recovery review are not complete;
   do not switch the old executor to TFTP by flag or treat these tests as a
   physical pass. Do not disconnect or readdress the PC uplink automatically.
   The protocol and RAM-to-writer core then passed 113/113 new simulation/file
   tests at 20:01 UTC; evidence is
   `outputs/preflight/f323-ethernet-handoff-20260911T200026Z/result.json`.
   At that checkpoint the cores lacked native adapters; neither core has an
   execute CLI. The unchanged
   backend's legacy UART/YMODEM label is retained as a preloaded-branch constant,
   not reused as evidence of bulk transport. Actual adapters, promoter/recovery
   integration and the network-scope owner decision were pending. No device
   or LAN access was performed by this work.
   The subsequent native-adapter/composition stage at 20:48 UTC passed 111/111
   tests (fake UART/guard, synthetic files and one loopback server lifecycle).
   See the current execution boundary above and the Ethernet preparation doc.
   No LAN or device action was performed by this qualification. A fresh,
   separately requested read-only SSH observation at 20:44 UTC still identified
   F321, build `ad60c8e1e49dfbbf`, with uptime 9,793.19 seconds. This is not a new
   radio/client/traffic gate. F323 remains uninstalled.
   F323 is not installed. See
   `docs/OPENMITRASTAR_F323_BROWSER_COMPAT_CANDIDATE.md`.
   Full browser acceptance still requires physical retest after a separately
   qualified and authorized installation; no radio capability was added.
   The F319 claim/map/unload gate remains physically accepted as historical
   evidence. Post-probe SSH, UI/API and both radio control planes passed at
   2026-09-07 19:29 UTC. Keep exact F314 as the proven recovery artifact;
   F319 acceptance does not establish new client/traffic or full-release proof.
   See `docs/OPENMITRASTAR_F319_SPI_OWNER_PROBE.md` and
   `outputs/preflight/f319-runtime-probe-20260907T192754Z/result.json`.
   F321 preserves classic branding and adds responsive fixes and explicit
   CAC/DFS observations. It does not include a native radar provider. Its
   immutable packaging manifest still records the original offline decision;
   installation evidence is separate. The artifact, tests and installation are
   in `docs/OPENMITRASTAR_F321_CLASSIC_UI_CANDIDATE.md`.
2. Validate F315 shadow acquisition before allowing F316 callback authority;
   then prove CAC, evacuation, 1,800-second NOP and non-DFS rollback in a
   separately authorized versioned `mtd4` campaign.
   **F322 shadow over F321 is prepared offline and is not installed**. Its image
   SHA-256 is `55145f55f904beb342dd67b39578a79fbc8a4d0bc68bae944402cab80e5f7f1a`.
   It preserves the installed UI, starts with acquisition disarmed and has no
   DFS callback/TX authority. See `docs/OPENMITRASTAR_F322_SHADOW_CANDIDATE.md`.
   Its executor and physical acquisition checks remain separate requirements;
   F321 acceptance does not qualify F322 or unlock CAC/DFS.
3. Keep F317 observe-only until F316 is physically accepted. Measure its CPU,
   memory and management-plane impact before enabling automatic application.
4. Complete persistence through the F318 two-eraseblock transaction contract.
   Do not reuse the F279 global-protection path and do not load the rejected
   F295 observer. F319 has proven exclusive controller ownership with
   zero register accesses and clean unload; do not repeat its accepted gate.
   This is a software resource claim, not address-decoding or hardware
   arbitration proof. F320 is now packaged offline with a legacy-map check and
   one control-register read; see `docs/OPENMITRASTAR_F320_SPI_CONTROL_READ.md`.
   Its physical executor, exact authorization and hard-halt/power-cycle
   contingency are still required. Only a later accepted gate may add
   exact per-block protection restoration before exposing writes.
5. Preserve the authenticated UI, established radio capabilities, protected
   partitions and exact F314 recovery path through every versioned iteration.
   Reprove physical client traffic for the selected firmware; control-plane
   readiness alone is not a traffic gate.

Recovery is exact F314 restoration to mtd4 through the verified Bootbase path,
not a claim that mtd3/linux_safety boots successfully. New hardware actions
require fresh ownership and physical binding. The completed F321 authorization
applies to its exact artifact and reviewed F314 contingency; it does not remove
the artifact, recovery or execution gates for a different candidate. Do not
repeat the F321 flash merely to correct its host-side verification reports.

`tools/audit_lyoko_full_liberation.py` currently audits the historical F314-F319
objective. Its installed-firmware field describes the last accepted record in
that scope, not the newer F321 observation above. The wider DFS, persistence
and final physical acceptance objective remains incomplete.

Defensive review prompts collected from the owner's Plus account, with
Daybreak Blue account access recorded, are in
`docs/LYOKO_CYBER_PROMPTS_DAYBREAK_BLUE.md`. They are inputs for future reviews,
not findings or an executed security audit.

Useful read-only command:

```powershell
python tools\monitor_q3_ap_association_readonly.py `
  --host 192.168.1.90 `
  --duration-seconds 180 `
  --interval-seconds 5 `
  --output-dir outputs\f3-certification\qtn-5g-f137-client-gate
```
## 23 de octubre de 2026: propuesta Doom XZ probada localmente

El propietario propuso SteveSanderson/xzwasm y un conjunto jugable de unos
2 MB. Candidato independiente confirmado: archivos1.963.925B;
SquashFS aislado XZ1MiB1.933.312B. Motor/WAD/glue iguales tras descompresión,
desktop/touch/movimiento/disparo/PCM y rechazo de entrada corrupta PASS local.
No modificaciónHGW/flash/bootenv ni transporteTLS físico de este candidato.
Fuentesgzip+ZIPDOS3.364.392B siguen conservados: el conjunto de2MB los excluye
de capacidad, no los borra ni cambia todavía la entrega firmware.
Ver docs/OPENMITRASTAR_DOOM_XZWASM_20261023.md y sus tres recibos.

Receta integradaR2 nueva en work/kernel-port/linux-7.3-radioeth-integrated-r2.
Primer intento STOP shebangash; segundo19módulos iguales, STOP hashEthernet
por ruta__FILE__ de dma-mapping.h (texto.rodata+relocs/build-id).
Receta normaliza ahora esa ruta; pareja final pendiente. No build físico ni
proceso compilador activo al cerrar este avance. No relabelar los intentos.
BaselineSSH22:21:44UTC kernel7.3, uptime4517s, APENABLED ES1, eth0carrier1,
eth1down; boundedfatalgrep sin líneas. Radios siguen prioridad.

