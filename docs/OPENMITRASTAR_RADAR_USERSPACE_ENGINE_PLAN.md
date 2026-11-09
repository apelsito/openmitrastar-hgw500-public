# Frontera UAPI para conservar el algoritmo OEM sin mezclar licencias kernel

21 de septiembre de 2026. Propuesta de implementación tras el NO-GO real de
F332: `kernel/module.c:1432..1478` impide que proveedor/qdrv combinen imports
Proprietary con símbolos GPL-only. No se cambiarán esos checks, exports o
licencias; tampoco se ocultará el propietario de callbacks.

## Arquitectura concreta

- El proveedor **GPL** conserva adquisición F333, PM/BB, configuración y reset
  de hardware, rate real, postfiltro F331, estado de generación, readiness y
  callback `void` a qdrv. Deja de importar cualquier símbolo de un módulo
  Proprietary.
- Un proceso **userspace ARC** ejecuta únicamente los objetos OEM exactos de
  F328/F330 y sus fachadas compatibles. No contiene F331 ni accede a MMIO,
  `/dev/mem`, UART, red o flash. No se carga ningún módulo kernel propietario
  para estas matemáticas.
- Un dispositivo de carácter de la propia imagen, modo 0600 y un único
  consumidor administrativo, conecta ambos mediante mensajes de tamaño fijo.
  No expone punteros kernel ni operaciones arbitrarias de registros.

## Mensajes y propiedad

La cabecera usa campos explícitos de 32 bits y tamaño/versión verificados:
session-id, job-sequence, generación, canal/ancho/scan y flags OCAC. Un trabajo
contiene hasta 128 pulsos raw de 16 bytes, la matriz ZC 49×112 y precisión
original, tiempo realtime sec/usec, ticks monotónicos OEM200, origen temporal
CNT y contador de polls. La respuesta contiene counts original total/current,
candidato, cfg300, stats700, número de flushes y estado. No devuelve direcciones.

El kernel mantiene un único trabajo pendiente. Leer no arma hardware. Responder
requiere la misma sesión/secuencia/generación; duplicados, respuestas tardías,
longitudes distintas o parámetros fuera de dominio fallan cerrados. Close,
muerte del consumidor o timeout retiran READY e invalidan la continuidad antes
de que qdrv pueda completar CAC.

## Reset sin transferir control de MMIO

F330 puede solicitar un reset durante el batch o cualquiera de los dos flushes.
El servicio envía una petición limitada a ese trabajo y request-id. Solo el
kernel ejecuta las dos escrituras CNT bajo BB y devuelve su timestamp realtime
posterior. El request-id es idempotente: una repetición devuelve la respuesta
guardada sin otra escritura. Una cancelación de generación invalida también
los resets. No existe un ioctl de dirección/valor genérico.

El resultado declara emisión de la secuencia, no un ACK inexistente del
hardware ni quiesce. F330 solo confirma su estado previsto con esa respuesta.
El PM duty del worker se libera en éxito, cancelación o fallo. La espera IPC no
retiene el mutex que necesita atender las peticiones de reset.

## Pipeline preservado

El servicio inicializa los motores por generación, ejecuta F330 y conserva sus
counts, aplica el guard OEM de carga/rate, llama al detector periódico solo en
el poll debido y al batch con `current_window_count`, y hace dos flushes tras
un candidato. El kernel aplica F331 con los datos devueltos y su ring de rate
real. La autorización y entrega del callback siguen exclusivamente en kernel.

El servicio no concede READY por arrancar. READY requiere una primera
transacción completa, incluso si la captura válida está vacía. El qdrv bridge
ya preparado exige esa generación antes de empezar/completar CAC o contar un
dwell OCAC. Reintentos de enable no renuevan el epoch.

## Validación necesaria antes de sustituir F332

1. Tests de protocolo: truncados, límites, dos consumidores, sesión anterior,
   generación obsoleta, duplicados, close/timeout y reset idempotente.
2. Handler del servicio enlazado con los dos objetos OEM originales y ejecutado
   en QEMU contra los vectores/cuentas existentes; los resets son simulados y
   se distinguen de los reales.
3. Binario userspace ARC estático y proveedor GPL compilados. Auditoría completa
   `inherit_taint`/GPL-only y grafo de carga sin motores Proprietary kernel.
4. Trazas de integración y latencia en el equipo, con recuperación disponible;
   después CAC/radar/CSA/NOP/weather/OCAC físicos. Ningún oracle sustituye RF.

Esta nota define el siguiente trabajo; no afirma que el servicio/UAPI estén
implementados ni que el bundle kernel F332 anterior sea cargable.
