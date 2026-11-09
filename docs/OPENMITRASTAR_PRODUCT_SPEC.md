# OpenMitraStar HGW-500BNA-QCv2 — product specification

Status: `DRAFT v0.1`  
Date: `2026-08-31`  
Target: `HGW-500BNA-QCv2 A2`  
Baseline: persistent `F150`, Linux `5.10.260-openmitrastar-radiohw`  
Product role: owner-controlled dual-band videobridge / access point

## 1. Purpose

OpenMitraStar turns the HGW-500BNA-QCv2 into a recoverable, inspectable and
owner-controlled device while retaining the hardware-specific radio and packet
processing paths that make the platform useful.

The product replaces the opaque operator control plane and fragile legacy glue.
It does not replace proven hardware behavior merely to obtain a cleaner-looking
software architecture.

The governing principle is:

> Modernize the control plane; preserve, isolate and progressively certify the
> hardware data plane.

## 2. Product definition

The OEM device is an Ethernet-connected dual-band Wi-Fi bridge. The parity
profile is therefore:

```text
upstream HGU/LAN
       |
    Ethernet
       |
      br0
     /   \
  2.4G   5G
```

Client DHCP, DNS, Internet and multicast traffic normally traverse the L2
bridge to the upstream HGU. OpenMitraStar does not terminate the provider WAN
in its default profile.

### 2.1 Primary users

- The device owner, who needs clear local controls and observable behavior.
- A developer or maintainer, using an explicit time-bounded maintenance mode.
- A recovery operator, using the preserved Bootbase/UART/SPI recovery chain.

### 2.2 Product promises

- No hidden operator access.
- No undisclosed cloud telemetry.
- No secret-dependent diagnostics output.
- No loss of factory identity, calibration or recovery partitions.
- No avoidable CPU slow path when a certified hardware path exists.
- Every release is reproducible, versioned and rollback-aware.

## 3. Current baseline and scope boundary

F150 is the implementation baseline, not the finished product.

Demonstrated on the physical unit:

- persistent cold boot from physical `mtd4/linux_live`;
- Ethernet management and SSH at `192.168.1.90`;
- operational 2.4 GHz baseline;
- autonomous 5 GHz startup during `rcS`;
- 5 GHz real-client association, dynamic ARP, bidirectional packet movement
  and ICMP on the isolated open-lab network;
- preserved `mtd3/linux_safety` manual UART rollback path.

Not yet release-certified:

- 5 GHz WPA2 using the private persistent credential;
- 5 GHz integration into the intended LAN bridge and upstream DHCP path;
- DFS/regulatory behavior outside the proven channel 36 path;
- repeated cold boots and long traffic/thermal soak;
- complete owner UI/API and production security policy;
- full accelerated-path performance parity.

## 4. Non-negotiable platform constraints

### 4.1 Flash and recovery

- The immutable OEM input shall never be modified.
- Normal firmware writes shall target only physical `mtd4/linux_live`.
- `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5` shall not be written during normal
  product iteration.
- Logical `mtd6/rootfs_live` shall never be treated as a physical SPI region.
- `mtd3/linux_safety` shall remain the manual UART rollback image.
- Every flash candidate shall include exact path, size, SHA-256, slot-fit result,
  Bootbase contract, protected-partition evidence and rollback procedure.
- The system shall not modify Bootbase environment while normal SSH management
  is healthy.

### 4.2 Factory identity

- Calibration, regulatory data, device MAC identities and other protected
  `mtd5` data shall be preserved byte-for-byte.
- OpenMitraStar shall not synthesize calibration or silently substitute generic
  power tables.
- Diagnostics and exports shall redact client MACs, credentials and calibration
  contents by default.

### 4.3 Memory ownership

- Linux shall claim only the proven Linux-visible RAM region.
- MuC, AuC, DSP, PCIe, HBM, TQE, DMA and firmware-owned regions shall remain
  reserved until their ownership and coherency contracts are proven.
- A larger reported RAM total is not a success criterion if it overlaps a
  hardware or firmware reservation.

## 5. Target architecture

