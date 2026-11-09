# F329: watchdog Topaz con Linux 5.10

Trabajo offline del 21 de septiembre de 2026. HGW-500BNA-QCv2 A2 exclusivamente.
El entregable es un overlay de kernel y sus objetos compilados, no una imagen de
flash ni una certificación de recuperación autónoma. No se ha contactado el
dispositivo, leído MMIO, abierto UART, cambiado red ni instalado el candidato.

## Implementación

Se reutiliza `drivers/watchdog/dw_wdt.c` de la copia local Linux 5.10.260. Los
cambios están separados en `work/kernel-port/versions/f329-watchdog/`; el árbol
base, F321, F326 y sus fuentes de ejecución selladas quedan intactos.

El compatible específico es `quantenna,topaz-wdt-f329`. La DT entregada mantiene
`status = "disabled"` y no incluye la propiedad de experimento. El driver exige
máquina HGW exacta, `quantenna,watchdog-experiment`, ventana legacy exacta de
0x20 bytes y reloj declarado de 125 MHz antes de registrar el dispositivo. La
propiedad autoriza un experimento; no certifica los resultados físicos.

Con esa propiedad y un watchdog previamente apagado, probe lee CR una vez y
no escribe CR, TORR ni CRR. Si ya está armado, devuelve `-EBUSY` sin adoptarlo,
retimarlo ni desarmarlo. No carga daemon, init script, timer de alimentación ni
canary temprano. Abrir `/dev/watchdog` sí es una acción que arma el dispositivo:
no se debe usar como consulta de estado.

Se conservan los algoritmos y la integración con watchdog core de Linux:

- `start`: selecciona TOP, escribe TORR, envía `0x76` a CRR y habilita EN en modo
  reset; no escribe el campo TOPINIT no documentado por el BSP.
- `ping`: una escritura `0x76` en CRR.
- `set_timeout`: redondea al TOP soportado y alimenta si está activo. Se limita
  a 1..17 segundos según el modelo de reloj; no ofrece un timeout virtual mayor
  que el hardware como si protegiera frente a un halt del kernel.
- `stop`: devuelve `-EBUSY`. No se conoce un reset por periférico que permita
  desarmarlo. `nowayout` se fuerza en Topaz y no se anuncia magic close.
- `get_timeleft`: lee CCVR; el resultado en segundos depende del reloj supuesto.
- IRQ/pretimeout no se habilitan. No existe aceptación de su cableado/polaridad.

Se evita la lectura genérica de `COMP_PARAMS_1` en +0xf4 y el dump debugfs de
registros extendidos: el BSP solo documenta 0x20 bytes. No se instala un
controlador de reset opcional deducido ni se supone que bajar EN lo detenga.

## Dirección, reloj y límites del modelo

Fuentes locales contrastadas:

- `work/sources/Quantenna-GPL/common/topaz_config.h`: `TOPAZ_MMAP_UNIFIED=0`,
  `TOPAZ_MMAP_ALIAS=0`, `TOPAZ_APB_CLK=125000000` para ASIC.
- `work/sources/Quantenna-GPL/common/ruby_platform.h`: watchdog legacy
  `0xf4000000`; alias `0xe40c0000` solo bajo el modo alias. CR/TORR/CCVR/CRR y
  STAT/EOI se sitúan en +0x00/+0x04/+0x08/+0x0c/+0x10/+0x14.
- `work/sources/Quantenna-GPL/drivers/ruby/soc.h`: TOP `0xc`, EN y modo IRQ;
  kick `0x76`; comentario OEM «5 Seconds».
- `work/sources/Quantenna-GPL/drivers/ruby/machine.c`: secuencia terminal de
  watchdog seguida de reset sysctl.

El reloj APB es una especificación de BSP, no una medida del reloj watchdog.
La tabla `2^(16+TOP)` es el modelo fijo de DesignWare, no un descubrimiento del
silicio Topaz. Bajo ambos supuestos, TOP 0xc da 2,147483648 s por etapa y
4,294967296 s con las dos etapas IRQ; es coherente en orden de magnitud con el
comentario OEM, pero no lo convierte en evidencia de temporización. TOP 0xe
da 8,589934592 s y TOP 0xf da 17,179869184 s en modo reset.

No se garantiza que un bus/MMIO detenido permita que el watchdog siga contando
y genere reset. Esa propiedad precisa una prueba física separada de la muerte
del proceso alimentador y del bloqueo de CPU/IRQ. Un timer software de 20 s no
prueba ninguna de esas propiedades.

## Propiedad y reinicio

