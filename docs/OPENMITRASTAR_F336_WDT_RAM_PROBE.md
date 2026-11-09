# F336: prueba del watchdog desde RAM

Fecha: 2026-09-21. Estado: **arranque RAM, armado/pets, cese de alimentación,
reset observado y retorno F321 verificados físicamente por el operador principal**.
Plataforma F321 27/27 PASS a las 13:48:53 UTC. Las pruebas offline también pasan.

F336 arranca un kernel diagnóstico desde RAM y monta el SquashFS F321 existente
en flash, de solo lectura. **El RAS F336 contiene sólo kernel: nunca se flashea.**
No incluye rootfs ni autoriza escrituras de particiones o del entorno Bootbase.

## Resultado físico del tercer intento

[Resultado y traza](../outputs/handoff-live/f336-ram-20260921T133950Z-51c6016b/result.json):
`CESSATION_RESET_AND_F321_RETURN_OBSERVED`.
[Plataforma tras retornar](../outputs/handoff-live/f336-ram-20260921T133950Z-51c6016b/return-platform/status.json):
**27/27 PASS**. No se realizó ningún test Wi-Fi/RF ni acceso a AELITA.

- F336 se identificó mediante `#336`, marcador DT y nuevo boot ID.
- El programa emitió 25 pets explícitos. Tras CEASE, 42 muestras mantuvieron EN=1
  y observaron el contador descendiendo, sin incrementos registrados.
- El primer marcador de reset UART llegó entre **8,766 y 8,782 s** después del
  último pet, según el intervalo envío/acuse del reloj host. Incluye la latencia
  hasta ese marcador de Bootbase; no es una medición precisa del oscilador.
- No hubo fallback software, veredicto negativo ni cierre del descriptor antes
  del reset. La captura no detectó fatal ni panic.
- En Bootbase, CR EN=0 en ambas lecturas y CCVR=65535 estable. El retorno directo
  confirmó el kernel F321, ausencia del marcador RAM y otro boot ID.
- CRC de mtd4 completo **`6ed8e483` antes y después**; ningún comando de escritura
  de flash. Lector UART, puerto y procesos quedaron contenidos.

Esto prueba el cese y reset con CPU/SSH en funcionamiento normal. **No prueba
recuperación ante CPU/IRQ/bus bloqueados, causa de reset en registros de silicio,
reset completo de chip ni ausencia de productores entre muestras.** Esos límites
siguen reflejados como falsos en el evaluador. Los intentos fallidos anteriores
se conservan sin reetiquetar.

## Entrega verificable

- Build: `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f336-wdt-ram-20260921T123734Z\result.json`.
- RAS: subruta `a\F336-WDT-RAM-ONLY-NOT-A-FLASH-IMAGE.ras.bin`,
  1.531.365 bytes, SHA-256
  `c200f12bf38a7e94235817e208601cd6c2b42e2e11d846c0e24da9e0b8a8c675`,
  CRC32 `3d8484ca`.
- Utilidad ARC estática: [resultado de build](../outputs/kernel-port/f336-wdt-probe-20260921T124221Z/result.json),
  `f336-wdt-probe-a`, 25.528 bytes, SHA-256
  `dda1cd752fcb43d4e222ea60a40595b10e6fbc647a62925df2559ed811b5e92e`.
- [Manifiesto del ejecutor revisable](../outputs/preflight/f336-executor-20260921T133902Z/plan.json),
  SHA-256 `3f915f594dbac67c82c900eaaa922d63ff88b6ff5cc72ec2e3f38649bca09f67`.
  El [plan inicial sin ejecutor](../outputs/kernel-port/f336-ram-plan-20260921T125700Z/plan.json)
  se conserva como antecedente.
- [Auditoría adicional del payload, configuración y peers](../outputs/kernel-port/f336-ram-readiness-20260921T125401Z/result.json).
- [19 pruebas del ejecutor real con transportes falsos](../outputs/kernel-port/f336-executor-tests-20260921T133800Z.json),
  [7 de NUL/reactivación del lector](../outputs/kernel-port/f336-marker-rearm-tests-20260921T133800Z.json),
  [16 del evaluador](../outputs/kernel-port/f336-plan-tests-20260921T125300Z-r2.json),
  además de las 14 de la utilidad: **56 pruebas offline PASS**.

Dos compilaciones independientes produjeron ELF e imagen idénticos. Se usó un
clon aislado del árbol F329 y el mismo toolchain ARC700/uClibc de la línea F321;
la diferencia de `CONFIG_CC_VERSION_TEXT` corresponde al nombre del ejecutable
`arc-linux-gcc` frente a `arc-snps-linux-uclibc-gcc`, cuyos archivos son iguales.
La única opción funcional adicional frente a F329 es `WATCHDOG_SYSFS=y`.
Los imports de los módulos exactos del rootfs F321 resuelven contra F336 y sus
peers; esto no sustituye el arranque y la prueba física de las radios.

