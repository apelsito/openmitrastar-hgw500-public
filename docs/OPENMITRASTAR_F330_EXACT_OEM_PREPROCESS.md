# F330: preprocesado OEM exacto con reset de hardware diferido

Fecha: 21 de septiembre de 2026. Alcance exclusivo HGW-500BNA-QCv2 A2. Se ha trabajado con ficheros locales, compilación ARC y QEMU; no se ha conectado al equipo, cargado un módulo ni escrito firmware. F328 no se ha modificado.

## Resultado implementado

F330 reutiliza el código original de `radar_preprocess` en `.text+0x26e8..0x2c14`: **1.324 bytes**, SHA-256 original `bec41b847947ebdd2b13367a60429edc535c8df0d71d74364275afc698338ca4`, extraídos del `radar.ko` OEM SHA-256 `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332`.

Se conservan sus operaciones, branches, filtros, copias, estadísticas y retorno. Las 68 relocaciones originales se reconstruyen. **Sólo dos operandos de dirección MMIO** se convierten en relocaciones a dos celdas RAM de registro: los writes originales a `0xe6091518`, en las instrucciones `0x2b4a` y `0x2b64`. Los helpers BB se enlazan a registradores de una solicitud, nunca al hardware. Que esas celdas reciban cero prueba el recorrido del binario en la emulación, no una escritura física.

El motor detecta esa solicitud, conserva un snapshot previo y otro posterior y devuelve `F330_RESET_REQUIRED`, con `committed=0`. Mantiene bloqueados los siguientes batches. Sólo una confirmación del backend real puede publicar el nuevo estado y devolver el batch pendiente ya comprometido; una confirmación fallida mantiene el motor bloqueado. No se simula un reset físico exitoso ni se pierde silenciosamente el batch que lo solicitó.

## Artefactos verificados

Oracle canónico:

`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f330-preprocess-20260921T103429Z/result.json`

- Resultado: `PASS_ORIGINAL_PREPROCESS_QEMU_NO_HARDWARE`.
- **24 casos, cero fallos**, QEMU termina por `flag 1` con exit code 0, sin stderr ni `guest_errors`.
- Cada caso contiene el input raw, su hash comprobado frente a lo recibido en QEMU, pulsos de salida, índices fuente para ZC, historial, estadísticas, estado del reset y canaries.
- Biblioteca `libf330-preprocess.a`: **20.784 bytes**, SHA-256 `d9c1f1a4584a44728d255acd497273fce404f5c34d2068b043d847d9721c6bb6`.
- Dos objetos de la implementación portadora son reproducibles; el enlace ARC tiene cero símbolos sin resolver.

Motor Linux 5.10:

`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f330-kernel-preprocess-20260921T103900Z/result.json`

- `a/f330_preprocess_engine.ko`: **23.668 bytes**.
- SHA-256 `b566b28a7e6da502497afc40a1d4c5e8ca005135dd3c0aa82650f9b728e19a58`.
- Dos builds idénticos, kernel `5.10.260-openmitrastar-radiohw`, licencia `Proprietary` como el OEM.
- Imports: únicamente `mutex_lock` y `mutex_unlock`.
- El wrapper serializa las operaciones y rechaza contexto IRQ/atomic. Su carga no inicia el motor ni accede al hardware.
- Compilación aceptada; **módulo no cargado y firmware no creado**.

La primera ejecución `f330-preprocess-20260921T103108Z` agotó el timeout de 12 segundos mientras imprimía la salida completa del caso de 256 pulsos. Se preserva como fallo de aceptación; no se ha reetiquetado. El runner posterior tiene 45 segundos y continúa exigiendo salida voluntaria 0: un timeout sigue siendo fallo. Los avisos RWX del linker pertenecen exclusivamente al ELF bare-metal QEMU y se conservan.

## Semántica demostrada del historial y los argumentos

La firma inferida y ejecutada es:

```c
raw_pulse_t *radar_preprocess(unsigned *total_count,
                            raw_pulse_t *new_raw, unsigned new_count,
                            unsigned *current_window_count);
```

El cuarto argumento no es el número de muestras raw de entrada ni el tamaño anterior del historial. El OEM conserva dos ventanas:

1. Copia la ventana previa desde el puntero `.data+0x2c`, usando el número `.bss+0x1020`.
2. Procesa las muestras nuevas después de esa copia, con el puntero de merge reiniciado a NULL: **no hace merge entre el último pulso previo y el primero nuevo**.
3. `total_count` recibe el total de la ventana previa más la nueva procesada.
4. `current_window_count = total_count - previous_window_count`.
5. Conserva para la llamada siguiente sólo esa ventana nueva, mediante `history_pointer = buffer + previous_window_count * 16` y `history_count = current_window_count`.

En QEMU, batches de 3, 2 y 1 pulsos produjeron `(total,current) = (3,3), (5,2), (3,1)`. Dos llamadas vacías posteriores produjeron `(1,0)` y `(0,0)`. Esto descarta un historial acumulativo indefinido. El worker entrega el cuarto argumento a `detect_radar` y lo usa en el historial del postfiltro; la denominación antigua `count_last_window` no justifica pasar el count raw o la ventana previa.

Los tests también confirman:

