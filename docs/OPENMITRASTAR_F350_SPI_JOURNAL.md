# F350: proveedor SPI y journal común BP0, sólo cualificación offline

21 de septiembre de 2026. **PASS_OFFLINE_COMMON_BP0_JOURNAL**, 29/29
comprobaciones. No se ha cargado este módulo ni ejecutado acceso SPI en el HGW.
F349 sigue siendo la preparación separada de la primera observación pasiva.
No hay imagen de firmware, ejecutor físico ni autorización de instalación en
este entregable. F348, F340 y sus artefactos originales permanecen intactos.

## Implementación

Fuente nueva: `work/kernel-port/versions/f350-spi-journal/`.

`provider/` contiene el adaptador kernel y el núcleo probado, junto con copias
byteidénticas de F342 y F345 y la interfaz F318. Sus cabeceras C estándar se
adaptan con shims propios de compilación; no se cambian los núcleos cualificados.
`kernel-overlay/` deriva del guard F348 y añade dos exports GPL:

- `qtn_topaz_flash_stage_page(cookie, offset, data, length)`: sólo los primeros
  dos bloques de store, máximo 256 bytes y sin cruzar página. Usa las escrituras
  de byte del aperture uncached entre PP02 y COMMIT, como el driver OEM.
- `qtn_topaz_flash_quarantine(cookie)`: cierra permanentemente la admisión de
  lectores/claims hasta reboot, retiene la referencia MTD y retira el propietario
  de tarea antes de soltar el mutex. No hay reset/reuse ni timeout auto-release.

Ante estado del controlador/comando indeterminado, el módulo conserva además
una referencia a sí mismo: no puede descargarse ni ceder su recurso MMIO.
La exclusión compartida cubre las cinco vistas ROM heredadas de F348. No se
afirma exclusión de un módulo ajeno que acceda directamente al bus o de DMA.

El transporte reproduce las secuencias justificadas del GPL vendor:
RDID 9F, RDSR 05, RDSCUR 2B con cambio temporal y restauración de SPI_CONTROL,
WREN 06, WRDI 04, PP02 con bytes de staging y COMMIT, y borrado D8. PP/borrado
sólo admiten `0xdc0000`/`0xdd0000`. No se publican direcciones ni opcodes libres.

Los argumentos de dirección para Topaz se escriben como `SPI_MEM_ADDR` del
vendor; el swap de ID/status conserva la semántica OEM. Los bytes seriales de
lectura de F345 se reutilizan con perfil UNKNOWN: no se falsifica su contexto
individual WPSEL ni `exact_part_verified`.

Toda lectura array exige WIP=0, SPI_CONTROL original y READ_ID como cierre de
CS antes de entrar en el aperture. `sync` también termina con ese cierre.
Después de una lectura se repite READ_ID. El modelo falla si se intenta leer
array dejando RDSR u otra orden como último comando. Esto corrige el candidato
histórico de módulo `f350-provider-20260921T160932Z`, que no debe utilizarse.

El `map_info.virt` real viene de `devm_ioremap_resource`; el ARC `ioremap`
selecciona PAGE_KERNEL_NO_CACHE fuera de su ventana hardware uncached, y
`ioremap_prot` fuerza `pgprot_noncached`. Las fuentes exactas se conservan como
witnesses de la cualificación. No se deduce uncached de un cast C.

## Protección y modelo de memoria

La vía de escritura requiere un snapshot real con RDID `c22018`, WPSEL=0,
BP3..0=0, WIP/WEL iniciales a cero y sin estado CP/suspend. No identifica cuál
de las dos familias está instalada. `exact_part_verified` siempre queda a cero.

Ambas familias permiten la misma vía PP02/D8 cuando BP=0. La preservación de
protección es un **NOOP verificado**, no un desbloqueo. Cada witness F342 se
deriva del estado común observado; se compara antes y después, junto al
controlador y los registros. Otro modo/protección/identidad devuelve
EOPNOTSUPP. No se soporta escritura individual de DPB ni restauración FF.

E/P_FAIL previos pueden ser históricos: se registran y conservan, sin limpiarlos.
Un cambio posterior provoca error y se comprueban los datos/CRC. No se emite
CLSR30 (su semántica cambia entre familias), RDCR15, WRSR, WPSEL, OTP, SPB ni
protección global.

Fuentes primarias locales en
`outputs/research/f345-nor-datasheet-20260921T135832Z/`:

- MX25L12836E, PM1514 rev.1.7: p11, BP1 protege dos bloques y BP8 todos;
  p17, registro de estado; p28, security; p46, tPP máximo 5 ms y D8 máximo 2 s.
- MX25L12835F, PM1795 rev.1.7: p10, BP1 protege un bloque y BP9 todos, con
  selección de extremo T/B; p31, estado; p85, tPP máximo 1,5 ms y D8 650 ms.
- AN0177 rev.3 y diagramas de protección previamente vinculados a F345.

