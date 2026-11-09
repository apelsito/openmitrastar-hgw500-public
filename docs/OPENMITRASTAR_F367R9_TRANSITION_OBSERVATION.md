# F367r9 — observación dirigida de la primera transición52

R9 es una imagen de diagnóstico para localizar el bloqueo observado tras
`CHANNEL_RESULT request=52 exit_code=0` en R8. No declara una causa física
demostrada ni corrige la política DFS. Mantiene ruta CSA, argumentos, retornos,
admisión TX, CAC/NOP, HEALTH y horizontes existentes.

La reproducción acotada
`outputs/preflight/f367r8-csa-hostlink-20260922T220822Z/result.json`
ejecutó ocho casos/13 comprobaciones de la ruta y la macro original. Con
DEFAULT real3, un ACK ausente llega al límite de51 ticks; con un valor distinto
puede llegar a5.001. Jiffies congelados impiden vencer ese límite interno.
Son casos condicionales, no valores medidos durante R8. No se usa el silencio
o el reset posterior para atribuir una de esas causas.

## Marcas y lectura del resultado

| Límite | Observación nueva | Qué discrimina |
| --- | --- | --- |
| Temporizador CSA | `OMF367R9_CSA` before/after, primer52 | Si entra y retorna el callback real y con qué contexto |
| qdrv_set_channel | `OMF367R9_BOUNDARY` entry, STORE38, preparación radar, CHANGE17, on_newchan | Último callee alcanzado y retorno cuando existe |
| Contexto radar | before/after admit, scan-context, native-context, readiness | Separa admisión, publicación del epoch y petición de READY |
| Hostlink | `OMF367R9_HLINK` empty/dequeue/completion, before/progress/after | Opcode38/17/35/26, presupuesto original y progreso de cada reloj |
| Controlador | `OMF367R9_READ` región/modo/snapshot before/after | Getter o lectura que no retorna |
| Snapshot interna | `OMF367R9_SNAPSHOT` kernel/proc-schema/proc-fields | Separa lectura kernel de las dos lecturas de estado del proveedor |

Las marcas kernel contienen jiffies, ktime, IRQ/softirq, IRQ deshabilitadas y
preempt count. Hostlink registra el valor compartido consumido por la decisión
de timeout como `cal_wait` y su disponibilidad, separado de la muestra
`cal_shared_current`. El DEFAULT es el real del header. No se intenta acceder
a `g_qtn_params`: ese objeto pertenece al código MuC y no es un global Linux.

El arm es interno de qdrv, una sola vez para52, ventana8s. Hostlink admite
hasta seis progresos por espera, uno por segundo, y48 líneas más una marca de
agotamiento. El retorno de una espera ya iniciada se puede registrar después
de la ventana. Las fronteras qdrv tienen límite32. El peer tiene contador
local independiente y dos marcas; no introduce dependencia wlan→qdrv.

La traza inactiva de fronteras retorna antes de leer ic/chan. El script status
emite sus marcas por stderr sólo con `OM_F367_R9_READ_TRACE=1`, exportado por
ese enter-dfs. Sus lecturas originales y su stdout JSON son idénticos;
keeper y consultas normales permanecen silenciosos. No se registran SSIDs,
MACs, claves, datos de calibración ni argumentos de potencia.

## Preservación y componentes

Prueba de fronteras/control/status final:
`outputs/preflight/f367r9-transition-observation-20260922T222752Z/result.json`.
Recupera los originales al retirar anotaciones, ejecuta wrappers con una
llamada y retorno idénticos, comprueba el cap y un puntero inválido con traza
inactiva, y compara stdout JSON byte a byte con la traza apagada/encendida.

Prueba hostlink R2 final:
`outputs/preflight/f367r9-hostlink-trace-r2-20260922T224107Z/result.json`.
Recupera la macro original, comprueba una sola lectura para la decisión de
calstate y mantiene el peer patch idéntico. No se repiten bancos DFS previos.

Sólo cambian los módulos qdrv y wlan. El wlan ya compilado se conserva:
`outputs/kernel-port/f367r9-peer-sealed-20260922T223737Z/result.json` liga su
fuente y cabecera a la procedencia real del wlan de R8. El wlan original del
árbol coincide con el artefacto R8; su comando registrado contiene la cabecera
`../qdrv/qdrv_dma_wire.h` y los mismos flags OPENMITRASTAR. La cabecera también
coincide con la ya sellada en R7. No se sustituye por un homónimo.

El cierre distingue una compilación del peer reutilizada de los dos builds
del qdrv final. Dos repacks con esos componentes no equivalen a certificar
una release completamente reconstruida desde fuentes. La captura física y
el retorno F365 siguen siendo responsabilidad exclusiva de root.
