# OpenMitraStar Linux 5.10 — los OGs, las joyas y la deuda real

Snapshot: `2026-08-31 CEST`

## Objetivo

Este documento identifica a las personas o equipos originales detrás de los
comentarios más memorables encontrados durante el port del
`HGW-500BNA-QCv2 A2`, separa claramente su procedencia y conecta esas pistas
históricas con las cagadas y mejoras relevantes para el Linux 5.10 actual.

No todo comentario presente en el dump GPL fue escrito por MitraStar,
Telefónica o Quantenna. El árbol mezcla al menos:

1. Linux upstream histórico.
2. BSD/net80211 y MadWifi.
3. BSP y drivers de Quantenna.
4. Glue OEM MitraStar/Telefónica.
5. Cambios locales de OpenMitraStar.

Cuando no existe un `git blame` o metadato individual demostrable, se atribuye
al equipo o linaje y se marca la incertidumbre. No se inventa un culpable.

## Estado desde el que se escribe

- El equipo vivo responde por SSH en `192.168.1.90`.
- Kernel observado: `5.10.260-openmitrastar-radiohw`.
- `wlan0` y `wifi0` tenían carrier `1` en la comprobación read-only.
- F155 fue escrito y verificado en `mtd4/linux_live` el 31 de agosto de 2026:
  SHA-256 del candidato
  `28d7a26edb6bbc61ef0a8425dfcff388f569f41b3f27b25fcee6bcc143abdb71`.
- F155 es una variante diagnóstica de la rama segura iniciada en F151, no el
  nuevo punto de rollback funcional.
- F150 sigue siendo el checkpoint dual-radio conocido-bueno: asociación de
  120 segundos, ARP dinámico, ICMP 10/10 y tráfico bidireccional.
- F150 debe conservarse sin modificaciones mientras F151-F155 terminan sus
  gates de WPA2, inactividad, GSO y TX pool.

Evidencia:

- `docs/OPENMITRASTAR_F150_CURRENT_STATE.md`
- `work/mission-state/q3-persistent-composite-f155-5g-txpool-trace-from-f154/build/flash-one-shot-20260831T192101Z/result.json`

## Hall of fame: comentario, OG y procedencia

