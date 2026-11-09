# F352 — dos puertos Ethernet independientes

## Resultado

F340 registra **un netdev y utiliza un solo MAC físico cada vez**. No hay un
switch TQE oculto que permita usar ambos conectores simultáneamente en ese
camino. El OEM sí crea un netdev por MAC y su arranque añade ambos al bridge.

F352 implementa el paso mínimo de paridad: dos netdev, cada uno con sus rings,
IRQ, NAPI, contadores y enlace, reutilizando el DMA directo de F340. La
cualificación offline pasa; **ningún conector ni tráfico físico se ha probado**.
No se ha creado ni instalado firmware.

Resultado inmutable:
`outputs/kernel-port/f352-qualified-20260921T163718Z/result.json`.
SHA-256: `957aadf65852c479a21a171581a3b8ae08190d518b094941512c6387bdf5dd13`.

Módulo: `outputs/kernel-port/f352-qualified-20260921T163718Z/a/qtn-topaz-emac-f352.ko`.
24.544 bytes; SHA-256
`41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e`.
Las dos compilaciones producen los mismos bytes y sus imports existen en el
kernel F340 Linux 5.10.260-openmitrastar-radiohw, ABI ARC700 v4.

## Qué hace realmente F340

La fuente exacta `qtn-topaz-emac.c` del árbol aislado que produjo F340 tiene SHA
`ffa1535e9432ca06190bef23f3382650a271d74770d082b6654b76ea028fc860`.
Coincide con la copia local analizada. La cualificación verifica además el DT
**extraído del ELF real F340**, su igualdad con el sidecar y una única llamada
a `register_netdev` en el desensamblado de `qtn_emac_probe`.

| Camino | Hecho demostrado por código |
| --- | --- |
| Registro F340 | Un `alloc_netdev`, un registro y un par de rings. |
| Selección | `qtn_emac_select_rescue_port` busca primero MAC1/PHY3 y después MAC0/PHY1; guarda un único `regs`, IRQ, MAC y PHY. |
| Momento de selección | Sólo durante `ndo_open`; no existe cambio continuo de conector después de abrir la interfaz. |
| DMA | `qtn_emac_hw_start` selecciona RX nativo con `RXP_SYNC_RX_DMA` y TX AHB con `TXP_AHB_ENABLE`. |
| TQE/EMAC vendor | `om-radio5-start` carga `switch_emac` con `w3_symbols_only=1` y rechaza que aparezcan `eth1_emac0`/`eth1_emac1`. La presencia del módulo no significa que controle estos conectores. |

Dos regiones MMIO y dos PHY descritos en DT eran **dos candidatos para un único
netdev**, no dos puertos concurrentes. Una prueba de gestión por Ethernet sólo
acredita el camino usado en ese ensayo; no acredita el segundo conector.

## Referencia OEM y correspondencia

`drivers/ruby/arasan_emac_ahb.c` define `iflist[0]` y `iflist[1]`, con bases e IRQ
distintas y MDIO compartido a través de EMAC0. `emac_init_module` llama a
`emac_probe` por cada entrada habilitada; cada una tiene netdev, rings y NAPI.
`drivers/topaz/switch_emac.c` también crea una interfaz por entrada, aunque usa
el camino acelerado TQE. `etc/init.d/S40network` renombra y añade ambas a `qbr`.

| Orden F352 | Netdev esperado | MAC | PHY | IRQ | Base |
| ---: | --- | ---: | ---: | ---: | --- |
| 0 | eth0 | 1 | 3 | 20 | 0xe8000000 |
| 1 | eth1 | 0 | 1 | 19 | 0xed000000 |

La tabla describe el enlace lógico DT/OEM. La etiqueta impresa de cada
conector físico **no está establecida** por esta cualificación. El nombre
`eth%d` conserva el esquema Linux existente; una futura aceptación debe
confirmar esos nombres y su correspondencia real.

## Implementación

Fuentes nuevas en `work/kernel-port/modules/f352_dual_emac/`:

- `qtn-topaz-emac-f352.c`: derivado reproducible del driver exacto F340.
- `f352_pair.inc`: creación/retirada de ambos netdev, requisitos del hardware y
  monitor de enlace independiente.
- `f352_contract.h`: resolución de modos MII, derivación OEM de la dirección
  secundaria y gestión de fallos al crear el par.
- `f352-disabled.dtsi`: selección explícita del nuevo compatible, deshabilitada.
- `om-ethernet-f352` y `S56-f352-ethernet`: configuración del segundo miembro
  del bridge; sólo pertenecen a una futura imagen F352.

