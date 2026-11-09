# F348: exclusión común de lectores ROM y proveedor cooperante

Preparado el 21 de septiembre de 2026. F348 es un kernel de desarrollo
offline derivado de F340; no contiene proveedor SPI, operaciones de escritura,
journal conectado ni ejecutor físico. No se ha instalado. F340, F341 y sus
imágenes originales permanecen intactos.

## Cambio y ámbito

La copia versionada está en
`work/kernel-port/versions/f348-flash-arbitration/`. Sólo cambia cuatro archivos
del árbol kernel: `map_rom.c`, `physmap-core.c`, el núcleo incluido
`qtn_topaz_flash_guard_core.inc` y la cabecera pública
`include/linux/mtd/qtn_topaz_flash_guard.h`.

Un mutex común protege las lecturas `map_rom` de cualquier mapa que solape
`[0x90000000, 0x91000000)` en la máquina DT
`mitrastar,hgw-500bna-qcv2`. Los demás equipos/mapas conservan el comportamiento
anterior. Las cinco vistas DT de F340 son:

| Dirección | Tamaño | Uso |
|---|---:|---|
| `0x90020000` | `0x10000` | entorno principal, ROM |
| `0x90030000` | `0x10000` | entorno secundario, ROM |
| `0x90f80000` | `0x80000` | data/calibración, ROM |
| `0x90960000` | `0x460000` | rootfs_live, ROM |
| `0x90dc0000` | `0x1c0000` | lyoko_store, ROM |

El DT completo y la configuración son byteidénticos a F340. El kernel tiene
identidad de compilación `#348`, conserva el release compatible con los módulos
y mantiene el marcador DT de su base F340. No es una nueva imagen de firmware:
el marcador F340 por sí solo **no identifica** este kernel. El manifiesto y el
hash del kernel son la identidad del artefacto F348.

## API GPL y contrato de duración

Tres exports GPL:

```c
int qtn_topaz_flash_claim(u64 *cookie);
int qtn_topaz_flash_release(u64 cookie);
int qtn_topaz_flash_read_store(u64 cookie, u32 offset,
                             void *buffer, size_t length);
```

`claim` sólo funciona en contexto de proceso. Obtiene una referencia MTD al
dispositivo `lyoko_store` antes de tomar el mutex, comprueba después que sea el
mapa registrado con nombre, dirección y tamaño exactos, y conserva esa
referencia hasta la liberación. Esto evita adquirir `mtd_table_mutex` dentro
del mutex del dominio. `release` libera primero el dominio y después la
referencia MTD. El propietario es la tarea actual; la generación de 64 bits no
se reutiliza ni desborda. Un token/tarea incorrecto no libera la exclusión.

No existe liberación automática por timeout, señal, error de copia ni trabajo
diferido. La misma tarea debe terminar su operación y liberar explícitamente.
La API rechaza contexto atómico, recursión del propietario y cookies obsoletas.
El mutex permite dormir; no mantiene IRQ deshabilitadas ni hace espera activa.

El futuro consumidor debe reservar y materializar previamente todo su código,
buffers y datos; no puede retornar a userspace, provocar faltas de páginas
respaldadas por flash, llamar a `mtd_read` ni cambiar bindings durante un claim.
Una lectura ROM recursiva de la misma tarea devuelve `-EDEADLK`. Las otras
tareas esperan. No se afirma que estas precondiciones puedan imponerse a un
módulo kernel arbitrario que no respete el contrato.

`read_store` usa directamente el `map_copy_from` existente del mapa retenido,
sin recursión por `mtd_read`. Sólo permite offsets relativos a `lyoko_store`;
valida longitud/overflow y no exporta el puntero del mapa. El proveedor deberá
demostrar fin de comando y restauración de read-array antes de leer o soltar
el claim. F348 no modifica ni comprueba el estado eléctrico del chip.

## Cierre de accesos directos y lifetime

Las vistas protegidas no publican `_point` ni `_unpoint`. En la configuración
MMU real, `drivers/mtd/mtdchar.c:mtdchar_mmap` ya devuelve `-ENODEV`; la rama
antigua `vm_iomap_memory` está bajo `if (0)`. Se conserva esa fuente sin cambios
y se ejecuta su función exacta en el harness. `/dev/mem` y `/dev/kmem` están
desactivados. También están desactivados PHRAM, MTD_RAM, BLOCK2MTD y OF_OVERLAY.