```text
                         OWNER CONTROL PLANE

  browser ── HTTPS ──> openmitrastard ──> typed adapters ──> radio/system APIs
                         |      |
                         |      +── local metrics and event journal
                         +──────── config transaction engine

  SSH maintenance ── key-only, explicit, time-bounded, locally auditable

  ---------------------------------------------------------------------------

                          CERTIFIED DATA PLANE

  5 GHz client ─> qdrv/wlan ─> HBM/TQE/FWT* ─> EMAC ─> upstream LAN
  2.4 GHz client ─> Realtek path ─────────────> EMAC ─> upstream LAN

  * Enable each accelerated component only after ownership, coherency,
    rollback, traffic and stability gates pass. A safe proven fallback is
    preferable to an unverified acceleration claim.
```

### 5.1 Architectural separation

- The control plane configures services; it shall not proxy ordinary client
  packet traffic through userspace.
- UI failure shall not stop forwarding or radio service.
- Metrics collection shall be bounded and shall not sit in the packet path.
- Radio-specific vendor behavior shall be isolated behind typed adapters rather
  than spread across CGI, shell scripts and unrelated boot stages.
- Boot ordering shall be explicit, dependency-aware and observable.

### 5.2 Service model

The target uses a small supervisor/state machine with these logical services:

| Service | Responsibility | Failure containment |
|---|---|---|
| `platform` | board identity, GPIO, LEDs, protected state | never writes protected flash |
| `network` | Ethernet, bridge, management address | keeps recovery management path |
| `radio2g` | Realtek module, hostapd and 2.4 GHz state | independent of 5 GHz restart |
| `radio5g` | Quantenna modules, firmware, QCSAPI and hostapd | independent bounded restart |
| `config` | validate, stage, commit and roll back config | transactional, schema-versioned |
| `telemetry` | local metrics and event journal | removable without product failure |
| `api` | authenticated local API and static UI | not part of packet forwarding |
| `maintenance` | SSH developer window and diagnostics | disabled by default in release mode |

The names are logical contracts; implementation may use BusyBox init scripts
first and migrate to a compact `openmitrastard` supervisor later.

## 6. Functional requirements

Requirements use the identifiers `FR-*`. `MUST`, `SHOULD` and `MAY` have their
usual normative meanings.

### 6.1 Boot and lifecycle

- `FR-BOOT-001` The device MUST cold-boot autonomously from `mtd4` without a
  post-boot operator command.
- `FR-BOOT-002` Ethernet management, 2.4 GHz and 5 GHz MUST have explicit
  readiness states and bounded startup timeouts.
- `FR-BOOT-003` A failed optional service MUST NOT prevent recovery management.
- `FR-BOOT-004` Boot logs MUST identify the firmware version, config schema,
  radio stages and final health state without printing secrets.
- `FR-BOOT-005` The release MUST preserve the manual `mtd3` UART rollback path.
- `FR-BOOT-006` A service restart MUST be scoped; restarting 5 GHz MUST NOT
  unnecessarily tear down Ethernet or 2.4 GHz.

### 6.2 Ethernet and bridge

- `FR-NET-001` The default product profile MUST operate as an L2 videobridge.
- `FR-NET-002` Client DHCP, ARP, DNS, IPv4 and normal Internet traffic MUST
  traverse between each enabled radio and the upstream Ethernet LAN.
- `FR-NET-003` The default profile MUST NOT run PPPoE, NAT or a competing DHCP
  server.
- `FR-NET-004` The management address policy MUST provide a deterministic local
  recovery address and avoid conflicting with the upstream DHCP service.
- `FR-NET-005` Bridge changes MUST be staged and rolled back automatically if
  management reachability is lost.
- `FR-NET-006` Multicast transport MUST preserve IPTV-style L2 behavior; IGMP
  snooping and flooding policy require explicit certification.

### 6.3 Wi-Fi 2.4 GHz

- `FR-2G-001` The release MUST provide WPA2-PSK with CCMP at minimum.
- `FR-2G-002` A physical client MUST reach `AUTHORIZED`, obtain upstream network
  configuration and pass bidirectional traffic.
- `FR-2G-003` Wrong credentials MUST be rejected without destabilizing hostapd
  or management.
- `FR-2G-004` Rekey, disconnect, reconnect and radio restart MUST recover without
  reboot.
- `FR-2G-005` The known-good 2.4 GHz path MUST not regress while 5 GHz or UI
  features are being developed.

### 6.4 Wi-Fi 5 GHz

