# OpenMitraStar F293 sequential dual-radio soak

Date: 2026-09-04

`tools/run_f293_sequential_dual_radio_soak.py` prepares a resumable prolonged
traffic campaign for the F293 datapath candidate using the one currently
available AELITA Wi-Fi client.

## Cycle

Every cycle performs:

1. 32 MiB downstream and upstream on 2.4 GHz;
2. a bounded 2.4 GHz association soak;
3. restoration to `MOVISTAR-WIFI6-A348`;
4. 32 MiB downstream and upstream on 5 GHz;
5. a bounded 5 GHz association soak;
6. another restoration to the original Wi-Fi;
7. router memory, uptime, radio lifecycle and fatal-marker snapshot.

Each completed cycle is written before the next begins. A failed transfer,
disconnect, router-health failure, fatal marker, low-memory condition or lost
SSH aborts the campaign. The controller speed server is stopped in all exits.

`--resume` continues an interrupted campaign only when the existing plan uses
the same candidate, duration and per-band soak. Cycle directories must be
contiguous and every recovered `cycle.json` must be PASS. Without `--resume`,
the runner refuses to overwrite a non-empty evidence directory.

## Boundary

- Default duration: 6 hours.
- Maximum accepted duration: 24 hours.
- Candidate pinned to F293 SHA-256
  `76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37`.
- No router configuration or MTD write.
- Dry-run: PASS; router and AELITA SSH available.
- Physical execution: NOT RUN.

This is a valuable prolonged sequential gate, but it is not the final
simultaneous dual-radio certification. A second independent Wi-Fi client is
still required to prove concurrent 2.4/5 GHz contention.

Evidence:

- `outputs/preflight/f293-sequential-soak-resumable-20260904T023221Z/plan.json`
- `tools/test_run_f293_sequential_dual_radio_soak.py`
