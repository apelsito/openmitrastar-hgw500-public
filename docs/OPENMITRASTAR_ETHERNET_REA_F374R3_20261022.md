# Ethernet HGW500: REA integral y candidato F374r3

Fecha: 22 de octubre de 2026. Trabajo offline sobre el HGW-500BNA-QCv2 A2.

Se ha recuperado el desensamblado completo de los módulos Ethernet OEM y del
port, cotejado sus callbacks con las fuentes GPL y reconstruido F352 exactamente.
F374r3 corrige el tratamiento de timeout durante la recuperación RX. Su módulo
completo compila dos veces idéntico y pasa la revisión independiente del alcance.
**OFFLINE PASS; NO_GO_INSTALL; port Ethernet completo y release aún pendientes.**

No se accedió al router, SSH, UART ni radio. No hubo flash, reinicio, cambio de
bootenv, instalación de módulos o cambio de proveedor/configuración Codex/REA.

## Qué tenemos entero y qué no

| Artefacto | Funciones exportadas por REA | Bytes ejecutables originales y desensamblados | Bytes fuera de cuerpos Ghidra, excluyendo NOP | Funciones con avisos |
| --- | ---: | ---: | ---: | ---: |
| OEM emac.ko | 20 candidatos | 9.496 / 9.496 | 20 | 7 |
| OEM emaclib.ko | 89 candidatos | 13.432 / 13.432 | 118 | 20 |
| OEM switch_emac.ko | 37 candidatos | 9.584 / 9.584 | 8 | 12 |
| F352 | 36 direcciones, 38 símbolos | 10.768 / 10.768 | 0 | 13 |
| F374r3 | 36 direcciones, 38 símbolos | 10.960 / 10.960 | 0 | 13 |

Todos los bytes ejecutables están preservados y contrastados con el objdump ARC
pinnado. Los cuerpos, pseudocódigo, referencias y límites de cada función están
exportados. El pseudocódigo **no es el C original ni una equivalencia semántica
global**: los bucles hardware ARC, fixups y dos instrucciones sync OEM mantienen
límites explícitos. Los nombres locales eliminados del OEM son correlaciones con
el fuente; los seeds no los convierten en identidades observadas.

El MCP REA instalado rechaza EM_ARC_COMPACT. Se reutilizó la adaptación local
ARC700/ABI3 ya existente con Ghidra 12.1.4 y el Sleigh ARCompact, sin cambiar la
instalación. Los ELF enlazados son **ANALYSIS_ONLY_NEVER_LOAD_OR_FLASH**: contienen
direcciones externas sintéticas y nunca deben instalarse ni entrar en firmware.
Los módulos originales no se modificaron.

Evidencia de cobertura: [ledger final](../outputs/rea/ethernet-full-20261022T132851Z/final-r3-coverage/REPORT.md).
Seeds/callbacks: [auditoría](../outputs/rea/ethernet-coverage-20261022T133734Z/REPORT.md).
877 registros de observación REA están serializados con identificadores canónicos
verificados en los cinco directorios `*-evidence-seal-r2` de la campaña.
Estos sellos nuevos usan autoridad analyst-inference porque analizan un ELF
derivado; conservan hashes del original y los límites de las direcciones.

## Base reproducible y corrección

F352 se reconstruyó dos veces desde fuente con los comandos ARC retenidos y el
contexto generado F363. Cada módulo de 24.544 bytes coincide byte por byte:

```text
41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e
```

Se comprobaron 684 inputs, 38 funciones, 273 RELA, 155 símbolos y 77 imports.
[Resultado baseline](../outputs/rea/ethernet-baseline-20261022T133249267080Z/result.json).
El árbol histórico completo F358 sigue ausente; este resultado prueba la
reconstrucción de Ethernet F352 usando headers/contexto conservados.

El OEM comprueba la parada DMA y fuerza un reset local si falla. F352 ignoraba
el retorno de su poll RX y rearmaba descriptores aunque DMA siguiera activo.
F374r3 exige que los bits de estado RX actuales sean cero; un STOPPED latched
no basta. En timeout mantiene descriptores, buffers, índice, base y ACK intactos,
restaura los controles y cuenta el fallo sin declarar reinicio/progreso exitoso.
Aplica cooldown a los intentos fallidos y restaura IRQ cero a TX/RX/MAC 0x111,
porque NAPI puede haber enmascarado temporalmente las interrupciones.

Dos builds completos F374r3: **24.768 bytes**, SHA-256:

```text
d1a0fbb05b876855454f65519a0ecc64c20106c1c437174e2519281f99f46eed
```

Fuente: [F374r3](../work/kernel-port/f374r3-ethernet-rx-quiesce/qtn-topaz-emac-f352.c).
SHA-256 del fuente: `33a3eb4a25469f39927c4b429dfb40b7afd3f54a8cf319c4c1e727bcab21b82c`.
[Build final](../outputs/rea/ethernet-f374-build-20261022T135845610793Z/result.json).