`CONFIG_MTD_BLOCK_RO=y` conserva lecturas ordinarias por MTD para rootfs. El
escáner JFFS2 existente tolera el rechazo de `mtd_point` y usa su buffer de
lectura. No se cambia el fallback ni el rootfs. La aceptación física de estos
caminos con F348 sigue sin ejecutar.

ROM/PHYSMAP son builtin y los mapas DT son estáticos. F348 suprime los
atributos sysfs bind/unbind de physmap sólo en HGW: su `remove` puede devolver
`-EBUSY` cuando hay referencias MTD, pero driver core puede liberar devres aun
con ese retorno. Permitir unbind dejaría una vía de retirada incompatible con
el lifetime. La retirada normal del store espera el mutex y borra su referencia
publicada antes de destruirlo. No se garantiza seguridad frente a código
kernel externo que fuerce retirada programática fuera de este contrato.

## Verificación offline

`tools/test_f348_flash_arbitration.py` compila el mismo núcleo C incluido por
el kernel con mutex pthread real y servicios de memoria simulados. Seis grupos
comprueban exclusión lector/claim, lector/lector, tarea y token, lectura relativa,
errores de copia y adquisición, rechazo atómico, overflow de generación y
retirada que espera mientras la referencia está retenida.

El segundo harness compila el `map_rom.c` real y la función MMU
`mtdchar_mmap` real sobre servicios RAM: cinco vistas protegidas, dos mapas
fuera de ámbito, hooks, referencias, lecturas, rechazo de escritura/erase,
recursión y rechazo de mmap sin llamar al servicio de mapeo. GCC `-fanalyzer`
se ejecuta sobre el núcleo/harness. Estas pruebas no acceden al dispositivo.

`tools/build_f348_flash_arbitration.py` copia el árbol F340 a un directorio
nuevo, comprueba los hashes de las fuentes base, aplica sólo los cuatro
archivos, registra el diff íntegro del árbol y compila en dos directorios O
independientes con tiempo y rutas normalizados. La cualificación compara
kernel/raw/DT/config/exports, las cinco ventanas y los hashes de las pruebas.

Resultado canónico **PASS_OFFLINE_READER_ARBITRATION**, 20/20 checks:
`outputs/preflight/f348-qualified-20260921T154126Z/result.json`, SHA-256
`1e24828d7291319c98e56c6de0a84a3f36f1ce73299b6283d091d0d5ac370d0c`.

Pruebas nativas:
`outputs/preflight/f348-reader-tests-20260921T153549Z/result.json`, SHA-256
`d1dd31aa09f84754502ebb37e3bca8767c31640c6620ecbcbd6c2fd0e9b85cd5`.

Build canónico:
`/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f348-flash-arbitration-20260921T153439Z`.
Su `result.json` tiene SHA-256
`0567c761caf5da2467b790dac4159a82ee4edb90503b92e74ad018c50e9056f0`.
Los archivos de `a/` y `b/` son idénticos:

| Artefacto | Bytes | SHA-256 |
|---|---:|---|
| `f348.vmlinux` | 5.184.356 | `02967fef4fa7105968f10145d0e392d23d2a77b003a3873787b725c20c92ad9c` |
| `f348.raw.bin` | 3.733.472 | `29e21513779324055f0513ea1c78071e8992a2a9114069f962b9b4f94530df40` |
| `f348.dtb` | 5.721 | `d317a0b3680631548796909ec6970c4e3c2f4d204a2f5b83e601c88931937a47` |
| `f348.config` | 53.607 | `f374913b8d2adc7c4138af32263b650eeb967b4defc0139cfd00e6bff7ba1118` |
| `Module.symvers` | 291.215 | `d72fd037a741802348b7d24ac443b5a3e227f2f851d319b23ab71f1f39944c1d` |

Fuente aislada WSL:
`/home/user/openmitrastar-build/f348-flash-arbitration-20260921T153439Z/linux`;
directorios O independientes `a` y `b` junto a esa fuente. Entrada kernel
`0x8493e000`, símbolo final `_end=0x84d02000`. Los warnings heredados de caché
ARC no afectan al PASS de compilación; el analizador del núcleo nuevo está
limpio. Este documento no autoriza una instalación ni convierte las pruebas
nativas en aceptación física, RF, del arbitraje eléctrico o del futuro journal
SPI.