| Joya | OG mejor demostrado | Procedencia | Confianza | Por qué |
|---|---|---|---|---|
| `Warning! This version leaks memory like crazy!` | **Greg Kroah-Hartman** | Linux USB serial/Edgeport, versión 0.3 de 15-02-2000 | Alta | La propia entrada del changelog lleva su nombre y fecha. No es Quantenna ni MitraStar. |
| `magic baudrate thingy: not sure what it does` | **Bart Hartgers** | Driver Linux `ark3116` | Alta | La línea entra con el cambio `f4c1e8d5...`; el fichero y `DRIVER_AUTHOR` también nombran a Hartgers. |
| `ugly -- i2c hijacks our memory hook...` | **David Brownell** | Driver Linux `isp1301_omap` | Media-alta | El fichero es de Brownell y el historial público conserva el bloque bajo su cambio de 2008; el movimiento de fichero impide tratar ese commit como prueba absoluta de primera autoría. |
| `puissant code-fu` | **Rusty Russell** | Documentación de `lguest` | Alta | Introducido por el commit de documentación `e1e72965...` firmado por Russell. |
| `I don't know, possibly flush` | **William Greathouse**, probablemente | Driver Linux Belkin USB serial | Media | El header identifica a Greathouse como autor original. El Git público comienza con la importación inicial de Linus y no conserva blame anterior de esa macro. |
| `pardon any stupid mistakes` | **William Greathouse** | Header fechado del driver Belkin | Alta | La frase está dentro de su entrada de 12-10-2000 y explica que trabajó mediante UsbSnoop sin documentación original. |
| `XXX good enough to keep from crashing?` | **Sam Leffler** como mejor atribución | BSD/net80211, después MadWifi y Quantenna | Media-alta | El fichero acredita a Atsushi Onoe y Leffler; la importación histórica pública que contiene la frase es de Leffler. |
| `XXX racey but good 'nuf?` | **Sam Leffler** como mejor atribución | BSD/net80211/MadWifi | Media | Misma línea de código y copyright; el snapshot no conserva un blame anterior que permita excluir a otros contribuidores. |
| `NB: racey, does it matter?` | **Sam Leffler** como autor de base; **Pavel Roskin** como revisor posterior | net80211/MadWifi scan | Media | El copyright es de Leffler y `$Id` muestra una revisión posterior de `proski`. No debe asignarse automáticamente la frase a Roskin. |
| `### Hack alert ###` | **Equipo de ingeniería Quantenna** | `qdrv_tx.c`, traducción ARP en modo 3-address | Alta para empresa; baja para individuo | El fichero sólo publica copyright corporativo 2008-2013. No hay historial individual distribuido. |
| `Double free check is already broken...` | **Equipo Quantenna Topaz/HBM** | `platform/topaz/hbm.c` | Alta para empresa; baja para individuo | El fichero publica copyright Quantenna 2012, pero no autor personal. |
| `HW bug workaround - dummy access breaks up bus transactions` | **Equipo Quantenna EMAC** | `platform/ruby/emac_lib.h` | Alta para empresa; baja para individuo | Es una peculiaridad de bus/silicio conservada por el BSP. No es un comentario genérico de Linux. |
| `Workaround for transfer across slow ethernet interfaces` | **Equipo Quantenna qdrv** | `qdrv_wlan.c` | Alta para empresa; baja para individuo | Código específico de la integración Quantenna. |
| `Hack for ASUS/Broadcomm 3ss client to turn down power` | **Modificación vendor posterior sobre código de Sam Leffler/MadWifi** | `ieee80211_wireless.c` | Media | El fichero base viene de Leffler y fue revisado en MadWifi por `mrenzmann`; el bloque usa estructuras Quantenna, así que no es honesto endosárselo a Leffler o Michael Renzmann sin blame vendor. |

## Quiénes son los OGs principales

### Greg Kroah-Hartman

Autor de la entrada `leaks memory like crazy`. La gracia no era una broma
gratuita: el changelog dice que la demo CeBit 0.3 perdía memoria, y dos días
después la 0.4 ya no perdía memoria en cada escritura aunque conservaba fugas
pequeñas al arrancar.

Fuente local:
`work/sources/Quantenna-GPL/linux_2.6.35.12/drivers/usb/serial/ChangeLog.history:705`.

### Bart Hartgers y Simon Schulz

Bart Hartgers reescribió el driver ARK3116 en 2009 partiendo del trabajo de
Simon Schulz. Hartgers es el autor demostrable de `magic baudrate thingy` en el
historial público de Linux.

Commit:
<https://github.com/torvalds/linux/commit/f4c1e8d597d1a440175db0d709c921cf3a49cfe7>

### David Brownell

Veterano del subsistema USB de Linux y autor del driver ISP1301/OMAP donde
aparece `i2c hijacks our memory hook`. La frase describe una interacción real
entre lifecycle, I2C y una espera de completion; no es únicamente decoración.

Historial conservado:
<https://github.com/torvalds/linux/commit/b8da8677d4f88db066c1cfe34529d970a060de46>

### Rusty Russell

Autor de `lguest` y del maravilloso `puissant code-fu`. En contexto explica
que arreglar bien el rendimiento de shadow page tables con highmem requeriría
una solución bastante más profunda que el diseño existente.

Commit:
<https://github.com/torvalds/linux/commit/e1e72965ec2c02db99b415cd06c17ea90767e3a4>

### William Greathouse

Autor original del driver Belkin F5U103. Su header explica honestamente que no
tenía el trabajo original ni documentación del dispositivo y que reconstruyó
el protocolo con UsbSnoop en Windows 2000. Es probablemente el responsable del
`possibly flush`, pero el historial Git anterior a la importación inicial no
permite certificar esa línea individualmente.

### Atsushi Onoe y Sam Leffler

