# OpenMitraStar F207 Storage Read-Only Probe

Fecha: 2026-09-01

F207 integra la Foundation F205 con un split seguro dentro de la particion
fisica `mtd4/linux_live`:

- kernel y cabecera: `0x7e0000 + 0x180000`;
- `rootfs_live`: `0x960000 + 0x460000`;
- `lyoko_store`: `0xdc0000 + 0x1c0000`.

## Artefacto

- Bytes: `5,144,576`.
- SHA-256: `82234ff4812fbf3a6b1537712acd2500bb8953cde1c2b317b920a571aaa5216f`.
- Kernel LZMA: `35960c60607226fc2f58fbff271362221eac7b0e666c9e73b9cfee5a4de23d9e`.
- DTB: `7063f6b1f7b0180226c0d0fc6fd0ecd2659e18463664d42dd2a88726a2e80d81`.
- Rootfs headroom: `1,015,808` bytes.
- Validacion fisica: `NOT_RUN`.

## Seguridad

- `lyoko_store` es `mtd-rom`, no se monta ni formatea.
- Los 28 eraseblocks reservados permanecen completamente `0xFF`.
- El candidato termina antes del comienzo del store.
- El probe SPI lee JEDEC/status y no registra MTD ni contiene erase/write.
- `mtd0`, `mtd1`, `mtd2`, `mtd3` y `mtd5` permanecen fuera del cambio.

F207 es reproducible y no esta autorizado para flash.
