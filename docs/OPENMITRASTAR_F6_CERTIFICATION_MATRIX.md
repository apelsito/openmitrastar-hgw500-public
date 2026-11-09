<!-- f6-source-json-sha256: 5ce945845a75973a19f68f9c606e9e824b5ed22a3be0142949a6274cc1f2ba04 -->
<!-- f6-entry-count: 49 -->

# OpenMitraStar F6 certification matrix

Cutoff: **Thursday, August 20, 2026**  
Target: **MitraStar HGW-500BNA-QCv2 A2 / Linux 5.10.260**  
Verdict: **INCOMPLETE — this is not an F6 PASS**

## Status discipline

- `PROVEN`: the entire stated requirement is demonstrated at matching scope.
- `PARTIAL`: real implementation or evidence exists, but the full requirement is not proven.
- `PENDING`: implementation or the discriminating test has not been completed.
- `BLOCKED`: a concrete evidenced blocker prevents completion.

Offline build, emulation and static analysis do not prove hardware runtime. A RAM
boot does not prove persistent boot. Control-plane readiness does not prove client
traffic. Bridge Internet does not prove DNS, NAT or firewall behavior.

The OEM capability matrix classifies routed WAN/PPPoE/NAT/VoIP as not applicable
to the observed videobridge role. The prime objective nevertheless names WAN,
DHCP, DNS, NAT and firewall. Those requirements remain open until the objective is
explicitly reconciled with the source-backed OEM role; they are not silently
removed here.

## Current score

| Status | Count |
|---|---:|
| PROVEN | 13 |
| PARTIAL | 21 |
| PENDING | 10 |
| BLOCKED | 5 |
| **Total** | **49** |

Delta from the August 19 matrix: **no status promotion or demotion**. The F3
real-client certificate and 5 GHz controls postbaseline artifact improve offline
readiness only; both remain hardware-pending, so the counts stay unchanged.

## Load-bearing blockers

1. **5 GHz VAP:** MuC reaches core start, then faults before a usable `wifi0` exists.
2. **DFS:** the current Linux 5.10 radar compatibility backend is intentionally fail-closed.
3. **Persistent body:** no candidate is flash-eligible; the existing persistent slot is defective.
4. **Final services:** DNS/NAT/firewall and the complete Movistar service/control matrix are not certified.
5. **Release evidence:** no post-flash rollback, power-loss persistence or 24/72-hour soak exists.

## Requirement matrix