- `FR-5G-001` The release MUST start the matched qdrv/wlan/firmware stack
  autonomously.
- `FR-5G-002` The production profile MUST use WPA2-PSK with CCMP at minimum and
  consume the private persistent credential without copying it into the image,
  process list, command line, evidence or logs.
- `FR-5G-003` A physical client MUST reach AUTH, ASSOC and AUTHORIZED and show
  bidirectional packet/byte deltas.
- `FR-5G-004` The client MUST obtain upstream DHCP, resolve DNS and pass ICMP and
  HTTPS through the intended bridge policy.
- `FR-5G-005` Channel, bandwidth, country/regulatory domain and transmit power
  MUST be explicit owner-visible state.
- `FR-5G-006` DFS channels MUST perform the required CAC/radar behavior and MUST
  fail closed when regulatory state is unavailable.
- `FR-5G-007` Quantenna userspace and driver components MUST remain version/ABI
  matched as one release unit.
- `FR-5G-008` A 5 GHz service failure MUST leave Ethernet recovery management
  and the 2.4 GHz service available whenever hardware state permits.

### 6.5 Hardware acceleration

- `FR-DP-001` The implementation MUST preserve the option to use HBM, TQE, FWT,
  switch and radio offload paths.
- `FR-DP-002` No accelerated component may be enabled in release mode until its
  memory ownership, DMA/cache coherency, interrupt, queue and cleanup contracts
  have passed hardware tests.
- `FR-DP-003` Acceleration MUST be observable through counters and health state;
  the UI/API MUST NOT label a path accelerated solely because modules loaded.
- `FR-DP-004` A certified fallback path MAY be used while an accelerator remains
  gated, but its performance and CPU cost MUST be disclosed.
- `FR-DP-005` No refactor may remove a hardware workaround without a targeted
  test showing that the workaround is obsolete on this exact silicon.

### 6.6 Configuration and persistence

- `FR-CFG-001` Configuration MUST use a documented, schema-versioned
  OpenMitraStar format rather than operator-specific object names.
- `FR-CFG-002` Changes MUST follow validate -> stage -> apply -> verify -> commit.
- `FR-CFG-003` Failed network or radio changes MUST automatically restore the
  last known-good configuration.
- `FR-CFG-004` Secrets MUST be stored separately from ordinary exported config,
  with restrictive permissions and no plaintext diagnostics exposure.
- `FR-CFG-005` Factory reset MUST preserve bootloader, recovery firmware,
  calibration, MAC identities and protected partitions.
- `FR-CFG-006` Backup/restore MUST reject corrupt, unsigned or wrong-model data.

### 6.7 Local API and user interface

- `FR-UI-001` The UI MUST be a local, static client of a documented versioned
  API; it MUST NOT require a cloud account.
- `FR-UI-002` The dashboard MUST show Ethernet, 2.4 GHz, 5 GHz, bridge,
  management, firmware and recovery health separately.
- `FR-UI-003` Radio controls MUST expose SSID, enabled state, channel policy,
  bandwidth, security mode and redacted client state.
- `FR-UI-004` Destructive operations MUST present the exact target, consequence,
  validation result and rollback path before execution.
- `FR-UI-005` The UI MUST distinguish configured, starting, ready, degraded and
  failed states.
- `FR-UI-006` UI/API responses MUST not include PSKs, private keys, ACS-style
  credentials, raw calibration data or unredacted client MACs.

Initial API surface:

| Method and path | Purpose |
|---|---|
| `GET /api/v1/status` | aggregate health with per-service states |
| `GET /api/v1/network` | Ethernet, bridge and management state |
| `GET /api/v1/radios` | redacted 2.4/5 GHz state and capabilities |
| `PATCH /api/v1/radios/{id}` | validated staged radio change |
| `GET /api/v1/clients` | redacted association and traffic summary |
| `GET /api/v1/privacy` | outbound connections and disabled remote services |
| `GET /api/v1/events` | bounded redacted event journal |
| `POST /api/v1/maintenance/session` | create a time-bounded developer window |
| `DELETE /api/v1/maintenance/session` | revoke the developer window immediately |
| `GET /api/v1/firmware` | running version, hashes, slots and rollback state |

The endpoint names are a compatibility target and may change only through an
explicit API version transition.

### 6.8 Privacy