Son los OGs del net80211 que terminó viajando por BSD, MadWifi, Quantenna y
nuestro port. Onoe figura en el soporte inicial de power-save; Sam Leffler es
el autor dominante de los ficheros net80211 de 2001-2005 y la mejor atribución
para `good enough to keep from crashing?` y `racey but good 'nuf?`.

La importación pública de FreeBSD que conserva el primer comentario fue hecha
por Leffler:
<https://github.com/freebsd/freebsd-src/commit/68e8e04e93c1ec3d37022223b69073f50d3d4981>

### Pavel Roskin y Michael Renzmann

Los identificadores SVN conservados en los ficheros revelan revisores del
periodo MadWifi:

- `proski` = Pavel Roskin, visible en `ieee80211_scan.c`.
- `mrenzmann` = Michael Renzmann, visible en `ieee80211_wireless.c`.

Esos `$Id` demuestran que tocaron la revisión del fichero, pero no que
escribieran todos los comentarios que contiene. Esa distinción importa.

### Quantenna Communications y Mats Aretun

Los ficheros `qdrv`, TQE, HBM, FWT y EMAC publican casi siempre autoría
corporativa. `qdrv_module.c` sí expone:

```text
MODULE_AUTHOR("Quantenna Communications Inc., Mats Aretun")
```

Mats Aretun es por tanto un OG nominal del módulo qdrv. Sin embargo, no hay
evidencia para asignarle personalmente `Hack alert`, el double-free roto o
cualquier workaround concreto. Para esos comentarios la atribución correcta
es **equipo Quantenna**, no Mats por asociación.

## Las cagadas OEM deliciosas, con evidencia

El boot OEM real del 17 de agosto de 2026 conserva una cápsula perfecta de
embedded Linux 2015:

| Evidencia | Lectura |
|---|---|
| Faltan `wlan1_addr` y `wlan2_addr`; el script continúa con `ifconfig` | Glue que no valida precondiciones antes de aplicar MACs. |
| `Starting inetd ...` y después `Stopping inetd ...Telnet disabled` | Se arranca infraestructura que la propia política apaga segundos después. |
| `cp: cannot stat '/etc/admin.conf'` | Dependencia opcional tratada como si existiera. |
| `killall: ntpclient: no process killed` | Cleanup no idempotente y ruidoso. |
| `system is overloaded : spend more ~500ms!` en MDIO | Una lectura de control puede bloquear medio segundo y el boot lo acepta. |
| `PCI cache line size set incorrectly (0 bytes) by BIOS/FW` | Firmware/bootloader entrega un valor absurdo; el driver sobrevive corrigiendo o ignorando. |
| `Can't allocate more fcs for AuC` y `MU debug flag failed` | Fallo de recursos/diagnóstico MuC tolerado como no fatal. Sigue apareciendo también en F150-F155. |
| `csa_fail` | El event plane registra fallo de channel switch sin detener el producto. |

Fuente principal:
`outputs/uart-live/reboot-capture-20260817.log`.

Esto no demuestra que el núcleo OEM fuese malo. Demuestra que había buen
datapath rodeado de glue que esperaba errores y seguía adelante.

## Cagadas nuestras durante el port — y qué enseñaron

### 1. Doble inicialización del host bridge PCIe

Se llamó manualmente a `devm_of_pci_bridge_init()` aunque `pci_host_probe()`
ya lo hacía en Linux 5.10. Resultado: colisión de recursos
`0xc0000000-0xc1ffffff` y falsa apariencia de fallo hardware.

Lección: antes de portar un patrón de 2.6 a 5.10, comprobar el lifecycle actual
del subsistema.

### 2. RX desalineado en ARC

TX9 alcanzó un segundo `Misaligned Access` antes de SSH. TX10 añadió rutas
`query-safe` y `signal-safe`, respetando que ARC700 no perdona accesos que x86
tolera silenciosamente.

Lección: en este SoC, alineación y ownership son parte del ABI hardware.

### 3. V5 miraba el sitio equivocado

