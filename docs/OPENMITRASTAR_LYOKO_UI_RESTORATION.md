# Lyoko UI: restore the F314 product design

User correction, 2026-09-05: modernization must preserve the existing Movistar /
Telefonica UI, including its logos, structure and workflows. The generic
six-view redesign was not requested and is no longer the default entrypoint.

## Current continuation: classic UI 0.3.0 installed as F321

Prepared on 2026-09-07 UTC; installed during the 2026-09-07/08 UTC cycle and
independently checked again on 2026-09-11 at 09:13 UTC.

The current static package is
`outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9`, 229,279 bytes with UI
version `0.3.0-classic-dfs`. It retains the three original brand assets, the
139 static DOM IDs, the four original stylesheets and the original controller.
Additional CSS and accessibility handlers fix narrow forms, mobile navigation,
keyboard tabs, labels and focus. A direct `Canales y DFS` route opens the new
channel explorer and observation panel.

The panel distinguishes backend readiness, detector activity, CAC, the NOP
inventory and TX permission. It consumes the optional authenticated
`radios/5g/dfs` observation contract, falling back to F314 diagnostics only
when the endpoint is missing. Missing or inconsistent values remain unknown;
neither an empty malformed NOP inventory nor a local timer can grant permission.
Native observations refresh while the page is visible; older diagnostics stay
manual to avoid heavy polling. Channel inspection leaves the form unchanged
until `Llevar al formulario`, which retains the classic confirmation and
backend-gated transaction flow.

The source backend fix remains a separate offline overlay at
`versions/lyoko-dfs-contract-v1`. It prevents ready-as-TX reporting and checks
for provider loss or channel/width drift during CAC. It is not installed and
is not included in the UI-only candidate.

Verification for this package:

- TypeScript/build and 45 frontend behavioral tests: PASS.
- 85 packaging, API identity, inventory and emulator tests: PASS.
- Original CGI/session logic: 18 host-isolated checks PASS on pinned F314.
- Original mini_httpd/API integration: 21 host HTTP checks PASS on pinned F314.
- Packaged browser observations: no content overflow at 320, 390, 820 and
  1280 px; original branding, drawer/focus, keyboard tabs, meteorological CAC,
  channel inspection, confirmation and cancel-without-apply observed.
- JS Brotli budget: 40,168 bytes; CSS Brotli: 9,340 bytes. Both PASS.

Reports are beside the package manifest. `browser-observations.json` describes
manual browser observations, not an automated full accessibility certification.
The loopback emulator accepts `--dfs-scenario` to exercise fixed synthetic
states without RF. Its software is excluded from the firmware package.

The physical HGW now has **F321 built from exact F314** installed in
`mtd4/linux_live`, retaining the existing native kernel and radio controls.
The installed image is `5,337,088` bytes, SHA-256
`eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`.
The authorized cycle at
`outputs/flash-watch/f321-direct-20260907T235105Z-b42111c6` records full-slot
CRC32 `6ed8e483`, exact comparison of all candidate bytes, preserved protected
partitions and boot from mtd4. Hardware SHA-256 was not measured.

Its original promoter result remains `STOP_NO_AUTOMATIC_RETRY` because the
host parser classified a Linux PCI BAR assignment warning as a Bootbase error
after the successful flash readback. Independent platform and authenticated
HTTP checks passed on 2026-09-08. The UI gate's original legacy-JavaScript MIME
failure is preserved; correcting that host check did not change the firmware.

Fresh evidence under `outputs/postflash/f321-independent-20260911T091309Z`
records platform PASS (27 checks), UI/API/public HTTP PASS (12 installed file
hashes and 13 HTTP checks), and authenticated HTTP PASS (10 checks). Login,
the exact dashboard and frontend bundle, session API and logout invalidation
were exercised on the actual device. The pinned release is
`lyoko-foundation-6.8.5-f321-classic-ui-f314-device`, build `ad60c8e1e49dfbbf`.
File-only reconciliation at
`outputs/postflash/f321-acceptance-20260911T091500Z/result.json` records
`PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION` and preserves the original STOP.
See `docs/OPENMITRASTAR_F321_CLASSIC_UI_CANDIDATE.md` for the exact artifact,
immutable execution history, individual reports and recovery boundary.

This proves the installed UI files and native HTTP/session path; the packaged
browser observations above remain host observations. On-device browser
JavaScript, HTTPS/TLS, repeated cold boots, fresh physical client traffic and
CAC/DFS RF acceptance remain unproved by this campaign. **F322 is offline only**:
it adds disarmed shadow observation over the same UI and does not grant DFS
authority. See `docs/OPENMITRASTAR_F322_SHADOW_CANDIDATE.md`.

