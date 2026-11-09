# HGW-500BNA-QCv2 Linux 5.10 SSH Diagnostic

Date: 2026-08-24
Target: MitraStar HGW-500BNA-QCv2 / Linux 5.10.260-openmitrastar-radiohw

## Current live result

Read-only diagnostic command:

```powershell
python .\tools\diagnose_hgw500_ssh_management.py --host 192.168.1.90 --timeout 4 --no-write-report
```

Result:

- `ping`: PASS
- TCP `22`: open
- TCP `80`: open
- TCP `16667`: open
- `/getinfo.cgi`: model `MitraStar HGW-500BNA-QCv2`, firmware `product-rootfs-v1`, mode `ap`
- SSH with default `known_hosts`: `SSH_HOSTKEY_PROBLEM`
- SSH with isolated temporary `known_hosts`: `SSH_AUTH_REJECTED_PUBLICKEY`
- Classification: `SSH_AUTH_REJECTED_MANAGEMENT_OK`
- Physical reboot indicated: no
- Router RAM writes: none
- Router flash writes: none
- Router reboot: none

This means the router is alive and the SSH daemon is listening. The current
blocker is authentication/key provisioning, not network recovery.

## Offline key/rootfs facts

The W4 product squashfs contains:

- `/etc/passwd` with `root` home set to `/run/openmitrastar/admin`
- `/usr/sbin/om-ssh`
- `/usr/sbin/om-ssh-ready`
- `/usr/share/openmitrastar/keys/factory-authorized_keys`

The factory authorized key in the squashfs has the same fingerprint as the
local Windows key:

```text
SHA256:pBtUFbtw8ud9gGKqhXj3kBz2rhNv6syDjb7lvGwSoBc
```

Therefore the key material itself is not the obvious mismatch. The remaining
likely causes are runtime home/path lookup, generated `/run/openmitrastar/admin`
permissions, Dropbear root account policy, or a persisted revoke/override under
`/persist/openmitrastar/ssh`.

## Offline fix staged

The product `om-ssh` template now launches Dropbear with:

```sh
-D "$ssh_dir"
```

where `ssh_dir=/run/openmitrastar/admin/.ssh`.

Dropbear 2026.94 supports `-D` as the authorized_keys directory selector. This
removes ambiguity around `~/.ssh` expansion and forces the daemon to read the
same `authorized_keys` file that `om-ssh` generated from the factory and
persisted key sources.

This is an offline rootfs-template fix only. It has not been flashed and has not
been RAM-booted on the router.

## Safe next checks

Use this discriminator before asking for a physical reboot:

```powershell
python .\tools\diagnose_hgw500_ssh_management.py --host 192.168.1.90 --timeout 5
```

Only treat physical recovery as indicated if the status is:

```text
MANAGEMENT_UNREACHABLE_PHYSICAL_RECOVERY_CANDIDATE
```

If SSH is still `SSH_AUTH_REJECTED_MANAGEMENT_OK`, do not reboot for SSH alone.
The next product fix should add a boot-time SSH attestation endpoint/log that
records, without printing key material:

- effective root home from `/etc/passwd`
- existence and mode of `/run/openmitrastar/admin/.ssh/authorized_keys`
- whether the factory key was appended
- whether `/persist/openmitrastar/ssh/revoke-factory-key` exists
- Dropbear daemon start result

Do not expose private keys or credential file contents in chat or public
artifacts.
