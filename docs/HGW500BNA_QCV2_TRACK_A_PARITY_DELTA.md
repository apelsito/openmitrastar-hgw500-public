# HGW-500BNA-QCv2: delta ejecutable Track A

Fecha de corte: `2026-08-20`  
Alcance: WAN/VLAN/bridge/DHCP/DNS/NAT/firewall/IPv4/IPv6 y UI/CGI.  
Acciones sobre hardware: `0`. Escrituras flash: `0`.

El auditor `tools/audit_hgw500_track_a_parity.py` vuelve a derivar el camino
crítico desde tres fuentes locales independientes: el ZIP de dump verificado,
el rootfs OEM actual y el rootfs de producto Linux 5.10. No contacta hardware,
no lee valores secretos y no escribe flash. Genera:

- `outputs/kernel-port/movistar-parity/track-a-delta.tsv`;
- `outputs/kernel-port/movistar-parity/track-a-delta.json`;
- `outputs/kernel-port/movistar-parity/track-a-audit.json`;
- `outputs/kernel-port/movistar-parity/track-a-manifest.json`.

Cada fila incorpora prioridad, dependencia OEM, implementación 5.10, estado,
gap y prueba de aceptación. El auditor falla si reaparecen objetos WAN OEM,
reglas NAT, daemons DHCP/DNS locales o si falta el contrato de bridge.

## Decisión extraída del Origen

El camino mínimo hacia Internet no es PPPoE/NAT local, sino:

```text
HGU upstream -> Ethernet -> br0 -> cliente 2,4/5 GHz
```

La evidencia que fuerza esta clasificación es:

- `mode=ap`, `staticip=0`, `region=es` en `etc/default_config.txt`;
- `br0`, forward delay `0` y ageing `7200` en `scripts/qbr`;
- `dhclient -4 br0` solo para gestión STA en `scripts/start-prod`;
- cero objetos `WANDevice`, `WANConnectionDevice`, `WANIPConnection` y
  `WANPPPConnection` en `etc/config.default.xml`;
- cero reglas `MASQUERADE`, `SNAT` o `DNAT` en init/scripts;
- cero binarios `udhcpd`, `dnsmasq`, `named` o `dhcpd`;
- la bandera genérica PPPoE de la UI pertenece al backend `api_fake`.

Por tanto, PPPoE, NAT y servidor DHCP/DNS serían un perfil de router nuevo, no
paridad del firmware OEM de este videobridge.

## Tres gaps más cortos para Internet real

1. Arrancar por RAM la imagen exacta de producto actual tras cold boot y
   confirmar `br0=Ethernet+wlan0`, SSH y hostapd `ENABLED`.
2. Certificar durante al menos 10 minutos un cliente WPA2 con DHCP upstream,
   DNS, HTTPS, MTU, reconexión y contadores RX/TX avanzando.
3. Política cerrada offline: normal `staticip=1` en `192.168.1.90/24`,
   gateway/DNS `192.168.1.1`, y `.200` reservado a recovery. Falta ejecutarla
   en hardware y demostrar que no aparece un servidor DHCP competidor.

Después: ejecutar el smoke CGI sobre hardware. `firmware.cgi` continúa limitado
a validación y staging volátil; la escritura persistente pertenece al gate de
flash separado.