- `FR-PRIV-001` TR-069/CWMP MUST be absent or disabled by default.
- `FR-PRIV-002` MAUI/operator analytics MUST be absent from the release image.
- `FR-PRIV-003` `qharvestd` MUST not be removed blindly; its dependencies shall
  first be mapped. If it is not required for radio function, it MUST be replaced
  by bounded local metrics or removed.
- `FR-PRIV-004` The device MUST expose a local inventory of outbound control-
  plane connections with destination class, purpose and last activity.
- `FR-PRIV-005` The default release MUST initiate no undisclosed external
  control-plane connection.
- `FR-PRIV-006` Local telemetry MUST remain local unless the owner explicitly
  configures an export destination.

The Privacy page shall present at least:

```text
Operator remote management     disabled / absent
Cloud Wi-Fi analytics          disabled / absent
Remote telemetry               disabled / configured by owner
Hidden support access          none
Outbound control connections   count and inspectable purpose
Local diagnostics              enabled, bounded and redacted
```

### 6.9 Administration and developer mode

- `FR-ADM-001` Telnet and inetd-based remote shells MUST not be present in the
  release image.
- `FR-ADM-002` There MUST be no hidden support shell, magic password or operator
  credential.
- `FR-ADM-003` SSH MUST use public-key authentication; password root login MUST
  be disabled.
- `FR-ADM-004` Normal release mode SHOULD keep network SSH disabled.
- `FR-ADM-005` Developer Mode MUST be explicitly enabled for a bounded duration:
  15 minutes, 1 hour or until reboot.
- `FR-ADM-006` Enabling, extending and revoking Developer Mode MUST create a
  local audit event.
- `FR-ADM-007` UART recovery access remains a physical recovery boundary and is
  not replaced by the web UI.

### 6.10 Observability

- `FR-OBS-001` Logs MUST be circular, size-bounded and redact credentials,
  client identities and protected data.
- `FR-OBS-002` Radio events, service transitions, kernel fatal markers and
  management loss MUST be timestamped.
- `FR-OBS-003` Metrics MUST include CPU, Linux-visible memory, thermal state,
  interface counters, association count and accelerator state where available.
- `FR-OBS-004` Exported diagnostics MUST include a manifest describing exactly
  which categories were collected and redacted.
- `FR-OBS-005` Permanent high-volume debug tracing MUST be disabled in release
  mode and selectable by bounded diagnostic profiles.

## 7. Security requirements

- `SEC-001` The management UI/API MUST use authenticated HTTPS with modern TLS
  within the limits of the platform.
- `SEC-002` State-changing browser requests MUST have CSRF protection and a
  short authenticated session lifetime.
- `SEC-003` Input crossing UI/API, config, shell or vendor-tool boundaries MUST
  be schema-validated and safely encoded; arbitrary shell concatenation is
  prohibited.
- `SEC-004` The management plane MUST be bound only to intended local interfaces.
- `SEC-005` Release images MUST omit unused interpreters, daemons, CGI handlers,
  protocol stacks and legacy ciphers where ABI constraints permit.
- `SEC-006` WPA2-PSK-CCMP is the minimum wireless security baseline. WEP and
  TKIP MUST be absent from selectable owner profiles unless a documented radio
  ABI constraint makes removal unsafe; they MUST still remain disabled.
- `SEC-007` WPS MUST be disabled by default or require an explicit short-lived
  physical/local action.
- `SEC-008` Firmware updates MUST verify model, structure, declared size, hash
  and slot fit before any write.
- `SEC-009` A release manifest MUST identify all closed-source/vendor blobs and
  their hashes without redistributing material outside its authorized scope.
- `SEC-010` Security claims MUST be based on current image/runtime evidence, not
  solely on absence of strings in an older dump.

## 8. Performance and resource requirements

- `PERF-001` Control-plane services MUST remain responsive while both radios
  carry traffic.
- `PERF-002` UI, telemetry and logging MUST not introduce a packet-by-packet
  userspace path.
- `PERF-003` A release candidate MUST report CPU, memory, temperature, packet
  loss and throughput under the same workload used for its baseline.
- `PERF-004` A change causing more than 10% throughput regression or a material
  CPU/thermal regression against the latest accepted candidate requires an
  explicit waiver and explanation.
- `PERF-005` Memory high-water behavior MUST leave sufficient headroom for
  reconnects, rekeys, DFS events and diagnostic export without OOM.
