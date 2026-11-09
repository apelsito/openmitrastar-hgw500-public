# HGW-500BNA-QCv2 A2: matriz de paridad OEM/Movistar

Fecha de corte: `2026-08-18`  
Origen: `ES_s00.00_g001_100WNU0b24`, Linux `2.6.35.12`  
Destino: Linux `5.10.260-openmitrastar-radiohw` / OpenMitraStar  
Autoridad: rootfs OEM verificado, dumps, scripts, configuración, UI y evidencia actual bajo `work/mission-state`. No se usan configuraciones típicas de HGU como sustituto de evidencia.

## Decisión de producto

El equipo es un **Adaptador WiFi+ Dual / videobridge**, no el HGU que termina la WAN. El camino de paridad para dar Internet es:

```text
HGU Movistar -> Ethernet/uplink -> br0 -> wlan0/wifi0 o puerto cliente
                 DHCP/DNS/IPTV atraviesan L2 sin NAT local
```

El camino ya demostrado en Linux 5.10 es `eth0 + wlan0 -> br0`: un iPhone quedó `AUTHORIZED` en el AP diagnóstico y completó un Speedtest de `2.11 Mbps` de bajada, `4.50 Mbps` de subida y `50 ms`. La asociación WPA2 segura tiene `hostapd state=ENABLED`, pero su cliente final sigue pendiente. Evidencia: `work/mission-state/MISSION_STATE.md`, `work/mission-state/HARDWARE_STATE.json` y `work/mission-state/EVIDENCE_LEDGER.md`.

WAN/PPPoE, NAT, servidor DNS/DHCP doméstico, VoIP y terminación IPTV no son deuda de paridad de este firmware. Solo pueden añadirse después como un perfil de router nuevo.

## Estados

- `PROVEN_HW`: demostrado en el HGW mediante RAM boot y evidencia reproducible.
- `PROVEN_OFFLINE`: implementación/build/test comprobados, todavía no ejecutados en hardware.
- `PARTIAL`: parte funcional; falta el criterio completo de la fila.
- `BLOCKED`: existe un bloqueo técnico identificado.
- `DEFERRED`: código OEM presente pero actividad/configuración no demostrada.
- `N/A_OEM`: el producto OEM no implementa esa función.
- `TODO`: sin equivalente probado todavía.

## Matriz capability -> implementación -> equivalente -> gate

