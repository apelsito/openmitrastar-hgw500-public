# F333: adquisición raw y ZC contrastada con los loops OEM

21 de septiembre de 2026. Target exclusivo HGW-500BNA-QCv2 A2. Ningún UART, SSH, radio, MMIO físico o firmware fue utilizado/modificado en este trabajo. F328, F330 y el executor F326 permanecen intactos.

## Resultado

El nuevo C portable de `work/kernel-port/modules/f333_acquisition/` reproduce los loops OEM:

- Raw: `.text+0x3e08..0x3f28`, 288 bytes.
- ZC: `.text+0x3f66..0x40fe`, 408 bytes.

El oracle conserva sus instrucciones y branches, aplicando las relocaciones originales y sustituyendo exclusivamente operandos de direcciones físicas por RAM de fixtures. Las matrices y los bancos están llenos de datos deterministas. La biblioteca de producción **no contiene bytes OEM**: es fuente nueva `GPL-2.0-only`; los slices binarios permanecen únicamente en el oracle privado.

Resultado canónico:

`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f333-acquisition-20260921T110904Z/result.json`

- `PASS_PORTABLE_DECODER_VS_ORIGINAL_QEMU_LOOPS`.
- **2.368 casos raw**, incluyendo las 1.024 combinaciones de metadata high/low con tag activado/desactivado, wrap y máscaras OCAC.
- **320 casos ZC**, incluidos los bordes de RAM válida, la zona inválida, wrap, masks, count 0/18/19/128/255 y preservación de filas no escritas.
- **52.870 comprobaciones** y **1.756.160 muestras ZC comparadas**, cero fallos.
- QEMU termina voluntariamente con exit code 0; stderr y `guest_errors` vacíos.
- Lecturas fallidas, capacidad insuficiente, punteros fuera del dominio y estado ZC no disponible se rechazan sin afirmar captura completa.
- Biblioteca ARC reproducible: `libf333-acquisition.a`, **2.352 bytes**, SHA-256 `f9b3818d0e6eb0f9d59ccb3ac9cb86af5fe8aa43426620c38a0cd5f7f47e8b0b`.

Copyset aceptado para F332:

| Fuente | SHA-256 |
|---|---|
| `f333_acquisition.c` | `db2c2f6b70a48970ed3b62aecc8920498f0393dbd8a2464164f2a2dc9f0d88cb` |
| `f333_acquisition.h` | `f31c39d056421e1429ebcda5446841d31f6895a4b4fada456709dfcd36d4a8dd` |

El campo de snapshot se llama `current_ptr`, evitando la macro `current` del kernel Linux.

## Decodificación cerrada

El banco HIGH está en **`0xe6401400`** y el LOW en **`0xe6401000`**. Cada banco tiene 256 palabras de 32 bits. El loop lee primero HIGH y después LOW.

```c
start     = high & 0x07ffffff;
stop      = low  & 0x07ffffff;
max_power = ((high & 0xf8000000) >> 22) | (low >> 27);
tagged    = tag_enabled && ((low >> 27) & 1);
```

`max_power` es la concatenación de dos campos de cinco bits: **`(high_meta << 5) | low_meta`**, rango 0–1023. No es `max(high_meta, low_meta)`. El bit de tag participa en el campo LOW; no se elimina del valor de potencia. El flag `tag_enabled` controla si el tag se publica, no la reconstrucción de potencia. El oracle exhaustivo de esos campos confirma estas relaciones.

La salida tiene exactamente tres `u32` y un byte tagged en offset 12; el tamaño ABI es 16 bytes. F333 inicializa a cero los tres bytes de padding, que no forman parte de las cuatro magnitudes del detector.

## Punteros y cantidad raw

El OEM lee `NEW_CURRENT` (`0xe6091570`) y `NEW_START` (`0xe609156c`), sin el cursor acumulado del shadow F315:

```text
available = current_ptr - start
si current_ptr < start: available += 256
```