El recovery original reserva el mismo MMIO como tercer recurso. El overlay
F329 retira ese recurso de su DT y añade `quantenna,separate-watchdog`; recovery
mantiene LEDs, botones y reset sysctl, pero no reserva ni opera el watchdog
durante la vida normal. El driver DW es el único propietario normal.

`machine_restart()` invoca primero los handlers registrados. Si no hay ninguno
o retornan, conserva la secuencia exacta terminal OEM watchdog + sysctl. Así,
DT deshabilitada, probe fallido o ausencia de driver no eliminan la recuperación
anterior. Este fallback secuenciado de reinicio no equivale a dos drivers
concurrentes reservando y alimentando el mismo recurso.

La configuración fuerza driver/core built-in, nowayout y canaries apagados.
También suprime bind/unbind sysfs y PM; no se promete parada ni suspensión
segura de hardware irreversible. La comprobación de remove es defensa adicional,
no una garantía de que driver core respete un retorno de error de remove.

## Reproducción offline

`python tools/build_f329_watchdog_offline.py` crea un directorio nuevo de
evidencia, clona la fuente Linux en WSL y construye `vmlinux`, DTB, watchdog core,
DW y recovery para ARC. Parte del config exacto de F321 y aplica únicamente el
fragmento F329. No cambia el build compartido ni compone una imagen webformat.

`python tools/test_f329_watchdog.py` extrae las funciones C de ese driver,
sustituye servicios del kernel y MMIO por un arnés nativo acotado, y ejecuta los
casos de comportamiento y fallback. No reimplementa los algoritmos que prueba.
Los resultados quedan en carpetas UTC nuevas; los fallos previos se conservan.

Los PASS del arnés son pruebas de código bajo sustitutos. No prueban la
temporización, decodificación del bus, capacidad de reset ni disponibilidad del
equipo tras una expiración. Las bibliotecas ASan/UBSan del WSL actual no enlazan;
los ensayos válidos usan assertions y límites MMIO explícitos, no sanitizadores.

Resultado final offline:

- Build ARC: `outputs/kernel-port/f329-watchdog-20260921T101516Z/result.json`,
  `PASS_OFFLINE_BUILD_PHYSICAL_GATES_UNRUN`; kernel
  `5.10.260-openmitrastar-radiohw`. Se enlazan el driver, watchdog core y recovery.
- ELF `f329.vmlinux`: 5.181.944 bytes, SHA-256
  `8d1905643415d2a28304ccba2c25d515ff499b7387dc0651a7439ae990a375fd`.
  DTB: 5.438 bytes, SHA-256
  `0651e9e3f9bfef36853c3ec3e21119ef415cf407b040e7c6d838b6eb165f8b08`.
- Driver final: SHA-256
  `9f0498ccc2898137fd0ae09f9cccfc28b04e630abd01763429e3091eb743d6e7`.
  Tras `start`, fija `WDOG_HW_RUNNING`: watchdog core conserva la referencia
  al propietario al cerrar. También se rechaza remove si está activo o latched.
- `outputs/preflight/f329-watchdog-tests-20260921T101514Z/result.json`:
  25 casos C del driver, 2 de fallback terminal y 9 contratos estáticos PASS.
- `outputs/preflight/f329-source-replay-20260921T1016Z/replay-result.json`:
  el generador reproduce los 10 archivos del overlay byte a byte. Esto no es
  una afirmación de dos compilaciones independientes idénticas del kernel.

El build conserva cuatro warnings de código ARC no modificado (`tlb.c` y
`cache.c`); no hay warnings ni errores en el watchdog. Los builds anteriores
y los fallos de preparación/arnés permanecen como evidencia histórica. Solo
el build y tests finales anteriores están ligados al driver final.

`tools/qualify_f329_watchdog.py` vincula esos informes, fuentes, objetos y DT
compilada en un resultado nuevo. Su GO es exclusivamente offline; conserva
`NO_GO_NOT_A_COMPOSED_FIRMWARE_IMAGE` y `release_eligible=false`.

## Aceptación física pendiente

Antes de integrarlo en un firmware instalable debe cerrarse el contrato del
artefacto completo, fit de slot/Bootbase, hashes, backup, recuperación exacta y
lease. Una prueba dedicada debe demostrar carga inactiva, apertura explícita,
timeout observado, pings, alimentación detenida, reboot y recuperación del
mismo dispositivo; después, por separado, bloqueo de CPU/IRQ/bus relevante.

El experimento no se activará al importar scripts ni al arrancar F321/F326.
Hasta esos resultados, `watchdog físico PASS`, `recuperación desatendida PASS`
y `release PASS` siguen sin establecerse.
