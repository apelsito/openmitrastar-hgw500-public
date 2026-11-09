# OpenMitraStar HGW500 handoff

## Purpose and evidence boundary

OpenMitraStar is my firmware and reverse-engineering project for the MitraStar HGW-500BNA-QCv2 A2. I work across the boot chain, Linux, host drivers, radio microfirmware and HTTPS management. The goal is to understand the original system and bring a maintainable Linux 7.3 stack to the hardware, while preserving recovery and per-unit data.

Complete independent reset-to-DDR boot, missing OEM and radio semantics, QDRV shutdown, candidate-specific channel/width transitions, calibrated RF/DFS and prolonged load. Reconcile any new source publication against the frozen release maps before calling it a reproducible current image.

## Source and evidence entry points

- `docs/AGENT_CURRENT_MISSION.md`
- `handoff/AELITA_HANDOFF.md`
- `handoff/SOURCE_MANIFEST.json`
- `docs/STATUS.md`
- `docs/RELEASE.md`
- `build/releases/api-v2-r3/SOURCE_MAP_RELEASE.json`
- `sources/uboot-hgw500/`
- `tools/`

These paths are relative to this checkout. Some are preserved local additions
ahead of a remote branch; use the source/preservation manifests and the notes
below to establish which files a given clone actually contains. Do not guess
missing private inputs or replace an original with a similar-looking download.

## Continue from another machine

1. Clone the correct repository and branch from the [repository map](REPOSITORY_MAP.md).
   Initialize submodules only where the component actually declares them.
2. Read `docs/PUBLIC_SNAPSHOT.md`, the preservation/source manifest and the detailed
   [reference notes](REFERENCE_NOTES.md). Resolve baseline and target kernel first.
3. Verify the input hashes, analysis subject and compiler/processor definition.
   Keep preserved exports separate from any new analysis project.
4. Run the README's offline integrity checks. Missing context, original inputs
   or submodules are unmet dependencies, not permission to fabricate a passing result.
5. Put new build/analysis outputs in a fresh ignored `out/` or an external build
   directory. Record source hash, tool version, target ABI and the exact checks run.
6. Report source recovery, native compilation, byte comparison and any physical
   result separately. Installation/reboot/traffic tests need their own authority
   and exact-image recovery plan in the integration project.

## Handoff deliverables

- The selected source and immutable input hashes, with licences/provenance.
- A reproducible command or an explicit list of unresolved external inputs.
- New output locations and result receipts, leaving older evidence unchanged.
- A short explanation of what changed, which checks passed and what remains untested.
- A reviewed export containing no workstation paths, credentials, identity,
  client MACs, calibration or personalized image bodies.

The [firmware map](FIRMWARE_MAP.md) separates the OEM recovery, Core Boot R1 and
newer API v2 R3 integration. A historical acceptance does not transfer between them.

The root checkout verifier is `python handoff/verify_source_manifest.py`. The local integration checkout also has `tools/check_repository.py`; its CURRENT manifest is separate and must not be silently rebased onto an old remote snapshot.