| ID | Phase | System | Status | Evidence | Remaining gate / blocker |
|---|---|---|---|---|---|
<!-- f6-entry: F0-01 status=PROVEN -->
| F0-01 | F0 | Mission state | PROVEN | `state`, `hardware`, `ledger` | — |
<!-- f6-entry: F0-02 status=PARTIAL -->
| F0-02 | F0/F4 | Complete subsystem inventory | PARTIAL | `parity_doc`, `parity_manifest`, `master_checklist` | Finish disposition of every relevant OEM/runtime component. |
<!-- f6-entry: F1-01 status=PROVEN -->
| F1-01 | F1 | Stable Linux 5.10 hardware boot | PROVEN | `kernel_uart`, `product_uart`, `product_cold_uart` | — |
<!-- f6-entry: F1-02 status=PROVEN -->
| F1-02 | F1/F6 | UART and RAM recovery | PROVEN | `kernel_uart`, `recovery_runbook`, `ledger` | — |
<!-- f6-entry: F1-03 status=PROVEN -->
| F1-03 | F1 | CPU/MMU/IRQ/timers/DMA | PROVEN | `kernel_uart`, `emac_soak`, `switch_uart` | — |
<!-- f6-entry: F1-04 status=PROVEN -->
| F1-04 | F1/F6 | Ethernet traffic stability | PROVEN | `emac_soak`, `switch_uart`, `hardware` | — |
<!-- f6-entry: F1-05 status=PROVEN -->
| F1-05 | F1/F6 | PCIe host and endpoint | PROVEN | `kernel_uart`, `ledger` | — |
<!-- f6-entry: F1-06 status=PROVEN -->
| F1-06 | F1/F2 | TQE/HBM/switch EMAC | PROVEN | `switch_uart`, `hardware`, `ledger` | — |
<!-- f6-entry: F1-07 status=PARTIAL -->
| F1-07 | F1 | LED/button platform controls | PARTIAL | `controls_uart`, `stage0_contract`, `controls_postbaseline`, `hardware` | Hardware-test 5 GHz controls; complete front-panel and physical-button tests. |
<!-- f6-entry: F1-08 status=PARTIAL -->
| F1-08 | F1/F5 | Watchdog/reboot/power-cycle | PARTIAL | `state`, `watchdog_image`, `ledger` | Prove autonomous recovery after panic/hang on the installed candidate. |
<!-- f6-entry: F1-09 status=PARTIAL -->
| F1-09 | F1/F5 | Storage and filesystems | PARTIAL | `product_manifest`, `product_validation`, `backup_cert` | Hardware-validate SquashFS/JFFS2/MTD and transactional persistence. |
<!-- f6-entry: F1-10 status=PARTIAL -->
| F1-10 | F1 | All ports/platform devices | PARTIAL | `switch_uart`, `hardware`, `master_checklist` | Finish physical-port, GPIO, I2C, sensor and device coverage. |
<!-- f6-entry: F2-01 status=PROVEN -->
| F2-01 | F2/F6 | Bridge/LAN client Internet | PROVEN | `ledger`, `hardware`, `product_cold_uart` | — |
<!-- f6-entry: F2-02 status=PARTIAL -->
| F2-02 | F2 | WAN/uplink/ISP configuration | PARTIAL | `parity_doc`, `ledger`, `hardware` | Reconcile OEM videobridge role with prime WAN requirement and certify final uplink. |
<!-- f6-entry: F2-03 status=PARTIAL -->
| F2-03 | F2/F6 | DHCP/LAN addressing | PARTIAL | `ledger`, `hardware` | Test lease, renewal, reconnect and fallback behavior. |
<!-- f6-entry: F2-04 status=PENDING -->
| F2-04 | F2/F6 | DNS | PENDING | `master_checklist`, `ledger` | Capture direct client/router DNS query tests. |
<!-- f6-entry: F2-05 status=PENDING -->
| F2-05 | F2/F6 | Routing and NAT | PENDING | `parity_doc`, `master_checklist` | Certify a routed profile or formally amend the requirement. |
<!-- f6-entry: F2-06 status=PENDING -->
| F2-06 | F2/F6 | Firewall | PENDING | `master_checklist`, `parity_doc` | Define and execute policy tests. |
<!-- f6-entry: F2-07 status=PARTIAL -->
| F2-07 | F2 | IPv4 and IPv6 | PARTIAL | `kernel_uart`, `ledger`, `master_checklist` | Classify and test IPv6 applicability. |
<!-- f6-entry: F2-08 status=PARTIAL -->
| F2-08 | F2/F4 | Multicast/VLAN/QoS | PARTIAL | `ledger`, `parity_doc`, `master_checklist` | Run IGMP, multicast, VLAN and DSCP/802.1p parity tests. |
<!-- f6-entry: F3-01 status=PROVEN -->
| F3-01 | F3 | Wi-Fi 2.4 driver/interface | PROVEN | `ledger`, `product_cold_uart`, `hardware` | — |
<!-- f6-entry: F3-02 status=PROVEN -->
| F3-02 | F3/F6 | Wi-Fi 2.4 client traffic | PROVEN | `ledger`, `hardware`, `realtek_ap` | — |
<!-- f6-entry: F3-03 status=PARTIAL -->
| F3-03 | F3 | Wi-Fi 2.4 feature parity | PARTIAL | `realtek_ap`, `product_soak`, `master_checklist` | Secure-client negative/rekey, scan, STA/repeater and reconnect matrix. |
<!-- f6-entry: F3-04 status=PENDING -->
| F3-04 | F3/F6 | Wi-Fi 2.4 release stability | PENDING | `product_soak`, `master_checklist` | Run 24-hour minimum and 72-hour release soak. |
<!-- f6-entry: F3-05 status=PARTIAL -->
| F3-05 | F3 | Wi-Fi 5 platform/core | PARTIAL | `qdrv_control_uart`, `qdrv_vap_failure_uart`, `state` | Cold-validate the HRFLAGS deferral without fatal MuC markers. |
<!-- f6-entry: F3-06 status=BLOCKED -->
| F3-06 | F3 | Wi-Fi 5 `wifi0` interface | BLOCKED | `qdrv_vap_failure_uart`, `state`, `ledger` | HRFLAGS-before-VAP race; MuC fault at `uc_hostif_pullioctl+0x98`, EFA `0x3c`. |
<!-- f6-entry: F3-07 status=BLOCKED -->
| F3-07 | F3/F6 | Wi-Fi 5 AP/client traffic | BLOCKED | `qdrv_vap_failure_uart`, `ap5_offline`, `f3_client_cert`, `state` | Requires F3-06, then execute the prepared 600-second client certificate. |
<!-- f6-entry: F3-08 status=PARTIAL -->
| F3-08 | F3 | Wi-Fi 5 regulation/calibration | PARTIAL | `ap5_offline`, `state`, `hardware` | Validate ES RF power/calibration on hardware. |
<!-- f6-entry: F3-09 status=BLOCKED -->
| F3-09 | F3/F6 | DFS/radar/CAC | BLOCKED | `dfs_contract`, `state`, `master_checklist` | No native 5.10 radar backend; compat implementation denies DFS. |
<!-- f6-entry: F4-01 status=PROVEN -->
| F4-01 | F4 | Secure administrative access | PROVEN | `product_uart`, `kernel_uart`, `ledger` | — |
<!-- f6-entry: F4-02 status=PARTIAL -->
| F4-02 | F4/F6 | CGI/UI runtime on current image | PARTIAL | `w4_ui_manifest`, `product_manifest`, `w5_package`, `cgi_ram_image` | RAM-boot exact image and run live HTTP smoke. |
<!-- f6-entry: F4-03 status=PARTIAL -->
| F4-03 | F4 | UI functional parity | PARTIAL | `parity_doc`, `w4_ui_manifest`, `master_checklist` | Implement applied settings, password, firmware, reset and client controls. |
<!-- f6-entry: F4-04 status=PARTIAL -->
| F4-04 | F4 | Movistar services/config | PARTIAL | `parity_doc`, `parity_manifest`, `master_checklist` | Complete component disposition and applicable runtime tests. |
<!-- f6-entry: F4-05 status=PARTIAL -->
| F4-05 | F4 | LED parity | PARTIAL | `controls_uart`, `stage0_contract`, `controls_postbaseline`, `hardware` | Hardware-validate 5 GHz GPIO1/carrier behavior and remaining front-panel states. |
<!-- f6-entry: F4-06 status=PARTIAL -->
| F4-06 | F4 | Buttons/reset | PARTIAL | `controls_uart`, `hardware`, `master_checklist` | Physical Wi-Fi/WPS/reset testing remains. |
<!-- f6-entry: F4-07 status=PENDING -->
| F4-07 | F4/F5 | Backup/restore/factory reset | PENDING | `backup_cert`, `master_checklist`, `parity_doc` | Implement transactional configuration backup/restore/reset. |
<!-- f6-entry: F4-08 status=PARTIAL -->
| F4-08 | F4 | Observability/diagnostics | PARTIAL | `product_validation`, `w4_ui_manifest`, `product_uart` | Validate full live dual-radio/client/recovery truth. |
<!-- f6-entry: F4-09 status=PARTIAL -->
| F4-09 | F4 | Secret hygiene | PARTIAL | `w4_ui_manifest`, `parity_manifest`, `product_validation` | Scan complete endpoint, backup and release surfaces. |
<!-- f6-entry: F5-01 status=PROVEN -->
| F5-01 | F5 | Reproducible product/package | PROVEN | `product_manifest`, `w5_package`, `w5_bootbase`, `w5_validation`, `cgi_ram_image` | — |
<!-- f6-entry: F5-02 status=PENDING -->
| F5-02 | F5 | Exact CGI candidate RAM boot | PENDING | `w5_package`, `cgi_ram_image`, `state` | Boot SHA `f8285f5d…e89c` and run complete smoke. |
<!-- f6-entry: F5-03 status=PROVEN -->
| F5-03 | F5 | Flash backup/preflight | PROVEN | `backup_cert`, `hardware`, `recovery_runbook` | — |
<!-- f6-entry: F5-04 status=BLOCKED -->
| F5-04 | F5 | Persistent installation/cold boot | BLOCKED | `state`, `hardware`, `master_checklist`, `w5_package` | No flash-eligible candidate; existing persistent slot can fault with `EV_TLBProtV`. |
<!-- f6-entry: F5-05 status=PENDING -->
| F5-05 | F5/F6 | Configuration persistence | PENDING | `product_validation`, `master_checklist`, `hardware` | Atomic persistence and reboot/power-cut recovery tests. |
<!-- f6-entry: F5-06 status=PENDING -->
| F5-06 | F5 | Post-flash rollback | PENDING | `recovery_runbook`, `backup_cert`, `master_checklist` | Demonstrate rollback after candidate flash. |
<!-- f6-entry: F5-07 status=PENDING -->
| F5-07 | F5/F6 | Recovery after installation | PENDING | `recovery_runbook`, `kernel_uart`, `master_checklist` | Repeat UART/Bootbase/TFTP recovery after installation. |
<!-- f6-entry: F5-08 status=PENDING -->
| F5-08 | F5/F6 | Release soak | PENDING | `product_soak`, `emac_soak`, `master_checklist` | 24-hour minimum; 72-hour release target. |
<!-- f6-entry: F5-09 status=PARTIAL -->
| F5-09 | F5 | Installable/distributable firmware | PARTIAL | `w5_package`, `parity_doc`, `master_checklist` | Close flash, installer, signature, licensing/SBOM and blob strategy. |
<!-- f6-entry: F6-01 status=PARTIAL -->
| F6-01 | F6 | Certification matrix | PARTIAL | `state`, `ledger`, `master_checklist` | Reach zero PARTIAL/PENDING/BLOCKED rows. |
<!-- f6-entry: F6-02 status=BLOCKED -->
| F6-02 | F6 | Full OpenMitraStar certification | BLOCKED | `master_checklist`, `state`, `qdrv_vap_failure_uart`, `w5_package` | Blocked by 5 GHz/DFS and persistent installation; many final tests remain. |

