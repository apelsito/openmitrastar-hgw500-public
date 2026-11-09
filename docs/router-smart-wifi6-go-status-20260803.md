# Router Smart WiFi 6 Go - estado 2026-08-03

## Resultado corto

La base de Internet esta sana ahora mismo:

- PC por cable: `1 Gbps` estable.
- Adaptador: Realtek Gaming GbE Family Controller.
- Errores del adaptador: `0` RX/TX.
- Muestra pasiva: 291 puntos durante unos 48 minutos.
- Link speed observado: `1 Gbps` en todos los puntos.
- Fallos a router: `0`.
- Fallos a Internet: `0`.
- Fallos DNS: `0`.
- Latencia Internet: p50 `3 ms`, p95 `3 ms`, max `4 ms`.
- Latencia router: p50 `0 ms`, max `9 ms`.
- Recheck puntual posterior: `ping 192.168.1.1` 20/20, 0% perdida, media `0 ms`.
- Recheck puntual posterior: `ping 1.1.1.1` 20/20, 0% perdida, media `2 ms`.
- Recheck tras sesion SSH: `ping 192.168.1.1` 3/3, 0% perdida, media `0 ms`; Ethernet sigue a `1 Gbps`.

Conclusion: el problema fuerte de `100 Mbps` parece corregido ahora. Si vuelve, la regla practica es mirar capa fisica: cable, toma de pared, roseta, puerto del router/switch o terminacion.

## Cambios/estado de Windows

Estado actual del adaptador `Ethernet`:

- Velocidad y Duplex: negociacion automatica.
- Power Saving Mode: desactivado.
- Ethernet eficiente/EEE: desactivado.
- Green Ethernet: desactivado.
- Advanced EEE: desactivado.
- Gigabit Lite: desactivado.

Esto es coherente con un enlace gigabit estable sin que Windows intente ahorrar energia en la NIC.

## Router observado

- Gateway: `192.168.1.1`.
- SSH abierto: puerto `22`.
- Web abierta: puertos `80`/`443`.
- Check web read-only posterior: `http://192.168.1.1/` responde `200`; `https://192.168.1.1/` falla en `Invoke-WebRequest` por confianza SSL/TLS, coherente con certificado no confiado/local.
- Firmware visto por CLI: `VGL_g2.5_100XNT0b23`.
- Modelo/familia: MitraStar GPT-2742GX4X5v6 / Router Smart WiFi 6 Go.
- SSH entra en CLI restringida con usuario de propietario, no shell Linux.

La CLI restringida expone comandos como `sys`, `lan` y `wlan`, pero no expone `sh`, `deviceinfo` ni comandos de sistema Linux directos en el nivel probado.

Sesion real con `1234`:

- `sys swversion` -> `VGL_g2.5_100XNT0b23`
- `sys uptime` -> `24 15:27:13`
- `lan show` -> `br0 192.168.1.1/24`, RX/TX errors `0`, dropped `0`
- `wlan show all` -> 2.4 GHz canal `6 (Auto)`, `802.11ax`, ancho `20 MHz`, SSID principal habilitado, WPS habilitado
- `sh` -> `Can't find command`
- `engDbgtef` -> `Can't find command`
- Probes de soporte bloqueados: `sys state`, `sys imageinfo`, `sys atsh`, `sys telnetd --help`, `sys passwd` no aparecen; la CLI devuelve como validos solo `swversion`, `uptime`, `swupdate`, `updatecfg`, `backupcfg`, `reboot`.
- `sys swversion internal` devuelve la misma version `VGL_g2.5_100XNT0b23`.

## Sobre root / SSH

No hay root shell validada.

El firmware contiene simbolos y strings de comandos internos (`cmdsh`, `libCmd.so`, `rootCmds`, `deviceinfoCmds`, `telnetdCmds`, `current_permission`, `check_permission`), pero en vivo esos comandos no estan expuestos al nivel de permiso disponible.

