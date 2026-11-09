# F321 browser acceptance and compatibility corrections

Observed on 2026-09-11. The router remains on F321; this work did not flash,
reboot, open UART, apply radio settings or write the persistent store.

## Actual browser result: partial, not release acceptance

`outputs/postflash/f321-browser-20260911T094000Z/result.json` records an
interactive browser smoke test against `http://192.168.1.90`, not localhost or
demo mode. Pinned SSH at 09:40:00 UTC identified Linux
`5.10.260-openmitrastar-radiohw`, release
`lyoko-foundation-6.8.5-f321-classic-ui-f314-device`, build `ad60c8e1e49dfbbf`.

Normal login, JavaScript mount, real dashboard data, Home/Diagnostics/DFS/5 GHz
navigation and logout worked. The original Movistar and Telefonica branding
was visible. Selecting channel 120 in the inspection panel changed only the
local selection: Apply/Confirm stayed disabled, no configuration POST was
observed, and the 5 GHz form retained channel 36 / 80 MHz. The dashboard
redirected to login after logout. The temporary browser tab was closed.

Two defects prevent calling the browser integration complete:

| Defect | Physical observation | Cause |
| --- | --- | --- |
| Config-store status | HTTP 502 `config-store-contract`; `Parcial 18/19` and `No disponibles: configStore` | The old API's escaped opening brace is invalid in the HGW grep's BRE syntax. |
| DFS compatibility | `/api/v1/radios/5g/dfs` returns HTTP 200 with `lyoko.radio.status/v1`, `id=5g`; the panel says no recognized DFS contract | The legacy CGI ignores PATH_INFO, while the UI only falls back to diagnostics after HTTP 404. |

At 09:50:18 UTC a bounded pinned-SSH read tested the old and replacement
patterns with both a constant and the real `om-config-store status` output.
The old pattern returned 2 (`Invalid preceding regular expression`); `^[{]`
returned 0. The helper itself returned 0. Its feature remained disabled and
the store remained not ready. No modified CGI was executed on the device.
See the adjacent `ssh-regex-readonly.log` and `network-status.json` evidence.

## Offline corrections, not installed

- `work/lyoko-web-next/src/dfs-observation.ts` recognizes only the explicit
  legacy success/status/5g alias and then validates the legacy diagnostics
  envelope. Authentication, transport, malformed JSON, unknown schemas and
  native errors are not hidden by that fallback. Legacy CAC/NOP/TX remain
  unknown; no timer or readiness flag grants transmission authority.
- `tools/lyoko_config_store_status_contract.py` is a pure transformation of
  exact F321 API bytes, SHA-256
  `849ffe6a503d3be2a3083116dcafb6a6c4adf32f7eeee4a727bf64391caa1b09`.
  It changes only that guard to the literal-brace form. The result is 50,253
  bytes, SHA-256 `f7e6568f9749a848f0f5f9b75cd7eec8b4d0346d2214cb987f0b173a6ad763e1`.
  POST behavior, store permissions and the helper are unchanged. Other inputs
  and double application are rejected.

Verification:

- API/DFS focused Node tests: **27/27 PASS**.
- Config-store transformation/branch tests: **9/9 PASS**. These execute the
  extracted CGI branch with original header/error functions and temporary
  fake helpers, not a complete authenticated HTTP server. POST dispatch is
  stubbed; no real write branch is run.
- TypeScript `--noEmit`: PASS.
- Production static build: PASS at
  `outputs/frontend/lyoko-browser-compat-20260911T095313Z/dist`.
- CSS and all three brand assets remain byte-identical to installed F321.
  Build-time Brotli measurements are 40,232 bytes JS and 9,340 bytes CSS, within
  the existing 48 KiB / 16 KiB budgets. This does not claim Brotli serving or a
  device memory/performance benchmark.

Source/artifact hashes and exact verification scope are recorded in
`outputs/frontend/lyoko-browser-compat-20260911T095313Z/verification.json`.
The local sealed F321 and F322 images retain their prior exact hashes. No new
firmware image or flash authorization was produced by this work.

## Next gate

Update at 2026-09-11 14:16 UTC: these corrections are now integrated in the
reproducible offline F323 image described in
`docs/OPENMITRASTAR_F323_BROWSER_COMPAT_CANDIDATE.md`. F321/F322 artifacts and
the original browser evidence above remain unchanged. F323 is not installed.

Qualify its exact executor and recovery path before any separately authorized
installation. On the actual
installed result, require all 19 panel reads to succeed, legacy DFS observations
to display honestly, and normal login/logout and radio regression to pass.

Full migration remains incomplete: repeated cold boot and recovery, fresh
2.4/5 GHz client traffic and soak, native radar/CAC/evacuation/NOP, persistent
configuration and HTTPS/TLS are not proved by this browser test. A working
`mtd3/linux_safety` rescue rootfs is still unproved; exact F314 restoration to
mtd4 remains the documented tested recovery, not a silent substitute for that
remaining acceptance requirement.
