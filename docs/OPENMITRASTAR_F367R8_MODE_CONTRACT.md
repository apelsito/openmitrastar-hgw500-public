# F367r8 — token OEM de modo y lectura de CSA

R8 cambia exclusivamente `om-f367-control` y los metadatos/catálogos de la
imagen. Reutiliza todos los módulos, kernel/DT y helpers nativos de R7.

R7 pasó físicamente PREPARE52, con TX off confirmado, y después devolvió
`OMF367_ERROR reason=mode20`. La captura no contenía el errno de iwpriv porque
su salida estaba descartada. El `-EINVAL` se reproduce en el parser OEM;
no se atribuye retrospectivamente ese errno a la captura física.

El setter real `ieee80211_convert_mode` acepta `11ac` para el enum
`IEEE80211_MODE_11AC_VHT20PM` (11). Su getter presenta ese modo como `11ac20`,
pero esa etiqueta no es un argumento válido de escritura. R8 escribe `11ac`
y mantiene `11ac20` como readback. La ruta ifmedia SET/media-change conserva
la semántica `-ENETRESET`, aplica BW20 y publica PHY11 mediante el flujo OEM.
No se evita su comprobación de capacidades ni se altera calibración.

También se confirmó en código que el ioctl de canal para AP UP/RUN agenda
CSA y puede regresar antes del cambio. `ieee80211_finish_csa` actualiza el
canal y llama al backend posteriormente. Esto era una dependencia de código
del paso siguiente; R7 todavía no alcanzó físicamente ese ioctl.

El controlador emite una única escritura para modo, filtro20 y canal52.
Registra request/RC seguros mediante `OMF367_MODE_REQUEST`,
`OMF367_MODE_RESULT`, `OMF367_FILTER_RESULT` y `OMF367_CHANNEL_RESULT`.
Después observa únicamente la snapshot real, con un deadline monotónico
de5.000ms fijado antes de solicitar el canal. No reemite comandos ni renueva
los deadlines del supervisor, CAC o NOP. Usa las utilidades ya existentes.

El predicado final mantiene canal52, filtro20, PHY11, ES y DOTH/TPC activos.
Los fallos latched se comprueban antes del PASS. `OMF367_CONTEXT_READBACK`
separa confirmación, timeout y fallo, con tiempo transcurrido y campos
numéricos. La observación no acredita CAC ni permite TX DFS antes de él.

Prueba afectada:
`outputs/preflight/f367r8-mode-contract-20260922T211028Z/result.json`.
Pasan11 comprobaciones con parser/setmode/ifmedia SET/media-change/BW/getter
OEM y parsers de los argumentos siguientes. El transporte MuC y las
capacidades del fixture son fronteras explícitas; no se afirma ejecución RF.
El contrato de programación/completado CSA queda ligado a las fuentes.

Cinco casos ejecutan el helper real: confirmación demorada, timeout,
confirmación tardía, contexto52/20 con fallo latched y rechazo del modo.
Todos conservan una única escritura por comando; fallo y timeout nunca
publican `OMF367_ENTER_DFS`. La fuente probada del controlador tiene SHA256
`3306b43a514e02a5c41b81eeeaa06101e1316f29ff6b160c6973c1b81afbcaa8`.

No se recompilaron módulos ni se repitieron los bancos de relojes, regulación
o supervisor. No hubo hardware desde este subagente. Quedan pendientes la
validación física R8, CAC/NOP y tráfico con cliente; no se declara release PASS.
