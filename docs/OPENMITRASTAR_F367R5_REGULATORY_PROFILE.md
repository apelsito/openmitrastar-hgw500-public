# F367r5 — publicación regulatoria OEM del objetivo DFS52

F367r5 corrige la precondición de `PREPARE52` mediante el productor regulatorio
OEM. No modifica los clasificadores nativos, el algoritmo radar, CAC/NOP, los
canales activos, la calibración ni las condiciones de admisión TX.

Imagen sellada: `PASS_OFFLINE_F367R5_REGULATORY_PROFILE_IMAGE`.
Resultado privado:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f367r5-fullimage-20260922T174701Z/result.json`.
SHA256 `9a4364491804a3bc6cddc43a5970b39ee94efc93f30583532aebcd3ccc4753d1`,
5.464.064 bytes; full-slot CRC32 `131f097e`.
Manifest SHA256
`b5bc8aff0c578cf505cdcb7a5308fe2665cad16dd62da05bf4598b37ae616ce3`.
Dos repacks idénticos, Bootbase PASS, slot-fit PASS y696.320 bytes de margen
rootfs. Store `5d2ee646` y recuperación F365 `118901d4` conservados.

## Evidencia del bloqueo

La campaña R4 `f367r4-observe-v3-20260922T164636Z-35e95209` completó la
cuarentena y observó 27.398 jobs sin errores. `enter-dfs` devolvió
`OMF367_ERROR reason=prepare52`; la captura no conservó un errno o rama
discriminante del handler. El retorno F365 fue confirmado por root.

El defecto de composición se demuestra por la ruta real de fuentes:

- El helper R4 extraído fija ES, modo80 y canal36; no publica la máscara de
  canales que requieren DFS.
- El peer compilado `work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c`
  entrega `IEEE80211_IOCTL_EXT` al dispatcher, y su subioctl14 a
  `ieee80211_subioctl_set_chan_dfs_required`. Éste consume un vector de `int`,
  pone los bits de `ic_chan_dfs_required` y llama `ic_mark_dfs_channels`.
- `qdrv_wlan_80211_mark_dfs` exige país distinto de DEFAULT y ese bit antes de
  añadir `IEEE80211_CHAN_DFS` y PASSIVE al registro del canal. Fijar ES no
  crea por sí mismo esa máscara.
- `ieee80211_find_channel_by_ieee` exige además que52 esté en `ic_chan_active`.
  `PREPARE52` exige que el registro devuelto esté clasificado como DFS.
- El fixture inicial de F367 devolvía52 directamente y lo inicializaba como
  DFS. La prueba R5 ejecuta esos productores, lookup y getters reales.

Esto prueba el defecto del flujo y reproduce el rechazo sin clasificación;
no convierte retrospectivamente el texto físico `prepare52` en una rama que
la captura no emitió.

## Cambio acotado

`om-f367-dfs-profile publish` sólo admite `wifi0`, objetivo52 y país ES. Se
ejecuta después de `radar_bw80`, antes de `radar enable eu`, dentro de la fase
protegida `native-radar` y antes de la espera larga de cuarentena.

El permiso procede de una snapshot RAM del qdrv: AP36/80, ES, primera llamada
nativa pendiente, radar todavía deshabilitado, sin CAC/NOP/transición ni fallo.
Una marca privada con `O_CREAT|O_EXCL|O_NOFOLLOW` consume el único intento y no
se elimina. Una segunda publicación o una publicación posterior al arranque
nativo se rechaza. El callback OEM reinicializa estados del registro; por eso
esta operación pertenece exclusivamente al bootstrap anterior al proveedor,
nunca a la reentrada después de NOP.

La única mutación es `IEEE80211_IOCTL_EXT` con subioctl14, longitud1 y vector
`int {52}`. No llama SETCHANLIST, no cambia país/potencia y no asigna CHAN_DFS
desde el helper. Lee GETCHANLIST/GETCHANINFO antes y después: los32 bytes de
canales activos deben ser idénticos y todos los registros deben conservarse,
salvo añadir DFS/PASSIVE a52.36 debe seguir activo y noDFS.

`om-f367-dfs-profile check` es de lectura y se ejecuta también antes de cada
`PREPARE52`. El qdrv publica `target52_present`, `target52_active`,
`target52_dfs`, `target52_radar` y `profile_publish_allowed`. Los rechazos del
handler emiten `OMF367_CONTROL_REJECT reason=... error=...` antes del ABORT de
contención. Las condiciones que admiten PREPARE no cambian.

El subioctl regulatorio14 no es `IEEE80211_PARAM_MARKDFS`: este último cambia
`IEEE80211_FEXT_MARKDFS`, una opción de comportamiento/test histórica. Tampoco
es CAC_DONE, OCAC_DONE, fast-CAC o una inyección radar. F367 mantiene anulados
esos atajos; esta revisión no los invoca.

## Contratos y comprobaciones

Los structs y constantes del helper se extraen de los headers compartidos
OEM; no se inventa un layout. El build ARC comprueba: `iwreq`32 bytes,
`iw_point.length` offset20, `flags` offset22, entrada canal empaquetada7 bytes,
tabla1792 bytes. El ELF es ARC32 little endian, intérprete
`/lib/ld-uClibc.so.0`, dependencia única `libc.so.0`.

Prueba afectada:
`outputs/preflight/f367r5-regulatory-route-20260922T174157Z/result.json`.
Pasan21 comprobaciones y tres recorridos del helper real/common parser hasta
PREPARE. Ejecutan el productor y dispatcher OEM, lookup/getters reales,
`param_attr_store`, `sysfs_streq` y el handler qdrv. Se sustituyen transporte
socket/escritura, copia de usuario, claim y la primitiva TX de hardware. El
siguiente gate CAC se detiene expresamente en el fixture; no se afirma CAC
físico. Se comprueban rechazo original, publicación única, región incorrecta,
canal inactivo, error ioctl, readback alterado, NOP y conservación del deadline.

Componentes cualificados sin repetir bancos anteriores:
`outputs/kernel-port/f367r5-qualified-20260922T174654Z/result.json`.
Dos builds de qdrv/helper idénticos;41 módulos y1.979 imports resueltos.
El helper mide9.556 bytes. Kernel/DT, Ethernet, proveedor GPL, engine F338,
supervisor y lifetime F355 se conservan. Keeper/stage siguen siendo R3; sólo
control/common reciben la comprobación y los campos nuevos.

Los archivos/hash de peer, headers, qdrv, helper, tests y pruebas reutilizadas
están ligados en los JSON de fuentes/componentes y en el manifest de imagen.
La cuarentena local conservadora1800s, CAC70s, NOP1800s, sesión90min y HEALTH5s
siguen intactos. La clasificación no autoriza TX DFS antes de CAC.

La validación física de R5, CAC, cliente y NOP corresponde a root y permanece
pendiente hasta su evidencia. Esta revisión no declara DFS100 ni release PASS.
