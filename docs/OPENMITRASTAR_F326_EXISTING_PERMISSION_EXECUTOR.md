# F326 execution with an existing Windows firewall permission

Prepared on 2026-09-21. This document records executor preparation, not a flash
or physical DFS result. The parent operator alone controls the HGW campaign.

The executor now has an explicit `existing-permission` mode. Windows already
allows inbound UDP for the exact Python 3.12 executable on the active Public
profile. This mode reads and verifies that existing permission; it never
creates, modifies or removes a rule, requests elevation, changes firewall
policy, or falls back to another permission mode.

## Bound inputs

- F326 image unchanged: 5,320,704 bytes, SHA-256
  `7500036d0c7215a74d509b39419f65463efbd575b18d15703b3d05312262a767`.
- Exact F321 return unchanged: SHA-256
  `eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`.
- Source `192.168.1.49`, Ethernet interface 18, target `192.168.1.90`.
- Python: `/workspace/user-home/AppData/Local/Programs/Python/Python312/python.exe`,
  SHA-256 `4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a`.
- Existing rule: `UDP Query User{B53A0DF9-DAAE-4615-9572-87C57A3EF67B}/workspace/user-home\appdata\local\programs\python\python312\python.exe`.
- Normalized permission/profile/program fingerprint:
  `df0c7fac07a2dfae253bd0cef8f4b9a76e8b46b6965ba635be6831ccbbd8270f`.
- Delegated permission record:
  `outputs/authorizations/f326-existing-permission-20260921T102102Z/permission.json`,
  SHA-256 `7fa5f3c22ff9a5c4755c1740b14c8bd52fe8c11828a0443a181cf7fc4a912538`.
  The record says the agent bound the observed hashes; it does not claim the
  owner typed those hashes.

The permission projection includes the ActiveStore rule, relevant filters,
active connection profile, Public firewall profile and executable digest.
Every field is encoded deterministically and hashed. Missing/duplicate rules,
profile changes, program replacement or definition drift fail closed.

## Actual transport evidence

The parent operator's successful synthetic transfer is preserved at
`outputs/preflight/f326-existing-tftp-probe-20260921T102246Z/result.json`, SHA-256
`b09b2bd92c098c0a0833453a4c29670bcc08c7c7c14b4db506dc130281c6edbf`.
It proves 4,096 bytes, nine acknowledged blocks, zero retries, a successful
client exit, closed sockets/server thread, removed RAM client and unchanged
permission. It used the unchanged reviewed scoped server, SHA-256
`d4922784174d8e58d1aba60d5844c4fdc1e553159141a27ad43e6d1685ec5488`.

The earlier probe with a failed client process exit remains a separate FAIL.
Neither synthetic transfer is firmware, flash, Bootbase or RF acceptance.

## Runtime behavior

`temporary-scoped-rule` retains its original administrative checks and owned
rule cleanup. It is a separate explicit mode. An existing permission must not
be attached to that mode, and existing mode requires its exact record/hash.

Existing mode validates permission before any device/lease action, before each
transfer, across the borrowed F321 recovery and at final cleanup. It does not
insert firewall reads into an active erase/write or interrupt a writer. It
never claims ownership of the existing Windows rule and never removes it.

The server still serves only its pinned image filename to the pinned client
from the selected source address. Broader Windows permission is not translated
into a broader server policy. Physical identity, lease, protected readbacks,
Bootbase contract, RAM CRC, complete candidate verification, process containment
and the single exact F321 return remain unchanged.

Permission drift rejects the next transfer. Cleanup drift prevents a success
claim and lease release. Ambiguous writers retain the original STOP behavior;
no new retry, alternate firewall rule, privileged broker or F314 fallback exists.

## Qualification and launch

Preparation directory:
`outputs/preflight/f326-existing-permission-20260921T102102Z/`.

- Full Ethernet/capture/existing-permission suite: **685/685 PASS** in
  `ethernet-qualification-1.xml`.
- New review: `ethernet-executor-review.json`, SHA-256
  `20e42447195850c657447c1030f0d7b9dde5ef09677439b4842ad0c885e033a8`.
- All 86 execution sources are frozen in `final-source-snapshot/`.
- UART qualification is retained unchanged; it was not rerun.
- Both `final-plan.json` and `rollback-plan.json` are
  `OFFLINE_READY_FRESH_PHYSICAL_GATES_PENDING`.
- Launcher:
  `outputs/launchers/f326-existing-permission-20260921T102102Z/launch.ps1`,
  SHA-256 `49af210121609518a475ebd261eb4edd3afc57b758ca46d9bf4b587bb9eb76a0`.
- `launcher-ready.json` proves the launcher's file-only default passed without
  consuming its execution claim or starting hardware work.

The launcher requires `-Execute` and its exact self hash. It consumes one
CreateNew claim, writes `parent-started.json` with the actual physical run
directory, and writes `parent-result.json` when that attempt ends. It runs the
reviewed F326 capture-and-return cycle directly without an elevation child.
It changes only its own process module search precedence so Windows PowerShell
uses its own modules; no machine/user setting is changed.

The old administrative launcher, 645-test review and every previous evidence
directory remain preserved. Their review hashes do not validate these changed
execution sources. Use only the review and launcher identified above.
