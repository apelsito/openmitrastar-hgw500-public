# AELITA: paquete privado actual de Linux 7.3

Usar la versión señalada por `src/CURRENT`, actualmente la entrega R16 en
`src/linux-7.3-r16`. El directorio anterior `src/linux-7.3` y su herramienta
sellada permanecen como evidencia de aquella entrega.

La entrada actual es `tools/linux73_build_current.py`. Valida el manifiesto
completo y todas las listas de fuentes de Kbuild, incluyendo cada proveedor
físico. No reutiliza `.o`/`.ko`, ni cambia el kernel base o el checkout. El modo
`--plan-only` no crea una carpeta de build.

En Linux/WSL, clonar la rama privada y sus submódulos sobre un filesystem sensible
a mayúsculas, con rutas sin espacios. Fijar los commits que indique el manifiesto
de la entrega y comprobar sus hashes antes de usarlo en AELITA. El kernel base
upstream es `c03c1a14507dfaf8b856c2608f9ac216021fc222`, junto al port Topaz
BASIC/PCIe/Ethernet/Realtek elegido; un upstream sin ese port no sustituye a la
entrada preparada. El GCC ARC aprobado tiene SHA256
`3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263`.

```bash
python3 tools/linux73_build_current.py \
  --driver-source ~/openmitrastar/src/linux-7.3-r16 \
  --kernel-source ~/kernel73-port-preparado \
  --kernel-context ~/kernel73-config-base \
  --toolchain-prefix ~/arc-toolchain/bin/arc-snps-linux-uclibc- \
  --gpl-root ~/openmitrastar/vendor/legacy-firmware-source \
  --expected-config-sha256 <SHA256-config-base-de-la-entrega> \
  --expected-kernel-makefile-sha256 <SHA256-Makefile-de-la-entrega> \
  --output ~/builds/linux73-r16-a \
  --plan-only
```

Esperar `PASS_PLAN_ONLY_CURRENT_INPUTS_AND_ALL_MODULE_MEMBERS_VALIDATED`. Con
`--prepare-only` se materializan fuentes y contexto nuevos; con `--build` se
reconstruyen kernel, DT y todos los módulos base, seguidos por los módulos del
driver y sus proveedores juntos. La configuración requerida se obtiene del
manifiesto y exige además GPIOLIB, I2C, WEXT, NET_SCHED, bridge y libaes. Mantiene
la verificación de regulatory.db firmado, CPU750D, MMUv2/8 KiB, UP y ausencia de
forced module unload.

Las extensiones de ABI de `sk_buff` y `net_device` requieren reconstruir también
los módulos base existentes y Ethernet contra ese mismo kernel. El viejo
`Module.symvers` sólo es referencia; la composición utiliza el generado por el
build nuevo. No sustituir dependencias de HBM/TQE/GPIO/I2C/temperatura/bridge por
funciones vacías para obtener un enlace.

Firmware de radio, calibración, MAC, claves, PSK, configuración de unidad y DT
privado quedan fuera de Git. La herramienta excluye el initramfs privado del
build genérico y no empaqueta, instala ni ejecuta una imagen. El manifiesto del
kernel exportado debe acompañar a la entrega: sin `.git`, el commit es declarado
y el hash de Makefile por sí solo no demuestra todo el port.

Preparación y compilación son gates distintos. Antes de una imagen física:
segunda compilación reproducible, imports/exports actuales, ABI, regresiones y
ausencia de instrucciones prohibidas. No equivalen a 5 GHz AUTH/ASSOC/AUTHORIZED,
tráfico, soak, persistencia, rollback ni aceptación de release.