## DT, entrada y rootfs

El DT parte del F321 exacto, SHA-256
`7063f6b1f7b0180226c0d0fc6fd0ecd2659e18463664d42dd2a88726a2e80d81`.
Conserva las propiedades anteriores salvo separar la propiedad del recurso
watchdog del driver recovery, retirar canarios inactivos y añadir la identidad
RAM. Añade el nodo watchdog opt-in y su reloj declarado de 125 MHz. Esa frecuencia
es una hipótesis de configuración; **no está medida físicamente**.

El DT compilado, SHA-256
`d52304dff07d219a946a40cf661df98c692df99ba35a76de40c35d938c0e2771`,
se extrajo del ELF en `0x84956240`, se comparó con el sidecar y se encontró byte
a byte en el payload descomprimido. No depende de que Bootbase cargue un DT externo.

| Región | Dirección / límite |
|---|---|
| Recepción RAS en RAM | `0x83000000` |
| Scratch CRC32 | `0x84000000` |
| Carga kernel | `0x8493a000` |
| Entrada kernel | `0x8493e000` |
| Fin kernel | `0x84d02000` |
| Fin DDR | `0x88000000` |
| Rootfs F321 preservado | `0x90960000`, ventana `0x460000` |

No hay solapamientos entre esas regiones. El rootfs debe seguir siendo el F321
de SHA-256 `75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e`.
La cadena usa la receta ARC existente: nuevo ELF → raw → compresor LZMA legado
→ uImage → RAS. No hay encadenamiento a un kernel antiguo ni initramfs embebido.

El release permanece `5.10.260-openmitrastar-radiohw` para los peers. La identidad
diagnóstica es `uname -v` con `#336` y el DT
`/proc/device-tree/openmitrastar,f336-wdt-ram = F336_WDT_RAM_ONLY`.
El texto de versión del rootfs F321 no prueba que se haya vuelto a arrancar F321.

## Observación y secuencia de prueba

El driver conserva el rechazo del watchdog prearmado y no escribe CR, TORR ni
CRR durante probe. Los atributos de solo lectura `f336_control` y `f336_counter`
leen CR y CCVR usando el mapping del propio driver. Si no registra el dispositivo,
los parámetros `dw_wdt/f336_probe_seen` y `f336_probe_control` permiten distinguir
un rechazo prearmado de la ausencia de probe. `state=inactive` del framework
por sí solo no prueba EN=0.

La utilidad sin argumentos o con `--inspect` sólo lee identidad/DT/sysfs; no abre
`/dev/watchdog0`. `--session` espera órdenes por stdin. `ARM` comprueba identidad
y CR EN=0, abre el descriptor y usa ioctls estándar para timeout de ocho segundos.
`PET` alimenta explícitamente; `STATUS` observa; `CEASE` termina los pets propios
y mantiene el descriptor abierto mientras muestrea CR/CCVR cada 200 ms. La
sesión dura como máximo 120 segundos y la observación posterior a CEASE 40.

El runner propuesto debe registrar con un único reloj host el envío y el acuse
del último pet y el reset observado en UART continua. El proceso de muestreo y
SSH siguen vivos: la primera prueba no detiene IRQ ni CPU. El timeout elegido
no supera `max_hw_heartbeat_ms`, por lo que el core no necesita su worker de
alimentación mientras el watchdog está activo y el descriptor sigue abierto.

Una recarga del contador, un contador inmóvil, una lectura fallida o la falta
de reset dentro de la ventana impiden aceptar la prueba. La utilidad emite un
veredicto negativo **antes** de cerrar el descriptor y avisa que el cierre puede
provocar otro pet del core. Un reset posterior al cierre o a SysRq es recuperación,
no evidencia de expiración autónoma. El muestreo tampoco excluye escrituras entre
muestras ni demuestra la causa del reset a nivel de silicio.

Tras el reset, el operador debe observar Bootbase y leer primero el mapa legado
en `0xe0000004` (bits 29/30), después CR `0xf4000000` y CCVR `0xf4000008` dos veces,
con pausa host de 200 ms. EN=1, mapping incierto o contador que cambia mientras
se declara apagado bloquean la progresión. No se presupone reset de chip completo.