- `auc_tx=0` no arregló la asociación.
- `queue_enabled=0` no impedía directamente el dequeue.
- Los descriptores de gestión bajaron de 256 a 224: sí había procesamiento TX.
- El trace de `hardstart` excluía management, precisamente lo que necesitábamos
  observar durante AUTH/ASSOC.

V6 fue una mejora de observabilidad, no un cambio de colas/DMA/rings.

### 4. Trace después de posible consumo del `skb`

Una ruta diagnóstica podía inspeccionar el `skb` después de un enqueue capaz de
consumirlo. Se corrigió capturando antes los campos necesarios. Es un ejemplo
de instrumentación que introduce su propio bug.

### 5. Mezcla binaria qdrv/wlan en F147

F147 emparejó un `qdrv.ko` que exigía índices mapeados con un `wlan.ko` antiguo
que almacenaba índices crudos. El cliente nodo 5 llegó como `dest_port=5`, fue
rechazado y cayó al VAP nodo 4. F148 restauró el contrato y produjo
`dest_port=32773 node=5`.

Ésta fue la cagada más valiosa: demostró que dos módulos que cargan y permiten
asociación pueden ser ABI-incompatibles en el datapath.

### 6. Dos warnings sysfs todavía abiertos

- `qdrv_soc.c` declara `tqe_sem_en` con `S_IRWXU`/`0700`; un parámetro no debe
  llevar bits de ejecución. El sibling `switch_tqe.c` ya usa `0600`.
- `wps_button` anuncia lectura y escritura, pero sólo tiene callback de lectura.
  Debe anunciar `0400` o implementar un `store` real; aquí corresponde `0400`.

Son fixes pequeños y separados. No deben mezclarse con el gate WPA2/GSO/TX
pool porque no explican el datapath inalámbrico.

## Inventario completo de marcadores activos

Se exportaron todos los hits `TODO`, `FIXME`, `XXX`, `HACK`, `ugly`, `broken`,
`not sure`, `don't know` y `bogus` del árbol Quantenna que alimenta el port
5.10 actual:

```text
outputs/archaeology/linux510-active-comment-markers-20260831.csv
rows: 359
sha256: 06ed1960ae679e1218191ac654a0c51c15173dc213ca1899b3a3c1fd0e573b49
```

Los ficheros con más marcadores son:

| Fichero | Hits |
|---|---:|
| `wlan/ieee80211_wireless.c` | 62 |
| `wlan/ieee80211_input.c` | 52 |
| `wlan/ieee80211_output.c` | 24 |
| `wlan/ieee80211_node.c` | 23 |
| `wlan/ieee80211_proto.c` | 19 |
| `wlan/ieee80211_scan.c` | 17 |
| `platform/ruby/mv88e6071.c` | 16 |
| `wlan/ieee80211_scan_sta.c` | 14 |
| `wlan/ieee80211.c` | 13 |
| `wlan/ieee80211_crypto.c` | 11 |

El CSV es un inventario, no 359 bugs confirmados. `XXX` en código BSD antiguo
puede ser deuda, una decisión deliberada o una nota histórica. Cada cambio
necesita una prueba discriminante.

## Mejoras para el 5.10 actual

### P0 — preservar la línea buena

1. Mantener F150 y sus hashes como rollback funcional.
2. Tratar F155 como diagnóstico instalado, no como release aceptada.
3. No mezclar limpieza de comentarios, hardening y datapath en una sola imagen.
4. Convertir la pareja `qdrv.ko` + `wlan.ko` en una unidad de release con un
   `pair_id` común y rechazo de carga si no coincide.

### P1 — cerrar el producto inalámbrico

1. Terminar WPA2 sin exponer la PSK en logs.
2. Resolver la ruta GSO/TX pool observada en F154/F155.
3. Añadir DHCP/LAN sólo después de tráfico seguro bidireccional.
4. Probar DFS/CAC/regulatory y varios cold boots.
5. Ejecutar soak térmico y de tráfico largo.

### P1 — actualizar la base estable

El 31 de agosto de 2026, kernel.org publica `5.10.268`; OpenMitraStar ejecuta
`5.10.260`, ocho releases estables por detrás. Además, el mantenimiento oficial
de 5.10 está previsto hasta diciembre de 2026.