La ruta publicada `deviceinfo show file "\n/bin/sh"` no aplica tal cual en este runtime porque `deviceinfo` no existe en la CLI restringida disponible.

Limite operativo: no hacer exploit, reboot, `swupdate`, `updatecfg`, backup con secretos, ni cambios de WiFi mientras Gonzalo trabaja, salvo confirmacion explicita.

## Evaluacion de vias del texto pegado

Validado en modo lectura:

- El firmware trae `mhs_management.cgi`, `login_advance.cgi`, `ping.cgi`, `ping_traceroute.cgi` y la pagina `pages/maintenance/remotemgmt/RemMagSSH.html`.
- Los binarios `mhs_management.cgi` y `login_advance.cgi` contienen referencias a `RemoteMGMT.SSH`, `SSHLan`, `SSHWan`, `support` y `8000`.
- El puerto TCP `8000` no respondio desde LAN en la comprobacion puntual, asi que el panel avanzado puede existir en firmware pero no estar levantado actualmente.
- `ping.cgi` existe como binario ARM, pero por strings solo se ven campos TR-069/diagnostico (`IPPingDiagnostics`, `pingIPAddr`, `PINGInterface`). No hay prueba suficiente de inyeccion OS sin desensamblado o prueba controlada.
- `dropbear` contiene strings de control de acceso para `InternetGatewayDevice.LANConfigSecurity.X_TELEFONICA-ES_WanSecurityEnable.1`, `root login rejected` y una referencia literal a `telefonica`.
- `libCmd.so` contiene la funcion local `doEnableShForSSH` en `0x0002bce0`, ademas de `MSTC_SUPPORT_ENCRYPTKEY_SHELL`, `ShellCommand`, `LoginPrivilegeMgmt`, `RomlevelToCmdlevel` y `CmdlevelToRomlevel`.
- La tabla `rootCmds` mapea `engDbgtef` -> `doEnableShForSSH` (`0x0002bce0`), pero ese comando no esta expuesto al usuario `1234` en runtime.
- `check_permission` se desensamblo como `command_mask & current_permission`.
- En `SysCmds`, los comandos visibles para `1234` tienen nivel `w3=0`; comandos de soporte como `telnetd`, `state`, `atsh`, `passwd` tienen `w3=0x8` o `w3=0xc`.
- Se encontraron `/usr/etc/passwd` y `/usr/teetc/passwd`, pero en la imagen extraida estan vacios.
- Un intento dirigido de la cuenta de soporte historica/documentada por SSH fallo con `Authentication failed`; no queda validada como disponible en este runtime.

No validado / requiere ventana autorizada:

- Activar telnet/SSH desde UI, importar backups o tocar `RemoteMGMT` cambia estado del router y puede abrir superficie de ataque.
- Reimportar config (`updatecfg`) o subir firmware puede cortar Internet o dejar el equipo inestable.
- Probar cuentas historicas/backdoor o payloads de RCE no aporta a la estabilidad de la linea y no debe hacerse mientras se trabaja.
- Hay evidencia offline de que `LoginPrivilegeMgmt` puede reescribir `/etc/passwd` con plantillas de `/bin/sh` y `/bin/cmdsh`, pero no hay evidencia suficiente de que esta imagen cree automaticamente una cuenta local concreta ni de una password fija reutilizable. Las apariciones de `telefonica` siguen sin validar una cuenta SSH disponible en esta unidad/runtime.

Interpretacion actual:

- La hipotesis "b23 tiene mecanismo de soporte para habilitar shell" queda parcialmente respaldada por `doEnableShForSSH`.
- La hipotesis "se crea automaticamente un usuario local concreto con password conocida" queda no confirmada en esta imagen/runtime.
- La hipotesis "`engDbgtef` habilita `sh`" queda respaldada offline por tabla, pero bloqueada por permisos en vivo.
- La sesion `1234` parece limitada a nivel `w3=0` y no tiene capacidad para comandos `mask=0x2`.
- La ruta mas limpia para soporte es pedir el nombre exacto del parametro RDM/TR-069 que alimenta `doEnableShForSSH` o `LoginPrivilegeMgmt`, no adivinarlo ni forzar `updatecfg`.