F350 no necesita conocer T/B porque sólo admite BP=0. Los límites software son
20 ms para PP y 2100 ms para D8; se duerme durante la espera, sin mantener IRQ
deshabilitadas. Hay límite de iteraciones además del reloj. Un acceso MMIO que
no retorna no puede acotarse con ese timeout: eso sigue siendo un gate físico,
no una propiedad demostrada del watchdog ni del bus.

## Dispositivo y contrato del consumidor pendiente

Cabecera canónica: `provider/f350_uapi.h`. Dispositivo
`/dev/om-f350-journal`, permisos 0600 y CAP_SYS_RAWIO en ioctl. Carga por defecto:
`allow_hw=false`, `allow_program=false`; ambos parámetros son de carga, 0400.
El init no reserva ni mapea el controlador y no hace MMIO. El consumidor debe
seguir este mismo default: ayuda/inspección local sin abrir el dispositivo.

ABI1, `F350_IOCTL`, estructura fija de **4180 bytes**. Se debe incluir la
cabecera al compilar, no copiar un número ioctl de otra ABI. Operaciones:

| Operación | Número | Resultado esperado |
|---|---:|---|
| OBSERVE | 1 | Snapshot ID/CTRL/status/security, sin payload |
| LOAD | 2 | Registro validado y payload de hasta 4096 bytes; EMPTY separado |
| SAVE | 3 | Payload 1..4096, commit visible, protección y witnesses verificados |
| INSPECT | 4 | Metadatos del journal sin copiar payload |

Toda reserva y copia de entrada ocurre antes del claim común. La respuesta se
copia después de liberarlo o de retirar su ownership mediante cuarentena.
No hay payload en logs. Un retorno ioctl cero sólo significa que se entregó la
estructura: el consumidor debe comprobar `status`, `backend_status` y
`journal_status`, además de `quarantined==0` y `claimed==0`.

`journal_status` conserva los códigos F342 (0 OK, 1 EMPTY, negativos propios).
`backend_status` conserva el error del proveedor. `status` es el resultado global;
los modos no soportados se exponen como EOPNOTSUPP. No aplicar `strerror` a los
códigos propios F342. Para SAVE se exigen también `commit_visible`,
`protection_restored` y `witnesses_unchanged`. LOAD con error deja longitud cero
y borra el payload de salida. El CLI todavía no está implementado.

## Evidencia y límites

El modelo C ejecuta el núcleo F350 y los F342/F345 reales: 4 KiB y alternancia,
CRC, ambos mapas BP, tiempos E/F, fallos históricos/nuevos, límites, WEL,
4.399 posiciones de error y cierre de CS/control antes de array. Cuenta
19.386.786 assertions; son comprobaciones del modelo, no transacciones físicas.
El adaptador kernel real pasa 10 casos nativos de default, permisos, ABI y
copias fuera del claim. El guard pasa siete grupos con pthread real, staging,
retención y cuarentena. Los análisis GCC están limpios.

Kernel y módulo se compilan dos veces con resultado idéntico. Todos los imports
del módulo resuelven en el kernel propio, sin warnings de enlace omitidos.
La cualificación liga el módulo **posterior a la corrección del footer** a ese
modelo y a ese kernel. No promueve el candidato 160932Z.

Kernel `#350` conserva el DT/config de F340 y su release para los módulos.
El ejecutor de host F340 comprueba `uname -v`; el supervisor F340 por sí solo
comprueba DT, driver y estado del watchdog, **no `uname`**. Una futura imagen
y consumidor deberán incorporar la nueva identidad y su owner. F356 añade
esa comprobación explícita al supervisor. El DT heredado no acredita la
integración. En el momento de este entregable quedaban sin ejecutar la
lectura pasiva F349 y la observación ID/protección,
transporte eléctrico, PP/borrado físico y persistencia tras interrupción.

Este entregable no contiene parada de CPU, pruebas Wi-Fi/AELITA ni acciones de
router. F343 permanece cancelado.

## Artefactos canónicos

- Cualificación: `outputs\preflight\f350-qualified-20260921T161419Z\result.json`
  SHA-256 `f6acac38db68da58e6fcefda6e51f2fbdc4e9e395063b3f3f7dfb860d3d4dd9e`.
- Módulo: `/workspace/user-home\Desktop\MitraStar\outputs\kernel-port\f350-provider-20260921T161206Z\a\qtn_f350_journal.ko`
  SHA-256 `ad02964ab380a3fe15ddb9cdb057d08dbf7f6a25d990a6121e43fbac42f50cf0`, 19652 bytes.
- Kernel: `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f350-flash-arbitration-20260921T155949Z\a\f350.vmlinux`
  SHA-256 `2cf8cb71b2fa90720ae7df3d868695ed2cd908c09405a762752d2c25df08558a`, 5184768 bytes.
- Module.symvers: `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f350-flash-arbitration-20260921T155949Z\a\Module.symvers`
  SHA-256 `9c3e80bb874c5848a1eb5c17a5ed9acb7848741b866a824c4eb6779f8f48e261`, 291345 bytes.