## Current implementation

`work/lyoko-web-next/src/main.tsx` renders `classic-app.tsx`. The complete F314
body is mechanically converted to static TSX without replacing its 139 DOM IDs,
classes, profiles, tabs, setting inspector, channel map or transaction controls.
The four original stylesheets, Movistar wordmark, Telefonica logo and router M
image are recovered byte-for-byte from the pinned F314 SquashFS:

`ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce`.

The original JavaScript transaction controller is retained during this stage.
The typed channel explorer and DFS observer now run inside that console; moving
an inspected channel into the form still uses its original confirmation flow.
Full migration of the transaction controller to TypeScript remains future work.

Source provenance: `work/lyoko-web-next/reference/classic-provenance.json`.
Generator: `tools/restore_lyoko_classic_ui_source.py`.
Regression checks: `work/lyoko-web-next/tests/classic-branding.test.mjs`.

The packaged local preview is served directly by the F313/F314 API emulator at
loopback port 4180. A Vite server is not required for this packaged preview.
The UI explicitly reports `Emulador`. These are synthetic readings, not physical
router results. No router, UART or flash action is involved.

## Explicit channel laboratory simulator

The host runner accepts `--lab-channels` on loopback only. In this mode all 28
catalogue channels can be staged, applied, committed and rolled back in the
emulator's RAM. This is a test mode of the Python HTTP server, not a new RF
backend or a setting that can be flashed to the router. Unknown manual channel
numbers remain inspection-only unless they are in the simulator catalogue.

`GET /api/v1/lab` and every simulated JSON response expose `simulation=true`,
`rf_transmission=false` and `physical_association=false`. The classical UI adds
an explicit laboratory badge and replaces the simulated DFS dialog's backend
description. No simulated ready flag is evidence of physical radar readiness.

`tools/test_lyoko_channel_lab.py`: 30 HTTP-level tests pass, including one
apply/readback/rollback cycle for every catalogue channel, CSRF and transaction
identity rejection, explicit-mode detection and preservation of the ordinary
emulator's restrictions. Browser inspection confirms that accepting the channel
warning enables preparation while application remains a separate action.

The typed channel catalogue and warning adapter run inside the original
console, retaining the original logos, styles and controller. F314/F319 radio
or flash gates have not been changed by the simulator work.

## Acceptance conditions carried forward

- Preserve both brands and the original white-console design.
- Preserve all classic pages, profiles, 2.4/5 GHz controls and transaction flows.
- Include the full channel catalogue, with explicit explanations and warnings
  for selections outside the verified regulatory/hardware profile.
- Distinguish CAC, weather-band CAC and post-radar NOP, considering bandwidth.
- Integrate physical radar/DFS and the portable optimization engine with real
  telemetry, readback and rollback evidence.

The earlier `lyoko-web-next-*` overlays under `outputs/frontend/` contain the
superseded visual prototype. Their passing size/hash checks do not qualify them
for deployment as a replacement for the classic UI. The restored build adds
multiple JS chunks and original media.

## Restored-console package verification

Earlier package: `outputs/frontend/lyoko-classic-tsx-5de8852058ef58ec/manifest.json`.
The packager now supports hashed JS/CSS chunks and preserves the three original
brand assets at their `/assets/` URLs. Output names are content-addressed;
rerunning an identical build verifies and reuses the package instead of creating
another candidate. Existing staging siblings are never deleted.

The 192,166-byte overlay contains ten files and one exact API transform. Applying
it to pinned F314 and F317 changes eight files; the three branding files remain
byte-identical. Two
independent native-Linux builds pass for each base, preserving all other entry
contents, owners, permissions and links:

| Base | Test SquashFS bytes | Rootfs headroom | Hash |
| --- | ---: | ---: | --- |
| F314 | 3,756,032 | 831,488 | `1d47bc2f41c356afdc1bd4b7c21015af2df09848f864eab305f50455bdd8c018` |
| F317 | 3,825,664 | 761,856 | `bfc52fa0a233a83db796ffea3c79205104ec6f63771e99d6532a8a244a4082e8` |

Evidence: `rootfs-integration-native-f314.json` and
`rootfs-integration-native-f317.json` beside the package manifest.
Twenty-six packaging, native-delta and identity-transform tests pass.

