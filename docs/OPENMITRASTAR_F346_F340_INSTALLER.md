# F346: instalación de F340 y retorno condicionado a F321

21 de septiembre de 2026. **F340 instalado y aceptado físicamente por el operador
principal.** No hubo ARM del watchdog, tests Wi-Fi/RF, asociación, tráfico de
clientes ni acceso a AELITA.

[Campaña física](../outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/result.json):
`PASS_F340_PERSISTENT_WATCHDOG_BASELINE`. Los 5.349.376 bytes se compararon con la
imagen y el slot completo dio CRC `2aa26ca6`; protegidos y store coincidieron antes
y después. Se observó `#340`, marcador F340 y nuevo boot ID
`d6ae3305-d867-4c4b-ac1e-42a2dccf7113`.
[Plataforma F340](../outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/platform-f340/status.json):
**27/27 PASS**. El watchdog quedó inactivo, EN=0, contador `0000ffff`,
`ready_for_arm=1` y `device_opened=0`. No hizo falta retorno a F321; UART y procesos
quedaron contenidos, y el operador confirmó el cierre del lease y del hold del host.

[Plan fijado](../outputs/preflight/f346-install-20260921T150921Z/plan.json), SHA-256
`b2938797dd74ee5297c1525cae744544d14a00150ad23d28c0123d2ced362cd0`.
[Resultado de cualificación](../outputs/preflight/f346-install-20260921T150921Z/result.json):
**39 tests PASS**, más los dos entrypoints por defecto sin acciones hardware.
[Revisión independiente ligada al plan y a sus fuentes](../outputs/preflight/f346-readonly-review-20260921T151634Z/result.json):
12 comprobaciones de revisión, sin hallazgos abiertos. Tampoco ejecutó hardware.

## Imágenes y resultado esperado

| Uso | Imagen | Bytes | SHA-256 |
|---|---|---:|---|
| Instalar | F340 watchdog baseline | 5.349.376 | `211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa` |
| Retorno condicionado | F321 exacto | 5.337.088 | `eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18` |

Las rutas y hashes completos autoritativos están en el plan. Sus imágenes se
verifican contra los manifiestos inmutables y el contrato Bootbase. F340 conserva
los módulos, scripts y configuración de radios de F321. Sólo añade el kernel con
driver watchdog inactivo, el supervisor manual y sus metadatos; no incluye F338,
F335 ni F339 y no arranca automáticamente un supervisor.

Se conserva **F340** si su boot ID es nuevo, el kernel es `#340`, el marcador DT
es `F340_WATCHDOG_BASELINE`, pasan las 27 comprobaciones de plataforma y el
supervisor en `--inspect` confirma watchdog registrado, inactivo, EN=0 y descriptor
sin abrir. Ante un fallo se intenta un único retorno a F321 cuando el dominio
UART, la propiedad del dispositivo y la contención estén demostrados.

## Ejecución propuesta

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/run_f346_watchdog_install.ps1 `
  -PlanPath outputs/preflight/f346-install-20260921T150921Z/plan.json `
  -PlanSha256 b2938797dd74ee5297c1525cae744544d14a00150ad23d28c0123d2ced362cd0 `
  -Execute
```

El entrypoint es [run_f346_watchdog_install.ps1](../tools/run_f346_watchdog_install.ps1).
Sin `-Execute`, valida archivos y termina. El worker es
[f346_install_executor.py](../tools/f346_install_executor.py); su import y CLI
por defecto tampoco acceden al dispositivo. La fuente del plan queda fijada y
debe volver a cualificarse si cambia antes de una campaña.

## Propiedad y transporte

El launcher usa el lock F319 canónico y sus dos mutexes para COM3/FTDI exacto.
El boot ID F321 debe permanecer igual antes y después del nonce SSH→UART.
El contexto `f346-install-context/v1` contiene los hashes reales F340/F321,
ese boot ID, el propietario vivo, su comienzo y su lease. No reutiliza un
contexto F334 ni modifica un manifiesto antiguo para presentarlo como F340.

Se reutilizan el lector UART corregido de F336, el servidor TFTP de archivo
único verificado y el Job de procesos F321. El lector mantiene RX continuo,
invalida el prompt tras un handoff y descarta indicaciones de autoboot anteriores
al inicio de cada activación. Las líneas sensibles/desconocidas no se guardan
como UART raw.

Windows PowerShell usa sus propios módulos en el entorno de cada subproceso.
Esto corrige el caso observado donde heredar módulos de PowerShell Core dejaba
`Get-FileHash` sin resolver. No se cambia configuración global del host.