| ID | Capacidad | Implementación OEM y valores reales | Kernel / userspace / configuración OEM | Equivalente Linux 5.10 / OpenMitraStar | Estado actual | Prueba de aceptación |
|---|---|---|---|---|---|---|
| P01 | Rol de producto | Default `mode=ap`, `staticip=0`, `region=es`, `leds=1`; `start-prod` acepta `ap`, `sta`, `repeater` | `etc/default_config.txt`; `scripts/start-prod`; `var/www/top_menu.html` muestra “Adaptador WiFi+ Dual” | Perfil `videobridge` con AP/STA/repeater y gestión separada | OEM probado estático; 5.10 `PARTIAL` | Conmutar AP/STA/repeater, recuperar gestión y conservar modo tras cold boot |
| P02 | EMAC Ethernet | Según `emac0/emac1`, renombra a `eth1_0`/`eth1_1`; preserva MAC de bootcfg/JFFS2 | `etc/init.d/S40network:43-133`; `etc/network/interfaces` | `qtn-topaz-emac`, IRQ20 y polling fallback; MAC OEM todavía pendiente | Un camino `PROVEN_HW`; puertos/switch completos `PARTIAL` | Enumerar todos los puertos físicos, MAC reales y tráfico bidireccional por cada uno |
| P03 | Switch/HBM/TQE | Carga `switch_vlan`, `switch_tqe`, `switch_emac` según placa y puede usar dos EMAC/bond | `S40network`; módulos `lib/modules/2.6.35.12/extra` | Drivers nativos Topaz switch/HBM/TQE | `TODO/BLOCKED` | Boot sin herencia accidental OEM, contadores por puerto y forwarding sostenido |
| P04 | Bridge L2 | `qbr` crea `br0`, `setfd 0`, `setageing 7200`, añade Ethernet/radios y desactiva IPv6 por miembro | `scripts/qbr:30-124`; `S40network`; `start-vap` | Linux bridge `br0=eth0+wlan0`; gestión `192.168.1.200/24`; promisc preservado | `PROVEN_HW` para Ethernet + 2.4 | Cliente obtiene red upstream, ARP/DNS/ICMP/HTTPS e Internet; repetir con 5 GHz y todos los puertos |
| P05 | Estabilidad de gestión | La IP vive en `br0`; fallback AP `192.168.1.100`, STA `192.168.1.200` | `start-helpers.sh:31-32,182-227`; `qbr` | EMAC polling fallback y watchdog RAM-local | `PROVEN_HW` | Soak ya pasó 600 s, 47/47 ping+SSH; repetir con bridge, tráfico y radios simultáneos |
| P06 | WAN/PPPoE/ONT | No hay `WANDevice`, `WANConnectionDevice`, `WANIPConnection` ni `WANPPPConnection`; flags PPPoE de UI son `Implementation=api_fake` | `etc/config.default.xml`; `var/www/config.json:3,19-20`; menú real sin WAN | Ninguno en perfil de paridad; WAN permanece en el HGU | `N/A_OEM` | Auditor negativo debe seguir dando cero objetos/rutas WAN activas |
| P07 | VLAN | Soporte qvlan/switch y `vlanid.*`, pero defaults `etc/qwe.conf` dejan VLAN vacía | `scripts/topaz-qvlan`; `scripts/ruby-qvlan`; `etc/qwe.conf` | 802.1Q + bridge VLAN filtering solo bajo configuración explícita | OEM `DEFERRED`; 5.10 `TODO` | Tag/untag aislado y captura; no inventar VLAN WAN Movistar |
| P08 | DHCP transparente | `dhclient -4 br0` en STA; el bridge permite que clientes usen DHCP del HGU | `scripts/start-prod:49`; `usr/sbin/dhclient`; `sbin/dhclient-script` | Cliente DHCP de gestión opcional; tráfico DHCP de clientes atraviesa L2 | Paso de DHCP/Internet en AP abierto `PROVEN_HW`; política de gestión `PARTIAL` | Lease/renew/rebind del bridge y cliente físico, sin servidor competidor |
| P09 | Servidor DHCP local | UI/RDM contiene pools, pero no existe `udhcpd`/`dnsmasq` ni init inequívoco en este rootfs | `var/www/lan.cgi`; `lan.html`; `etc/config.default.xml`; ausencia de daemon | Desactivado para paridad; opcional solo con prueba OEM nueva | `DEFERRED`, no requisito | OEM vivo debe probar proceso UDP/67 y lease antes de portarlo |
| P10 | DNS | `Device.LAN.DNSServers=127.0.0.1`; no se encontró daemon DNS enlazado al arranque | `etc/config.default.xml:32`; `etc/resolv.conf`; ausencia de `dnsmasq`/`named` | Resolver de gestión; DNS de clientes atraviesa bridge al HGU | Cliente Internet `PARTIAL`; servicio local `N/A/TODO` | Resolución desde equipo y cliente, identificando servidor efectivo sin asumir proxy |
| P11 | NAT/routing doméstico | `iptables` empaquetado, pero sin `MASQUERADE`, `SNAT`, `DNAT` ni init NAT demostrado | `usr/sbin/iptables*`; búsqueda negativa en `etc/init.d` y `scripts` | `ip_forward=0`, sin NAT en perfil videobridge | `N/A_OEM` | Tablas NAT vacías y direcciones del cliente sin traducción |
| P12 | Firewall | Assets HomeStation usan backend `api_fake`; no existe política WAN OEM demostrada | `var/www/config.json`; `APIS/returnFirewall*.txt`; `iptables` | Firewall local mínimo para gestión, separado del forwarding L2 | Paridad router `N/A_OEM`; hardening `TODO` | SSH/HTTP solo en interfaces permitidas sin romper DHCP, multicast o bridge |
| P13 | IPv4 de gestión | IP desde `/mnt/jffs2/ipaddr`, CCC o bootcfg; fallback AP `.100`, STA `.200`; netmask persistente | `start-helpers.sh:182-227`; `etc/network/interfaces`; `Device.LAN` | Una IP de gestión en `br0`; recovery fija `.200` | Recovery `.200` `PROVEN_HW`; política OEM completa `PARTIAL` | DHCP/fallback, conflicto ARP, renovación y recuperación sin doble IP |
| P14 | IPv6 | `S40network` y `qbr` escriben `disable_ipv6=1`; DHCPv6 solo si `dhcpv6=1`, ausente del default | `S40network:55-68`; `qbr:82`; `start-prod:192-197`; `dhclient-dhcpv6.conf` | Primera paridad mantiene gestión IPv6 desactivada; bridge transparente debe probarse | OEM desactivado/dormant; 5.10 `TODO` | RA/ND e IPv6 L2 sin anuncios DHCPv6/router no solicitados |
| P15 | IPTV | No termina IPTV; transporta multicast y ajusta QHOP según lista multicast/RSSI; `qbr` controla snooping/flood | `scripts/qbr:45-49,87-88`; `scripts/linkrssi.sh:20-76`; bridge OEM | Bridge con IGMP/MLD snooping; `CONFIG_BRIDGE_IGMP_SNOOPING=y` ya compilado | Terminación `N/A_OEM`; transporte `PROVEN_OFFLINE/PARTIAL` | Join/leave, MDB, no flood indebido, DSCP/802.1p intactos y unicast concurrente |
| P16 | VoIP/SIP | No hay `VoiceService`, SIP/ATA, daemon ni CGI activo; cadenas de idioma no cuentan | Auditor negativo sobre `config.default.xml`, init, scripts y menú | Ninguno | `N/A_OEM` | Mantener prueba negativa; no crear telefonía ficticia |
| P17 | TR-069/CWMP | `ManagementServer` y binarios existen; `PeriodicInformEnable=0`, `UpgradesManaged=0`, `STUNEnable=0`; URL y credenciales omitidas | `etc/config.default.xml:7-26`; `sbin/tr69c`; `sbin/zyCwmpStun`; `/mnt/ccc/tr069_*` | Agente opt-in solo si runtime OEM demuestra dependencia real | OEM presente/dormant `DEFERRED`; 5.10 `TODO` | Capturar proceso e Inform del OEM sin exponer secretos; si inactivo, marcar removed intencionadamente |
| P18 | Wi-Fi 2.4 GHz | PCI `10ec:818b`, `rtl8192cd.ko`, QWE, `wlan0`, VAP/WPS | `S55qwe`; `lib/wlan/wlan1.sh`; `etc/qwe.conf` con secretos omitidos | `rtl8192ee` + cfg80211/mac80211 + regdb ES + hostapd | AP abierto, asociación e Internet `PROVEN_HW`; WPA2 `ENABLED`, cliente final pendiente | WPA2 `AUTHORIZED`, clave incorrecta rechazada, DHCP/Internet, rekey y reconnect |
| P19 | Wi-Fi 5 GHz | qdrv/wlan, MuC/AuC/DSP, QCSAPI, `wifi0`, radar/DFS y potencia ES | `qdrv.ko`; `wlan.ko`; `etc/firmware`; `qtn_regulatory_db.bin`; `power_tables/tx_power_QSR1000_es.txt` | Stack Quantenna 5.10 ABI-coherente `.89` | `BLOCKED` antes de MMIO/RF por ABI host `.62.1` vs firmware `.89` | Cerrar TXBF/MuC-DSP/SCS/VAP, crear wifi0, CAC/DFS, asociación y tráfico |
| P20 | Seguridad Wi-Fi | WPA/WPA2, WPS, ACL y PSK persistentes; valores sensibles no se publican | `hostapd.conf`; `wpa_supplicant.conf`; CGI Wi-Fi/WPS; `qwe.conf` | WPA2-PSK-CCMP mínimo; WPS opt-in; API y logs redactados | Crypto software y hostapd `PROVEN_HW`; cliente seguro pendiente | AUTHORIZED, rechazo de clave errónea, ACL/WPS y ausencia de PSK en diagnósticos |
| P21 | LEDs | `/proc/led_control`; `wlan2.4GB` es GPIO11 activo-alto; monitor de estado radio/WPS | `etc/default/led.sh`; `usr/sbin/sys`; `sbin/monitor_wifi`; `start-prod` | LED class `openmitrastar:green:wlan2g`, ligado a wlan0 en modo AP | GPIO11 y brillo `0 -> 255` con AP `PROVEN_HW` | Repetir off/monitor/AP/stop y mapear el resto del frontal |
| P22 | Botón Wi-Fi/reset/RF | `monitor_button`: GPIO2 2.4 y GPIO4 5G, ambos activos-bajos y acción persistente tras 10 x 500 ms; el boot OEM actual confirma además qdrv WPS en GPIO4 activo-bajo, sondeo 300 ms y evento al soltar; proceso actual `monitor_rfenable 12 1`; reset GPIO5 | Binarios exactos `usr/sbin/monitor_button`, `monitor_reset_device`, `monitor_rfenable`; `start-helpers.sh`; `start-prod`; UART OEM `WPS: push button GPIO pin 4` | GPIO2: corto no-op, largo `wifi2g-toggle`. GPIO4: qdrv conserva WPS al soltar y un contador independiente emite `wifi5g-toggle` una vez a ~5 s. GPIO5 separado | GPIO2/4/5 portados; GPIO12 OEM actual; falta certificación física de las tres ventanas de GPIO4 | Pulsar GPIO4 `<5 s`, `5..<10 s` y `>=10 s`; comprobar WPS/toggle/debug sin inventar `wps2g-start` ni `wps5g-start` |
| P23 | Persistencia/config | `/mnt/ccc` contiene config CCC; `/mnt/jffs2` enlaza datos; `S60CCC` crea `config.xml`; mini_fo usa overlay RAM | `inittab:18-20`; `rcS:40-51`; `S60CCC:9-12`; `scripts/overlay` | SquashFS inmutable + `/persist` JFFS2 inicialmente RO + esquema v1 normalizado | Skeleton reproducible `PROVEN_OFFLINE`; runtime `TODO` | RAM boot productivo, montar mtd5 RO, migración, corte durante write y recuperación |
| P24 | Factory reset | Restaura hostapd/WPA, HTTP, VLAN, CCC y borra estado TR-069; preservación de MAC/calibración no certificada E2E | `scripts/restore_default_config:205-380`; `restoredef.cgi` | Reset transaccional con allowlist explícita de regiones únicas | OEM estático; 5.10 `TODO` | Snapshot antes/después; bootloader, MAC, calibración y recovery idénticos |
| P25 | Backup/restore | Helpers SFTP mueven `romfile.xml`; flujo completo no demostrado | `scripts/sysBackupCfg.sh`; `scripts/sysUpdateCfg.sh` | Export firmado/cifrado, schema/model/version y redacción | OEM `DEFERRED`; 5.10 `TODO` | Export -> reset -> import -> cold boot; rechazo corrupto/otro modelo |
| P26 | UI OEM | Menú real: 5G AP/STA, 2.4G, password, sysinfo, LAN, firmware, avanzado, reset y ayuda | `var/www/top_menu.html`; CGI reales; `libweblanguage.so` | UI estática/API pequeña primero; TypeScript compilado fuera después | Assets/overlays OpenMitraStar offline; integración 5.10 `TODO` | Smoke GET/POST, sesión/CSRF, funciones equivalentes y cero secretos en respuestas |
| P27 | HTTP/HTTPS/getinfo | Tres mini_httpd: `80`, `443 ssl`, `16667`; ejecutados por `S92httpd` | `S92httpd`; `minihttpd.conf`; `minihttpd_ssl.conf`; `minihttpd_getinfo.conf` | Servidor pequeño con TLS moderno y endpoints documentados | OEM probado estático; 5.10 `TODO` | Login, CSRF, TLS, reinicio, consumo RAM y aislamiento del puerto getinfo |
| P28 | Administración | UART; inetd/telnet salvo marker; Dropbear empaquetado sin init inequívoco | `inittab`; `S42inetd`; `inetd.conf`; `usr/sbin/dropbear` | UART recovery + SSH key-only; telnet eliminado | SSH/UART `PROVEN_HW` | Rotación/revocación, shell owner explícita, telnet cerrado y recovery independiente |
| P29 | Firmware/recovery | UI y scripts validan/escriben `linux_live`; Bootbase/TFTP/uImage disponibles | `firmware.cgi`; `FWupgrade.sh`; `validate_image`; `update_image_flash` | Manifest/hash, RAM boot equivalente, slot exacto y rollback | Recovery RAM/F2 backup `PROVEN_HW`; flash 5.10 `NO-GO` | Cold boot, smoke, slot inmutable y rollback probado antes de declarar candidato |
| P30 | NTP/logging | `ntpclient` existe, pero config lo deshabilita y arranque visible está comentado; syslog/qharvestd opcionales | `etc/ntpclient.conf`; `start-ntpclient`; `S90maui`; `run_syslogd` | NTP después de red; logs circulares/redactados y exportables | OEM actividad `DEFERRED`; rootfs productivo `PROVEN_OFFLINE` | Hora, timezone, rotación, pérdida de red y export sin secretos |

