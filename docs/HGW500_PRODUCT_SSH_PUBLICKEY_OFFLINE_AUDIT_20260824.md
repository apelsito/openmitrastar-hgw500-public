# HGW-500BNA-QCv2 product SSH publickey offline audit

Date: 2026-08-24

Scope: offline-only review of the Linux 5.10 product rootfs SSH publickey
rejection. No router access, RAM write, MTD write, flash, reboot, or binary
artifact edit was performed.

## Evidence

- Current W4 product SquashFS
  `work/mission-state/w4-rootfs-product/build/openmitrastar-product-rootfs-v1.squashfs`
  contains `usr/share/openmitrastar/keys/factory-authorized_keys` with
  fingerprint `SHA256:6imOdRFcQvZy6rZcUVK7SBjm6QCq+J/1GR7FNQNntjA`.
- Local `/workspace/user-home\.ssh\id_ed25519.pub` has
  `SHA256:pBtUFbtw8ud9gGKqhXj3kBz2rhNv6syDjb7lvGwSoBc`.
- Current F5 gzipinit initramfs contains
  `SHA256:pBtUFbtw8ud9gGKqhXj3kBz2rhNv6syDjb7lvGwSoBc`, but its
  `source_rootfs.sha256` points at an older W4 hash than the current W4
  `build/manifest.json`.
- W4 `/etc/passwd` sets root home to `/run/openmitrastar/admin` and shell to
  `/bin/ash`; `/etc/shells` includes `/bin/ash`.
- W4 `om-ssh` writes `/run/openmitrastar/admin/.ssh/authorized_keys` from the
  factory key unless `/persist/openmitrastar/ssh/revoke-factory-key` exists,
  then starts Dropbear with `-D "$ssh_dir"`.
- Dropbear 2026.94 resolves `-D` as the directory containing
  `authorized_keys`, validates shell membership, and does not reject publickey
  auth solely because the root password field is locked.

## Offline conclusion

The current local artifacts are not one coherent SSH identity chain. W4's
current SquashFS/manifest carries the old `6imOd...` bootstrap key while F5
gzipinit and the Windows admin key carry `pBtUF...`. The live device only
reporting `product-rootfs-v1` is ambiguous and cannot distinguish these builds.
That mismatch is sufficient to explain a root publickey rejection: the server
can be offering a product image whose authorized key set does not contain the
client key being tried.

Secondary offline possibilities remain:

- `/persist/openmitrastar/ssh/revoke-factory-key` exists on the device.
- `/persist/openmitrastar/ssh/authorized_keys` replaced the intended key set.
- Runtime ownership or mode of `/run/openmitrastar/admin/.ssh/authorized_keys`
  differs from the boot script contract.

Those cannot be proven without read-only runtime evidence, so they are not
claimed as current facts.

## Minimal offline fix

- Future W4 builds now write a non-secret `OPENMITRASTAR_BUILD_ID` and
  `OPENMITRASTAR_BOOTSTRAP_AUTHORIZED_KEY_FINGERPRINT` into
  `/etc/openmitrastar/release`.
- `getinfo` now exposes `build_id` and
  `bootstrap_authorized_key_fingerprint`, so a live HTTP read can identify the
  exact SSH key lineage without SSH access.
- W4 builds can now require `OM_EXPECTED_AUTHORIZED_KEY_FINGERPRINT`, preventing
  accidental rebuilds with the old WSL key path.
- W5/F5 manifests now propagate the W4 bootstrap key fingerprint.
- The F5 build script and one-shot runner now fail closed if the F5 manifest's
  source rootfs hash or bootstrap key fingerprint diverges from the current W4
  manifest.

This does not change existing binary images. Rebuild is required before the
new getinfo identity appears inside a SquashFS/webformat artifact.
