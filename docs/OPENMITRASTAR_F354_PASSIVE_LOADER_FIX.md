# F354: misma lectura pasiva, cargador con parámetros y una sola llamada

Preparado el 21 de septiembre de 2026, sólo offline. F354 deriva del marco
F349 y conserva F340, su supervisor, el módulo pasivo F347, las dos lecturas
previstas y el retorno read-only. No hay escritura flash, TFTP, cambio de radio,
prueba Wi-Fi ni parada deliberada de CPU. El agente preparador no lo ejecutó.

## Causa demostrada de la carga F349

F340 contiene `/bin/insmod -> busybox`, binario de 279604 bytes con SHA-256
`537b409a13db65380cebff31a24b2cfe8d9ebe38678b35fe6c205db080c5773d`.
El inventario de la imagen y la observación read-only de root coinciden.

En ese binario exacto, `insmod_main` empieza en `0x12490`. Tras obtener
`argv[1]`, la instrucción `0x124a6` fija `r1=0x4ee30`, cuyo primer byte es NUL,
y llama a `bb_init_module` en `0x1256c`. No procesa `argv[2+]`. Es el resultado
de compilar sin `FEATURE_CMDLINE_MODULE_OPTIONS`. El árbol BusyBox actual más
nuevo tiene esa opción habilitada, pero produce otro hash; no representa el
binario instalado. No se ha recuperado ni inventado su antigua `.config`.

Así, `execute_read=1` no llega al módulo. El init de F347 devuelve EACCES cuando
`execute_read` está a cero, antes de reservar o acceder a MMIO. F349 imprimía
los diez parámetros sysfs sólo si la carga tenía éxito, pero el validador
comprobaba su cardinalidad antes de `load_rc`; el resultado visible fue
`probe_fields`. El código exacto de carga de ese intento no quedó preservado:
no se añade retrospectivamente al resultado. La prueba negativa posterior,
sin parámetro, devolvió EACCES y no reinició el equipo.

Evidencia física anterior de root, conservada:

- `outputs/handoff-live/f349-passive-20260921T162050Z-0cb97d7b/result.json`:
  FAIL de probe, nueve pets del supervisor, CEASE y retorno F340 con 27 checks;
  CRC completo `2aa26ca6`, protecciones iguales y contención cerrada.
- `outputs/handoff-live/f349-loader-negative-20260921T162706Z/result.json`.
- `outputs/handoff-live/f349-loader-identity-20260921T162837Z/result.json`.

## Cambio funcional mínimo

Se utiliza el cargador que F340 ya incluye: `/usr/sbin/ram-insmod-qtn`,
**816 bytes**, SHA-256
`8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6`.
No se recompila ni instala otro cargador y no se modifica BusyBox.

Su instrucción `0x100d6` obtiene `argv[2]`; `0x10104` lo pasa en r1 y
`0x10108` selecciona syscall 273. Hay una sola `finit_module` en `0x1010c`,
con flags cero y sin fallback a `init_module`. El parámetro se pasa como un
único argumento literal `execute_read=1`. El loader acepta un solo string de
parámetros, como el camino qdrv ya existente.

Se exige hash, archivo regular, permiso executable y ausencia de symlink antes
de ARM y justo antes de cargar. El digest/path del loader se incluyen también
en el contexto y plan. `rmmod` permanece como en F349. No hay segundo intento
de lectura/carga ante un fallo.

## Diagnóstico y recuperación

`load_rc` se valida antes de exigir los campos sysfs. El wrapper convierte
los mensajes fijos del loader en `ok/load_fail/open_fail/usage/other` y sólo
registra si stderr contiene datos; nunca copia sus contenidos arbitrarios.

El transporte de la probe conserva stdout por allowlist antes de validar el
retorno SSH: códigos, nombres conocidos de campo y valores con formato
restringido. Ante timeout se contiene el mismo hijo SSH y se conserva su
salida parcial; no se lanza otro. Los desconocidos se cuentan, no se guardan.

Las cuatro clases de marcador OMSPICTRL se capturan parcialmente en éxito,
error y finally. Sólo se conservan las porciones conocidas de esas líneas,
sus contadores y la presencia de fatal; no UART bruto. Se mantiene la espera
host de dos segundos para el lector UART asíncrono. Una captura parcial nunca
se convierte en PASS ni autoriza repetir la operación.

Owner, nonce, FD watchdog, ARM/BEGIN, CEASE, contención y retorno F340 conservan
el marco F349. El plan previo consumido y su claim no se reutilizan. El launcher
nuevo usa su propio contexto, lease, nonce y claim one-shot. Se comprueba el
mínimo de 500 MiB libres en C antes de preparar y antes de iniciar hardware.

## Pruebas y plan final

`outputs/preflight/f354-loader-20260921T164208Z/result.json` conserva los dos
binarios exactos, disassemblies y ocho casos nativos. Se ejecutan cuerpos C
reales con syscalls simuladas: BusyBox sin/con la feature, argumento entero,
carga positiva, EACCES sin reintento, fallo de apertura y argv extra rechazado.
No se ejecuta el ELF ARC ni se carga un módulo real durante esas pruebas.

Plan final:
`outputs/preflight/f354-passive-20260921T164435Z/plan.json`, SHA-256
`ae10485d3c4b957652e4e8eb6d2b22a7267972a748126321eaa4cc98deab077c`.

**70 pruebas PASS y 93 source pins**: 39 Python, 19 contexto, cuatro del owner
real con backend watchdog fake, y ocho del cargador. Incluye los 52 casos de
F349 y añade argumentos/diagnóstico. Los defaults Python y PowerShell son
read-only. Otro agente verificó independientemente 93/93 pins y hashes de las
pruebas, sin volver a ejecutarlas ni tocar el dispositivo.

Entrada de operación reservada a root:
`tools/run_f354_passive_probe.ps1`. Requiere plan/hash exactos y `-Execute`;
sin ese switch sólo valida offline. Este documento no es evidencia de que la
campaña se haya ejecutado o de que el SPI control haya sido leído físicamente.