## Orden de cierre para Internet y paridad

1. Cerrar WPA2 físico: `AUTHORIZED`, DHCP upstream, DNS e Internet.
2. Mantener EMAC/SSH y bridge durante soak con ráfagas e inactividad.
3. Enumerar todos los EMAC/puertos y preservar MAC reales.
4. Validar multicast/IGMP/DSCP para transporte IPTV.
5. Completar 5 GHz con ABI, DFS y calibración coherentes.
6. Arrancar rootfs productivo SquashFS + persistencia RO y probar migraciones.
7. Completar mapa frontal, reset, UI, backup/restore y cold boot.
8. Solo entonces abrir gate de flash/rollback M7.

## Pruebas negativas obligatorias

La matriz se invalida si se presenta como paridad una función sin implementación OEM real. El auditor offline debe verificar:

- cero objetos `WANDevice`, `WANPPPConnection` y `VoiceService` en `config.default.xml`;
- `var/www/config.json` declara `Implementation=api_fake` para PPPoE/3G genéricos;
- ninguna regla `MASQUERADE`, `SNAT` o `DNAT` en init/scripts OEM;
- ausencia de daemon `udhcpd`, `dnsmasq` o `named` en el rootfs;
- ningún artefacto de matriz contiene PSK, password, usuario ACS, URL ACS, claves, certificados o el fichero privado de laboratorio.

La copia TSV auditable está en `outputs/kernel-port/movistar-parity/capability-matrix.tsv`.