Plan correcto:

1. Rebasar 5.10.260 → 5.10.268 offline.
2. Revisar específicamente ARC, PCI, IRQ, skb/networking y DMA.
3. Reconstruir los 25 módulos con el mismo toolchain.
4. Probar primero por RAM/TFTP.
5. Exigir Ethernet, SSH, 2.4 GHz, 5 GHz y traffic gates antes de considerar
   persistencia.

Fuentes primarias:

- <https://www.kernel.org/>
- <https://www.kernel.org/releases.html>
- <https://cdn.kernel.org/pub/linux/kernel/v5.x/ChangeLog-5.10.268>
- <https://docs.kernel.org/process/stable-kernel-rules.html>

ARC continúa documentado en kernels actuales, por lo que una rama futura no
está descartada por arquitectura. El problema real es portar de nuevo Topaz,
PCIe y el ABI vendor, no la desaparición de ARC:
<https://docs.kernel.org/7.1/arch/arc/arc.html>.

### P2 — dos perfiles de kernel

`release`:

- trazas OMQDRV/OMRTL desactivadas o muy rate-limited;
- `KALLSYMS` y debug pesado fuera si el ahorro es medible;
- política de panic/reboot explícita;
- módulos y rootfs verificados contra manifest.

`diagnostic`:

- símbolos suficientes para stack traces útiles;
- trazas bounded por contador/tiempo;
- fault evidence persistente en host;
- nunca presentada como release.

La config F150 actual tiene, entre otros, `MODULE_SIG` desactivado,
`HARDENED_USERCOPY` desactivado, `KALLSYMS` desactivado,
`SCHED_STACK_END_CHECK` desactivado y `PANIC_ON_OOPS` desactivado. No deben
activarse todos a ciegas: ARC700, 50-56 MiB visibles y el ABI vendor exigen
medir tamaño, RAM, rendimiento y compatibilidad uno por uno.

Referencia de hardening:
<https://docs.kernel.org/security/self-protection.html>.

### P2 — sanear sysfs y APIs legacy

1. Cambiar `tqe_sem_en` a `0600`.
2. Cambiar `wps_button` a sólo lectura `0400`.
3. Sustituir `sprintf` por `sysfs_emit` donde el API disponible lo permita.
4. Revisar callbacks que bloquean en lecturas sysfs, especialmente el wait del
   botón WPS.

Referencia:
<https://docs.kernel.org/filesystems/sysfs.html>.

### P2 — preservar el fast path

Modernizar no significa pasar todo por ARC700:

```text
5 GHz -> qdrv -> HBM -> TQE -> FWT -> EMAC
```

Los comentarios de workarounds de bus, HBM y Ethernet son señales de que parte
del código feo encapsula peculiaridades reales. Primero medir y crear tests;
después refactorizar.

### P3 — retirar control-plane OEM con evidencia

- Telnet/inetd: fuera.
- shell de soporte oculta: fuera.
- TR-069, MAUI y analytics de operador: fuera por defecto.
- telemetría local redactada: sí.
- conexiones salientes: inventario visible y allowlist.
- no eliminar `qharvestd` hasta demostrar que qdrv/QCSAPI no depende de él.

## Veredicto

Los OGs no eran un único equipo. Esta placa es una excavación de veinte años:
Linux USB de Greg KH/Brownell/Rusty, net80211 de Onoe/Leffler, MadWifi de
Roskin/Renzmann, y encima el datapath de Quantenna, donde Mats Aretun es uno de
los pocos ingenieros publicados por nombre.

La conclusión importante no es reírse del código viejo. Es saber qué tipo de
comentario estamos leyendo:

- chiste upstream sin relación con el router;
- deuda net80211 que sí ejecutamos;
- workaround de silicio que probablemente hay que conservar;
- glue OEM que podemos eliminar;
- o bug introducido por nuestro propio port.

Ese mapa permite modernizar sin borrar accidentalmente veinte años de
conocimiento hardware escondido dentro de comentarios aparentemente cutres.