La red debe ser Ethernet 18, origen .49 y destino .90, con la regla UDP ya
existente; no hay UAC, nuevas reglas ni cambios de IP/ruta. Red/permiso se verifican
antes de transferir y al volver a usar SSH después del boot. **La ventana serial
erase→program no depende de que Windows mantenga ese perfil de red**: la imagen
ya está recibida, comprobada en RAM y el servidor cerrado. En esa ventana siguen
siendo obligatorios lease, PnP, fuentes fijadas y precondiciones UART.

## Backup, escritura y readback

Antes de modificar el HGW se guarda una copia exacta de la referencia F321 en
`.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f346-private-backup-*`.
`restrict_acl` se aplica al directorio **antes de copiar** y al archivo después.
El reporte sólo guarda ruta/hash. Esa copia más los backups protegidos existentes
se vinculan a lecturas CRC frescas del dispositivo; no se presenta como un dump
físico nuevo ni como SHA-256 observado en hardware.

La única escritura posible es el prefijo de **0x5e0000 bytes** que comienza en
**0x007e0000**, dentro de `mtd4/linux_live`. `lyoko_store` desde 0x00dc0000 queda
fuera. Este candidato exige que el store siga en el estado borrado conocido de
F321; contenido inesperado impide la instalación, sin normalizarlo ni borrarlo.

La secuencia reutiliza el protocolo ya verificado del escritor F321:

1. WDT inactivo, selector leído sin cambiarlo, CRC frescos de mtd0/1/2/3/5,
   store y slot F321.
2. TFTP F340 exacto; tamaño, `iminfo`, CRC de RAM y cierre del servidor.
3. Revalidación del dominio y de la imagen en RAM antes de habilitar el escritor.
4. `spi_flash erase` exclusivamente del prefijo; recibo exacto y CRC de región FF.
5. `spi_flash write` del número exacto de bytes del candidato; recibo completo.
6. Lectura de todo el slot, CRC esperado, comparación byte a byte del prefijo,
   protección de mtd0/1/2/3/5 y store sin cambios.
7. Nueva lectura de la imagen desde SPI a RAM, verificación y `bootm` directo.
   No se llama `bootselect`, `run`, `saveenv` ni se cambia selección persistente.

Las cadenas `read/erase/write` y sus rangos son literales permitidos. No se
aceptan nombres desconocidos del dispatcher. La [revisión del Bootbase exacto](../outputs/preflight/f346-bootbase-paths-20260921T144707Z/result.json)
vincula las ramas utilizadas a su binario: no pasan por WPSEL, DPB/OTP ni desbloqueo
global; `unlock_hw` es una rama aparte y no está permitida. Es una conclusión
sobre esas rutas concretas, no sobre todos los comandos o caminos de arranque.

## Fallos y retorno

Si falla selector, protegido, store o transferencia **antes de erase/write**, se
puede retornar al F321 original sólo leyendo su prefijo, comprobando su CRC e
`iminfo` y haciendo un único `bootm`. Ese retorno no exige borrar store ni corregir
los protegidos discrepantes. La operación original sigue marcada como fallo.

Después de una escritura, la recuperación requiere imagen F321 recibida y
verificada de nuevo, dominio seguro y helpers contenidos. Sólo entonces se vuelve
a escribir el mismo prefijo y se verifica F321 con sus 27 checks. Un fallo de ese
retorno no provoca otra tentativa, F314 ni modificación de bootenv.

Una operación erase/write cuyo final no se demuestra deja
`flash_command_in_flight=true`: no se emite otro escritor ni un reboot automático.
La falta de contención o de dominio conserva el directorio de bloqueo como barrera.
Los timeouts esperados del SSH que ordena reboot se contienen y sólo un prompt
UART nuevo permite continuar; el timeout por sí solo no prueba el reset.

Los resultados principales son `PASS_F340_PERSISTENT_WATCHDOG_BASELINE`,
`FAILED_F340_WITH_EXACT_F321_RETURN` y los estados explícitos de parada/retorno
no demostrado. Un retorno correcto no reetiqueta como exitosa la instalación
fallida. No se abre `/dev/watchdog` durante estas comprobaciones.

## Validación y límites

23 tests ejercitan el pipeline y Host con flash/RAM simuladas: instalación,
readbacks, errores de ACK/CRC, retornos, store/protegidos inesperados, prompt
antiguo/nuevo, NUL del DT, pérdida de red tras erase y helpers no contenidos.
Otros 16 prueban el contexto PowerShell con sustitutos explícitos de PnP/lease.
No utilizan el dispositivo. Los defaults Python y PowerShell se ejecutaron
sin `Execute` y no hicieron acciones hardware.

La evidencia previa F336 prueba cese de pets con CPU/SSH sanos y reset observado.
No demuestra recuperación frente a CPU/bus bloqueados, causa de reset en silicio
ni reset completo de chip. F346 no incluye un experimento de ese tipo ni una
activación automática del watchdog.