F333 exige los punteros dentro de 0–255; no trunca bits desconocidos. El loop OEM puede leer hasta 255 registros en ese dominio. Para EU con tag desactivado, el preprocesado utiliza **los primeros 128**, no los últimos 18. El metadata portable devuelve tanto `captured_count` como `preprocess_count`. Con tag activado, la captura no impone la reducción a 128: un consumidor con ese límite debe rechazar/gestionar explícitamente el caso, no truncarlo sin más.

Cuando se usa la máscara OCAC, se consulta por índice lógico desde cero. El loop OEM incrementa el puntero de los bancos **sólo al seleccionar un registro**; el índice de la máscara avanza siempre. F333 conserva ese comportamiento, verificado contra los bytes originales, y no lo sustituye por saltar una posición física por cada cero de la máscara.

No se afirma que dos punteros iguales basten para diagnosticar todos los posibles overruns físicos. La información adicional de overflow y la coherencia de la captura deben establecerse en el backend real.

## ZC: 18 filas nuevas, matriz de 49×112

El loop ZC obtiene un segundo snapshot de `NEW_CURRENT/NEW_START`, con una sección BB independiente, y considera como máximo **18** filas. La matriz software es `s32 samples[49][112]` más el flag original `is_zc_accurate`.

El cursor inicial procede de **`.bss+0x1018`**, normalmente cero tras `radar_clear_pt`. No se deriva como `CUR_CHMEM - count * 112`. En el binario exacto, la rama que calcularía un cursor desde `CUR_CHMEM + 64` queda inalcanzable después del cap a 18; se conserva en el oracle y no se activa inventando un caso.

Para el perfil EU, cada fila ocupa 28 palabras hardware:

- Cada palabra válida se expande a cuatro enteros, byte menor primero, valores 0–255.
- Las direcciones de `0xe6400000` a `0xe6400dff` son válidas para este loop.
- En `0xe6400e00..0xe6400fff`, cada palabra produce **cuatro `-1`**, exactamente como el OEM. El loop continúa: no abandona la fila ni rellena ceros.
- El cursor avanza cuatro bytes y vuelve al comienzo al superar `0xe6400fff`.
- Cada fila contiene siempre 112 muestras emitidas cuando todas las lecturas solicitadas completan, incluyendo los marcadores `-1` de la región inválida.
- Las filas no escritas permanecen intactas; no se vuelve a inicializar toda la matriz cada poll.

La máscara OCAC compacta filas de forma análoga al loop raw: no avanza el cursor físico ZC cuando se descarta una entrada lógica. `captured_rows` permite conocer cuántas filas de la matriz se actualizaron; no debe confundirse con el número raw ni con el número total de pulsos preprocesados.

`software_zc_accurate` y `complete` son distintos. El primero es estado de procedencia OEM; el segundo sólo indica que se completaron las lecturas solicitadas por el helper. Una lectura que falle devuelve `F333_READ_FAILED`, `complete=0`; una fuente no disponible devuelve `F333_ZC_NOT_ACCURATE`, sin promoverla a accurate. El caller debe invalidar el batch completo o usar staging ante un fallo: no publicar la parte de matriz ya escrita como captura completa.

## Consumo tras el snapshot

El worker sigue este orden: snapshot raw bajo BB → liberar BB → snapshot ZC bajo BB → liberar BB → `radar_clear_pt` bajo BB → liberar BB → preprocesado. No existe en ese camino una igualdad obligatoria de los dos snapshots; preservar el orden no demuestra por sí mismo su coherencia física.

`f333_get_consume_plan()` entrega una descripción inmutable de diez acciones, que **no ejecuta**. El backend debe mantener BB owner 1 para toda la secuencia:

1. `0xe6000320 = 2` (clear interrupt).
2. `0xe6091530 = 0` (CUR_CHMEM).
3. `0xe6091520 = 0` (PTR_H).
4. `0xe609151c = 0` (PTR_L).
5. `0xe609156c = 0` (NEW_START).
6. Software: contador de cola OCAC `.bss+0x9158 = 0`.
7. Software: `is_zc_accurate`, `.bss+0x9100 = 1`.
8. `0xe6091570 = 0` (NEW_CURRENT).
9. Software: cursor ZC `.bss+0x1018 = 0`.
10. Software: limpiar los 256 bytes de máscara OCAC en `.bss+0x915c`.

