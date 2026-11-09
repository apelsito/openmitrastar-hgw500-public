# OpenMitraStar F316 active radar candidate

Date: 2026-09-05

F316 promotes the reconstructed QT4 provider from shadow-only observation to an
active-capable Linux 5.10 DFS/CAC implementation. It remains an offline physical
candidate; no claim of regulatory or hardware correctness is made until the
complete physical campaign passes.

## Artifact

- Candidate bytes: `5,283,840`
- Candidate SHA-256:
  `79418b72b5511974852d707bd5d181017acb168ab2a370450e8f3f6fd04194df`
- Full-slot CRC32: `4fbca31f`
- Full-slot SHA-256:
  `f3e3f9ccc820eb22a78e73f962606e98ceccb6b50e975b634673685249b8da31`
- Kernel SHA-256:
  `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`
- Native provider: `qtn_radar_native.ko`, 57,720 bytes, SHA-256
  `92e9a21e528b28fa4a0634f19fa73552f220f4cbd5646856392021a0cd565481`.

## Offline result

The provider and external-radar qdrv link contract pass. The portable
classifier covers preprocessing, SSR/ITLV, LSR/chirp, candidate selection and
postfiltering, while unresolved weather and physical-vector branches remain
fail-closed. Callback authority is disabled in the standalone offline artifact;
the firmware candidate enables the provider for the future guarded campaign.

The required physical proof is: non-DFS boot, dual-radio regression, standard
and weather CAC timing, real radar callback, evacuation, 1,800-second NOP and
rollback. Until then installed F314 remains authoritative.

