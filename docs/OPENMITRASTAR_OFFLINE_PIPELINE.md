# OpenMitraStar Linux 5.10: pipeline offline

Esta automatización ofrece un único punto de entrada para inventariar, comprobar,
compilar con caché y validar el estado Linux 5.10 sin tocar el router.

## Comandos

Dry-run/preflight seguro:

```powershell
python .\tools\openmitrastar_offline_pipeline.py preflight
```

Build incremental reproducible (reutiliza la caché WSL y solo genera RAMSSH):

```powershell
python .\tools\openmitrastar_offline_pipeline.py build --jobs 4
```

Validación posterior sin compilar:

```powershell
python .\tools\openmitrastar_offline_pipeline.py validate
```

## Garantías de alcance

- El bin OEM es una entrada inmutable, fijada por tamaño (`6729728`) y SHA-256
  (`f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f`).
- Solo se permite el builder incremental RAMSSH conocido. Se fuerza
  `TOPAZ_PACK_FLASH_ARTIFACTS=0`, `TOPAZ_INCREMENTAL=1` y un
  `SOURCE_DATE_EPOCH` fijo.
- El build conserva los flags del `.config` existente para no reactivar por
  accidente watchdogs o probes diagnósticos.
- Los scripts invocados se inventarían y hashean. El preflight bloquea el build
  si detecta comandos de red/transferencia en esa ruta permitida.
- Se vuelven a hashear las entradas al terminar. Si otro agente o proceso cambia
  el port durante la ejecución, el resultado queda `BLOCKED` y se exige repetir
  desde una instantánea estable.
- No existe ninguna etapa de HTTP, SSH al router, TFTP, UART, despliegue, reboot
  o flash.
- Todos los artefactos quedan con `candidate_eligible=false`. Las imágenes
  `RAM-ONLY`, `NO-FLASH` o `NO-GO` nunca se promueven a firmware candidato.

La salida RAMSSH sigue siendo explícitamente:

```text
linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.*
```

Que pase esta pipeline demuestra reproducibilidad, integridad del uImage,
contrato de configuración y coherencia de hashes. No demuestra por sí solo que
una imagen sea segura para flash ni autoriza escribirla en hardware.

## Salidas

La pipeline escribe de forma atómica en `outputs/offline-pipeline/`:

- `manifest.json`: entorno, entradas y artefactos con SHA-256, checks, política
  de seguridad, caché y resultado.
- `report.md`: resumen legible.
- `manifest.sha256`: hash del manifiesto.
- `build.log`: solo cuando se ejecuta el modo `build`.

El `inputs.fingerprint_sha256` es estable mientras no cambien los scripts,
parches, fragmentos de configuración, initramfs o toolchain inventariados. La
marca temporal del manifiesto no forma parte de ese fingerprint.
