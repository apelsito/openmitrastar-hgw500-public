# Linux 7.3: Realtek 2,4 GHz compilado; prueba física pendiente

Resultado contrastado el 22 de octubre de 2026. El kernel con PCIe Topaz y
18 módulos se ha compilado en dos salidas independientes con bytes idénticos.
Los imports de los módulos se resuelven y la revisión del ensamblador no
encuentra SWAPE, LLOCK o SCOND. Esto es aceptación offline, no Wi-Fi físico.

Referencia upstream: `c03c1a14507dfaf8b856c2608f9ac216021fc222`.
Kernel: `7.3.0-openmitrastar-radio73-v1`, 4980564 bytes,
SHA-256 `25c726d1d5d9a0ed617985dc974452233ced07c132687acafad167bf816bacd3`.

Módulo `rtl8192ee.ko`: 115764 bytes,
SHA-256 `a84f22941a5e7441df2896edd110027616bbb61da63b09203fe021474e464048`.
La pila incluye rtlwifi, rtl_pci, btcoexist, mac80211, cfg80211, firmware loader
y las dependencias criptográficas. Configuración efectiva: ARC750/MMU v2,
páginas de 8 KiB, UP, PREEMPT_NONE, MSI desactivado. La exigencia de base
regulatoria firmada permanece habilitada; no afirmar que el builder la desactivó.

Evidencia copiada y verificada:
`../outputs/rea/movistar-port-20261022T1327175411798Z/realtek-repo/kernel/radio2g-linux-7.3-v1/OFFLINE_RESULT.json`.
El manifiesto fuente de 76 archivos ha vuelto a verificarse localmente. Incluye
66 archivos de overlay Realtek y seis archivos de plataforma. La receta portable
ha pasado su plan de inputs; su reconstrucción completa todavía no se ejecutó.
La compilación independiente ya realizada es la prueba existente.

No se ha ejecutado esta build en el HGW. PCIe físico, carga de firmware,
registro de wiphy, modo AP, asociación WPA2 y tráfico de 2,4 GHz están pendientes.
Esta build tampoco incluye el driver Ethernet ni un initramfs integrado para
probar ambas funciones. SSH, radio de 5 GHz, persistencia y rollback mtd3 no
tienen aceptación Linux 7.3.

## Diferencia Ethernet detectada y variante local v3

La imagen Ethernet reset-v2 sí arrancó físicamente desde RAM, conservando el
release string `7.3.0-openmitrastar-eth73-v1`. La prueba anterior por eth0 recibió
2018/2018 ecos UDP de 384 bytes durante unos 218 segundos, a tasa limitada;
no prueba rendimiento máximo ni soak prolongado.

En la última captura física eth0 estaba bajado y eth1 estaba arriba con carrier,
en 192.168.1.91. eth1 recibe, pero TX vuelve a detenerse tras nueve completaciones
con estado DMA WaitEOT. El reset local consiguió stopped y permitió reapertura;
el bloqueo reapareció. UART fue liberada al finalizar esa captura. Este documento
no vuelve a observar ni modifica el dispositivo.

El original `emac_lib_init_mac` programa doce registros locales que reset-v2
dejaba heredados: jabber TX/RX, cuatro filtros, tres palabras de identidad de
las tramas pause, tiempo de pausa y dos umbrales TX. La nueva variante
`../work/kernel-port/linux-7.3-ethernet-macinit-v3/` incorpora esos valores antes
de habilitar TX/RX. Es una hipótesis para WaitEOT; la causa no está confirmada.

Pruebas v3 nuevas y separadas:

- Fixture ejecutada: 256 casos, 134400 checks, valores obtenidos del original,
  banco vecino conservado; tres mutaciones erróneas compiladas y rechazadas.
- Regresión reset/lifecycle: 28 casos, 48153 checks; cuarentena DMA preservada.
- Módulo completo compilado dos veces contra el contexto radio73: bytes idénticos,
  80 imports resueltos, sin SWAPE/LLOCK/SCOND. 26372 bytes,
  SHA-256 `528e1862dbbf391f33e62c5bd9a2dfe7325439aca23fdeaa01c364f96786bbf0`.

Evidencias nuevas bajo
`../outputs/rea/movistar-port-20261022T1327175411798Z/`:
`eth73-oem-macinit-fixture-v3-r1`, `eth73-macinit-reset-regression-v3-r1` y
`eth73-oem-mac-module-v3-r1`. El contexto original no se modificó: la build usa
una copia nueva y compara el ELF original con el copiado.

GO offline para integrar y preparar una imagen RAM nueva. NO-GO para afirmar
TX físico corregido, Wi-Fi funcional o release. Pendiente: diagnóstico de
registros/descriptor TX, initramfs con radioload explícito y firmware/regdb
correctos, imagen completa con DT privado preservado, contratos Bootbase,
arranque RAM y pruebas físicas. No hubo UART, reinicio, radio, flash ni bootenv
en la preparación v3.
