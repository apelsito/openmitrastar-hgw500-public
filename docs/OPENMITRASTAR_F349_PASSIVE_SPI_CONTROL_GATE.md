# F349 — lectura pasiva de SPI_CONTROL en F340

Preparación offline terminada el 21 de septiembre de 2026. **48 pruebas PASS**:
27 del protocolo y del `run()` real con modelos de host/UART, 17 de contexto
PowerShell y 4 con procesos C reales y watchdog simulado. Los puntos de entrada
por defecto validan archivos y no acceden al equipo. Ninguna lectura física del
probe se ha ejecutado durante esta preparación.

Plan inmutable: `outputs/preflight/f349-passive-20260921T161357Z/plan.json`.
SHA-256: `14cd49028f3b5e1540f951d16af287d6cc9bb4a90f4490089e1026ff444d605d`.
Resultado: `outputs/preflight/f349-passive-20260921T161357Z/result.json`.
El plan vincula 68 archivos, incluyendo las fuentes, imágenes, pruebas,
bibliotecas de transporte y contratos anteriores que realmente reutiliza.

## Alcance de la operación

El módulo F347 es el mismo código del probe F320, recompilado para F340:

| Artefacto | Bytes | SHA-256 |
| --- | ---: | --- |
| `qtn-topaz-spi-control-probe.ko` | 7.592 | `6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a` |
| Supervisor F340 de producción | 33.720 | `cc6492dc5d5689f30e3c22bdfd843e3bb40c2b19a53ddd6bdd94d3775d05fb9a` |
| Imagen F340 instalada | 5.349.376 | `211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa` |

La inserción explícita con `execute_read=1` lee una vez el mapa SYSCTL en
`0xe0000004`. Si los bits `0x60000000` permiten el mapa legacy, reclama y mapea
el recurso y lee una vez `SPI_CONTROL` en `0xe2000004`. No escribe registros
SPI, no accede a aperturas de comandos de flash y no ejecuta transacciones NOR.
La retirada libera recursos sin realizar E/S de registros. Un mapa incompatible,
conflicto de recurso, fallo de lectura, timeout o reset impide el PASS.

El resultado es la palabra de control sin interpretar. No demuestra propiedad
exclusiva de todos los maestros hardware, identificación 35F/36E, funcionamiento
de comandos SPI ni escritura de configuración. La petición de recurso de Linux
no constituye una prueba de arbitraje con firmware de otros procesadores.

F343 permanece rechazado y no se reutiliza. F349 no incluye parada deliberada
de CPU, dirección inválida, cambio de radio, tráfico Wi-Fi ni acceso a AELITA.
Un fault/reset durante la lectura es **FAIL**, nunca una aceptación de CPU-halt.

## Secuencia y propietario del watchdog

1. El launcher exige F340, ruta Ethernet local existente, nonce SSH→UART,
   PnP exacto y lease F319. Un claim de host exclusivo consume el plan una sola
   vez. No abre TFTP ni modifica reglas de firewall.
2. Comprueba identidad, hash del supervisor, ausencia de otro owner y módulo,
   almacenamiento de sólo lectura, watchdog inactivo y `console_loglevel > 6`
   mediante lectura de `/proc/sys/kernel/printk`. No cambia el nivel de consola.
3. Activa RX UART continuo y copia el módulo a un directorio RAM privado.
   Verifica de nuevo su SHA-256 antes de insertarlo.
4. Crea el supervisor F340 real en proceso separado, con stdin cerrado y HUP
   ignorado desde la shell; registra el PID anunciado y lo compara con el peer
   real de la API. `state.json` no se acepta como prueba de propietario.
5. El cliente canónico comprueba socket privado, UID root, `SO_PEERCRED`, PID,
   instante de arranque, boot ID y token de sesión. ARM y BEGIN se envían dentro
   de la misma orden SSH, con `&&`, para respetar la ventana de cinco segundos.
   La fase `spi-control-read` dura como máximo 60 segundos; la sesión, 180.
