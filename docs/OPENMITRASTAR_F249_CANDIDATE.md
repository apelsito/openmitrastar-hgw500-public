# OpenMitraStar F249 integrated opkg candidate

F249 combines the exact F223 EMAC RX-ring-256 kernel with the exact F248
Foundation 5.0 rootfs.

- Bytes: `5242880`
- SHA-256: `3f6c5775abd93e6003c59fe425d6a8609c8fab5e1b9eca53f4975654e7f6618a`
- Kernel SHA-256: `30b71c86ce2585b1efce48870f04a69c481515cd1c6f90335dd7f25c5e1a8cd8`
- Rootfs SHA-256: `28ec3c6c78df99c2bd8e0c3bd80337b11731d23f77159ca3ffd2271728f46588`
- Full-slot SHA-256: `c8b15566501477db03e944fbf9ad7c789891fe909c8d2cc7a8ab78ac607be6bc`
- Hardware state: `NOT_RUN`
- Classification: integration hold, not authorized for flash.

F249 adds no changes beyond its two parents. F247 remains the frozen physical
candidate so package-compatibility work cannot contaminate the datapath trial.