That earlier package explicitly remains `release_eligible=false` and
`flash_supported=false`; its immutable flags have not been reinterpreted as a
device result. Host HTTP/TLS and browser evidence is described below, while the
later installed F321 package has its own device checks above. The Python
channel-laboratory backend is not packaged. Passing simulation tests does not
enable physical radio transmission in this overlay.

## Authentication logic executed from the pinned firmware

`tools/verify_lyoko_cgi_sessions.py` now executes the exact `om-oem-cgi` and
`om-api-v1` shell scripts from each pinned image in a minimal Linux chroot with
host-native POSIX tools. The CGI is unchanged; the API receives only the declared
hash-pinned frontend identity transform that will be packaged. It supplies
only a synthetic password hash and temporary client-bound sessions; no real
credentials or radio/network control executables are installed in the test root.

Eighteen behavioral cases pass on each base (F314 and F317): anonymous and
unknown sessions, exact new dashboard bytes for a valid session, security
headers, wrong client, expiry, malformed expiry, invalid cookie paths,
disallowed methods, anonymous API rejection, authenticated session API, login,
secure cookies, logout, failed-login rate limiting, rejection of anonymous
frontend metadata requests and exact identity of the authenticated split bundle.

Evidence beside the current package manifest:
`cgi-sessions-isolated-f314.json` and `cgi-sessions-isolated-f317.json`.
These reports qualify the shell-script authentication logic. They do not prove
ARC instruction execution, mini_httpd HTTP/TLS behavior, the browser-to-CGI
session workflow or radio hardware. Those remain acceptance gates.

## Frontend identity synchronization

`etc/lyoko/frontend.env` now identifies the active TSX version/build and the
new internal HTML. Fixed-path legacy asset hashes still describe the retained
files, with their exact byte total updated. `/api/v1/frontend` keeps its previous
fields and adds `asset_layout=split-v1` plus `bundle`, containing the exact active
HTML, JS chunks, CSS and brand URLs, lengths and SHA-256 hashes.

The transform in `tools/lyoko_frontend_identity.py` accepts only the pinned F314
and F317 API hashes, modifies only the frontend branch and preserves the
authentication guard. The native verification checks its exact before/after
hash, every metadata reference and all unrelated contents and permissions.
The local emulator can use the same packaged identity when started with this
package. No emulator-only radio flags enter the firmware overlay.

## Native HTTP and browser qualification

`tools/verify_lyoko_http.py` matches the source hash of mini_httpd used by F314
and verifies the shipped ARC binary hash before building a host-native server.
The server runs in a minimal chroot on an ephemeral loopback port, using the
firmware CGI/API scripts and the packaged frontend identity transform.

Twenty-one HTTP checks pass on each base, including login, protected dashboard,
absence of the public HTML bypass, session cookie flags, exact asset hashes,
JavaScript/CSS MIME types, CSP, frontend identity, CSRF header forwarding and
logout. Evidence: `native-http-f314.json` and `native-http-f317.json` in the
current package directory.

Browser observation also verified synthetic login, TSX/controller loading,
both logos, the new UI build label, navigation and logout followed by rejected
dashboard access. The minimal environment intentionally has only two of the
nineteen runtime data providers; the UI reported that partial state. See
`browser-observations-f314.json`. The browser-hold command did not produce its
final report, so these are explicitly separate observations, not a fabricated
automatic-run result. The server process was absent on recheck.

HTTPS/TLS and actual ARC/hardware execution are not proved by those host HTTP
tests. The later F321 campaign above records native device HTTP/session checks
separately. Subsequent host TLS qualification and prospective ARC linking are
documented in `docs/OPENMITRASTAR_TLS_MODERNIZATION.md`; that TLS integration
has not been installed by the UI-only F321 campaign.

## Subsequent HTTPS integration, 2026-09-06

The original layout and media remain unchanged. The prospective server now
links wolfSSL 5.9.2 for ARC700 and fixes server-owned HTTPS CGI identity plus
the missing HTTPS `api/v1/*` route. Host tests pass 22 checks for each of TLS
1.2 and 1.3 on both pinned firmware bases. Combining the existing classic UI
with only the new TLS executable and configuration produces reproducible
temporary rootfs images of 3,395,584 bytes (F314) and 3,465,216 bytes (F317),
preserving all unrelated files and metadata.

See `outputs/userland/ui-tls-rootfs-f314.json`,
`outputs/userland/ui-tls-rootfs-f317.json` and the TLS modernization document.
These are offline integration proofs, not new installed firmware or real
radio-channel enablement.