Cada instancia queda fijada a un MAC/PHY y conserva el DMA/rings de F340.
No puede seleccionar el puerto vecino. Las transacciones MDIO comparten mutex;
la secuencia MASK/CTRL del reloj comparte spinlock con IRQ locales desactivadas.
El monitor MII consulta cada puerto cada 500 ms, mantiene carrier apagado ante
error y actualiza velocidad/dúplex como `emac_lib_adjust_speed` del OEM. Usa
`rtnl_trylock`, evitando bloquear al `ndo_stop` que cancela el trabajo con RTNL
tomado. La negociación de 1000 Mb exige capacidad común local y remota.

El driver comprueba los tuples exactos de DT, los bits OEM ENET0/ENET1 liberados
y DMA fuera de soft reset. Si falta ese estado, rechaza el probe. No introduce
el reset global de NETSS/IOSS/PHY del OEM ni inventa otra secuencia MMIO.
El control de reset y reloj completo sigue dependiendo del handoff de Bootbase;
ese requisito debe verificarse en la futura aceptación física.

El atributo antiguo de estadísticas del dispositivo sigue mostrando el puerto
primario. Cada netdev añade `lyoko_emac_port_stats`, usado como marca de que
pertenece al driver F352; el helper no lee su contenido para comprobar presencia.

## Identidad y bridge

El DT F340 contiene una dirección provisional; la identidad efectiva se aplica
después desde userspace. Por eso el helper deriva la MAC secundaria de
`/sys/class/net/eth0/address`, **antes de subir eth1**, sin imprimir direcciones.
Sigue exactamente `scripts/mac_setlocal` del OEM: suma 2 al primer octeto.
No lo sustituye por una operación OR y rechaza el desbordamiento.

El helper requiere el driver F352 en ambos netdev, `br0` ya creado, eth0 unido,
eth1 sin otro master, sin IPv4 propia y inicialmente apagado. Sólo modifica
eth1. Comprueba la MAC aplicada y la pertenencia al bridge; ante fallo retira
eth1, restaura su dirección previa y verifica que vuelva a estar apagado.
No cambia la dirección, configuración ni estado de eth0/br0 ni de las radios.

`--status` es el comportamiento por defecto y no realiza mutaciones. El arranque
`S56-f352-ethernet start` usa `--attach` y debe instalarse únicamente junto a una
imagen F352 cuyo driver/DT se hayan integrado expresamente. Los comandos
`/bin/ifconfig` y `/bin/brctl` existen en el inventario exacto F340; no se asumen
`tr`, `timeout`, `rmdir` ni otras utilidades ausentes del rootfs mínimo.

## Verificación y límites

- **4.933 comprobaciones C**: modos comunes de negociación, valores inválidos,
  derivación de dirección y fallos de creación/retirada. GCC `-fanalyzer` pasa.
- **12 escenarios del helper real en una fixture Linux**: estado, alta,
  idempotencia, marcas/bridge ausentes, otro master, IPv4 existente, errores al
  subir/unir, readback fallido, fallo de dirección y desbordamiento.
- Dos módulos ARC idénticos, imports verificados contra F340.
- DT candidato compilado: sólo cambian `compatible`, `status` y
  `qtn,f352-dual-direct` del nodo Ethernet. Todos los demás nodos y propiedades,
  incluidas flash, watchdog, PCIe y radios, se conservan. El estado es `disabled`.

Falta aceptar físicamente cada conector y ambos simultáneos: negociación,
desconexión/reconexión, bridge entre puertos, tráfico bidireccional, errores y
estabilidad de gestión. No se reclama aceleración TQE, QoS, VLAN/multicast
completos, rendimiento ni aceptación general del port. Wi-Fi/RF/AELITA no forman
parte de estos ensayos offline y siguen aplazados por el usuario.

La cualificación final reutiliza el build fuente-coincidente del
`20260921T162320Z`; no crea otro clon de kernel. Se puede reproducir la parte
DT/helper/evidencia con `python tools/qualify_f352_dual_emac.py`, que exige más
de 500 MiB libres en C: antes de escribir.

## Incidencia local preservada

La unidad C: llegó a cero bytes libres durante la actualización del constructor.
Sólo `tools/build_f352_dual_emac.py` apareció vacío entre los inputs registrados.
Se detuvieron las escrituras y, tras recuperarse espacio, se restauró mediante
temporal, validación AST, SHA exacto y renombrado atómico. Hash original restaurado:
`d0b13263ec99c64607e477ba71abacaa379d53c62655392b5fc97f2793d7c122`.
El build y sus resultados anteriores se mantienen intactos. No se atribuye la
incidencia al VHDX de WSL: root confirmó que reside en D:.
