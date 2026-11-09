# F361: journal de arranque y guardado explícito

Imagen offline PASS; ocho casos específicos de integración pasan y el lector
ARC fue validado por root sobre el journal real (slot0/seq1/586B/hash073747...).
No hardware ejecutado por el agente de construcción. Kernel/config/DT y
supervisor son byteidénticos a F358 (#358).

Arranque: S30 lee el journal por MTD ROM con el core F342 en un snapshot RAM.
Vacío, corrupto o settings inválidos conservan el fallback; nunca se formatea,
borra ni guarda automáticamente. Se proyectan 22 settings admitidos por el
validador real y se verifica el normalizador exacto antes de seleccionarlos.
CONFIG_SCHEMA sirve sólo como versión. ORIGIN_MTD5_IMPORTED, RADIO5G_SSID y
RADIO5G_CONFIG_SOURCE almacenados se ignoran: el origen protegido se vuelve a
obtener por S25. No se confía en esos valores del journal.

S31 carga el proveedor ya probado con allow_hw=1 allow_program=1; su init no
hace MMIO ni comandos SPI. El guardado se ejecuta sólo al POST autenticado
config/store action=commit, mediante F351/F356, seguido de LOAD y comparación
SHA/tamaño. No ARM, CEASE ni reboot automáticos. El error se devuelve sin
reintentos y no se promete recuperación automática ante un fallo de bus.

Se usan únicamente utilidades presentes en F358: no mktemp, rmdir, cmp ni tr.
El helper C size-text valida ASCII/tamaño sin MTD; el lock se limpia con rm y
se comprueba que desaparezca. La ruta API conserva autenticación/confirmación,
corrige su guard de esquema y publica las limitaciones.

Límites: esto conserva la configuración gestionada, no todos los parámetros
live del radio. config/commit de transacciones radio sigue siendo volatile.
No persiste PSK, el SSID 5GHz derivado, bandas/anchos ni ajustes avanzados que
no formen parte de los22settings. Los perfiles fijos del normalizador/runtime
no se amplían. Rollback de configuración por API no se implementa y se rechaza.

La instalación debe conservar el store F360 completo: SHAa7620cf8f6a8a8764e082e524c1968915e0ad4b6810be939522deed67b0302a8,
CRC31bf4416, antes y después del boot. El slot de la imagen incluye ese estado
para su CRC esperado; no asume storeFF. Fallback F358+MISMOstore: CRC3e8db0dc.

Resultado `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f361-fullimage-20260921T191701Z\result.json`
SHA-256 `62d320fcf785fbb8a444fe5a6d14862857cf5f4e4e920167076844493050aad0`.

Imagen `/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f361-f358-config-persistence-device-bound\openmitrastar-linux510-f361-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
5378048B SHA`0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af`.

Manifest SHA`62e07bf5c1453a293c0f6717b882fc65ef88c4c57e0f1919e41a01d3c19357dd`; versión `lyoko-foundation-6.9.9-f361-config-persistence-device`, build `bb3ff4b022137a58`.
PrefijoCRC`4cb7f99e`, slotconjournalCRC`edca3610`.
