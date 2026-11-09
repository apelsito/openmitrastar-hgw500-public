# OpenMitraStar F198 Device Candidate

Fecha: 2026-09-01

F198 es la variante privada por dispositivo de F197. Conserva el contrato
comun de radios e integra la identidad SSH unica de
`hgw500bna-qcv2-a2-primary`. No debe redistribuirse.

## Artefacto Privado

- Bytes: `5,120,000`.
- SHA-256: `731cb79756ea373a4cc3b4211fd9d167d8ab5284a55c3a19ce5ededf95034388`.
- CRC32 candidato: `ca918000`.
- SHA-256 slot completo: `12df577676d4af4f29eebfb25dd6df9c5ccec83aa9177b383fec5e11e5ef8b2f`.
- CRC32 slot completo: `98de81d3`.
- Fingerprint esperado: `SHA256:XdJ+6V/47WKwN1fy0WXU9D9IPPHE3dNT/jBhq92NEfM`.
- Validacion fisica: `NOT_RUN`.

El contrato de promocion apunta exclusivamente a `mtd4/linux_live`, protege
`mtd0`, `mtd1`, `mtd2`, `mtd3` y `mtd5`, y permanece
`BLOCKED_RECOVERY_UNPROVEN`. No se ha ejecutado flash, UART ni reboot.
