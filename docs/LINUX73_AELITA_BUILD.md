# Construcción privada del driver Quantenna para Linux 7.3 en AELITA

La entrada portable es `tools/linux73_build.py`. Utiliza sólo repositorios,
kernel y toolchain que ya estén presentes. El modo `--plan-only` valida hashes,
fuentes, cabeceras, Kbuild y el overlay sin crear directorios ni compilar.

Usar Linux o WSL con un sistema de archivos sensible a mayúsculas. Clonar la
rama privada seleccionada y sus submódulos en el disco Linux, fuera de `/mnt/c`:

```bash
git clone --branch <rama-privada-verificada> --recurse-submodules <remote-privado> ~/openmitrastar
git -C ~/openmitrastar submodule update --init --recursive
```

Conservar el commit exacto de cada repositorio/submódulo en el manifiesto de la
entrega. El kernel base usado por esta línea procede del commit
`c03c1a14507dfaf8b856c2608f9ac216021fc222`; requiere además el overlay Topaz
BASIC, Ethernet/PCIe/Realtek y configuración de la entrega elegida. Un árbol
upstream sin ese port no sustituye al kernel preparado. El GCC ARC aprobado
tiene SHA256 `3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263`.
Si el kernel mantiene `.git`, la herramienta comprueba su HEAD. Para un árbol
exportado sin Git, registra que el commit es declarado; conservar el manifiesto
completo del kernel preparado junto a la entrega. El hash de Makefile por sí
solo no prueba todo el port.

El paquete del driver se proporciona por argumento; en el repositorio de
entrega la ubicación prevista es `src/linux-7.3`. Debe conservar `source/`,
`headers/`, `providers/`, `kernel-overlay/`, `Kbuild` y `result.json`. El GPL
original se pasa con `--gpl-root`; no depende de una ruta histórica de Gonzalo.

```bash
python3 tools/linux73_build.py \
  --driver-source ~/openmitrastar/src/linux-7.3 \
  --kernel-source ~/kernel73-preparado \
  --kernel-context ~/kernel73-config-base \
  --toolchain-prefix ~/arc-toolchain/bin/arc-snps-linux-uclibc- \
  --gpl-root ~/openmitrastar/vendor/legacy-firmware-source \
  --expected-config-sha256 <hash-config-de-la-entrega> \
  --expected-kernel-makefile-sha256 <hash-Makefile-de-la-entrega> \
  --output ~/builds/linux73-qdrv-a \
  --plan-only
```

El contexto base aporta `.config` y `Module.symvers` como referencias. El plan
debe terminar en `PASS_PLAN_ONLY_INPUTS_VALIDATED`. Para materializar fuentes
independientes usar los mismos argumentos con `--prepare-only`. Para construir
usar `--build`: crea un kernel y contexto nuevos, aplica el overlay, activa
WEXT y libaes, recompila el kernel con **todos sus módulos base**, y construye
QDRV/WLAN y los cuatro proveedores con el `Module.symvers` nuevo. También activa
`NET_SCHED` y bridge: las funciones WEXT y qdisc necesitan el kernel construido,
y los cuatro exports privados de FDB/aislamiento requieren el overlay real de
bridge en la entrega seleccionada. No sustituirlos por funciones vacías. No copia
objetos ni módulos antiguos. Los logs permanecen en la salida versionada.

El ABI añadido a `sk_buff` y `net_device` exige reconstruir también los 19
módulos existentes y Ethernet; no mezclar módulos del kernel previo con el
nuevo. Los proveedores son módulos separados porque tienen sus propios
`module_init`. La clase privada PM QoS conserva su contrato Quantenna y CCMP
utiliza `aes_prepareenckey`/`aes_encrypt` de libaes.

La herramienta no empaqueta ni instala una imagen. Excluye el initramfs privado
del build genérico; firmware interno de radio, calibración, MAC, credenciales,
PSK, claves TLS/SSH y DT privado se mantienen fuera de Git y se integran mediante
los gates de la unidad física. No publicar esas entradas en logs o repositorios.

Repetir el build en una segunda salida, comparar hashes y cerrar imports,
exports, ABI, regresiones y auditoría de instrucciones antes de probar una
imagen autorizada. Un build aprobado no establece 5 GHz AUTH/ASSOC/AUTHORIZED,
tráfico, persistencia, rollback ni aceptación del release.
