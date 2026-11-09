# F342: journal de configuración A/B portable

21 de septiembre de 2026. **Implementación y validación offline PASS.** No hay
backend SPI, MMIO, interfaz MTD ni escrituras persistentes habilitadas. No se ha
accedido al router, UART, AELITA ni Wi-Fi/RF.

[Resultado y manifiesto](../outputs/kernel-port/f342-config-journal-20260921T141638Z/result.json).
[Revisión independiente vinculada al manifiesto](../outputs/preflight/f342-readonly-review-20260921T141855Z/result.json):
sin hallazgos abiertos en el core portable; no sustituye la validación física ausente.
El archivo `a/libf342journal.a` tiene **7.082 bytes**, SHA-256
`acc87d8e012e3309654704608cca1a871800543f1a39cfcc62fd7d28002af8e0`.
Dos compilaciones ARC700 independientes producen el mismo objeto y archivo.

## Implementación

- [API](../work/kernel-port/modules/f342_config_journal/f342_journal.h) y
  [core](../work/kernel-port/modules/f342_config_journal/f342_journal.c).
- [Pruebas](../work/kernel-port/modules/f342_config_journal/test_f342_journal.c) y
  [builder](../tools/build_f342_config_journal.py).
- Se reutiliza `struct f318_store_ops` y sus dos bloques reservados. Los archivos
  de F318 no se modifican; sus hashes quedan fijados en el manifiesto.

Los únicos destinos de erase/program son los bloques de 64 KiB en **0x00dc0000**
y **0x00dd0000**. La API no acepta una dirección física. El payload es un blob
opaco de **1..4.096 bytes** que el caller mantiene inmutable. No hay puntero activo
adicional ni escritura en bootenv. Los otros 26 bloques de `lyoko_store` están
fuera de las direcciones de escritura generadas por el core.

El caller aporta un workspace de **552 bytes**; no se coloca el payload de 4 KiB
en la pila. El mayor frame individual del core compilado para ARC es 104 bytes;
esto no cuenta la pila de sus callbacks externos. El archivo sólo necesita
`memcpy`, `memcmp` y `memset` además de las operaciones suministradas.

## Formato en flash

Todos los enteros son little-endian y se codifican byte a byte, sin cargas
desalineadas de 64 bits.

| Offset | Bytes | Campo |
|---:|---:|---|
| 0 | 4 | Commit: `ffffffff` pendiente; `00000000` comprometido |
| 4 | 4 | Magic `F342` |
| 8 | 1 | Versión 1 |
| 9 | 1 | Slot 0 o 1; debe coincidir con su bloque |
| 10 | 2 | Tamaño de cabecera, 32 |
| 12 | 4 | Longitud, 1..4096 |
| 16 | 8 | Secuencia, 1..UINT64_MAX |
| 24 | 4 | CRC32 del payload |
| 28 | 4 | CRC32 de los bytes 4..27 de cabecera |
| 32 | longitud | Payload |

La marca de commit queda fuera del CRC de cabecera para poder programarla al
final con una transición NOR `1→0`. La secuencia no envuelve: guardar desde
`UINT64_MAX` devuelve `F342_ESEQUENCE` antes de desproteger o borrar.

La selección usa la mayor secuencia entre registros válidos. Dos válidos con
secuencia igual son ambiguos y producen error, incluso si sus payloads coinciden.
Una secuencia cero es un registro inválido; no impide recuperar el otro válido.
Cabecera, slot, longitudes, commit y CRC de payload se validan antes de aceptarlo.

## API y política de recuperación

```c
f342_inspect(ops, workspace, result);
f342_load(ops, workspace, staging_payload, capacity, result);
f342_save(ops, workspace, immutable_payload, length, result);
```

`load` e `inspect` sólo requieren `claim`, `read` y `release`. Funcionan con el
resto de callbacks a NULL y no consultan ni cambian protección. `load` devuelve
datos únicamente como válidos cuando su retorno es `F342_OK`; el buffer de salida
es staging y puede quedar parcialmente rellenado si falla una segunda lectura.
No se debe activar configuración desde ese buffer en caso de error.

Para guardar, si hay un válido se conserva su bloque y se usa el otro bloque
reservado como destino, aunque contenga un intento cortado/inválido. La existencia
del válido establece el journal A/B sobre esos dos bloques. Si no hay ninguno
válido, sólo se inicializa un bloque comprobado **completamente FF**, no simplemente
con cabecera FF. Si ambos están ocupados sin ningún válido, devuelve
`F342_ECORRUPT` sin desprotección ni borrado. No hay formateo o migración destructiva
implícitos de registros desconocidos/F318 antiguos.

Un slot inválido no desplaza al último commit válido. Un corte durante erase,
cabecera, payload o commit parcial deja seleccionado el commit anterior; cuando
la marca final completa y los CRC son válidos, el nuevo registro puede recuperarse.
No se promete reconstruir datos si ambos registros están corruptos.