34 de 38 cuerpos permanecen iguales tras canonicalizar relocaciones. Cambian
el worker de recuperación, estadísticas, inicialización del contador y creación
del puerto por el tamaño de su estructura privada. Se cotejaron las 9 secciones
de datos, todas sus relocaciones, símbolos y los 40 bytes fuera de funciones.
La única normalización de esos huecos es NOP ARC e0 78 para alineamiento a 4;
el reparto cambia en las funciones modificadas pero el multiset total no cambia.
Metadata, alias DT y 77 imports permanecen iguales. El nombre F352 del módulo se
conserva para comparación offline; no se ha creado un paquete de instalación.

Fixture: **60 casos / 48.678 comprobaciones** con helper y cola del caller
extraídos del fuente y macro real de polling Linux 5.10. Se repitió con compilador
independiente. Incluye DMA busy permanente, STOPPED antiguo, último read del
poll, controles distintos, IRQ cero y completion NAPI tardío.
[Resultado](../outputs/rea/f374r3-rx-quiesce-fixture-20261022T141640Z/result.json).
Seis mutaciones negativas demuestran que el gate rechaza byte de datos, destino
RELA, función duplicada, byte en hueco ejecutable, tail adicional y relocación
que cruza un cuerpo. [Revisión final](../outputs/rea/ethernet-r3-final-review-20261022T1401144672462Z/REVIEW.md).
La fixture no ejecuta todo el worker, su elegibilidad ni el lifecycle completo.

## Límite de instalación y trabajo pendiente

El candidato está restringido al worker de un netdev activo del kernel UP,
PREEMPT_NONE. NET_RX_BUSY_POLL fue revisado en ese contexto; no se extiende la
conclusión a SMP o kernels preemptibles.

El problema de lifetime DMA heredado sigue abierto: ndo_stop, cleanup de open y
remove pueden liberar memoria tras una parada incierta. Linux no permite impedir
el cierre devolviendo error de ndo_stop. Hace falta diseñar y verificar un
contrato de parada/reset **local EMAC** que cubra esos caminos y preserve el otro
puerto y las radios. F374r3 no añade reset y no declara ese problema resuelto.

También quedan paridad de ethtool/PHY, filtrado multicast/promiscuidad, diagnóstico
TX, flow control y la aceleración TQE/HBM como camino separado. La reconstrucción
de switch_emac no prueba que F352 implemente ese camino. Véase la
[auditoría de fuente](../outputs/rea/ethernet-source-audit-20261022-133356Z/REPORT.md).

Gates físicos UNRUN: carga/boot del candidato, ambos conectores, asociación bridge
simultánea, tráfico bidireccional, stop/reopen, fallo real DMA, soak, cold boot,
rollback y release. Un futuro firmware requiere versión, hash/size, slot fit,
Bootbase, readback/rollback y autorización exacta antes de cualquier escritura.
Sólo el mtd4 físico es candidato normal; no escribir protegidas ni mtd6 lógico.

## Reproducción

Usar REA-Linux existente y el toolchain ARC del proyecto. Los paths generados y
fuentes/contexto están pinnados; no usar el compilador Windows para el módulo.

```powershell
wsl.exe -d REA-Linux -u root -e /opt/rea/python/bin/python3 /workspace/user-home/Desktop/MitraStar/tools/build_f374_ethernet_rx_quiesce.py --candidate /workspace/user-home/Desktop/MitraStar/work/kernel-port/f374r3-ethernet-rx-quiesce
wsl.exe -d REA-Linux -u root -e /opt/rea/python/bin/python3 /workspace/user-home/Desktop/MitraStar/tools/test_f374_ethernet_rx_quiesce.py --candidate /workspace/user-home/Desktop/MitraStar/work/kernel-port/f374r3-ethernet-rx-quiesce --output /workspace/user-home/Desktop/MitraStar/outputs/rea/f374r3-new-fixture-UNIQUE
```

Siempre usar directorios nuevos. Algunos objetos históricos desaparecieron
durante esta sesión; el build final usa copias ya selladas del baseline únicamente
cuando su hash coincide exactamente. No se restauraron ni reemplazaron outputs;
el mapping consta en `exact-baseline-input-substitutions.json`.
Los generadores r1/r2/r3 y sus candidatos anteriores permanecen independientes.

El ZIP de entrega Ethernet incluye fuentes y pruebas propias, GPL de referencia,
módulos completos, comandos y evidencias REA/coverage. Es un handoff técnico
local, **no una imagen flashable ni aprobación de instalación**. El toolchain y
contexto de kernel conservados siguen disponibles en la entrega técnica general
del 22-10-2026; no se duplican aquí como otra distribución del entorno completo.
