# F331: postfiltro OEM recuperado y portado a Linux 5.10

> Errata de integración ABI, 21-09-2026: la unidad rate descrita más abajo como
> paquetes/s es incorrecta. El símbolo OEM `detect_drv_sample` mide 8 bytes;
> `spinlock_t` UP sin DEBUG_SPINLOCK ocupa 0, `tx_pkts` está a +0 y `tx_bytes`
> a +4. El worker lee +4 en `0x3be2`: consume **bytes/s**. F332 usará
> `sample->tx_bytes`. Las operaciones numéricas y los resultados diferenciales
> F331 permanecen válidos porque comparan las palabras originales; sus nombres
> de parámetro/comentarios de unidad quedan como evidencia histórica. No se
> alteran los artefactos binarios ya verificados.

21 de septiembre de 2026. Trabajo local exclusivo del HGW-500BNA-QCv2 A2.
No se ha conectado al equipo, leído MMIO, cargado módulos ni escrito firmware.

## Resultado

Se ha cerrado la derivación que F316 dejaba como entradas desconocidas
`history_reject` y `lsr_history_reject`. El nuevo core C reproduce los cálculos
de historial, FH, rechazo LSR, estado malo, rate y condición de callback. Ya no
recibe esos dos rechazos como booleanos que otro componente tendría que adivinar.

Los bloques OEM `.text[0x43c0,0x4c06)` y `[0x4c80,0x4cb0)` conservan **2.166
bytes originales** en un oracle privado. Sus relocaciones se resuelven sobre
memoria de prueba. Se reemplaza únicamente la salida `0x4c06` por un trampoline
de retorno y se excluye la cola de scheduling/PM. El callback OEM apunta a un
contador privado de QEMU, nunca a qdrv. El módulo de producción contiene solo
el C reconstruido, no esos bytes ni el antiguo ciclo de vida OEM.

**5.360 comparaciones diferenciales PASS**: 4.096 estados deterministas, 64
fronteras de ancho/PRI/duplicados/rate y 1.200 polls secuenciales que recorren
ambos modos de historial. Se comparan las 240 entradas, índices, sumas, memoria
de detección rechazada, temporizador, estado, rechazo LSR, contador de rechazos
y la condición final de llamada. Los tests exigieron QEMU exit 0, salida exacta,
stderr/guest_errors vacíos y conservación de los bytes antes de relocar.

Oracle canónico:

`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f331-postfilter-20260921T103709Z/result.json`

El core también pasa **460 assertions nativas** de contexto, entrada ausente,
no mutación en fallo, ring/rate, fronteras y autorización siempre falsa; GCC
`-fanalyzer` pasa. Dos builds independientes del módulo ARC son idénticos:

`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f331-kernel-20260921T103722Z/result.json`

`f331_postfilter_port.ko`: **5.148 bytes**, SHA-256
`a73a10ed48e35f888b12566e5bacbc17e3a215cb53d42f8dc54e484075424d74`.
Kernel `5.10.260-openmitrastar-radiohw`, config exacto F321. Importa únicamente
`__modsi3`, `__udivsi3` y `memset`, todos exportados por el vmlinux exacto F321.
El módulo no registra dispositivos, timers, workqueues ni callbacks de radar.

## Correcciones respecto a las hipótesis anteriores

**La entrada no era el recuento de la ventana previa.** `r17`, cargado de
`sp+0x14`, conserva `total_count`. `sp+0x10` contiene `current_window_count`,
salida de preprocess igual a `total_count - old_count`. Es el valor insertado
en el historial y entregado como tercer argumento de `detect_radar`. F330
confirma esta interpretación ejecutando secuencias originales. El nombre
`prior_window_count` de la fachada F328 anterior necesita reconciliación al
componer el pipeline; F331 usa los nombres precisos.

**Hay un único anillo de 240, con una ventana corta desfasada.** Sin LSR se
usa el índice corto y envuelve a 20. Con LSR, el índice corto empieza en 220,
el largo en 0, ambos envuelven a 240 y solo se escribe la posición larga.
Ambos valores salientes se capturan antes de esa escritura. Esto mantiene
ventanas reales de 20 y 240 polls sobre el mismo almacenamiento. No se actualiza
dos veces la misma entrada ni se envuelve siempre el corto a 20.

**El matcher no es una comparación de conjuntos.** Cuenta cada PRI antiguo
no nulo y sus coincidencias contra las tres posiciones nuevas; requiere igualdad
entre número antiguo, número nuevo no nulo y número de parejas coincidentes.
PRI duplicados pueden provocar rechazo. El shortcut FH y las tolerancias de
ancho/PRI respetan inclusividad y aritmética unsigned de las instrucciones.

**9, 24 y 2 son polls.** Las transiciones incluyen entrada en malo con 9,
extensión a 24, decrementos de 1 o 2 y retorno a bueno cuando el temporizador
signed es menor que 1. El candidato que agota ese temporizador todavía se
rechaza en esa iteración. La cadencia nominal OEM de 50 ms haría 9 polls ≈450 ms
y 24≈1,2 s; esto no es una medición de jitter o latencia real.

