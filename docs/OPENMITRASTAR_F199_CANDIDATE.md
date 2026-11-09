# OpenMitraStar F199 Transaction V2

Fecha: 2026-09-01

F199 endurece la configuracion de radios sin modificar kernel, modulos,
firmware RF, DMA, colas, bridge, paquetes ni almacenamiento.

## Artefacto

- Bytes: `5,124,096`.
- SHA-256: `b61a1c6f10a1ffc767c28566ad5f948cd57d75c8d0660d648c9bfff5f8c1c7bc`.
- CRC32 candidato: `547872bc`.
- SHA-256 slot completo: `cad64498be26de8aa193121860d2ae0cdeb2af100d9ae2fffa03b510bb2d00b0`.
- CRC32 slot completo: `6e1e12fe`.
- Kernel LZMA: `ec029c052c3374d68e3e15c03353b487c12e12c3c431b6398b301877ef8f1d7c`.
- Validacion fisica: `NOT_RUN`.

## Transaccion V2

- lock exclusivo con recuperacion de lock abandonado;
- propietario derivado de sesion y direccion cliente;
- identificador aleatorio de 256 bits;
- expiracion limitada a 30-1800 segundos;
- snapshots antes/despues;
- apply y rollback con verificacion de lectura;
- errores de rollback propagados como `recovery-required`;
- una nueva etapa no puede destruir un rollback disponible;
- recuperacion del estado de transaccion mediante `GET /api/v1/config/status`.

La aplicacion material sigue desactivada por defecto. F199 es un candidato
offline y no esta autorizado para flash.

## Evidencia

- Tests Foundation/API/transaccion: `18/18 PASS`.
- Apply material y rollback simulados: PASS.
- ID incorrecto, sesion distinta, expiracion, lock y fallo de rollback: PASS.
- Dos builds consecutivos byte-identicos.
- `SHA256SUMS`, Bootbase y slot-fit: PASS.