- `PERF-006` The webformat artifact MUST fit physical `mtd4` (`0x7a0000` bytes)
  with its manifest and entry contracts passing.
- `PERF-007` A claimed accelerated path MUST demonstrate traffic counters and a
  measurable CPU/throughput benefit over its fallback under a controlled test.

## 9. Required UI views

### 9.1 Overview

- Firmware version and running slot.
- Recovery slot preservation status.
- Ethernet, bridge, 2.4 GHz and 5 GHz health.
- Client counts using redacted stable aliases.
- CPU, memory and temperature summary.
- Active warnings with direct remediation.

### 9.2 Wi-Fi

- Separate 2.4 GHz and 5 GHz cards.
- SSID, security, channel, bandwidth, regulatory state and TX power readback.
- Association and traffic state, not merely hostapd process state.
- Staged changes with automatic rollback countdown.

### 9.3 Network

- Physical port/link state.
- Bridge membership and management address.
- Upstream DHCP observations without exposing unrelated client data.
- Multicast/IGMP state when certified.

### 9.4 Privacy

- Remote-management and analytics components: absent, disabled or enabled.
- Current and recent outbound control-plane connections.
- Local telemetry categories and retention.
- One-click redacted diagnostics preview before export.

### 9.5 Maintenance and recovery

- Developer Mode state and expiry.
- Public-key management.
- Read-only firmware/partition identity.
- Firmware validation result before a separately authorized write.
- Clear statement that UART/manual recovery is still required for some failures.

## 10. Features intentionally removed or disabled

| OEM capability | OpenMitraStar disposition |
|---|---|
| operator TR-069 profile | removed or disabled by default |
| MAUI cloud analytics | removed |
| hidden support shell | removed |
| Telnet/inetd shell path | not built |
| Dropbear 0.52 behavior | replaced by maintained key-only SSH |
| legacy CGI control surface | replaced by static UI + typed API |
| unconditional unused VAP creation | create only configured interfaces |
| permanent verbose debug | bounded diagnostic profiles |
| operator-specific config objects | normalized OpenMitraStar schema |
| cross-calling shell glue | explicit service dependencies/state machine |
| WEP/TKIP owner profiles | disabled/removed subject to ABI safety |

## 11. Explicit non-goals for the parity release

- Replacing Bootbase.
- Writing a full-chip image during normal updates.
- Turning the device into the Movistar WAN terminator.
- PPPoE, domestic NAT, VoIP termination or an authoritative LAN DHCP/DNS server.
- Replacing working Quantenna firmware, MuC/AuC/DSP blobs or radio ABI solely
  for source-code purity.
- Claiming WPA3 where the radio/driver stack cannot prove it safely.
- Enabling all available RAM without a complete reservation map.
- Enabling hardware acceleration based only on module load success.
- Cloud accounts, mandatory vendor services or remote owner tracking.

These may become separately specified profiles or research tracks. They are not
allowed to delay or destabilize the owner-controlled videobridge release.

## 12. Release gates

### Gate R0 — immutable inputs and reproducibility

- OEM input hash matches the pinned reference.
- Candidate path, bytes and SHA-256 are recorded.
- Build inputs and vendor blobs are listed by hash.
- Slot-fit, Bootbase and persistent-entry contracts pass.

### Gate R1 — recovery

- `mtd3/linux_safety` and protected-partition hashes remain unchanged.
- Manual UART rollback procedure is current and tested or backed by accepted
  recent evidence.
- No bootenv dependency is introduced.

### Gate R2 — persistent platform

- Repeated cold boot from `mtd4` succeeds.
- Ethernet management and SSH recovery readiness pass each cycle.
- No new kernel panic, Oops, fatal MMU, DMA or filesystem marker appears.

### Gate R3 — secure dual radio

- 2.4 GHz WPA2 client acceptance passes.
- 5 GHz WPA2 client acceptance passes using the private persistent credential
  without secret disclosure.
- Wrong-key, reconnect, rekey and scoped radio-restart tests pass.

### Gate R4 — L2 product path

- Both radios pass upstream DHCP, ARP, DNS, ICMP and HTTPS.
- Bidirectional counters advance on client, radio, bridge and Ethernet layers.
- Management remains reachable during traffic and radio recovery.
- No unintended DHCP server, NAT or PPPoE process is present.