## Rate: productor y aritmética

En `qdrv_radar_sample_work`, el GPL calcula
`sample->tx_pkts = MuC.tx_sample_pkts / ic_sample_rate`; son paquetes por segundo.
El período por defecto es 1 segundo. El worker radar toma ese valor sincronizado
cada vez que el contador signed de polls es múltiplo de 20, lo inserta en un
anillo de 10 y actualiza `max_ps_cnt` con comparación signed.

`f331_rate_from_muc` reproduce la división y rechaza un divisor cero.
`f331_rate_observe` reproduce cadencia, ring e instantáneo/max. Si corresponde
muestrear y falta una muestra válida, devuelve `F331_UNKNOWN` sin alterar estado.
No lee MuC, no adquiere locks externos ni fabrica un valor cero. Su estado se
inicializa explícitamente por el caller; no se borra automáticamente al cambiar
una generación del clasificador, pues el fragmento `radar_start` no demuestra
ese borrado del ring de rate.

El gate suma las diez palabras con wrap unsigned de 32 bits y compara esa suma
unsigned con `maxRate`. La comparación del instantáneo con `maxInstRate` es
signed. Se conservan ambas semánticas. No se divide la suma por diez. El perfil
EU exacto derivado por F328 tiene `rateFilter=0`; F331 no sustituye ese perfil
por los defaults de otras ramas documentados en F316.

## API y composición

Fuentes: `work/kernel-port/modules/f331_postfilter/`.

```c
f331_begin(state, generation, channel, bandwidth, lsr_enabled);
f331_step(state, config, observation, decision);
```

El caller conserva y serializa el estado desde el worker dueño. `begin` es un
reset explícito de estado, no una consulta ni una operación a repetir en medio
de una generación activa. `observation.valid` debe declarar los seis grupos de
datos: counts, metadata de última detección, métricas LSR, rate, configuración y
candidato. Una entrada ausente, generación/canal/ancho divergente, cambio LSR
sin reinicializar o índice imposible se rechaza sin mutar el estado.

`callback_condition` describe la condición OEM exacta. **`callback_authority`
permanece siempre falso.** No hay puntero de callback en el core. La entrega
única, el contexto físico vigente y la autorización pertenecen a la integración
F327/F328/F330; el bypass diagnóstico `noreject` tampoco concede autoridad.

Mapas útiles para obtener los valores originales (config empieza en
`.bss+0x12a4`; estadísticas en `.bss+0x13d0`):

| Grupo | Offsets relativos |
|---|---|
| Config counts | `maxPulseCnt=156`, `maxPulseCntLSR=160`, `maxPulseCntFH=164`, `minDetectTh=168`, `ssrMaxPulseCnt=92` |
| Config PRI/PW | forbidden max/min `96/100`, tolerancias PRI/PW `104/108`, FH PRI min/max `124/128`, FH PW min/max `140/144`, Korea min/max `292/296` |
| Config LSR/rate | LSR PW/count diff `176/180`, LSR enabled/detected `214/215`, rate enabled/max/instant `219/220/224` |
| Estadística LSR | pulse count `84`, max/min PW `92/96`, min/max pulse count `100/104` |
| Estadística rate | diez muestras `632..668`, último `672`, máximo `676` |
| Última detección | count `680`, PRI vector `684/688/692`, PW `696` |

No debe marcarse válido el ring de rate solo porque el buffer de F328 se haya
inicializado a cero: debe existir su productor o una muestra real válida.

## Límites que siguen fuera del componente

El input `candidate` corresponde al punto OEM `0x43c0`. Antes, el worker aplica
los gates de carga `0x41f0..0x42bc`, llama dos veces a preprocess con count=0
después de una detección (`0x42c0..0x42e8`) y puede aplicar un veto específico JP
(`0x42ea..0x43bc`, EU salta ese veto). F331 no afirma que ese tramo previo esté
integrado. F330/root reciben la necesidad de las dos llamadas vacías y los
nombres de counts corregidos. Los contadores/metadata entregados deben provenir
del detector OEM de la generación correspondiente.

El oracle usa debug verbose=0 de forma explícita; los logs de depuración no se
comparan. Los 5.360 casos no constituyen prueba exhaustiva de todos los estados
posibles ni de radar físico. Los helpers de muestreo rate se validan por fuente
y tests nativos; el oracle extraído cubre el gate consumidor, no la concurrencia
del muestreo MuC. No se ha creado firmware, ejercido BB/QT4, probado CAC/CSA/NOP
ni entregado callbacks a qdrv. El ELF QEMU presenta el segmento RWX esperado del
arnés bare-metal; no se instala en el router.

## Reproducción

```powershell
python tools/build_f331_postfilter_oracle.py
python tools/build_f331_postfilter_kernel.py --oracle-dir '<nuevo oracle PASS>'
```

Cada ejecución preserva sus entradas y resultados en una carpeta UTC nueva.
`PROVENANCE.tsv` enlaza las fórmulas con las instrucciones y las validaciones.
