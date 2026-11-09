# HGW500: independent workstation handoff â€” 23 October 2026

## Start here

Clone this repository to `C:/Users/<user>/Desktop/MitraStar` for documentation,
source inspection and local tests. Historical scripts contain owner-local paths;
inspect their CLI/path constants before using another location. Never execute a
historical builder merely because it is included. Run only the selected version
with its exact inputs. The root workspace was not a Git repository; this is a
new private publication preserving the original local working trees.

Read `AGENTS.md`, `docs/AGENT_CURRENT_MISSION.md`,
`docs/OPENMITRASTAR_LINUX73_TLS_WIFI_20261022.md`,
`docs/OPENMITRASTAR_VERSIONES_TAMANOS_20261023.md` and
`docs/OPENMITRASTAR_DOOM_XZWASM_20261023.md`. Later records in those documents
supersede earlier checkpoints. Old F314-F319 objective audit is historical.

## Latest physical checkpoint — R2 update at 00:55 UTC, 23 October 2026

This update supersedes the earlier RAM-only orientation below. Current mission
records `lyoko-linux73-2g-doom-open-r2` programmed to physical mtd4 prefix:
6,062,800 bytes, SHA256
`500b617b659f3b2c8ed075ed493f721ad112ef2fc6245df9422ec9462feab2b9`.
Readback byte comparison and boot from readback passed, with exact PID1,
open 2.4 GHz AP **wanna play Doom**, automatic DHCP/HTTPS, LYOKO login at `/`
and Doom at `/Doom`. Administrative API without session returns403.

This publication only reads existing local files and transfers the exact image
privately to Aelita; it performs no hardware action or new build. Read
`docs/OPENMITRASTAR_DOOM_OPEN_R2_20261023.md` and the exact release/source-input
manifests under `outputs/releases/`. Source continuity fixes3,010 kernel input
entries from1,452 compiler dependency records and202 public root entries,
with no unresolved referenced sources. It is the existing local build tree,
not a portable clean rebuild proof. Credentials/calibration remain direct-only.

R2 cold power-cycle after programming is UNRUN; the prior image had one normal
coldboot observation. 5GHz, persistent editable configuration, soak/repeatability
and physical rollback remain pending. Do not wake/message the separate5GHz chat
or perform more device operations without new owner indication.

## Earlier RAM evidence — historical



* Accepted diagnostic RAM image: `radioeth73-events-RAM-ONLY.ras.bin`;
  6,980,384 bytes; SHA256
  `9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e`.
* Linux `7.3.0-openmitrastar-radio73-v1`, SSH key authentication;
  each Ethernet port separately passed TLS1.2/1.3 GET/POST 65,536 bytes.
* 2.4 GHz WPA2 association, AUTH/ASSOC/AUTHORIZED and bidirectional TLS traffic
  passed in recorded client campaigns. It does not prove a final release soak.
* LYOKO HTTPS login/session/logout and Doom desktop/touch/movement/fire/audio
  passed. Firmware persistence and complete image fit remain pending.
* Quantenna R26 source/modules compile proof is delivered in its private driver
  repository. 5 GHz RF/client/traffic and physical load remain unaccepted.
* No flash, reboot, radio, UART or device access occurred for this publication.

## Obtain the current maintained driver and toolchain

Windows may keep the main repository; Linux compilation needs a filesystem
sensitive to case, with no spaces in the Linux paths. Install/verify WSL2 Linux
or a real Linux build host, then clone inside its home directory.

```bash
gh repo clone apelsito/openmitrastar-hgw500-quantenna-5ghz-driver ~/openmitrastar-drivers -- --branch port/linux-7.3 --recurse-submodules
cd ~/openmitrastar-drivers
git submodule status --recursive
cat src/CURRENT
```

Publication-time remote commit: `40ec2e98b63377282acb1613b57353547f9923d1`;
`src/CURRENT` selected `linux-7.3-r26`. Its submodules pin Linux
`c03c1a14507dfaf8b856c2608f9ac216021fc222`, Realtek/board
`a924ed874ba925c1b9fb2e42cbb2ef2e59d74e5d`, and Quantenna GPL
`116a8b0cd80d75e6bc3b8d21646f9c7fa4ce1cf9`. Verify after cloning. The driver
tree here was read only; another agent's uncommitted source work was not touched.

The full toolchain is already a private GitHub prerelease asset. API verification
at publication confirmed uploaded state, size and SHA256 digest.

```bash
mkdir -p ~/openmitrastar-deps
gh release download aelita-arc-toolchain-15.2.0-10504-20261022 --repo apelsito/openmitrastar-hgw500-quantenna-5ghz-driver --dir ~/openmitrastar-deps
cd ~/openmitrastar-deps
printf '%s  %s\n' cb37498e50328183732b84d93cba670076888f66868c3c7385119f1e8e45825a arc-snps-linux-uclibc-gcc15.2.0-10504-aelita.tar.xz | sha256sum -c -
tar -xJf arc-snps-linux-uclibc-gcc15.2.0-10504-aelita.tar.xz
```

