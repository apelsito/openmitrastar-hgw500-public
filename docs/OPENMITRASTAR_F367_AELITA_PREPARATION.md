# F367 AELITA client harness, prepared offline

The configuration is `configs/f367_aelita_client.json`. Image, installation and
AP readiness are deliberately unbound. The generator has no execute option;
its output has `execution_allowed=false`. No client, HGW or main-router operation
was performed to prepare this harness.

Run `python tools/f367_aelita_harness.py` to produce a timestamped bundle. It
reuses the existing WPA2 XML/DPAPI and WLAN query functions, canonical pinned
SSH policy, and `tools/openmitrastar_l2_speed_server.py`. Existing historical
physical runners are unchanged. The known AELITA reference at
`outputs/handoff-live/aelita-wired-and-internet-reference-20260922T112644Z/result.json`
only measures the main-router path; it is not HGW client evidence.

## Future root integration

Before dispatch, bind an exact qualified F367 image and completed installation.
The image object needs `path`, `sha256`, `bytes`, `version` and a
`qualification` object with its result `path` and `sha256`. The installation
object needs its result `path` and `sha256`. The root AP/CAC campaign must supply
an `openmitrastar.f367-ap-client-readiness/v1` receipt binding image hash, boot ID,
channel52/BW20, detector readiness, completed CAC and TX permission. This receipt
is a proposed integration boundary, not existing physical proof. Refresh live
version/boot/AP state over pinned HGW SSH immediately before client dispatch.

The root orchestrator must then authorize a separate execution configuration,
verify its exact source hashes, and run the following phases through the pinned
AELITA `.63` SSH connection. The physical dispatcher is intentionally not added
here while F367 is unbuilt/unaccepted.

1. Capture: prove remote computer `APELSITO`, account `aelita`, SSH local address
   `.63` on Ethernet6, DHCP still Disabled and strong-host send/receive Disabled
   on6 and17. No address, route, DHCP, adapter, firewall or ICS setting is changed.
2. Capture the current profile name separately from its SSID. Export without
   `key=clear`, wrap the XML/state in DPAPI, and keep it under SYSTEM/Admin ACL.
   Copy and hash-check the payload/config/library into that protected stage.
   Run a SYSTEM restoration probe, then arm its240-second independent restoration
   task before allowing connection. The original profile is not modified.
3. Stage the private JSON input through SSH stdin, encrypting it on AELITA as
   `inputs.dpapi`: `run_id`, `test_ssid`, `psk`, `target_bssid_tag`. Follow the
   existing WPA2 secret transport; never place the PSK in arguments or reports.
   Obtain the salted target BSSID tag from the exact HGW snapshot below.
4. Connect once to the temporary WPA2 profile. Require matching salted BSSID,
   channel52, Wi-Fi17 IPv4 and unchanged Ethernet control. The public client tag
   is SHA256 of the run nonce plus lowercase colon-separated current client MAC;
   the raw MAC stays in memory.
5. Root captures `f367_aelita_router_snapshot.sh <nonce> <exact-F367-version>`
   over pinned HGW SSH. It reads hostapd `all_sta`, boot ID and Wi-Fi counters;
   it emits salted station tags and AUTH/ASSOC/AUTHORIZED flags without MACs.
   Match the exact AELITA tag before starting transfers. No AP/DFS state is changed.
6. Start the existing bounded HTTP server on controller `.49:8081`, explicitly
   allowing only the observed client Wi-Fi IPv4. Do not use unrestricted defaults.
   `Traffic` makes4MiB GET and PUT plus HTTPS HEAD, all using IPv4
   `curl --interface <Wi-Fi-IP> --noproxy '*'`. It requires the returned local IP
   to match Wi-Fi17. HTTPS HEAD does not certify DNS resolution over Wi-Fi.
7. Capture the second HGW snapshot while AELITA remains associated. Require the
   same run, firmware/boot and authorized client plus increasing RX/TX bytes.
8. In root `finally`, invoke `Restore`, stop only this run's HTTP server, collect
   `client.json` and `restore.json`, and evaluate with
   `f367_aelita_harness.evaluate(config, client, before, after)` after parsing the
   snapshots. Require exact profile restoration/hash, temporary profile removal
   and unchanged Ethernet. Failed restoration retains the watchdog and private
   backup. Wire loss does not prevent attempting Wi-Fi restoration.

No use of ordinary route selection is accepted for transfers. There is no
unbound fallback when source binding fails. The main router is never configured.
The source-bound external probe is independent of the prior main-router reference.

The client task budget starts after the real AP/CAC gate. This harness neither
waits out nor shortens DFS CAC/NOP/quarantine and cannot enable DFS authority.
Actual restoration, WLAN parsing on this host and physical traffic remain unrun.
