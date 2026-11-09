# Entrada actual de AELITA: proveedores nativos con IPv6

La entrada que reproduce R16 es `tools/linux73_build_current_ipv6.py`. Conserva
intacta la herramienta anterior y añade `IPV6=y` a los requisitos obligatorios.
FWT, TQE e iputil utilizan tipos y campos reales de IPv6; la exclusión del
offload NDISC privado de QDRV tiene un alcance distinto.

Seguir el directorio de fuentes y la herramienta indicados por `src/CURRENT`
o por los metadatos de la entrega privada. Para R16, usar
`src/linux-7.3-r16` con esta herramienta. Mantener los demás argumentos y hashes
de la [guía de la entrega actual](LINUX73_AELITA_CURRENT_BUILD.md), cambiando sólo
el ejecutable:

```bash
python3 tools/linux73_build_current_ipv6.py \
  --driver-source ~/openmitrastar/src/linux-7.3-r16 \
  --kernel-source ~/kernel73-port-preparado \
  --kernel-context ~/kernel73-config-base \
  --toolchain-prefix ~/arc-toolchain/bin/arc-snps-linux-uclibc- \
  --gpl-root ~/openmitrastar/vendor/legacy-firmware-source \
  --expected-config-sha256 <SHA256-config-base-de-la-entrega> \
  --expected-kernel-makefile-sha256 <SHA256-Makefile-de-la-entrega> \
  --output ~/builds/linux73-r16-ipv6-a \
  --plan-only
```

El plan valida todas las fuentes y listas de proveedores de Kbuild, su selección
de tipos IPv6, GPIOLIB/I2C, WEXT, regulatory.db firmado y el resto de requisitos.
El build comprueba cada requisito en la configuración final tras `olddefconfig`.
Reconstruir kernel y módulos juntos; no mezclar objetos ni `Module.symvers` del
kernel anterior. `--plan-only` no crea la salida ni inicia compilación.

Fuentes y evidencia permanecen privadas. Firmware, calibración, MAC, claves y
configuración de la unidad quedan fuera de Git. Esta corrección de build no
autoriza ni prueba operaciones físicas del router.
