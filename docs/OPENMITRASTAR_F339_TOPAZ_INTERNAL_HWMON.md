# F339: sensor interno Topaz en hwmon Linux 5.10

21 de septiembre de 2026. **Driver y contrato offline PASS; sensor físico,
reloj, fin de conversión y exactitud térmica todavía sin validar.** No se ha
accedido al HGW ni a AELITA, probado Wi-Fi/RF ni creado un firmware flasheable.

Se reutiliza la implementación OEM del sensor interno, ya parcialmente portada
en `work/linux510-radio-port/quantenna-v6-scheduler-diag/platform/topaz/temp_sens.c`.
F321 incluye `temp_sens.ko` y su startup llama a `load_module temp_sens.ko`.
Ese port conserva la tabla y las escrituras de inicialización, pero suprime el
proc diagnóstico y carece de hwmon/readiness/errores de rango. F339 es su
**reemplazo**, no un segundo driver que comparta el hardware con él.

El SE95 externo y `temp_sensor.ko` son otra función, por I2C. Este trabajo no
establece su presencia en la placa ni modifica ese driver.

## Artefactos

- [Resultado del driver](../outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z/result.json):
  `PASS_OFFLINE_HWMON_OEM_ORACLE`.
- [Contrato DT/configuración/símbolos](../outputs/kernel-port/f339-contract-20260921T134736Z/result.json):
  **13/13 PASS**.
- [Source versionado](../work/kernel-port/versions/f339-topaz-hwmon/temp_sens.c),
  [core de conversión/protocolo](../work/kernel-port/versions/f339-topaz-hwmon/topaz_temp_core.h),
  [fragmento DT](../work/kernel-port/versions/f339-topaz-hwmon/topaz-internal-temperature.dtsi),
  [adaptación del consumidor qdrv](../work/kernel-port/versions/f339-topaz-hwmon/qdrv-consumer-error.patch).

| Artefacto | Bytes | SHA-256 |
|---|---:|---|
| `temp_sens.ko` | 8.116 | `b8e4532d6019a54186290f501e8a40e57192d85e9ea3f43296dc3ba1cca3e17e` |
| `hwmon.ko` | 15.696 | `9ace8d9c0e7a2451d39465af994fc0f38e6821ed2b03ec4e4ba9d7e2e2ede627` |
| Kernel de compilación `f339.vmlinux` | 5.169.976 | `ff0ea79a5e801821a4f1b3c47edd102b1312545d031d4a7bfb3cf9de4d7ecace` |
| DT por defecto | 5.588 | `64f45e4ebddac2c31dc1e6656f6acd09d324bd14de41b9b87aa356b434d834ea` |
| DT ejemplo de separación del recurso | 5.588 | `f89d6267f1138258130d80ec9bcaee532cd690bd7894ae28e2adb669a3ea10aa` |

Dos compilaciones independientes del nuevo driver son idénticas. El kernel y
hwmon se reutilizan de un build completo previo de Linux: sus hashes se verifican
antes y después, pero **no se declara una segunda compilación independiente de
esos dos componentes**. La única diferencia funcional de configuración respecto
al F321 exacto es `CONFIG_HWMON=m`; se conserva la ABI ARC700 y el release
`5.10.260-openmitrastar-radiohw`.

Los imports de ambos módulos también cierran contra los exports del ELF F321
exacto más `hwmon.ko`. Es evidencia de enlace; no es aceptación runtime de cargar
el módulo bajo una configuración de kernel distinta a la usada para compilarlo.

## Fuente OEM y protocolo

Fuente primaria: `work/sources/Quantenna-GPL/drivers/topaz/temp_sens.c`, SHA-256
`ef542efef64406330610e6b504082dea4e2692e4f87041fe3d35cac3879bee41`.
Las direcciones y máscaras proceden de `common/topaz_platform.h` y
`common/ruby_platform.h`. La implementación y su tabla mantienen la licencia
GPL-2.0-or-later de Quantenna.

| Registro, mapa legado | Uso demostrado |
|---|---|
| `0xe0000108`, control | Escrituras OEM exactas `2`, `0xfffffffe`, `1`, en ese orden |
| `0xe000010c`, test control | Documentado en header; F339 no lo lee ni escribe |
| `0xe0000110`, datos | Código de temperatura en `0x00000fff`; END_CONV en `0x00001000` |

Se usa directamente la máscara END_CONV, bit 12. El macro OEM
`TOPAZ_SYS_CTL_TEMP_SENS_DATA_END_CONV_S` vale 11 y contradice esa máscara;
F339 no utiliza ese desplazamiento. La tabla original se compara literalmente
con la incorporada al core, y el oracle compila la función de conversión OEM.

La inicialización ocurre una vez al hacer probe del nodo habilitado y cualificado.
Las lecturas no reinician el convertidor. OEM tampoco establece una operación de
parada al descargar: F339 retira su propietario software sin inventar una secuencia
de apagado. No hay calibración por dispositivo, lectura de trim/fuses ni fórmula
de interpolación en esa fuente; no se han añadido valores supuestos.

OEM no espera END_CONV y no define timeout. F339 espera ese bit con un límite
software de **100 ms**, comprobando el tiempo monotónico y durmiendo entre polls.
Ese límite es una política del port, no una latencia medida ni una especificación
del sensor. Tampoco puede acotar un acceso MMIO que bloquee el propio bus.

