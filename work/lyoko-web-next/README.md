# Lyoko Web Next

> Public source snapshot. [Scope, provenance and verification](docs/PUBLIC_SNAPSHOT.md).

The current classic build is `0.3.0-classic-dfs`, package
`outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9`. It adds responsive and
keyboard fixes plus a direct channel/DFS observation view without replacing
the original branding, IDs, styles or controller. The selected offline firmware
is F321 over pinned F314; see `docs/OPENMITRASTAR_F321_CLASSIC_UI_CANDIDATE.md`
from the workspace root. It has not been installed. DFS physical validation
remains separate.

For the packaged local preview, run from the workspace root:

```powershell
python tools/run_lyoko_web_next_emulator.py --package outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9 --bind 127.0.0.1 --port 4180
```

Optional `--dfs-scenario weather-cac` demonstrates a fixed simulated CAC
reading. All scenario responses identify simulation and no RF. The emulator is
never packaged for the router. The older measurements below are historical.

Current product direction (2026-09-05): restore the original F314 Movistar /
Telefonica design. `src/main.tsx` now uses `classic-app.tsx`, with all 139 original
DOM IDs, four byte-identical stylesheets and original logos. Its controller is
still legacy JavaScript while typed handlers are ported incrementally. The
six-view redesign in `src/app.tsx` is experimental and is not the default UI.
See `docs/OPENMITRASTAR_LYOKO_UI_RESTORATION.md` in the workspace root.

The restored-console package is now validated at
`outputs/frontend/lyoko-classic-tsx-5de8852058ef58ec`. It includes hashed chunks
and the three original brand assets at their original URLs. Its native F314 and
F317 integration reports and 18 host-isolated CGI/API cases per base pass. The
authenticated frontend API identifies the active split bundle. HTTP/TLS/browser
integration and physical regression remain deployment gates. It is not a
flashable firmware. Run `python tools/package_lyoko_web_next.py` from the
workspace root to create or verify the content-addressed package for a build.

The build measurements and overlays below describe the superseded prototype,
not a release-qualified replacement for the classic console.

Host-built, router-served UI for OpenMitraStar and future Lyoko board targets.
The router runs no Node.js runtime: Vite and TypeScript only produce immutable
static assets. The application uses the existing authenticated `/api/v1`
contract and falls back to a clearly labelled laboratory snapshot when opened
outside a router.

## Design boundaries

- Preact + Signals, no full React runtime.
- No remote fonts, CDN, analytics, `eval`, inline event handlers or HTML injection.
- Same-origin credentials and API calls only.
- ES2020 target; responsive and reduced-motion aware.
- JS Brotli budget: 48 KiB. CSS Brotli budget: 16 KiB.
- Hashed assets suitable for immutable caching and SquashFS packaging.
- No service worker, avoiding stale control-plane UI after firmware upgrades.
- Functional desktop sidebar and persistent mobile navigation for all six views.

## Build

```powershell
npm ci
npm run build
npm run check
```

Verified production result on 2026-09-05:

- JavaScript: 32,751 bytes raw / 11,235 bytes Brotli.
- CSS: 8,382 bytes raw / 2,407 bytes Brotli.
- TypeScript, bundle budgets, desktop/mobile browser checks and npm audit: PASS.

The next integration step packages `dist/` beside the existing authenticated
CGI shell while keeping the current API and rollback image unchanged.

The adapter accepts the F314 API as a partial capability set: a missing future
endpoint such as F317 optimization no longer replaces valid live status and
radio data with the laboratory snapshot.

When F317 is present, the same UI consumes its native optimization contract:
mode, volatile persistence, supervisor/engine state, sequence, last decision
and the explicit `automatic_apply=false` boundary.

Native Linux integration checks pass on pinned F314 and F317, including all
directory/file permissions, owners, links and hashes. The rebuilt sizes are
3,727,360 and 3,792,896 bytes, with 860,160 and 794,624 bytes of headroom.
Only four frontend files change and one directory is added. See the
`rootfs-integration-native-f314.json` and `rootfs-integration-native-f317.json`
reports under `outputs/frontend/lyoko-web-next-f314-f317-contract-20260905`.

This is still a prototype: classic CGI transaction/control parity and an
authenticated runtime test are pending. Packaging PASS does not authorize
replacing the proven console. The native reports supersede the older NTFS-based
metadata comparison.
