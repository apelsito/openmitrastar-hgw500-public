# OpenMitraStar F191 Candidate

Fecha: 2026-09-01

## Estado

F191 integra dos ramas independientes sobre la base F188:

- kernel F189 con multicast IPv4 e IGMP snooping compilados;
- rootfs F190 sin clave privada SSH embebida.

Es un candidato offline reproducible. El router fisico continua en F170.

## Artefacto

- Archivo: `openmitrastar-linux510-q3-persistent-f191-network-security-from-f189-f190-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `5,115,904`.
- SHA-256: `ae3aff7ff11baaea244a616b344872de36e1774d60f23ad34c9f2369fe9d9e05`.
- CRC32 candidato: `7b2000ab`.
- CRC32 slot completo: `bd8f65e1`.
- SHA-256 slot completo: `0cd355b54d7be84ff53384b634c4903e8d658f7bf2c1e9abc8da776440ff438c`.

## Contratos Demostrados Offline

- `CONFIG_IP_MULTICAST=y`.
- `CONFIG_BRIDGE_IGMP_SNOOPING=y`.
- `CONFIG_VLAN_8021Q=y`.
- NAPI EMAC conservado en 128.
- `IP_MROUTE`, GVRP y MVRP desactivados.
- `multicast_snooping=0` forzado hasta certificacion fisica.
- Script de politica multicast presente en el SquashFS.
- Clave privada Dropbear embebida ausente del SquashFS.
- 25 tests PASS y build repetida byte-identica.

## Hold De Release

F191 no es aun release porque:

1. la identidad SSH es efimera hasta certificar `lyoko_store`;
2. multicast/IGMP no tiene trafico fisico probado;
3. NAPI=128 sigue pendiente de la campana comparativa real;
4. recovery mtd3 necesita una prueba fisica reciente.

