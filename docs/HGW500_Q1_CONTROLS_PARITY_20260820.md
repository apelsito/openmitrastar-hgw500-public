# HGW-500BNA-QCv2 Q1 front-panel and reset parity

Date: 2026-08-20; corrected with current-unit evidence 2026-08-21  
Scope: offline source/build contract only in this checkpoint; no hardware access and no flash write.

## Classification

`PORTED` means the Linux 5.10/product-rootfs implementation exists and has an offline test contract. It does not silently imply a physical-button or LED observation unless the evidence column says so. `UNKNOWN` means the OEM evidence available here does not identify the control. `BLOCKED` means the identity is known but complete behavior is not implemented or not yet testable.

| Control | Classification | Evidence and exact boundary |
|---|---|---|
| Boot/status lower visible LED, GPIO7 OpenMitraStar policy | PORTED | Target-gated driver + DT + `S90-ready`; hardware log proves assertion during boot and clear at ready. The owner reports the OEM also showed lower green during startup and then off. Exact OEM GPIO/RGB writer remains unproven, so this claims observable sequence parity, not exact channel provenance or an enclosure label such as “Power”/“IPTV”. |
| Power LED as a distinct front-panel function | UNKNOWN | No source-backed distinct Power LED GPIO/polarity/state table was found. GPIO7 is not relabelled as Power without evidence. |
| Ethernet link/activity LED | UNKNOWN | No software GPIO mapping was found. A PHY/switch-driven LED is plausible but unproven and therefore not claimed. |
| IPTV-labelled/status LED | UNKNOWN | The OEM role transports IPTV at L2, but no source-backed front-panel IPTV LED identity/policy was found. |
| WLAN 2.4 GHz LED, GPIO11 active-low | PORTED | OEM identifies logical GPIO11; 2026-08-21 RAM-only physical discriminant proved `255=off`, `0=on`; Linux 5.10 DT/driver polarity corrected. |
| WLAN 5 GHz LED, GPIO1 active-high | PORTED | OEM ELF/GPL table and target-gated Linux 5.10 carrier policy; integrated here from the reproducible post-baseline artifact. Physical GPIO1 observation remains pending. |
| WPS indication on GPIO11/GPIO1 | BLOCKED | The OEM shares WLAN/WPS LEDs and has blink/error state machines. Steady radio state is ported; WPS handshake/error blink parity is not. |
| Reset indicator LED | UNKNOWN | No separate reset LED GPIO/polarity/state contract was found; reset behavior is represented by the button action and logs only. |
| Wi-Fi 2.4 button, GPIO2 active-low | PORTED | Exact OEM `monitor_button`: release before five seconds has no action; ten 500 ms pressed samples toggle the 2.4 GHz RDM `Enable` object and save. Kernel emits only `wifi2g-toggle` on the long action. Physical press validation remains pending. |
| RF/mode switch, GPIO12 active-high | OEM_CURRENT | Current OEM process capture is exactly `monitor_rfenable 12 1`; the binary changes wifi0 AP/STA mode state. GPIO2 is only the generic `/proc/amber` branch and is not the current-unit invocation. |
| GPIO4 combined 5 GHz/WPS path | PORTED | Exact `monitor_button` embeds the active-low 5 GHz toggle at ten 500 ms samples. The current-unit OEM boot resolves the separate qdrv current to GPIO4 polling, active-low. Linux 5.10 configures `gpio set wps 4 0` before VAP creation and independently emits one persistent `wifi5g-toggle` at the fifth second; qdrv still owns the release event (`<10 s` WPS, `>=10 s` debug dump). Physical enclosure-button actuation remains a hardware gate, not a semantic ambiguity. |
| Reset button, GPIO5 active-low | PORTED | OEM `start-prod` calls `monitor_reset_device 5 0`; GPL policy is `<1 s none`, `1..<5 s reboot`, `>=5 s factory reset + reboot`. Linux 5.10 now emits only userspace actions; physical validation remains pending. |
| Restart execution | PORTED | Existing Topaz watchdog/sysctl restart handler remains the kernel endpoint; GPIO5 short-reset action routes to normal userspace `reboot`. |
| Factory-reset transaction | PORTED | Userspace resets only `/persist/openmitrastar/config`; it refuses unless persistence is RW and a pre-existing managed-config backup has a valid SHA-256. Bootloader, environment, MAC, calibration, radio data, SSH keys and Wi-Fi PSK are outside the transaction. |

## OEM timing facts

- GPIO2: `monitor_button` samples every 500 ms; ten stable-low samples invoke the 2.4 GHz Enable toggle and save. No short-release or WPS action exists in that binary.
- GPIO5: `monitor_reset_device 5 0`; the GPL callback selects no action below one second, reboot from one to below five seconds, and restore-default plus reboot at five seconds or longer.
- GPIO12: the current OEM process runs `monitor_rfenable 12 1`; it is an RF/AP-STA mode-switch path, not GPIO2.
- GPIO4: the two sources are concurrent rather than conflicting. `monitor_button`
  toggles and persists 5 GHz after ten 500 ms samples; qdrv polls the same
  active-low pin every 300 ms and acts on release (`<10 s` WPS, `>=10 s`
  debug dump). A 5..10 s hold therefore performs the 5 GHz toggle and later
  emits WPS, exactly as the OEM currents specify.

## Safety invariants

1. Kernel GPIO handlers never call MTD, erase, flash, config deletion or factory reset.
2. `om-factory-reset` requires the explicit confirmation token and a verified, pre-existing backup.
3. The reset scope is the managed OpenMitraStar config directory only.
4. No `/dev/mtd*`, bootloader environment, calibration, MAC or radio-data path appears in the transaction.
5. Failed validation leaves the current config untouched and does not reboot.

## Offline build evidence

- `qtn-topaz-recovery.o`: `3dd08376f318fc8c55d00fc6480f80659773bbc7bed369d42d72f8432a36408b`.
- DTB with GPIO7/11/1/2/5 properties: `ee941083d556c58b4a8057f754830a002498d9cf5dce3ee559643f6efc179e9b`.
- qdrv 25-module bundle with HOSTAP/RUN carrier publication: `outputs/kernel-port/quantenna-linux510-radiohw-q1-controls-20260820`; qdrv SHA-256 `b406f17333fe41114a2d8f307d9d6e71fad3b96be210cf55e8110b4afc141ca2`; `depmod` unresolved output empty.
- Tests: 29/29 PASS; driver checkpatch: 0 errors, 0 warnings.

## Remaining hardware gates

- Observe GPIO1 on/off against `wifi0` HOSTAP+RUN.
- Press GPIO2 for less than five seconds and for at least five seconds; verify no-action versus one persistent toggle.
- Identify the physical GPIO12 RF/mode switch and verify its two stable states without changing persistent configuration.
- Correlate the enclosure's Wi-Fi Plus control with GPIO4 on hardware and
  verify the three hold windows, without changing the already proven OEM
  semantics in software.
- Press GPIO5 in the three timing windows with a verified backup present for the factory-reset case.
- Map the enclosure Power/Ethernet/IPTV labels and WPS blink/error behavior from physical observation plus OEM state transitions.
