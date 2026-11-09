# F322: observacion shadow sobre la UI F321

Actualizacion de ejecucion, 2026-09-19: el gate actual de adquisicion devuelve
`NO_GO_ARM_CLEANUP_CONTRACT`. El donor F315 no apaga el capturador ni restaura
registros/SRAM al desarmar; su mutex BB es una referencia de lector. Los pasos
historicos de armado descritos al final no se pueden ejecutar hasta cerrar ese
contrato. [F324 lifecycle](OPENMITRASTAR_F324_RADAR_LIFECYCLE.md) contiene la
correccion de software parcial, las pruebas offline y el bloqueo de hardware.
F322 sigue sellada y desarmada; no se ha instalado.

Estado de esta entrega: **OFFLINE PASS / NO_GO_PHYSICAL**. La imagen esta
preparada, pero F322 no se ha instalado ni ha demostrado funcionamiento del
detector en el HGW. Esta entrega no crea ni ejecuta un promotor de flash o de
armado de adquisicion.

## Artefacto exacto

Directorio privado:

`/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f322-f321-shadow-device-bound`

Imagen:

`openmitrastar-linux510-f322-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`

| Campo | Valor verificado offline |
| --- | --- |
| SHA-256 de imagen | `55145f55f904beb342dd67b39578a79fbc8a4d0bc68bae944402cab80e5f7f1a` |
| Bytes de imagen | `5320704` |
| Full-slot bytes | `7995392` |
| Full-slot SHA-256, relleno FF | `2249c56824f495517af4945e5e5fff4d6c365198b97b88e51a0769549a40074f` |
| Full-slot CRC32 | `1f34e4df` |
| Rootfs bytes | `3747840` |
| Rootfs SHA-256 | `5368441251a899a632db5aa89993af536d794235dddc2e28395457acfdc0e0c3` |
| Margen rootfs antes del store | `839680` bytes |
| Bootbase y slot-fit | `PASS` |
| Version | `lyoko-foundation-6.9.1-f322-shadow-f321-device` |
| Build firmware | `e480f419df74f5c6` |
| UI heredada | `0.3.0-classic-dfs`, build `72dd5d1877544af9` |

Base inmutable F321: imagen SHA-256
`eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`,
rootfs `75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e`.
La aceptacion fisica de F321 pertenece a su campana separada y sigue siendo un
prerrequisito del manifiesto F322; este build no consulta el equipo.

El manifiesto y SHA256SUMS privados conservan
`candidate_eligible=false`, `flash_supported=false` y `release_eligible=false`.
Una autorizacion o resultado de F321 no se convierte en un resultado fisico de
F322.

## Cambio limitado

Se reutilizan los binarios F315 ya construidos y verificados por hash:

| Binario | SHA-256 |
| --- | --- |
| `qdrv-f315-external-radar.ko` | `1dda1a7c7e86bc6391dc113f45d7a3372fcb36894f0a7202abf82688076c35b0` |
| `qtn_radar_shadow_f315.ko` | `a4781e911aabca66ed5e640ae03a5b6772be0af6553cd64e035ec0b26f29d3c7` |

El kernel LZMA es identico al de F321/F315:
`fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`.
Se conserva el contrato ABI offline del donor F315; no se ha compilado el
kernel, el toolchain ni los modulos. Esto no demuestra que la carga del modulo
ni la adquisicion funcionen en esta nueva imagen.

La comparacion completa del rootfs, con tipos, modos, propietarios, enlaces y
contenido, permite exactamente nueve rutas modificadas o nuevas:

- `etc/openmitrastar/release`
- `lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko`
- `lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qtn_radar_shadow_f315.ko`
- `usr/libexec/openmitrastar/om-api-v1`
- `usr/sbin/om-dfs-status`
- `usr/sbin/om-radarctl`
- `usr/sbin/om-radio5-start`
- `usr/share/openmitrastar/radio5g/artifacts.sha256`
- `usr/share/openmitrastar/radio5g/driver-contract.env`

Se preservan 434 entradas ajenas al cambio y 69 directorios existentes. Los 10
archivos del paquete UI `72dd5d1877544af9` mantienen sus hashes, al igual que
`om-qtnctl`, `om-radioctl`, autenticacion, credenciales e identidad del equipo.
No se incorpora el overlay API, los controles ni el detector con autoridad de
F316. F315, F316 y F321 permanecen selladas.

El arranque usa `shadow_enable=1 shadow_arm=0`, canal 36, ancho 80, intervalo
de sondeo 50 ms y limite 18 muestras del donor. Se elimina el armado automatico
que tenia el arranque F315 y se exige `shadow_arm=0`, `configured=0` y
`callback_invocations=0` antes de declarar preparado el arranque de la radio.
La configuracion/lectura del bloque de adquisicion requiere un paso fisico
explicito posterior. `radar_start` y `radar_get_status` siguen devolviendo falso;
no hay autoridad radar, habilitacion DFS TX ni habilitacion weather.

## Observacion de la UI

La API F321 recibe una sola ruta nueva autenticada y de lectura:

`GET /api/v1/radios/5g/dfs`

La ruta usa el `require_read` existente y ejecuta `om-radarctl status`, que
delega a `om-dfs-status`. El resto de la API permanece byte-identico. El
colector solo lee el proc F315 y getters WEXT fijos con timeout; no arma ni
configura la radio.