Esto procede de la función OEM `radar_clear_pt`, `.text+0x3920..0x39c4`. **No escribe `CNT_L` ni borra SRAM.** No debe sustituirse por `f315_clear_capture`, que añade ambas cosas. Las dos escrituras periódicas de `CNT_L` pertenecen al reset de preprocesado F330 y siguen una transacción distinta.

`radar_start` inicializa `is_zc_accurate` a cero; los escritores identificados `radar_clear_pt` y `update_zc_pointer` lo ponen a uno y reinician el cursor. `radar_enable` hace clear antes del primer worker. El flag a uno después del consume no prueba que todas las filas del batch anterior contengan datos recién adquiridos; se conserva por separado la procedencia de esa captura.

## API para F332

```c
f333_decode_pair(high, low, tag_enabled, raw);
f333_capture_raw(snapshot, read_word, context, raw_output, capacity, metadata);
f333_capture_zc(snapshot, read_word, context, matrix49x112, capacity, metadata);
f333_get_consume_plan(&actions);
```

El callback `read_word` recibe un espacio HIGH, LOW o ZC y un índice de palabra, y debe indicar éxito/fallo. Puede trabajar contra fixtures, un snapshot inmutable o las ventanas acotadas del backend. F333 no adquiere BB, no accede directamente al MMIO ni supone que el hardware haya permanecido quieto. El backend debe conservar el orden de lectura de los bancos y demostrar la propiedad/coherencia necesaria.

Tras adquisición, F330 suministra `zc_source_index` para la ventana nueva. Hay que combinarlo con las filas realmente adquiridas, respetando `-1`, máscaras y disponibilidad. No se añaden filas cero para justificar `accurate=1`.

## Diferencias identificadas respecto a F315/F327 shadow

| Shadow anterior | OEM/F333 demostrado |
|---|---|
| `power_code=max(meta_high,meta_low)` | Concatenación de 10 bits |
| Tag siempre desde bit 27 LOW | Tag condicionado por configuración |
| Raw y ZC comparten límite 18 | Raw hasta 255 capturados; EU procesa primeros 128; ZC considera 18 |
| Conserva cursor local y recorta a muestras recientes | Lee desde NEW_START; consume los punteros después |
| ZC se reconstruye hacia atrás desde CUR_CHMEM | Cursor software inicial, avance secuencial |
| Termina la fila al entrar en región inválida | Escribe `-1` y continúa hasta 112 muestras/wrap |
| `accurate` por mínimo sintético de muestras | Estado/procedencia original separado de completitud |

## Incidencias del oracle, preservadas

Las primeras ejecuciones no fueron PASS. Se identificaron dos defectos del harness: aliases negativos de bases que GNU ld dejó section-relative, y pérdida de la fase original `PC % 4 == 2` al reubicar el slice ZC. ARC calcula algunos branches desde el PC alineado: perder esa fase desplazaba los destinos dos bytes. El harness ahora usa `ABSOLUTE` para los aliases y conserva la fase de cada slice; ambos contratos se verifican antes de arrancar QEMU. **Las fórmulas del C portable no se cambiaron para acomodar esos fallos.**

Los dumps diagnósticos y timeouts anteriores siguen en sus directorios originales. El oracle canónico no admite timeout, crash, logs de error o comparaciones fallidas como éxito.

## Pendientes físicos reales

- Verificar los campos/rangos de punteros y comportamiento de overrun en la placa real.
- Demostrar coherencia de bancos y correspondencia de snapshots raw/ZC bajo la propiedad BB real.
- Ejecutar y verificar el consume de punteros sin confundirlo con reset CNT/SRAM.
- Integrar con F330/F331/F328 revisado, preservando capacidades y validez; después validar detector, CAC, evacuación y NOP físicamente.

Reproducción local: `python tools/build_f333_acquisition.py`. Las opciones `--suite raw` y `--suite zc` sirven para diagnósticos parciales y quedan identificadas en sus resultados. La aceptación citada aquí corresponde a `suite=full`.
