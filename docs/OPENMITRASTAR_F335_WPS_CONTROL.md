# F335: control WPS por banda y overlay de arranque

21 de septiembre de 2026. Este trabajo crea código, binarios y pruebas offline; no accede al HGW, no cambia radios ni crea/escribe un firmware.

## Entrega

Overlay: `versions/f335-wps-control/overlay/`.

Resultado canónico: `outputs/kernel-port/f335-wps-control-20260921T125655Z/result.json`.

**30 tests pasan**: comandos correctos 2g/5g, estados modernos y Quantenna, login/CSRF existentes, métodos/cuerpos inválidos, rechazo de PIN, ausencia de PIN en argv/salidas/logs, timeout de subprocesos, errores con ACK engañoso, límite de salida, cancelación, AP-PIN y rollback, exclusión por banda, conservación del arranque y regresión del CLI sin WPS.

| Binario | Bytes | SHA-256 |
|---|---:|---|
| `om-wpsctl` | 33.716 | `636d21cf4ec75c3fcbe9b560dd0f54506051d883756beb5fb2fbea6092be7db2` |
| `hostapd` 2g, construido por la raíz desde el source/libnl baseline | 620.284 | `9d4339e59814163277bf08aa4894f7d0c3ea4a01c726973b6b11d0c8edbef564` |
| `hostapd_cli` 2g | 58.484 | `6c36e862764ae01b4f90e9525164c697139943ef54ab598ef4aacc244873db4d` |

El helper tiene dos builds ARC idénticos, enlace estático y ninguna instrucción `llock`/`scond` en la inspección realizada. Usa la misma libc no-atomic empleada para el nuevo hostapd. El daemon y CLI Quantenna permanecen byte por byte como F321; sus comandos requeridos se verificaron en el CLI extraído de su SquashFS (SHA-256 `67df5a9d7e6484101ac29f25c8f178cdea2bef51d4ea3f6fcdeeebb9eb033504`).

## Backend implementado

```text
om-wpsctl 2g|5g status
om-wpsctl 2g|5g pbc
om-wpsctl 2g|5g cancel
om-wpsctl 2g|5g pin              # PIN sólo por stdin
om-wpsctl 2g|5g ap-pin           # AP-PIN de 8 dígitos sólo por stdin
om-wpsctl 2g|5g ap-pin-disable
```

- `status` no inicia WPS y no crea locks/archivos. Puede probarse desde RAM sin instalar la feature: devuelve `control_enabled=false` y observa las capacidades reales del daemon/CLI.
- Las mutaciones requieren usuario local root, feature `OPENMITRASTAR_WPS=1` y exclusión `fcntl` por banda. No dependen de `flock`, `timeout`, `jq` ni `command -v`.
- Cada subproceso CLI tiene un límite monotónico de cinco segundos. Se recogen exit code, EOF, salida excesiva y error; no se declara éxito sólo porque aparezca un `OK` antes de un exit no cero.
- El PIN se valida antes de enviarlo: 4 u 8 dígitos para enrollee, checksum para 8; AP-PIN exige 8. Se transmite por stdin al modo interactivo del CLI, nunca como argumento de proceso. Su salida, aunque contenga eco/PIN, permanece en memoria y se descarta tras comprobar la respuesta.
- Los resultados de mutación indican `accepted=true`, **`enrolled=false`**. Un ACK de control no prueba que el cliente se haya asociado.
- `cancel` cancela PBC/enrollee PIN y deshabilita AP-PIN. La operación específica `ap-pin-disable` sólo cierra la ventana AP-PIN.
- AP-PIN se instala por 120 segundos; si la petición falla o no queda confirmada, el helper intenta únicamente su disable como rollback. Distingue fallo recuperado de estado no verificado. No repite el alta.

Comandos subyacentes:

| Operación | 2,4 GHz | 5 GHz Quantenna |
|---|---|---|
| CLI/socket/interfaz | `/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0` | `/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0` |
| Estado | `raw WPS_GET_STATUS` | `wps_status` |
| PBC | `wps_pbc` | `wps_pbc wifi0` |
| Cancelar registrar | `wps_cancel` | `wps_cancel wifi0` |
| PIN de enrollee, stdin | `wps_pin any <PIN> 120` | `wps_pin_bss wifi0 any <PIN> 120` |
| AP-PIN, stdin | `wps_ap_pin set <PIN> 120` | `wps_ap_pin_bss wifi0 set <PIN> 120` |
| Deshabilitar AP-PIN | `wps_ap_pin disable` | `wps_ap_pin_bss wifi0 disable` |