6. Ejecuta una sola inserción `/bin/insmod`, recoge los parámetros exactos y
   ejecuta una sola retirada `/bin/rmmod`. Exige lecturas 1+1, escrituras 0,
   proveedor transaccional deshabilitado, módulo retirado, boot ID conservado
   y cuatro mensajes UART ordenados y coherentes con sysfs.
7. Sólo después de una lectura completa válida solicita CEASE al owner. El
   supervisor deja de alimentar y mantiene el FD abierto. El reset posterior
   permite terminar la sesión armada sin fingir un desarme.
8. Tras un prompt Bootbase nuevo, exige WDT EN=0 y contador estable, verifica
   protegidos y CRC de F340 y arranca directamente su prefijo desde flash.
   El retorno exige un boot ID nuevo, marca F340, 27 comprobaciones de plataforma,
   watchdog inactivo y ausencia de los archivos del owner anterior.

Las escrituras necesarias para alimentar el watchdog usan el driver y sus
ioctl estándar. La afirmación «cero writes» se refiere a los registros SPI del
probe. El retorno Bootbase sólo lee flash y modifica `bootargs` en RAM con
readback; no usa `saveenv`, `run`, selector, write, erase, unlock ni WPSEL.

## Fallos y cierre

La creación del owner se marca como intentada antes de lanzar SSH. Si se pierde
la respuesta con el PID, el runner consulta la API y reconcilia el peer por
token y boot ID. Nunca mata un posible propietario armado. Antes de ARM, un
owner confirmado inactivo puede expirar por su propio plazo; sólo después se
eliminan los archivos del directorio de staging. Puede quedar el directorio
UUID vacío en RAM, que desaparece con el siguiente arranque.

Una respuesta ARM perdida no autoriza insertar el módulo. El runner conserva
el fallo, intenta CEASE/retorno de forma acotada y nunca repite el probe. Un
reset perdido puede terminar en recuperación software explícita; esto sigue
siendo FAIL y no acredita la respuesta del watchdog.

Si la verificación de protegidos/CRC falla pero el prefijo F340 validado logra
arrancar y pasar plataforma/WDT, el resultado guarda ambos hechos por separado:
**retorno confirmado y prueba fallida**. No reinicia una segunda vez ni conserva
un falso estado de watchdog armado. Si `bootm` retorna, no se reintenta.

Si no se demuestra liberación del watchdog o contención de procesos/lector,
se conserva la barrera de lease. No se mata el propietario remoto ni se prueba
un cierre mágico. Las cuatro líneas OMSPICTRL validadas se guardan aparte en
`probe-uart-sanitized.log`; el redactor UART compartido permanece intacto. Los
resultados públicos no incluyen tokens de sesión, PSK, calibración ni MAC de
clientes.

## Ejecución reservada al operador físico

Validación local sin dispositivo:

```powershell
python tools/f349_probe_executor.py --plan outputs/preflight/f349-passive-20260921T161357Z/plan.json --plan-sha256 14cd49028f3b5e1540f951d16af287d6cc9bb4a90f4490089e1026ff444d605d
```

Comando preparado para root, después de la revisión del plan:

```powershell
& tools/run_f349_passive_probe.ps1 -PlanPath outputs/preflight/f349-passive-20260921T161357Z/plan.json -PlanSha256 14cd49028f3b5e1540f951d16af287d6cc9bb4a90f4490089e1026ff444d605d -Execute
```

No se ejecutó `-Execute` durante la preparación. Las pruebas nativas compilan
las fuentes F340 con `F340_TEST`: sólo simulan apertura, ioctl y alimentación,
y no acceden a `/dev/watchdog`. Comprueban los clientes y sockets reales en
WSL, pero no sustituyen la aceptación física del módulo ni garantizan que el
watchdog recupere un bloqueo de CPU, bus o chip completo.
