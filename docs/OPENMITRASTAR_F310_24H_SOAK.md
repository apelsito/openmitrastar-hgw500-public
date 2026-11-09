# OpenMitraStar F310 24-Hour Soak

Date: 2026-09-04

## Contract

The runner is restricted to the exact F310 firmware and a 24-hour target:

- runtime: `lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device`;
- candidate SHA-256: `df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330`;
- sequential real-client traffic through AELITA on 2.4 GHz and 5 GHz;
- SSH v2 with pinned router and AELITA host keys;
- shared physical lock with the post-promotion gates;
- no flash, MTD write or persistent configuration write.

The runner preserves F306's resumable evidence lineage but rejects any target
other than exactly 86,400 active seconds. A continuation imports only complete,
contiguous PASS cycles and never edits the source evidence directory.

## Files

```text
tools/f310_soak_runner.py
tools/f310_soak_consolidate.py
tools/test_f310_soak_runner.py
tools/test_f310_soak_consolidate.py
```

## Offline Preflight

```powershell
python tools\f310_soak_runner.py `
  --output-dir outputs\preflight\f310-soak-24h
```

## Future 24-Hour Run

```powershell
python tools\f310_soak_runner.py --execute `
  --ack OPENMITRASTAR_F310_SEQUENTIAL_DUAL_RADIO_SOAK `
  --duration-hours 24 `
  --output-dir outputs\soak\f310-24h
```

Resume the same evidence directory with `--resume`. To continue from an
immutable prior F310 evidence directory, use `--seed-from` and a new output
directory.

## Offline Consolidation

```powershell
python tools\f310_soak_consolidate.py `
  --source-dir outputs\soak\f310-24h `
  --output-dir outputs\soak\f310-24h-summary
```

The consolidator never opens SSH or executes remote commands. It accepts only
the F310 schemas, exact firmware identity, exact candidate hash and 24-hour
target, deduplicates identical inherited cycles and fails closed on lineage or
duration inconsistencies.

## Offline Result

- Runner dry-run: PASS with `target_duration_seconds=86400`.
- AELITA host-key mode: `pinned`.
- Candidate match: PASS for SHA-256
  `df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330`.
- Dry-run plan:
  `outputs/preflight/f310-soak-24h-20260904T205100Z/plan.json`.
- No soak was started and no hardware action was performed.
