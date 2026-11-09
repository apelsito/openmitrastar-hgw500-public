# Lyoko Liberation Principle

Lyoko es el HGW-500BNA-QCv2 liberado sobre Bootbase y Linux 5.10. No es un
ejercicio de compatibilidad superficial: todo subsistema util del hardware
debe avanzar por esta secuencia:

```text
DISCOVERED -> UNDERSTOOD -> CONTROLLABLE -> OBSERVABLE -> TESTED -> DOCUMENTED
```

## Alcance

- SquashFS de solo lectura como sistema base, con `/run` y `/tmp` en tmpfs.
- Realtek 2,4 GHz y Quantenna 5 GHz funcionales, medidos y optimizables.
- RF, canales, potencia, bandwidth, DFS, rates, colas, DMA, IRQ y recovery.
- Bridge, multicast, IGMP y VLAN con trafico real.
- Web/API propias con modos Normal, Advanced y Developer.
- Configuracion `validate -> stage -> apply -> verify -> commit`, con rollback.
- LEDs, botones, GPIO, temperatura y watchdog observables/controlables cuando
  el hardware lo soporte de forma segura.
- Paquetes `.ipk` propios para ARC700, uClibc y ABI Lyoko; ningun binario
  OpenWrt arbitrario se considera compatible.
- Evidencia reproducible, hashes, benchmarks y hitos conservados en
  `docs/museum/`.

## Frontera De Escritura

- La iteracion normal escribe exclusivamente `mtd4/linux_live`.
- `mtd0`, `mtd1`, `mtd2` y `mtd5` permanecen protegidas.
- `mtd3/linux_safety` solo puede cambiar como operacion excepcional de
  provisioning de recovery, con autorizacion exacta, hashes, readback y plan
  de retorno; nunca es almacenamiento general.
- La vista logica `mtd6/rootfs_live` nunca es un destino fisico.

## Regla De Evidencia

Un build offline, un control plane activo o una asociacion no equivalen a una
release. Cada afirmacion debe distinguir build, boot, control plane, cliente,
trafico, recovery y estabilidad prolongada.