## Exact evidence catalog

| Evidence ID | Path | SHA-256 | Scope |
|---|---|---|---|
| `state` | `work/mission-state/MISSION_STATE.md` | `3b1f5878ce4c942890f91a20f7ed2a8d3a95e4634a82b81f4d55a302a33c1d01` | Current blocker and accepted milestones |
| `hardware` | `work/mission-state/HARDWARE_STATE.json` | `16ea08a3fb57f3527883f5952fcee4ad5c851a7fdecfc17aff41d28c433d2e95` | Structured hardware state |
| `ledger` | `work/mission-state/EVIDENCE_LEDGER.md` | `00ba5b24afb4b00d7fb4a3467beb5048f6b6b4758a97b7a71d6183ca7bf0f4c7` | Evidence ledger through cutoff |
| `master_checklist` | `work/mission-state/FULL_MIGRATION_TO_ENHANCEMENTS_CHECKLIST.md` | `d52c539d43fa8d1aff48d9a9d7dc86f997234f57cf529238e5ba2917cebd1caf` | Migration-complete requirements |
| `kernel_uart` | `outputs/uart-live/ramssh-cycle-20260817-204324.log` | `890066841b70c383295bf78e135d11cf23b5fb8be80044d0f77666bf2659fe23` | Linux 5.10/PCIe/Ethernet/SSH boot |
| `emac_soak` | `outputs/kernel-port/emac-management-soak/20260818-123340/summary.json` | `cf8349a345cb7228ba379206341d2c99f3393f2533eba7a7c2fce75c9a816fab` | 600-second management soak |
| `switch_uart` | `outputs/uart-live/w3-switch-emac-handoff-20260819-164256/topaz-20260819-164256.log` | `63ef3a6e55ddcf979422f0033026db6b860a87b6b3a4a7bddce2cd5063f89d86` | TQE/FWT/HBM/switch management |
| `qdrv_control_uart` | `outputs/uart-live/qdrv-control-20260819-164432/topaz-20260819-164433.log` | `5df8536a76f8f984471bcb9d90632c35ce70d3c1a111b74cedd91c6c234c200a` | qdrv control-ready/RF blocked |
| `qdrv_vap_failure_uart` | `outputs/uart-live/w3-qdrv-sequential-20260819-234234/topaz-20260819-234235.log` | `fefaf9938a62b7bd67a04fd3f6266df3088cb1e851447267cefef94fbe9d551f` | Core start plus VAP-path MuC failure |
| `controls_uart` | `outputs/uart-live/ramssh-cycle-20260818-145252.log` | `4e34a66056724577f3cf165ea8914da582ffcd20d09f4cd3953d279e461eb9d7` | LED/button registration |
| `product_uart` | `outputs/uart-live/ramssh-cycle-20260818-181532.log` | `bc9a9d8abd35dc65dcab891d8305418ec89421be2fc78d78eb817799e45a65d9` | Product SSH/API boot |
| `product_cold_uart` | `outputs/uart-live/ramssh-cycle-20260818-193430.log` | `504c0edddfaa2e3fabe4549517ba8aaf3e6416766f84ccae53ec41003e94dd88` | Cold RAM boot/product AP |
| `product_soak` | `outputs/kernel-port/product-ap-soak/20260818-1936/run/summary.json` | `d773310b02fecc0b84c006b6e13f0c1d21c9d3f019391f468bed76a4c27db82e` | 615.843-second AP management soak |
| `realtek_ap` | `outputs/kernel-port/realtek-ap-runtime/detached-20260818-142808/orchestrator.log` | `b2e20b37ea31e2914666a81cf24634df5a1a238d587c5b9cb6b6ceb9a04510c6` | WPA2 control plane |
| `stage0_contract` | `work/mission-state/W1_GPIO7_STAGE0_READY_CONTRACT.md` | `fbed3d83dfe50b2f735e598aeddbaa464ec6f7c44c4125beb9b71b954bc6fa74` | Boot LED policy |
| `recovery_runbook` | `recovery/HARDWARE_RECOVERY_RUNBOOK.md` | `20e0c4fb0d2dbe3d247dacb43cab4fbd0f7c4f687f7ce8c073b78c9e15010cfb` | UART/Bootbase/TFTP recovery |
| `backup_cert` | `work/mission-state/F2_FLASH_BACKUP_CERTIFICATION.md` | `ac0fc49a56d30281e82ab6ae1c5d3efddb04fa67c8725484914d4efff6a17c3e` | Flash backup certification |
| `parity_doc` | `docs/HGW500BNA_QCV2_OEM_MOVISTAR_PARITY_MATRIX.md` | `4ed870958a79ddb7f5e71a4425444883a19fb93af40a7f85e6e5f6bc0f347fd2` | OEM parity inventory |
| `parity_manifest` | `outputs/kernel-port/movistar-parity/manifest.json` | `f5b912984db14da84d784a8bd969d95cb6b2339741fa682b385b0d4e58b75c0e` | Parity verifier manifest |
| `w4_ui_manifest` | `work/mission-state/w4-ui-parity/manifest.json` | `347d522691832734f519001deb4893d53034a965dc721f7ea3a0ef457a219697` | CGI/product/HTTP offline gate |
| `product_manifest` | `work/mission-state/w4-rootfs-product/build/manifest.json` | `eebd7ca1759aea1e693890fbe29d274ce1681be3329bb88d636e0043f07d2799` | Integrated product rootfs |
| `product_validation` | `work/mission-state/w4-rootfs-product/build/validation.log` | `0b8a0d449dd08e8fb6e2b8ff83085572b17f623c60d9527238f8ad5825286275` | Rootfs/API/config validation |
| `w5_package` | `work/mission-state/w5-cgi-product-ram-candidate/build/packaging-manifest.json` | `47bf30b75cb76810c0c4a51c554d8b4b7a34f3ea2b3ff73fd26d5e710211ce00` | Reproducible RAM package |
| `w5_bootbase` | `work/mission-state/w5-cgi-product-ram-candidate/build/bootbase-contract.json` | `391c3f53f0d88dfdc612d265483d3a4e3e5059d19d5d55e1343d9338391460b8` | Bootbase/RAS/slot contract |
| `w5_validation` | `work/mission-state/w5-cgi-product-ram-candidate/build/validation.log` | `b587cf949ee2a5ee9bc8175dd1ff37451501d4a84c1081bca254fca468c65bfd` | W5 validation log |
| `cgi_ram_image` | `work/tftp/omvl/linux510-product-cgi-ram-v1-RAM-ONLY.bin` | `f8285f5d760bbe71a7c4cc4a1ad92421304a60b76efc002e8225656a1e78e89c` | Current RAM-only candidate |
| `watchdog_image` | `work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin` | `5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358` | Protected watchdog image |
| `ap5_offline` | `outputs/kernel-port/qcsapi-5g-ap36-bw80-ram-only-20260819/abi-report.json` | `a38cca2548ab86abc2caf580dc629e5596aa3ba21ea6b48f39cdf630a0bbac91` | 5 GHz AP36 offline bundle |
| `f3_client_cert` | `work/mission-state/w3-offline/W3_QTN_5G_F3_CLIENT_CERT_CONTRACT.md` | `3f936b86dc1cab9229cf5badb287b08815a559f6240693e725cbbf7c10a4473b` | 600-second client certificate, offline only |
| `controls_postbaseline` | `outputs/kernel-port/hgw500-controls-5g-postbaseline-20260819/manifest.json` | `1c3502644fef18e3e85900c8f0c5c8bc87ac66197e0b97cd0a61f26c4aa28bc4` | 5 GHz GPIO1/carrier controls, offline only |
| `dfs_contract` | `work/mission-state/w3-offline/W3_DFS_ES_80_CONTRACT.md` | `0d9ac444a1229e851ee6220e8cd9e461d69558d661dc0031fa1efbdc363a3edf` | DFS fail-closed contract |

## Verifier

Normal execution must fail while any requirement is not `PROVEN`:

```powershell
python tools/verify_openmitrastar_f6_certification.py
```

Audit-only execution verifies integrity but permits an incomplete result:

```powershell
python tools/verify_openmitrastar_f6_certification.py --allow-incomplete
```

F6 may be declared complete only when normal execution returns zero and prints
`F6_CERTIFICATION_PASS`.
