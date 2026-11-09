# OpenMitraStar F246 integrated candidate

F246 combines the exact F223 EMAC RX-ring-256 kernel with the exact F245
Foundation 4.9 rootfs.

## Artifact

- Bytes: `5238784`
- SHA-256: `8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12`
- Kernel SHA-256: `30b71c86ce2585b1efce48870f04a69c481515cd1c6f90335dd7f25c5e1a8cd8`
- Rootfs SHA-256: `653769991d82a8250cc9ac2f4ae3aac4a872b932c90ffbed0e28668929a20e24`
- Full-slot SHA-256: `ca5a30d69b95425fb834910e964745273e88ba4f5ce33c48b0c72964ed9abeac`
- Hardware state: `NOT_RUN`
- Classification: integration hold, not authorized for flash.

There are no additional kernel or rootfs changes beyond its two parents.
Promotion requires the F223 three-run physical 2.4 GHz campaign and the F245
package catalog/runtime gate, followed by dual-radio regression.