Toolchain archive: 59,864,216 bytes; directory `arc-toolchain`;
GCC SHA256 `3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263`.
Do not substitute the similarly named stock 2026.03 archive for this qualified
compiler/sysroot. Read driver `docs/AELITA_END_TO_END_SANITIZED_20261022.md`,
`docs/HANDOFF_LINUX73_R26.md`, `docs/AELITA_BUILD_ACCEPTANCE_20261022.md` and
`docs/AELITA_TOOLCHAIN.md`. Its `scripts/aelita_rebuild.sh` builds kernel/base,
Quantenna and Ethernet with real fresh `Module.symvers`; it does not install.

## Aelita needs these workstation capabilities

1. Git and GitHub CLI authenticated with read access to all three private HGW
   repositories; no token belongs in Git or the project directory.
2. Python3.12+ and a project venv. Hardware tooling imports Paramiko3.5.1,
   pyserial3.5, ymodem1.5.3, cryptography49.0.0 and psutil7.2.2 in the current
   workspace. Installing these libraries does not authorize device access.
3. PowerShell7, OpenSSH client, and Linux build tools: make, host GCC/binutils,
   bc, bison, flex, libssl-dev, libelf-dev, pkg-config, git, tar, xz, cpio,
   squashfs-tools, device-tree compiler and patch. Use the pinned ARC compiler.
4. Node/npm for LYOKO UI source. `work/lyoko-web-next/package-lock.json` pins
   dependencies; run `npm ci`, then its documented `npm test`/`npm run build`
   only for local UI development. This does not change the router.
5. Linux build disk space: source trees, two independent builds and toolchain
   need tens of GiB. The existing host's `/home/rea/...` trees are not in Git.

`python handoff/inspect_workstation.py` inventories local commands/modules
without installing, connecting, reading credentials or changing the machine.

## Download complete Doom assets independently

The complete local delivery is now a private prerelease:
`aelita-doom-complete-20261023-v3` in this repository. It contains the compact
runtime plus separate preserved original DOS distribution, sources, licenses
and provenance. No unit key, calibration or router image is included.

```bash
mkdir -p ~/openmitrastar-doom
gh release download aelita-doom-complete-20261023-v3 --repo apelsito/openmitrastar-hgw500 --dir ~/openmitrastar-doom
cd ~/openmitrastar-doom
printf '%s  %s\n' 2bd43ad86b779daeb375a3173fdbd879314e25581e0b1bcef8903f5bead597a9 doom-xz-full-preserved-delivery-20261023-v3.tar.gz | sha256sum -c -
tar -xzf doom-xz-full-preserved-delivery-20261023-v3.tar.gz
```

Archive: 5,303,440 bytes. The engine/WAD are unchanged; exact source/binary
rebuild correspondence remains unproven. This is a packaging delivery, no
installation or complete firmware fit. Preserve `source-and-original/`
with a firmware release. API upload digest and a fresh local archive decode
were checked. Browser/physical evidence remains the individually dated docs.

## Direct private transfer remains necessary for exact unit reproduction

The following material cannot be inferred from code and is deliberately absent
from GitHub even though the repositories are private:

* Owner store `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary`
  includes exact accepted RAM and prior F367r9 firmware, TLS/SSH/WPA material,
  pinned host identity, protected-partition evidence and rollback inputs.
  Preserve provenance, hashes and restricted permissions during a direct
  authenticated encrypted transfer. No raw device-private content is logged.
* `/workspace/user-home/.ssh/id_ed25519` is the current owner access key referenced
  by scripts. Aelita needs authorized SSH access and verified host pins.
  Prefer its own owner key added through a separately authorized router action,
  or explicit secure migration of the existing key. Never place it in Git.
* REA-Linux `/home/rea/openmitrastar-linux73-20261022T135100Z/` includes accepted
  kernel/userland build context, exact libc/sysroot, service builds, private
  initramfs, firmware carriers and runtime reference. `work/kernel-port/`
  recipes often depend on these exact paths. Git contains recipes and source
  deltas, not all binaries or the Linux filesystem. A portable sanitized fresh
  module build can run via the driver repository without those owner inputs;
  an exact full unit image still needs them or verified rebuilds/provisioning.
* `outputs/` contains immutable physical transcripts, raw observations and
  candidate/acceptance receipts; it is not bulk published because captures can
  contain identities and sensitive output. Current summaries are in docs.
* Flash/readback and original OEM images/dumps remain direct-only. Do not
  recreate a physical partition from logical `mtd6/rootfs_live`.

Exact file/size/hash transfer inventory is in `PRIVATE_INPUT_MANIFEST.json`.
Acquisition and clone completion on Aelita are separate from this publication.

## Stop boundaries for the receiving Codex

Documentation and cloning do not authorize hardware access. Do not open COM3/4,
start TFTP, change radio/runtime, reboot, power-cycle, mutate bootenv or flash
for an inventory check. Start with authorized pinned read-only SSH when needed.
Only physical `mtd4/linux_live` is a normal write candidate, with exact artifact,
Bootbase, readback, rollback and explicit action authority. OEM/protected
`mtd0,1,2,3,5` remain preserved. `mtd3/linux_safety` rollback requires physical
acceptance and must not be claimed merely from preserved bytes.
