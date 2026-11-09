# F366 native acquisition campaign and later DFS acceptance

22 September 2026. This document describes an offline-prepared runner. No
hardware, AELITA, UART, radio or flash action was executed by its author.
The root operator remains the only hardware owner.

F366 is a diagnostic candidate on the actual F365 kernel/DT/Ethernet/store
baseline. It boots with 5 GHz pending, then explicitly activates real native
acquisition on channel36/BW80. Callback authority is compiled off. It cannot
complete DFS CAC/radar/NOP acceptance or provide a DFS release merely by
passing acquisition.

## Exact prepared run

The final plan is
`outputs/preflight/f366-acquisition-20260922T094403Z/plan.json`, SHA256
`64047f577ebeb9a123a24a73489db8bf2037acc9299e5b721febda8576a9d85c`.
It binds117 source files, the actual F366 qualification and the accepted F365
installation. The earlier094232 plan has source drift and must not be used.

- F366 image:5,447,680 bytes, SHA256
  `6b9e77c56de0a374531e2e863f6bd7f5668cd2dd5e87fa0b6eb00f03c4449fe6`;
  full-slot CRC `5ac61b5e` includes the actual sequence2 store.
- Exact F365 fallback:5,382,144 bytes, SHA256
  `43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`;
  full-slot CRC `118901d4`.
- Store CRC remains `5d2ee646`; its1,835,008 bytes are outside the erased
  firmware prefix. Protected OEM partitions are checked by the existing writer.

Review without hardware:

```powershell
python tools/run_f366_acquisition.py --plan outputs/preflight/f366-acquisition-20260922T094403Z/plan.json --plan-sha256 64047f577ebeb9a123a24a73489db8bf2037acc9299e5b721febda8576a9d85c
```

Only the root hardware operator adds `--execute`, after freezing the exact
plan sources and checking its applicable artifact/operation authorization.
The existing PowerShell5.1 launcher obtains the hardware lease, nonce-binds
COM3 to the known HGW and verifies the fixed wired management path.

The sequence is:

1. Verify current F365 identity, inactive watchdog, exact store and config.
2. Through the unchanged F365 writer, bind current physical full-slot/protected
   CRCs and install the F366 prefix. A write with ambiguous completion prevents
   any automatic second write.
3. Require F366 boot/2.4GHz/bridge management with qdrv/provider/wifi0 still
   absent,16 installed component hashes, stable Ethernet, store, sequence2
   config and inactive thermal state. The historical platform27 gate requires
   an active5GHz AP, so it is deliberately reserved for the F365 return.
4. Invoke `om-f366-diagnostic activate TOKEN32` once. The exact supervisor owns
   its watchdog FD for at most180s. Module-load/core/VAP/radio/observation phases
   keep their original bounded deadlines; the host never opens or pets the FD.
5. Persist each `OMF366_STATUS` JSON line to host disk with flush/fsync before
   CEASE; collect exactly20 observations, advancing jobs, final postfilter,
   channel36, zero callbacks and no reported faults. Failed startup/observation
   emits redacted ERROR/FAILURE_STATUS before CEASE.
6. Software-drain the provider, retain the dirty module, let the watchdog reset
   and intercept Bootbase. No module unload/reload is attempted. If the watchdog
   return does not occur within its full absolute deadline and margin, the
   existing single serial recovery path is the conditional fallback; that
   outcome cannot be acquisition PASS.
7. Always restore exact F365 once, then verify its full-slot readback, new boot,
   platform27, store, config, Ethernet and disabled thermal state. Failed
   containment/unknown owner/ambiguous flash retains the lease and blocks retry.

The run lives under `/workspace/OpenMitraStar/f366-acquisition/`. The transcript is
`diagnostic-transcript.log`; `diagnostic-before-return.json` and
`failure-before-recovery.json` preserve evidence before the host return path.
`result.json` distinguishes diagnostic telemetry from actual reset and F365
recovery. A successful end state is
`PASS_F366_ACQUISITION_WITH_F365_RETURN` only.

## Minimal continuation toward DFS

`tools/f366_dfs_campaign.py plan --output-dir <new-directory>` emits the
file-only detailed continuation plan using the existing F301 occupied-block
classifier and unchanged70/600/1800-second policy timers. It does not reuse
F301's image identity or grant RF authority.

After acquisition physically passes, a subsequent coherent versioned candidate
must introduce reviewed callback authority, TX/CAC/availability observations and
a supervisor lifetime that covers complete weather CAC and NOP. F366's180s
diagnostic lifetime is insufficient. Do not extend it by runtime override.

Begin actual DFS service at100/20: require current ES/EU, DOTH/TPC, complete
driver/regulatory channel support and no NOP; verify detector continuity and
CAC TX suppression for70s plus observation margin. Then prove WPA2 association,
AUTH/ASSOC/AUTHORIZED,32MiB each direction and120s useful traffic. Bind a bounded
HTTPS probe to AELITA's Wi-Fi source/interface; a wired internet response is
not evidence for the Wi-Fi path.

Minimum later policy-branch coverage is52/80,100/80,116/80,132/40 and140/20.
116/80 includes120/124/128, so its weather CAC remains600s although primary116
alone is not in the weather sub-band. This is representative branch coverage,
not certification of every primary or every radar waveform. Reject140/80,
whose complete block would require channel144 outside this project's ES map.

Complete width changes before the radar/NOP trial: the inherited NOP expiry
uses current width, so width must remain fixed while any NOP is active. A
reviewed software injection on100/80 may prove TX-stop/CSA, evacuation to36/80,
client recovery and NOP on100/104/108/112. Retain same boot/region/width for the
full1800s, verify reuse is rejected throughout, then require fresh CAC after
expiry. Label this result SOFTWARE_INJECTION: it cannot establish RF radar
sensitivity or waveform classification.

Positive RF detector acceptance still needs an authorized calibrated radar
source, controlled coupling/attenuation, exact waveform/timing and independent
RF observation during CAC and in-service operation. Acquiring real empty/noise
windows and matching old classifier vectors does not replace that evidence.

## AELITA and validation boundary

Root discovers the current AELITA address, pinned SSH identity, wired adapter,
Wi-Fi adapter and original profile; do not assume historical `.63` or the
alias `Wi-Fi`. Preserve the wired SSH route, addresses and metrics. Use existing
association/transfer/restoration helpers only after adapting their old profile
identity and source binding. Never call old F293/F301/F314 execution entrypoints
with a substituted version string.

Restore the captured Wi-Fi profile and only scoped test resources on failure.
Keep PSKs and client MACs private; public evidence may contain association
state, channel/PHY, byte counts, hashes and redacted interface-path checks.

Preparation passed10 targeted Python tests and4 PowerShell context tests using
explicit fake devices/guards, plus both default CLI smoke checks. These verify
evidence parsing, unconditional fallback and rejection of ambiguous writes;
they are not physical or RF PASS evidence. No historical hardware/math bank
was rerun, and no F365 source or sealed F366 image was modified by this runner.