El estado moderno interpreta `PBC Status` y `Last WPS result`; descarta `Peer Address` y campos arbitrarios. Quantenna valida conjuntamente el código 0–12 y su nombre (`WPS_INITIAL`, `WPS_START`, `WPS_SUCCESS`, etc.), sin tratar respuestas desconocidas como idle. `UNKNOWN COMMAND` y `FAIL` representan falta de soporte/configuración, no un fallo demostrado del HGW.

### Corrección de compatibilidad tras smoke de sólo lectura

El smoke del operador `outputs/handoff-live/f335-readonly-smoke-20260921T121404Z/`
probó los binarios desde RAM contra F321, sin activar WPS ni cambiar radios.
El helper previo devolvió `status-contract` en 2g y `control-unavailable` en 5g.
Su resultado original `FAIL_RAM_CLEANUP` se conserva; el resultado separado
`cleanup-result.json` acredita la limpieza posterior. No se convierte en PASS.

La causa 2g es concreta: el CLI F321 no incluye el comando local `wps_get_status`.
La captura real posterior `outputs/handoff-live/f335-old-cli-status-20260921T125737Z/result.json`
confirma exit=0, stdout exacto `Unknown command 'wps_get_status'\n` y stderr vacío;
su [fixture negativa](../versions/f335-wps-control/fixtures/f321-cli-without-wps-status.json)
coincide con el caso probado.
En el source hostapd fijado por SHA-256 del tarball
`c1a978092c8a6e43a9e1bd47e1f334637b9c4969ca741c30ff45c24539132ca4`,
`hostapd_cli.c:1993` imprime `Unknown command '%s'` y el `main` termina con cero.
La prueba previa simulaba exit=1 y omitía esa combinación. El nuevo helper usa
`raw WPS_GET_STATUS`: `raw` está en la tabla fuera de `CONFIG_WPS`, por lo que
el propio daemon puede responder `UNKNOWN COMMAND` y se informa `unsupported`.
Además reconoce exclusivamente las líneas locales de comando desconocido
esperadas, con exit cero o uno, sin aceptar una mera subcadena dentro de otro error.

Los tests nuevos cubren esa línea local con exit=0, el daemon antiguo a través de
`raw`, ausencia de locks en status y el rechazo de una respuesta que sólo contenga
la subcadena. Son pruebas offline; la repetición física del smoke con este nuevo
hash sigue pendiente. No se cambió el tratamiento de errores de transporte 5g ni
se infirió WPS activo a partir del `FAIL` observado cuando está deshabilitado.

El anterior resultado offline de 27 tests y su binario se conservan en
`outputs/kernel-port/f335-wps-control-20260921T114038Z/`.

## API autenticada

Se amplía el dispatcher existente `om-api-v1`, después de su `session_valid`. No se añade un servidor ni CGI sin autenticación.

- `GET /api/v1/radios/{2g|5g}/wps`.
- `POST /api/v1/radios/{2g|5g}/wps/{pbc|cancel|pin|ap-pin|ap-pin-disable}`.

Todas las mutaciones usan el CSRF existente. PBC/cancel/disable exigen cuerpo vacío. PIN/AP-PIN usan `application/x-www-form-urlencoded` y sólo `pin=<dígitos>`. No se aceptan campos adicionales, duplicados o comandos arbitrarios. El PIN no vuelve en el estado general ni en las respuestas del alta.

## Arranque y credenciales

El compositor integra los binarios de 2g construidos por la raíz, el helper y la feature. Los productores de configuración llaman a `om-wpsctl <banda> config` para añadir:

- `wps_state=2`, `eap_server=1` y métodos `push_button keypad`.
- Datos estáticos del modelo, sin modificar MAC/calibración ni añadir una PSK distinta.
- AP setup cerrado por defecto; no se configura un AP-PIN al arrancar.
- `wps_cred_processing=1`: los nuevos ajustes recibidos de un external registrar no se aplican automáticamente al AP.
- Sólo en Quantenna, `ap_pin_fail_method=default`, necesario para que el timeout AP-PIN solicitado active la ruta de expiración y bloqueo nativa.