El retorno usa **bootm directo de una copia RAM del F321 leído de flash** y el
[contrato exacto de Bootbase](../outputs/preflight/f337-direct-f321-return-20260921T130000Z/result.json).
La lectura es `spi_flash read 0x007e0000 0x83000000 0x007a0000`; su respuesta debe
confirmar flash `0x7e0000`, memoria `0x83000000`, size y ret_size de 7.995.392.
Un CRC correcto de RAM residual no sustituye esa confirmación. El prefijo F321
de `0x517000` bytes exige CRC `bd1135df`. El CRC completo se obtiene de nuevo
antes del ensayo y debe repetirse al retornar; `6ed8e483` es sólo histórico.
No debe llamar `bootselect`, `runningbootcmd` ni
`run`: esas rutas pueden ejecutar `saveenv` si bootm retorna. Tampoco usa el viejo
`bootbase_ram_tftp_one_shot.py`, que modifica bootval/entorno. El uImage está en
offset cero y `bootm 0x83000000` recibe su cabecera; no se añade `+4` ni se trata
la dirección SPI como un mapping de CPU.
Si bootm retorna al prompt, se conserva el prompt y se declara fallo; no se
encadena automáticamente ningún fallback que persista selección.

La aceptación del retorno exige nuevo boot ID, ausencia del marcador F336,
`uname -v` igual al baseline F321 y los checks de plataforma del operador.
El evaluador sólo etiqueta `CESSATION_RESET_AND_F321_RETURN_OBSERVED`; deja
explícitamente sin probar reloj, causa de reset, reset completo y recuperación
ante bloqueos CPU/IRQ. F336 nunca habilita flash, incluso con esa evidencia.

## Ejecutor y fases

La primera campaña del operador,
`outputs/handoff-live/f336-ram-20260921T131641Z-9e5f6ff2/result.json`, conserva
`FAILED/ssh_deadline` en baseline: el reboot sí alcanzó Bootbase, pero SSH tardó
en terminar y el controlador no llegó a consultar el nuevo prompt. Recuperó
F321 por lectura y boot directo, con contención confirmada; no arrancó F336 ni
armó WDT ni emitió escrituras de flash. El plan inicial `d0c745…` queda superado.

La revisión `b72e992…` contiene el proceso SSH tras ese timeout y continúa sólo
hacia la comprobación de UART. El timeout queda registrado como transporte sin
prueba de reboot. Los nuevos tests usan `Host.reboot_to_prompt` y `Host.ssh`
reales con Popen falso: un prompt nuevo permite avanzar; silencio, prompt antiguo
o contención no demostrada fallan. Ningún otro comando tolera ese timeout.

El segundo intento,
`outputs/handoff-live/f336-ram-20260921T132233Z-03826f49/result.json`, llegó al
kernel F336, con watchdog registrado e inactivo según la lectura del operador.
Falló porque F321 no incluye `tr`, usado al leer el marcador DT. Durante su
recuperación, el lector volvió a procesar indicaciones viejas de autoboot y agotó
su límite. Ambos fallos permanecen en el resultado original; no se armó WDT.

El retorno separado desde ZHAL está en
`outputs/recovery/f336-bootbase-20260921T133521Z-9177a1ee/result.json`: lease nuevo,
nonce Bootbase fresco, lectura/CRC/boot directo, sin SSH ni reinicio adicional.
El operador verificó después F321 27/27. La revisión `3f915…` lee el marcador con
`cat` y elimina su NUL terminal en Python; cada activación del lector fija un
offset mínimo y descarta eventos anteriores. Sus siete regresiones ejercitan la
lectura real de Host y la reactivación real de Capture sobre transportes falsos.

[run_f336_wdt_ram.ps1](../tools/run_f336_wdt_ram.ps1) conserva el guard F319, sus
dos mutexes y el lock canónico `outputs/locks/f301-physical-radio.lock`, enlazados
al nonce de F321. Crea un contexto propio `f336-ram-context/v1`, con purpose
`ram-watchdog`, hash real F336 y sin permiso de flash. Revalida la regla UDP
existente, Python fijado, Ethernet 18/.49 y la ruta directa; no crea reglas ni
solicita elevación. El permiso de transporte antiguo no se presenta como permiso
de un candidato F334 ficticio.

[f336_wdt_ram_executor.py](../tools/f336_wdt_ram_executor.py) reutiliza el servidor
TFTP de un archivo y el serial nativo fijados. Un único lector UART permanece
activo antes del reboot, durante el kernel RAM, el experimento y el retorno.
Las líneas desconocidas o sensibles se descartan del log; las líneas admitidas
redactan MAC. Se conservan secuencia, tiempos, número de bytes y hash del flujo,
sin guardar UART raw. La parada del autoboot consume cada indicación nueva una
sola vez, con límite de tiempo y número de eventos.