### Gate R5 — regulatory and physical controls

- Country/regulatory state and power-table selection are correct.
- Non-DFS and DFS/CAC/radar behavior pass on applicable channels.
- Radio buttons, reset behavior and LEDs match their documented contracts.

### Gate R6 — security and privacy

- Telnet, hidden shells, legacy cloud analytics and undisclosed remote management
  are absent or disabled as specified.
- SSH is key-only and Developer Mode expiration/revocation pass.
- Outbound connection inventory matches packet-capture evidence.
- UI/API redaction, auth, CSRF and command-boundary tests pass.

### Gate R7 — soak and performance

- Repeated cold boots pass with both radios enabled.
- Long-duration dual-radio traffic/thermal soak passes.
- Packet loss, throughput, CPU, memory and temperature remain within the
  accepted envelope.
- No ARC, QMAC, MuC, AuC, DMA, queue or thermal fatal marker appears.

### Gate R8 — release bundle

- Final webformat image, manifest, SHA256SUMS and source/config provenance.
- Redacted acceptance evidence for every gate.
- Recovery and rollback instructions.
- Known limitations and intentionally disabled capabilities.
- A signed-off GO/NO-GO decision that does not conflate offline, boot,
  control-plane, client, traffic and release PASS states.

## 13. Delivery phases from F150

### Phase 1 — secure the proven 5 GHz path

1. Preserve F150 unchanged as the known-good rollback candidate.
2. Certify WPA2 on the isolated 5 GHz topology using the private credential.
3. Prove wrong-key rejection, reconnect and bidirectional traffic.
4. Produce immutable redacted evidence.

### Phase 2 — integrate the product bridge

1. Add 5 GHz to the intended L2 policy without losing management.
2. Prove upstream DHCP, DNS, ICMP and HTTPS.
3. Verify no competing DHCP/NAT service appears.
4. Repeat simultaneous 2.4/5 GHz traffic and management tests.

### Phase 3 — regulatory and resilience

1. Validate region, power table, channel and bandwidth state.
2. Certify DFS/CAC/radar behavior.
3. Run repeated cold boots, radio restarts and long thermal/traffic soak.
4. Remove the two known nonfatal sysfs permission warnings as a separate
   single-variable candidate.

### Phase 4 — owner product surface

1. Implement the config transaction layer and typed local API.
2. Add the Overview, Wi-Fi, Network, Privacy and Maintenance views.
3. Replace legacy management components and cross-calling shell glue.
4. Certify local auth, redaction, Developer Mode and diagnostics export.

### Phase 5 — accelerated-path optimization

1. Benchmark the accepted fallback/current path.
2. Enable or improve HBM/TQE/FWT components one independently gated step at a
   time.
3. Require observable counter, throughput and CPU benefit.
4. Keep the last accepted data path as a rollback option until soak passes.

## 14. Evidence and claim policy

Every result shall be classified as exactly one of:

- `OFFLINE PASS`
- `BOOT PASS`
- `CONTROL-PLANE PASS`
- `CLIENT PASS`
- `TRAFFIC PASS`
- `PERSISTENCE PASS`
- `RECOVERY PASS`
- `RELEASE PASS`
- `FAIL`
- `INCONCLUSIVE`

The following are never sufficient alone to claim usable Wi-Fi:

- module loaded;
- interface exists;
- carrier is 1;
- hostapd says `ENABLED` or answers `PONG`;
- SSID string is configured;
- IRQ or packet counter changed.

A product claim requires the matching physical-client, traffic, persistence,
security or recovery evidence described by its gate.

## 15. Source-of-truth documents

This specification defines the target product. Current-state and operational
claims remain governed by live evidence and these workspace documents:

- `docs/OPENMITRASTAR_F150_CURRENT_STATE.md`
- `docs/OPENMITRASTAR_HGW500_OPS.md`
- `docs/HGW500BNA_QCV2_OEM_MOVISTAR_PARITY_MATRIX.md`
- `docs/OPENMITRASTAR_PLATFORM_DOSSIER.md`
- the F150 build manifest and timestamped evidence directories

If this specification conflicts with a verified hardware constraint, protected
partition rule or newer accepted evidence, safety and current evidence win and
the specification must be revised.
