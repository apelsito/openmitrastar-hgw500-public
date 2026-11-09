# F351: consumidor mínimo del journal F350

Validación posterior en el HGW, 21 de septiembre de 2026 a las 16:42 UTC:
`outputs/handoff-live/f351-negative-arc-20260921T164227Z/result.json` registra
**PASS_REAL_ARC_NEGATIVE_CLI_ONLY**. El binario exacto ejecutó ayuda, rechazo de
stdin vacío, rechazo de 4097 bytes y rechazo de LOAD sin dispositivo. Los cuatro
casos pasaron, el boot ID permaneció igual y se retiró el ejecutable temporal.
No estaba presente el driver F350; hubo cero operaciones ioctl positivas,
escrituras flash, pruebas radio, uso de UART o activación del watchdog. Esto
valida ejecución básica ARC y fallos de entrada, no persistencia física.

La cualificación original de compilación se conserva a continuación:

21 de septiembre de 2026. **PASS_OFFLINE_CLI**: 73 casos nativos y dos
compilaciones ARC estáticas byteidénticas. No se ha abierto un dispositivo
real ni ejecutado el binario ARC. No hay integración en arranque, instalación,
activación de gates ni cambios de F349/F340/F350.

Fuente: `work/userspace/f351-journal-cli/`. Las tres cabeceras en `vendor/`
son copias exactas de las vinculadas a la cualificación final F350. El ABI
es de 4180 bytes, payload en offset 84. No requiere bibliotecas dinámicas ni
Module.symvers (es un programa de userspace).

## Uso y salidas

- Sin argumentos o `--help`: sólo ayuda; no abre el nodo ni sysfs.
- `observe`: snapshot numérico JSON, sin interpretar el control como permiso
  de escritura ni atribuir una identidad exacta E/F.
- `inspect`: metadatos JSON del registro; no expone payload.
- `load`: sólo bytes del payload, tras validar íntegramente la respuesta.
- `save`: consume stdin completo, de 1 a 4096 bytes, antes de abrir el nodo.
  Un byte 4097 o entrada vacía se rechaza. stdin debe llegar a EOF; durante esa
  lectura no se ha accedido al dispositivo. La salida sólo contiene metadatos.

El nodo es fijo: `/dev/om-f350-journal`. Se abre con O_NOFOLLOW y O_CLOEXEC.
Se exige inode character, UID/GID cero y modo exacto 0600. Major/minor deben
coincidir con `/sys/class/misc/om-f350-journal/dev`, cuyo filesystem debe ser
sysfs; el major esperado es el de misc (10). No se cambia el modo del nodo ni
se admite una ruta alternativa.

El consumidor exige ioctl rc=0 **y** resultado global, backend y journal
coherentes. Rechaza cuarentena, claim retenido, ABI/operación distintas,
identidad nula/ilegible, flags no booleanos, WIP, fases incoherentes, secuencia
cero y longitudes/slots inválidos. SAVE requiere commit visible, protección
restaurada y witnesses iguales. `exact_part_verified` debe seguir siendo cero
para esta versión F350. Los campos de salida se inicializan con un patrón que
permite detectar respuestas sin completar; LOAD comprueba además el tail cero.

El kernel F350 verifica el CRC y la copia completa de salida. El CLI sólo
empieza a escribir payload en stdout después de validar toda esa respuesta y
cerrar el descriptor. Un fallo de escritura de stdout devuelve error; no se
incluye payload en los diagnósticos. La memoria temporal se borra al terminar.

| Exit code | Significado |
|---:|---|
| 0 | Operación verificada o ayuda |
| 1 | Error de dispositivo, ioctl, contrato de respuesta o salida |
| 2 | Argumentos o stdin inválidos |
| 3 | Journal vacío: LOAD deja stdout vacío; INSPECT emite JSON `empty` |

No se debe interpretar ioctl rc=0 aislado como éxito. No se debe aplicar
`strerror` a los códigos propios del journal. El consumidor tampoco abre gates
del módulo: si `allow_hw`/`allow_program` están desactivados, la petición falla.

## Verificación y artefacto

El ejecutable nativo de pruebas usa wrappers de syscalls: nunca abre `/dev`
ni el sysfs real. Cubre default sin acceso, identidad falsa/symlink/permisos,
stdin binario/EOF/EINTR/overflow, EMPTY, 4096 bytes, respuesta intacta/parcial,
errores de ioctl y de las tres capas, flags de SAVE y cierre del descriptor.
GCC `-fanalyzer` pasa. El binario de producción no incluye los wrappers.

Build: `python tools/build_f351_journal_cli.py`, con el sysroot noatomic
existente y el toolchain ARC de la misión. La ejecución ARC permanece UNRUN;
no se utiliza QEMU ni se hacen pruebas Wi-Fi/AELITA.

Resultado canónico:
`outputs/userspace/f351-journal-cli-20260921T162420Z/result.json`, SHA-256
`3f8790851bf5d766e96c02023ce338c1a8b321f5405d2fb5619766ed7eefc2c3`.

Binario `om-journal-cli-a`, **25.524 bytes**, SHA-256
`dee84fd30d41734e52d4627418028a1d15cd64db87cca1bc3eef261aacb0edef`.
Su pareja `om-journal-cli-b` es idéntica. Pruebas en `tests.json`, SHA-256
`b7391ae8d3e95518e9cab52061fb880c576462890e32dc605bd2957409dee5c7`.

Vinculación F350:
`outputs/preflight/f350-qualified-20260921T161419Z/result.json`, SHA-256
`f6acac38db68da58e6fcefda6e51f2fbdc4e9e395063b3f3f7dfb860d3d4dd9e`.
Esta vinculación corresponde al módulo corregido tras el hallazgo del footer;
no al artefacto histórico F350 de 160932Z.
