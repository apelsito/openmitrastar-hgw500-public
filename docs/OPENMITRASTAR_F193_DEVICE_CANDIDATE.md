# OpenMitraStar F193 Device Candidate

Fecha: 2026-09-01

## Estado

F193 es una imagen privada y vinculada exclusivamente al dispositivo local
`hgw500bna-qcv2-a2-primary`. No es un firmware redistribuible y no se ha
flasheado.

## Artefacto Privado

- Ubicacion: `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f193-device-bound/`
- Bytes: `5,115,904`.
- SHA-256: `d47e2a9a4631520ec9e2bcda9bb108c9d28c1800a986905c3d0b770abdc956d6`.
- CRC32 candidato: `ac0db9bd`.
- CRC32 slot completo: `22c32219`.
- Fingerprint SSH esperado: `SHA256:XdJ+6V/47WKwN1fy0WXU9D9IPPHE3dNT/jBhq92NEfM`.

## Modelo De Identidad

- La plantilla generica 2.2 no contiene claves privadas.
- La clave Ed25519 se genera una vez fuera del workspace.
- El firmware privado contiene exclusivamente la identidad de esta unidad.
- Dropbear valida la clave antes de arrancar y publica solo el fingerprint.
- No se escribe `mtd5` ni se depende de `/persist`.
- Reutilizar esta imagen en otra unidad duplicaria identidad y esta prohibido.

## Evidencia

- Dropbear 2026.94 nativo abre la antigua clave y la nueva clave generada.
- Clave generada: 83 bytes, formato Dropbear Ed25519 valido.
- ACL local: solo usuario propietario y SYSTEM.
- Fingerprint extraido del SquashFS coincide con la identidad provisionada.
- Dos builds con la misma identidad producen el mismo firmware SHA-256.
- Temporales con material privado eliminados despues de cada build.
- Hardware: NOT_RUN.

## Gate Pendiente

Antes de promover F193 debe probarse recovery mtd3 y prepararse un gate UART que
acepte exactamente el fingerprint anterior como la unica rotacion autorizada.