Cada comando Bootbase pertenece a una lista literal. `setenv` sólo cambia valores
temporales y lleva readback exacto antes del uso. El envío de `bootm` invalida el
prompt: ningún byte nuevo implica que sigue sin haber prompt, aunque el buffer
retenga uno antiguo. El retorno a F321 se intenta una vez; si bootm vuelve al
prompt o no confirma identidad, no se llama otra vez ni se invoca bootselect.

El modo `Inspect` arranca F336, comprueba nueva identidad, perfiles MTD ROM,
`/persist` RO y ausencia de store montado, verifica el helper en RAM y ejecuta
sólo `--inspect`; después vuelve a F321. `Experiment` realiza lo mismo y espera
`ARM` o `RETURN` por stdin en esa misma sesión durante 120 segundos. EOF o tiempo
agotado retornan sin armar. `ARM` vuelve a comprobar boot ID, storage y estado
antes de abrir el watchdog. Es control del operador de la sesión ya autorizada.

Ejemplo listo para el operador, **no ejecutado por este subagente**:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/run_f336_wdt_ram.ps1 `
  -PlanPath outputs/preflight/f336-executor-20260921T133902Z/plan.json `
  -PlanSha256 3f915f594dbac67c82c900eaaa922d63ff88b6ff5cc72ec2e3f38649bca09f67 `
  -Mode Inspect -Execute
```

Sin `-Execute`, ambos entrypoints sólo validan archivos; esa ruta se ha probado.
La validación de plataforma 27/27 tras el retorno sigue siendo paso obligatorio
del operador principal: el resultado de este runner no la suplanta.

Los fallos de TFTP, lectura, marcador, expiración o recarga ajena siguen siendo
fallos aunque se recupere F321 por software. Se contiene el servidor y los
procesos previos antes del retorno. Un fallo de contención impide PASS. Si no se
demuestra contención, el launcher deja el directorio de bloqueo como barrera;
no afirma que la salida del proceso dueño pruebe el cierre de todos sus hijos.

La [auditoría de init F321](../outputs/preflight/f337-f321-startup-writes-20260921T130500Z/result.json)
verifica 41 entradas y cinco vistas DT `mtd-rom`. El arranque normal usa RAM
para claves temporales, entropía y configuración; no se encontró commit automático
del store. El gate runtime vuelve a comprobar cmdline/montajes/flags. La comparación
CRC antes/después cubre mtd4 completo; no se presenta como readback nuevo de todo
el chip SPI ni como prueba de ausencia de escrituras de cualquier software externo.

## Otros posibles productores de pet

La auditoría extrae y verifica 41 archivos de módulos/firmware del rootfs F321.
No encontró literales WDT directos en los módulos host. Las definiciones
`init_watchdog_timer`, `pet_watchdog_timer` y `global_disable_wd` existen en el
source vendor; no se encontraron llamadas a esos helpers en el source host
canónico inspeccionado ni sus símbolos en los módulos exactos.

El ELF MuC carece de section table. Se revisaron también los segmentos ejecutables
PT_LOAD; el instalador `qdrv_fw_install` los copia secuencialmente y sus offsets
coinciden con los escaneados. Las coincidencias de CR/TORR están a offsets impares,
sin alineación de instrucción ARC, y no aparece un literal CRR. Eso no identifica
un pet periódico ni permite descartar direcciones calculadas o accesos indirectos.
La discriminación concreta es observar CCVR al cesar nuestro pet con CPU/SSH
sanos. No se bloquea indefinidamente el ensayo por una constante ambigua.

## Reproducción y resultados preservados

Fuentes: [builder RAM](../tools/build_f336_wdt_ram.py),
[contrato DT/driver](../tools/f336_wdt_ram_contract.py),
[utilidad C](../work/kernel-port/versions/f336-wdt-ram/f336_wdt_probe.c),
[builder de utilidad](../tools/build_f336_wdt_probe.py),
[plan/evaluador](../tools/f336_wdt_ram_plan.py).
Los builders y el evaluador operan offline. El ejecutor separado descrito arriba
requiere `-Execute`; su modo por defecto sólo valida archivos.

Se preservaron los builds fallidos `122920Z` y `123628Z`: el primero compiló
correctamente el kernel pero invocó mal el compresor legado; el segundo detectó
la copia raw ausente en ese output fallido. El build canónico regeneró raw desde
el ELF y usó la receta original. No se modificaron artefactos F321/F329. Las
advertencias ARC cache/TLB preexistentes permanecen; no hubo avisos nuevos WDT.