No se ha encontrado un reloj específico del sensor en el protocolo OEM. El DT
no inventa un `clock-frequency=125MHz` para el convertidor; la relación entre
reloj de bus y conversión queda pendiente de la validación física.

## Conversión y errores

La tabla contiene **34 umbrales**, de código 3800 a 3421. El comentario OEM dice
−40 a 130 °C, pero el código real sólo produce índices 0..33 y extremos superiores
−40..125 °C. El proc antiguo imprimía un intervalo de cinco grados terminado en
ese extremo superior.

F339 conserva índice y fórmula dentro del dominio de tabla. `temp1_input` expresa
en miligrados el extremo superior, con etiqueta
`Topaz internal 5C interval upper bound`; el atributo de sólo lectura `interval`
devuelve `inferior superior`, también en miligrados. No representa una medida
continua con resolución de una milésima ni añade umbrales térmicos de alarma.

- Sin END_CONV, se espera hasta el límite y se devuelve `-ETIMEDOUT`.
- Código fuera de 3421..3800: `-ERANGE`, sin publicar un número.
- Driver no activo: API legacy `-ENODEV`.
- Fallo de transporte simulado: conserva su errno; no sustituye la lectura por cero.
- Error: el resultado de salida no se modifica.

Esto evita dos errores del original: códigos inferiores a 3421 terminan en
índice 34 pero dejan −40 °C como salida; códigos superiores a 3800 se saturan en
el primer intervalo aunque estén fuera de la tabla. Esas salidas no se aceptan
como temperaturas válidas.

El símbolo `int topaz_read_internal_temp_sens(int *temp)` permanece exportado.
En éxito devuelve el índice OEM y grados Celsius enteros; en error devuelve errno
negativo y no toca `*temp`. La llamada es dormible, como el worker qdrv identificado.
La adaptación qdrv comprueba 0..33 antes de actualizar los datos compartidos con
MuC; en error conserva los últimos datos y registra sólo un código de error.
No cambia el layout compartido con firmware ni afirma frescura de un valor retenido.

## DT y propiedad del recurso

El DT por defecto conserva todos los valores de los **23 nodos F321** y añade
únicamente `/soc/temperature-sensor@e0000108`, `reg=<0xe0000108 0xc>`,
`status="disabled"`. Ese DT se extrajo también del ELF y se comprobó semánticamente:
la desactivación no es sólo un sidecar.

Hay un solape existente: recovery reserva `0xe0000000+0x200`. Sus accesos sysctl
demostrados son únicamente +0 y +4. El ejemplo de ownership reduce **sólo su
primer recurso a 8 bytes** y conserva los recursos GPIO/WDT. El nodo del sensor
sigue deshabilitado. Al integrar sobre F329/F336, hay que conservar la cola real
del `reg` de ese candidato; no copiar el array F321 completo encima de su separación
de watchdog.

Probe exige el modelo HGW correcto, resource exacto, exclusión del recurso y
las propiedades explícitas `quantenna,temperature-experiment` y
`quantenna,clock-map-ownership-qualified`. No están presentes en los DT entregados.
Marcan una cualificación externa de mapa/reloj/propietario; no la descubren ni
prueban por sí solas. Un mutex protege muestreo, API legacy y retirada del dispositivo.

## Integración siguiente

1. Reemplazar el antiguo `temp_sens.ko`; no cargar ambos. Conservar el SE95 externo
   como componente separado, sin afirmar presencia física.
2. Integrar el core hwmon y cargarlo antes del reemplazo de `temp_sens.ko`.
3. Aplicar la adaptación del consumidor qdrv sobre el candidato que realmente se
   componga. El patch pasa dry-run sobre la fuente F334 fijada en el manifiesto;
   no se ha editado ni reconstruido el árbol F338 con él.
4. Separar el recurso sysctl sin perder GPIO/WDT y mantener el nodo deshabilitado
   hasta cualificar el mapa, END_CONV y la exclusión del propietario legado.
5. Posteriormente, en una prueba física aparte, comprobar código/END_CONV, lectura
   hwmon plausible y comportamiento de timeout. No hay test Wi-Fi/RF asociado a
   esta entrega ni operación sobre AELITA.

## Verificación y reproducción

El oracle cubre **4.096 códigos con DONE y 4.096 sin DONE**, más límites de la tabla,
escrituras de inicio, fallos inyectados, espera hasta su límite y conservación de
la salida en error: **17.584 comprobaciones PASS**. El contrato adicional verifica
DT embebido, preservación de nodos, separación de recursos, configuración, símbolos
y arquitectura: **13/13 PASS**. Ninguno ejecuta MMIO real.

[Builder completo](../tools/build_f339_topaz_hwmon.py) y
[cualificador con kernel completado](../tools/qualify_f339_from_completed_kernel.py).
El primer build `f339-topaz-hwmon-20260921T132841Z` conserva su FAIL: completó Linux
y hwmon, pero `-Wextra -Werror` convirtió avisos antiguos de cabeceras en errores
al compilar el módulo. La política del módulo se ajustó a la del kernel; los tests
portables conservan `-Wextra -Werror`. Los dos intentos de dry-run previos del patch
también permanecen como FAIL. La entrega canónica es `134348Z`; no se reetiquetó
ningún resultado anterior.