## Transacción de guardado

1. Adquirir el claim único y escanear ambos slots.
2. Capturar el byte opaco de protección del destino y los ocho testigos de F318.
3. Desproteger únicamente el destino, sincronizar y comprobar su estado. Verificar
   también los otros testigos **antes de cualquier erase**.
4. Borrar el bloque destino, sincronizar y leer sus 64 KiB para comprobar FF.
5. Programar cabecera y payload en fragmentos que nunca cruzan páginas de 256 bytes;
   cada fragmento lleva sync y readback exacto.
6. Verificar otra vez la cabecera pendiente y el CRC completo del payload.
7. Programar los cuatro bytes de commit al final, sincronizar y verificar el registro.
8. Restaurar el byte original exacto de protección, sincronizar y leerlo. Comprobar
   todos los testigos ajenos al destino, incluso si alguna comprobación falla.
9. Comprobar de nuevo la visibilidad del candidato y liberar el claim.

Cada operación de escritura intenta sync también cuando el callback informa error,
porque el dispositivo podría haber recibido parte o toda la operación. Después de
entrar en la fase que puede cambiar protección, se intenta restaurarla en todos
los caminos de error. No se llama a una operación global de lock/unlock.

`primary_status` y `failure_phase` conservan el primer error de la operación;
`restore_status` y `witness_status` registran los fallos de cierre por separado.
El retorno prioriza un fallo de testigos, después uno de restauración y después
el error primario. La limpieza fallida nunca se convierte en éxito.

`commit_visible` sólo vale uno tras verificar el candidato completo. Puede ser uno
aunque `save` haya fallado después al restaurar protección: el caller debe distinguir
persistencia observada de cierre seguro y no repetir ciegamente el guardado.
`programmed_bytes` cuenta bytes cuyo readback fue confirmado, no bytes supuestos
tras una operación incierta. Los slots reflejan las últimas observaciones disponibles.

## Contrato pendiente del backend

El proveedor debe serializar **todos** los lectores de flash y usuarios del modo
de comandos bajo `claim`, entregar lecturas actuales sin caché, respetar la página
NOR y tener callbacks acotados. `sync` debe establecer finalización real; un retorno
del callback por sí solo no demuestra durabilidad ni propiedad eléctrica del bus.
`release`, de tipo void en F318, debe completar la liberación.

Los testigos son los ocho offsets de protección heredados de F318; no se presenta
ese muestreo como una lectura exhaustiva de todos los DPB ni de todo el contenido
del chip. El core restringe las direcciones que solicita y detecta cambios en sus
testigos; no puede corregir un proveedor que escriba fuera del destino solicitado.

Ese proveedor **no está implementado aquí**. No hay ruta HTTP, scripts de modos,
comandos SPI ni carga del módulo rechazado de acceso directo. F344 puede mantener
su estado temporal separado en RAM; una integración posterior llamará a esta API
con un payload ya validado. No se registran payloads, PSK o credenciales.
El core no selecciona modelo de flash ni interpreta bits DPB: el valor no protegido
y el byte original proceden del proveedor cualificado, sin asumirlos por un ID.

## Evidencia

- **65.458 comprobaciones PASS**: tamaños, páginas, CRC, secuencias, readonly,
  bloques desconocidos, readbacks, restauración y testigos.
- **790 fallos inyectados**: un error en cada operación de una transacción completa,
  tanto antes como después del efecto cuando corresponde. La restauración de un
  fallo retornado se comprueba por separado.
- **4.186 casos de corte**: 4.154 abandonos mediante `longjmp` dentro del callback,
  antes de que pueda correr cleanup, más 32 instantáneas con un bit de commit
  pendiente. Cubren todos los prefijos de bytes de cada escritura de página
  y de commit, además de prefijos de erase.
  Los cortes incompletos exigen recuperar el anterior; sólo el commit completo
  exige el nuevo. El proveedor falso rechaza intentar commit antes de tener
  cabecera y payload completos con CRC válido. Nunca se acepta una mezcla.
- **GCC `-fanalyzer` PASS**, compilación C11 estricta y objeto/archivo ARC reproducibles.
- ASan/UBSan opcionales: **no ejecutados**, porque faltan sus librerías en el
  toolchain local. El manifiesto lo registra como `NOT_RUN_TOOLCHAIN_RUNTIME_UNAVAILABLE`.

El primer build `f342-config-journal-20260921T140955Z` conserva su FAIL de enlace
del sanitizer; sus pruebas y analyzer ya habían pasado. El primer resultado
completo `141142Z` mantiene su PASS. Después se reforzaron las expectativas de
cortes incompletos y las marcas parcialmente programadas: la cualificación
canónica `141638Z` repite tests/analyzer/doble build y conserva el mismo binario.
Ambas declaran el sanitizer ausente; no se reetiquetó evidencia anterior.
