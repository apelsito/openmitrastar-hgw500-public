# OpenMitraStar F239 DFS Observability

F239 layers a read-only DFS/CAC/regulatory surface over hardened F237.

It exposes the current channel and bandwidth, region code, 802.11h state,
driver CAC status, DFS switch state, CSA count, channel availability and raw EU
classification. Values are explicitly labelled as driver readbacks rather than
regulatory certification.

- Policy: fail-closed.
- DFS writes: none.
- Certified: false.
- Hardware validation: `NOT_RUN`.

## Artifact

- Bytes: `5218304`
- SHA-256: `780562d937e3b8cb3a02dfe931cb9e1259570e21068ad9399ded0ec9a2feaea5`
- Full-slot SHA-256: `a785b1e1e5479d9e6f17c6aa6a10bfeeadf5e37774253e335bf2630d965969db`
- Rootfs SHA-256: `3866978bdc01bb23443e816bcf1ebaea5f0135458046787e1f19c7178a065ba2`

F239 is an offline observability experiment and is not flash-eligible.