- Merge intraventana conserva el start del primer pulso, el stop del último y la potencia máxima; marca el índice ZC con `-1`.
- Las cotas de ancho y potencia se aplican sobre los valores y en el orden originales.
- El pulso terminal marcado se descarta incluso cuando el flag de configuración `tag` está a cero. No se ha cambiado ese comportamiento.
- El reemplazo de un pulso marcado conserva exactamente el mapa ZC del OEM. En el vector de reemplazo se devuelve el pulso raw 1 y el índice fuente de la primera salida continúa siendo 0; no se interpreta ni se corrige sin estudiar el consumidor.
- Se aceptan 128 muestras nuevas y 128 de historia: hasta **256 pulsos procesados de salida**.
- Los timestamps almacenados son de **32 bits** tras sumar el epoch; la máscara de 27 bits se usa en las diferencias. El vector con base `0x20000000` devuelve start `0x2000000a`, válido para el OEM. Rechazar toda salida superior a `0x07ffffff` rompe esta semántica.

F330 expone `zc_source_index[128]`; sólo las primeras `current_window_count` entradas pertenecen a la ventana nueva. No genera ZC inexistentes: esos índices deben aplicarse a las filas reales de la adquisición, conservando los valores `-1` y los estados de validez.

## Condición exacta del reset

El contador `.bss+0x1290` cuenta invocaciones de preprocesado. El binario solicita reset cuando:

```text
counter > 100 AND (total_count == 0 OR counter > 160)
```

En la rama normal incrementa el contador. En la rama de reset:

- incrementa `.bss+0x1298`;
- pone `.bss+0x1290` a cero;
- solicita BB owner 1;
- escribe cero dos veces en `0xe6091518`;
- libera BB owner 1;
- actualiza `.bss+0x1294` con `seconds * 10_000_000 + microseconds * 10`, con wrap de 32 bits.

QEMU verifica los límites 100/101 y 160/161, ambas escrituras registradas, enter/leave, ausencia de commit antes del ack, bloqueo de nuevos batches y backend rechazado. Tras el ack de prueba a 40 s + 5 us, la siguiente salida usa base `400000050`.

Una solicitud F330 **no es una autorización ni prueba de hardware**. El futuro backend debe ejecutar y verificar la operación real bajo ownership vigente, y entregar su tiempo de finalización. `f330_confirm_reset` recibe ese dato y publica el estado preparado; no hace la escritura. Un caller no debe convertir `F330_RESET_REQUIRED` en éxito porque su código sea positivo.

## Contrato para F327/F331/F332

Fuente y API: `work/kernel-port/modules/f330_oem_preprocess/`.

```c
f330_begin(generation, initial_timestamp_base, tag_enabled);
f330_prepare(generation, raw, count, clock_sec, clock_usec, result);
f330_confirm_reset(generation, request_id, backend_confirmed,
                   actual_sec, actual_usec, committed_result);
```

- Usar un único worker, fuera de BB y de contexto IRQ/atomic.
- Sólo consumir para detección/postfiltro un resultado con `F330_OK` y `committed=1`, incluido el batch pendiente devuelto tras un ack válido.
- Conservar por separado `total_count`, `current_window_count`, raw de salida y validez ZC. No inferir unos de otros.
- Cuando el detector emite candidato, el OEM llama a preprocess con count cero **dos veces** en `0x42c0..0x42e8`, antes del postfiltro. Hay que conservar el total/current del batch original para F331 y vaciar ambas ventanas; esos flushes también pueden solicitar reset.
- F315/F327 actualmente comparten el límite 18 para raw y ZC. El OEM distingue **128 raw** de **18 filas ZC por poll**. Antes de unirlos se deben separar las capacidades y permitir salida procesada 256; no truncar al límite diagnóstico 18 ni al límite inicial F328 100.
- El decoder de potencia desde los bancos QT4 y la adquisición/validez de cada fila ZC siguen siendo responsabilidades del backend de captura, no de esta biblioteca.

## Cadencia OEM comprobada

`radar_start` fija `.bss+0x1054` (`radar_cb_t.poll_freq`) a 50 en `0x7306/0x7308`. El tail del worker calcula `50 * 200 / 1000 = 10` jiffies OEM: **50 ms nominales**. F315/F327 tienen `poll_interval_ms=50`; a HZ 100 son cinco jiffies y el intervalo nominal coincide. No se ha medido aquí la latencia real bajo carga.

La llamada adicional `detect_radar_poll` usa `poll_counter % poll_freq == 0`, en `0x421c..0x4246`: una vez cada 50 polls activos, aproximadamente 2,5 segundos nominales. No equivale a llamarla en cada batch. Asimismo, los contadores 100/160 de F330 no son timers de 5/8 segundos: las llamadas vacías adicionales cambian su relación con el número de polls.

## Reproducción local

```powershell
python tools/build_f330_oem_preprocess.py
python tools/build_f330_kernel_preprocess.py --oracle-dir '<nuevo directorio privado con oracle PASS>'
```

Los resultados y binarios derivados permanecen privados y se crean en directorios nuevos. La integración física con F327, el postfiltro F331, el callback qdrv y CAC/evacuación/NOP no se declara completada por estas pruebas.