Carril seguro recomendado:

1. Usar UI oficial para desactivar WPS y revisar canal/ancho WiFi cuando haya ventana.
2. Pedir a Movistar el flujo oficial de soporte para shell temporal/reversible.
3. Si se necesita root para investigacion, hacerlo en ventana separada, con backup, consola local preparada y criterio de rollback.

## Riesgos y recomendaciones practicas

- WPS aparecia habilitado en la salida WiFi. Recomendacion: desactivarlo desde la UI si no se usa.
- Si alguna salida imprimio PSK/passwords, rotar claves despues de terminar la fase de pruebas.
- Si el enlace vuelve a `100 Mbps`, no insistir en drivers: probar otro latiguillo corto directo router-PC o certificar la roseta/cable de pared.
- Mantener autonegociacion en la NIC; forzar `1 Gbps Full Duplex` no arregla un fallo fisico real.

## Preguntas para Movistar / MitraStar

1. Para `GPT-2742GX4X5v6` con firmware `VGL_g2.5_100XNT0b23`, cual es el mecanismo oficial de elevacion de la CLI SSH de propietario a shell de mantenimiento?
2. Que cuenta/perfil habilita `rootCmds` o comandos como `deviceinfo`, `telnetd`, `sys atsh`, `sys atup`, `sys atwp`?
3. `MSTC_SUPPORT_ENCRYPTKEY_SHELL` y `sys a/6tj;4dkru4` son parte de un unlock oficial de soporte? Si si, cual es el flujo y como se desactiva despues?
4. Existe un modo temporal y reversible para shell Linux local sin modificar firmware ni abrir gestion remota WAN?
5. Hay documentacion de los niveles `RomlevelToCmdlevel` / `CmdlevelToRomlevel` o mapping de permisos para `cmdsh`?
6. Puede soporte generar un token/clave temporal para esta unidad por numero de serie, con caducidad?
7. Que cambios WiFi recomendais para rendimiento domestico en este modelo: WPS off, WPA2/WPA3, 2.4 GHz 20 MHz, 5 GHz canal/DFS, band steering, potencia, mesh?

## Siguiente paso seguro

Mantener monitor de red durante trabajo normal y, cuando haya ventana sin reuniones, hacer una prueba fisica A/B:

- PC directo al router con latiguillo corto conocido bueno.
- PC por la toma/cable de pared actual.

Si ambas quedan a `1 Gbps` sin perdida, el cuello queda descartado por ahora y pasamos a optimizar WiFi/UI.

Siguiente cambio reversible recomendado en ventana corta:

- Desactivar WPS desde la UI oficial.
- Confirmar que SSH/Telnet/WAN management no cambian.
- Mantener 2.4 GHz en 20 MHz.
- Revisar 5 GHz/canal DFS solo si hay clientes con cortes o baja velocidad.
- Guardar antes/despues en `docs/gpt2742-rescue-window-checklist.md`.

No hace falta root para este paso y aporta seguridad/estabilidad inmediata.

Herramientas preparadas:

- `tools/gpt2742_safe_window_check.ps1`: pre/post check de Ethernet, ping, puertos y estado WiFi local.
- `tools/gpt2742_wifi_scan_summary.py`: resume una captura `netsh wlan show networks mode=bssid` para decidir canal 2.4 GHz.
- `tools/gpt2742_link_monitor.ps1`: monitor continuo de enlace, ping a router/Internet y puertos `22/23/8000`.
- Baseline generado: `outputs/gpt2742-snapshots/safe-window-pre-20260803-132837.json`.
- Monitor corto OK generado: `outputs/gpt2742-monitor/link-monitor-20260803-133419.summary.json`.

Observacion local: `wlansvc` esta parado en este PC, asi que ahora mismo no hay escaneo WiFi desde Windows. Para elegir canal hace falta activar WiFi local o usar otro dispositivo/movil.
