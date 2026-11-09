# OpenMitraStar F252 configuration store candidate

F252 adds a disabled-by-default transactional configuration journal for the
future JFFS2 `lyoko_store` mount.

- Two alternating slots with SHA-256 metadata and atomic current-pointer swap.
- Validated non-secret radio settings only.
- `commit`, `load`, `rollback` and non-failing `status` operations.
- Requires `/persist` to be mounted read-write as JFFS2.
- No boot-time restore, API mutation or physical store write is enabled.

Artifact: `5242880` bytes, SHA-256
`77efef238561251a94a87c2a788975cd51e5f82ddb25336a164df5cdd1da43a4`.
Rootfs SHA-256: `1f3506ae8aa06fc7aad8561ac673f0f6dceb64442a2ce280f039b67a32d09f77`.
Hardware status: `NOT_RUN`.