No se ejecuta PBC ni un alta PIN durante el arranque. `om-radio-start` y `om-radio5-start` siguen lanzando hostapd en foreground, sin `-B`; se conserva la solución al `ENODEV` de `daemon(3)`. Los cambios completos se comparan contra F321: fuera del añadido WPS y del nivel de logging son idénticos. `om-rtlctl` y sus reglas HT40+/HT40− no se modifican.

Se sustituye el logging de los daemons por `-q`. Es funcionalmente necesario para esta integración: Quantenna registra comandos de control con PIN a nivel DEBUG, y el modo de credenciales notificadas puede producir un evento INFO con ajustes AP. El helper no guarda esas respuestas y los daemons quedan a nivel warning; se reduce la verbosidad de sus logs. Los sockets/status y el arranque foreground permanecen.

La cadena de arranque extraída de F321 es `inittab → rcS → S50-radio-ap → om-radio-start` y `S55-radio5-ap → om-radio5-start`. El kernel exacto tiene `CONFIG_INITRAMFS_SOURCE=""`. La aceptación final debe comparar también el perfil runtime 2g/F93, sin reconstruir sus parámetros desde memoria.

## Integración con F332/F334

**No copiar ciegamente los scripts baseline encima de una composición más nueva.** `tools/f335_wps_overlay.py` proporciona transformaciones aditivas:

```python
patch_radio2(current_radio_start_bytes)
patch_radio5(current_radio5_start_bytes)
patch_api(current_api_bytes)
```

Exigen anchors únicos y conservan el resto del contenido. La raíz debe aplicarlas al candidato compuesto, verificar su diff y recalcular el catálogo de `om-radio5-start`, el inventario y hashes finales. Así se conservan los cambios F332/F334 del provider/perfil qdrv. El overlay no cambia sus scripts ni el executor 86.

Asignar en el rootfs final modos 0755 a ejecutables/scripts y 0644 a la feature. Los hashes y rutas del overlay están en `versions/f335-wps-control/preparation.json`; la verificación final de filesystem pertenece al compositor.

Reproducción offline:

```powershell
python tools/build_f335_wps_control.py
```

## Alcance y aceptación pendiente

Esto implementa PBC, enrollee PIN, ventana AP-PIN acotada y cancelación. **No es WPS 100% aceptado físicamente.** El OEM define también AP-PIN/registrar en `wifi5g_adv.html`, aunque su visibilidad depende del perfil. El external registrar que cambia SSID/PSK sigue deshabilitado en este perfil; la API lo declara como `external_registrar_apply=false`. Su aplicación requiere un contrato de cambio/rollback de credenciales que este overlay no finge haber completado.

Faltan pruebas en la imagen integrada y con clientes reales:

1. Arranque dual-radio, perfil/HT40 y PSK/MAC/calibración preservados; estado WPS disponible sin sesión iniciada.
2. PBC por banda: enrolamiento, AUTH/ASSOC/AUTHORIZED y tráfico bidireccional.
3. Enrollee PIN correcto/incorrecto, timeout, cancelación y ausencia de PIN en diagnósticos.
4. AP-PIN explícito: acceso de registrar, expiración de 120 segundos y retorno al bloqueo; rollback ante fallo.
5. Botón GPIO4 y señalización/LED OEM. No se ha inventado una acción WPS para el botón 2g, cuyo contrato previo es toggle largo.

### Recorrido existente del botón de 5 GHz

La auditoría offline
`outputs/preflight/f335-wps-button-path-20260921T131109Z/result.json` pasa nueve
comprobaciones. El source qdrv emite `WPS-BUTTON.indication` al soltar GPIO4;
`driver_madwifi.c:1657` ya despacha ese evento a `hostapd_wps_button_pushed`.
El perfil compila MADWIFI y WPS. El artefacto hostapd Quantenna coincide por
hash y tamaño con el inventario F321 y contiene la cadena del evento.

Por tanto, la integración reutiliza ese recorrido. No debe añadirse un segundo
consumidor de `wps_button` que inicie PBC para la misma pulsación. La inspección
de source y la cadena del binario no sustituyen la prueba de evento físico ni
la equivalencia completa de source/binario; pulsación, enrolamiento y LED
continúan como gates físicos pendientes.
6. Cold boot sin reapertura automática de ventanas y API con sesión/CSRF reales.

Los tests usan CLIs simulados y una ejecución local del CGI autenticado; la interacción stdin con los CLIs ARC y los estados RF/clientes requieren la aceptación física correspondiente. No se ha ejecutado ningún control mutante sobre el HGW desde este trabajo.
