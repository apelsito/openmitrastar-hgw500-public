# R9 pending return: host17 binding

Prepared on 2026-09-23. This is the current host binding for the pending exact
F365 return. The earlier return plan with SHA256 `6cbc06e2...` binds interface18
and remains an immutable historical artifact. Its writer, recovery sequence,
lease handling and physical gates are unchanged in this revision.

The host interface change observed now **does not establish the cause of the
R9 failure**. The interface18 guards passed during the original R9 operation.
The router remains a separate recovery blocker; this host observation does not
prove a reboot, SSH availability or F365 return.

## Root observation

Root ran the read-only collector and obtained
[result.json](../outputs/preflight/r9-host17-observation-20260923T082938Z/result.json)
at 2026-09-23 08:29:39 UTC. SHA256:
`f71c4f90df7a2d32986a702eb8f4d3a5a700694ae50c8c4e7f01e080bd43e212`.
Status: `PASS_HOST17_ONLY_INDEX_REBIND`.

The original firewall permission, executable, filters and Public profile were
compared property by property. The sole difference is
`connection_interface_index: "18" -> "17"`. Current permission fingerprint:
`04bcaea30f6c9ee58ea825f2732e0d91807030aaf1e4c0dd911c45433d0b97ff`.
No rule, permission, address or route was changed; no listener or device access
was used by the observation.

The fresh binding requires:

- interface17, `Ethernet`, Up, 802.3, 1Gbps;
- adapter GUID `b75315d5-9f01-448f-a259-c9d8f25d2233`;
- PNP `PCI\VEN_10EC&DEV_8168&SUBSYS_E0001458&REV_16\6E8F9B4DC018000000`;
- source `192.168.1.49/24`, Preferred, `SkipAsSource=false`;
- target `192.168.1.90` via direct route `192.168.1.0/24`, next hop `0.0.0.0`;
- no IPv4 address on interface18 and UDP69 free before transport;
- every original permission/profile comparison unchanged except that index.

Any later drift aborts. Neither another index nor another NIC is selected
automatically. The collector and guard used by root are immutable source pins;
replacing them requires a separately justified observation and plan.

## Final plan and entry point

[Plan](../outputs/preflight/r9-return-host17-20260923T083056Z/plan.json), SHA256:
`43c3fd8de34c675501168e86180df1b46e45bf60b99024d78e0fa59745d60b18`.
It fixes 98 source/evidence/artifact files, including root's host observation,
the original permission and both new test results.

New versioned files:
[runner](../tools/run_f367r9_return_f365_host17.ps1),
[worker](../tools/f367r9_return_f365_host17.py),
[network and permission guard](../tools/f367r9_host17_guard.ps1),
[context](../tools/f367r9_return_context_host17.ps1),
[collector](../tools/collect_f367r9_host17_binding.ps1).
Historical guards, plans and permission records were not edited.

The default remains file-only:

```powershell
& "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File '/workspace/user-home\Desktop\MitraStar\tools\run_f367r9_return_f365_host17.ps1' `
  -PlanPath '/workspace/user-home\Desktop\MitraStar\outputs\preflight\r9-return-host17-20260923T083056Z\plan.json' `
  -PlanSha256 '43c3fd8de34c675501168e86180df1b46e45bf60b99024d78e0fa59745d60b18'
```

Root alone may append `-FreshBootId <the-real-fresh-R9-boot-id> -Execute` after
the required fresh R9 observation. All prior gates remain mandatory: pinned
SSH identity, new epoch, R9/#358, bootready, inactive watchdog, no qdrv/provider/
owner, unchanged store/configuration, nonce binding and both hardware mutexes.

The one permitted write remains exact F365, 5,382,144 bytes, SHA256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`.
Only the `0x5e0000` firmware prefix of physical mtd4 may be erased. The store,
OEM and physical mtd0/1/2/3/5 remain protected. There is no mtd6 physical write,
persistent bootenv change, AELITA access, radio trial, BREAK or serial fallback.
The original [recovery procedure](OPENMITRASTAR_R9_PENDING_F365_RETURN.md)
describes the unchanged readbacks and quarantine retirement contract.

## Verification

- [Host guard tests](../outputs/preflight/r9-host17-tests-20260923T082755Z/result.json):
  51 checks PASS using mocked host cmdlets. Every unrelated projection change
  and incorrect GUID/PNP/IP/route/old-index/UDP state is rejected. The permission
  snapshot body is identical to F325 except its function name and exact index.
- [Worker/launcher delta](../outputs/preflight/r9-host17-delta-final-20260923T083035Z/result.json):
  8 tests PASS. The launcher changes only its host17 entry points; every network
  call uses the new guard. Recovery and writer code are reused unchanged.
- [Default wrapper](../outputs/preflight/r9-return-host17-20260923T083056Z/wrapper-offline.json):
  Windows PowerShell 5.1 exit0, no `-Execute`, no host observation or device action.
  The original quarantine still contains only `owner.json`, SHA256
  `37c47a29576b1da2743057d974e1ec3850965c98eef956ba04ff2973e21b1b48`.

The earlier 16 recovery fault tests and 6 synthetic quarantine checks remain
valid and pinned. Physical return is **NOT RUN** by this revision.