El JSON mantiene `lyoko.radio.dfs-observation/v1` y anade `acquisition` con
estado de armado, configuracion, sondeo, secuencia, estabilidad de registros,
contadores de pulsos/filas y errores. No devuelve muestras crudas. Campos
ausentes, duplicados o de otro schema se muestran como desconocidos. Una
instantanea declara `liveness_verified=false` y
`physical_rf_detection_proven=false` porque no demuestra progreso temporal.

El modo shadow presenta `backend_ready=false` y `detector.running=false`.
`tx.authorized` y `dfs_tx_authorized` son `null`: el colector no dispone de una
observacion suficiente para afirmarlos. Esto es distinto del contrato de la
candidata, que impide autoridad DFS. CAC/NOP reflejan los getters disponibles;
no se inventan temporizadores ni una lista NOP completa. Los controles
`apply` y `bypass` son falsos. La UI se conserva sin una compilacion nueva.

## Verificacion y evidencia

- Builder: `tools/build_f322_shadow_from_f321.py`. Fija hashes de base, kernel,
  donor y paquete UI, calcula la identidad de fuentes y rechaza sobrescribir
  el directorio final.
- Transformaciones: `tools/f322_shadow_contract.py`.
- Un unico repack, un procesador: `tools/f322_shadow_rootfs_worker.py`.
- Pruebas pequenas: `tools/test_f322_shadow_contract.py`, **7 PASS**. Cubren
  transformaciones exactas, rechazo de drift, ruta autenticada, observacion
  desarmada y ausencia de autoridad deducida de contadores.
- Resultado del build:
  `outputs/preflight/f322-shadow-build-20260907T235828Z/result.json`.
- Verificacion de la ruta final, SHA256SUMS, full-slot, rootfs y UI:
  `outputs/preflight/f322-shadow-final-readonly-20260907T235949Z/result.json` y
  `bootbase-contract.json` del mismo directorio.
- JUnit final: `outputs/preflight/f322-shadow-offline-tests-20260907T2310/tests.xml`.
- Segunda reconstruccion independiente:
  `outputs/preflight/f322-shadow-repro-20260908T000424Z/result.json`,
  **REPRODUCIBLE PASS**, obtenida con
  `tools/reproduce_f322_shadow_candidate.py` y un unico repack secuencial de
  un procesador.

El primer test encontro una ruta fuente API heredada que no existe en el
overlay F314 reducido. Se corrigio el test para leer la API del SquashFS F321
exacto, sin alterar la candidata. Se conserva aquella evidencia fallida en
`outputs/preflight/f322-shadow-offline-tests-20260907T2304/tests.xml`.

La segunda reconstruccion reproduce exactamente imagen, rootfs, full-slot,
kernel, DTB, configuracion y el inventario completo de metadatos. Se han
verificado los mismos hashes de fuentes y helpers, el mismo build ID y el
mismo epoch; no se ha compilado nada. La copia independiente se conserva en
el directorio privado `firmware\f322-shadow-repro-20260908T000424Z`.

El manifiesto inicial de F322 permanece intacto, SHA-256
`e53a3b5e7224a57c26ce0ae8bf149ffe427bc259957402dd093791a6f902d48b`.
Por ser evidencia sellada, su campo original `reproducibility.second_build`
sigue indicando que aun no se habia realizado en aquel momento; el informe
posterior citado es la evidencia suplementaria de reproducibilidad. Esto no
cambia `NO_GO_PHYSICAL` ni los tres indicadores de promocion falsos.

## Siguiente experimento fisico pendiente

1. Cerrar la aceptacion y la recuperacion de la campana F321 y revisar una
   compuerta F322 separada, acotada, que no reutilice autorizaciones ni
   ejecutores antiguos F315/F316.
2. Revalidar identidad actual del equipo, backup/readback, candidato exacto y
   recuperacion antes de cualquier escritura autorizada en `mtd4/linux_live`.
3. Arrancar F322 en no-DFS 36/80 con adquisicion desarmada. Verificar identidad
   F322, UI conservada, SSH/Ethernet, ambas radios/clientes, cero callbacks y
   ausencia de marcadores fatales. La existencia del proc no cierra este gate.
4. Solo tras ese baseline, un gate revisado podra armar adquisicion durante una
   ventana limitada, tomar al menos dos observaciones separadas y desarmar al
   terminar o fallar. Debe exigir progreso temporal del sondeo, estado de
   configuracion coherente, cero autoridad/callbacks y continuidad de gestion.
   Lecturas vacias que progresan solo prueban actividad del sondeo: no prueban
   cronologia de capturas ni deteccion RF.
5. Mantener bloqueado el paso a una autoridad F316 hasta disponer de evidencia
   fisica de adquisicion, clasificacion y manejo de fallos, ademas de los gates
   de CAC/NOP y trafico correspondientes. F322 no cierra esos requisitos.

No hay ejecutor nuevo en esta entrega. La imagen conocida de recuperacion
heredada es exactF314, SHA-256
`a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11`,
full-slot CRC32 `d6b13baa`, con evidencia historica
`outputs/recovery/f319-f314-rehearsal-detached-20260907T111355Z/run/result.json`.
Aquel ensayo demuestra restauracion propia por Bootbase; no demuestra
recuperacion ante bloqueo duro de CPU, borrado parcial o arranque operativo de
`mtd3`. El plan fisico debe volver a comprobar su aplicabilidad al estado
actual y preservar OEM, bootenv, calibracion y `mtd0/1/2/3/5`. `mtd6` sigue
siendo una vista logica.
