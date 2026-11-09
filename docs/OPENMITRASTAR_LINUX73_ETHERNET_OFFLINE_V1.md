# Linux 7.3 Ethernet v1 — compilación y lifecycle offline

22 de octubre de 2026. HGW-500BNA-QCv2 A2, ARC750D/MMUv2/8 KiB.

El kernel `7.3.0-openmitrastar-eth73-v1` y el driver EMAC compilan dos veces
desde fuente y producen bytes idénticos. **OFFLINE PASS; NO_GO_HARDWARE.**
Ethernet está desactivado en el DT y el módulo no se incorpora al initramfs.
No se ha creado una imagen RAS de esta variante ni se ha accedido al router.
El último resultado físico es BASIC UART en RAM, aceptado a las 15:35 UTC;
su estado posterior no se ha refrescado durante este trabajo offline.

| Artefacto | Bytes | SHA-256 |
| --- | ---: | --- |
| Kernel ELF, lanes a/b | 4.455.148 | `3c173455469c84ed46664a9f3b36b80dfd112ab77b77cc1f755413cbb2a6e19a` |
| `qtn-topaz-emac-eth73.ko`, lanes a/b | 25.808 | `067f040165348edcdc3d125cf284f6921802cc3590909df9fe3772c0b9adf798` |
| DTB incrustado y sidecar | 2.268 | `f4b7246b5b3ba9e1d9db46669163bd54bc58b76c4eab42a6daed0d0785ce8b40` |
| Configuración, lanes a/b | — | `3fa10bfafc543dc9c8f0dfe3507c57373ae88c0ff98589747e428f32d091ac05` |

Las 80 dependencias del módulo existen en Module.symvers del kernel nuevo.
Kernel, módulo y PID1 carecen de instrucciones SWAPE/LLOCK/SCOND.
ENTRY/res_service `0x8493e000`, stext `0x8493e008`, end `0x84c52000`,
por debajo de DDR final `0x88000000`. Son direcciones enlazadas y
comprobaciones estáticas; no prueban DMA ni boot de esta variante.

## Cambios y evidencia

Base: F374r3 SHA fuente
`33a3eb4a25469f39927c4b429dfb40b7afd3f54a8cf319c4c1e727bcab21b82c`.
Se conservan dos netdev con DMA/rings/IRQ/NAPI independientes: MAC1/PHY3,
base e8000000, hwirq20; MAC0/PHY1, base ed000000, hwirq19; MDIO compartido.

La adaptación usa linux/unaligned.h, netif_napi_add_weight,
eth_hw_addr_set, of_get_mac_address con buffer y callback remove void.
Valida hwirq y el dominio snps,arc700-intc, sin exigir que virq sea 19/20.
El gate LHOST modifica sólo UART24 y, con QTN_TOPAZ_ETH73, Ethernet19/20.
DMA-ranges preserva DDR bus 0..128 MiB -> CPU físico 0x80000000.

El lifecycle comprueba la parada antes de reutilizar descriptores y después
de deshabilitar IRQ/NAPI. Un timeout queda latched: no se liberan buffers
ni rings y la reapertura devuelve EIO. El worker completo se serializa
con RTNL usando trylock, para que la cancelación desde ndo_stop no espere
a un worker bloqueado por el mismo lock. RX restart conserva F374r3.

El contraste estático OEM procede de las evidencias REA ya selladas y
arasan_emac_ahb.c: stop_traffic comprueba estados y reset_dma escribe
reset/release sin leer registros durante reset debido a la errata. Esta
variante no añade recuperación por reset ante timeout: conserva memoria
y bloquea el puerto. Quarantine no es recuperación ni garantía de
funcionamiento del hardware. La memoria retenida puede permanecer hasta
un reinicio externo; ese límite es explícito.

El MCP actual rechaza arquitectura arc700/EM_ARC_COMPACT incluso en las
vistas de evidencias portables. No se cambió REA ni se recodificó el ELF
como otra arquitectura. Se reutilizaron los resultados ARC/Ghidra existentes,
con sus límites de pseudocódigo y direcciones de análisis sintéticas.

## Comprobaciones ejecutadas

- Dos builds completos de kernel y módulo con toolchain ARC pinnado; igualdad
  de ELF, módulo, configuración y DTB.
- Lifecycle: 18 casos / 18.340 assertions con funciones reales open, stop,
  quiesce y destructores extraídas del candidato, MMIO/IRQ/NAPI simulados.
- RX restart: 60 casos / 48.606 assertions con helper/caller reales y macro
  iopoll de Linux7.3; incluye STOPPED latched, busy permanente y último read.
- Cuatro mutaciones compiladas y ejecutadas rechazadas: ignorar timeout,
  reabrir tras quarantine, omitir quiesce heredado y liberar rings retenidos.
- 95.978 archivos upstream cotejados byte a byte; siete fuentes adicionales
  declaradas; enlaces simbólicos normalizados por tarfile resuelven al
  mismo destino dentro del árbol. Ningún fichero adicional inesperado.
- DTB leído de las secciones del ELF real, idéntico al sidecar en ambos builds.

Fuentes y recetas: `work/kernel-port/linux-7.3-ethernet-v1/`.
Build Linux: `/home/rea/openmitrastar-linux73-20261022T135100Z/eth73-offline-v4`.
Evidencia Windows: `outputs/rea/movistar-port-20261022T1327175411798Z/`:
`eth73-lifecycle-v2`, `eth73-rx-restart-v1`, `eth73-source-elf-negatives-v3`.
Los intentos previos fallidos conservan sus outputs, sin reinterpretarse.

## Qué falta antes de un ensayo físico

PID1 sigue siendo el BASIC syscall-only; no carga módulos ni configura red.
Falta crear un initramfs de diagnóstico que permita cargar/subir/bajar
interfaces por UART, suministrar identidad del propietario sin guardarla
en el repo, habilitar DT, integrar módulo y empaquetar un RAS nuevo.
Ese cambio requiere un build y contratos propios; esta compilación no
se puede presentar como una imagen Ethernet funcional.

Faltan además pruebas ejecutadas del worker entero, probe/remove y
recursos compartidos. Routing IRQ, DMA/caché, ambos conectores, traffic,
stop/reopen, fallos reales, soak y retorno manual siguen UNRUN.
Las puertas de flash/readback/rollback, bootenv y particiones protegidas
de AGENTS.md permanecen vigentes. No se abre UART ni se reinicia con
esta preparación como única autoridad.
