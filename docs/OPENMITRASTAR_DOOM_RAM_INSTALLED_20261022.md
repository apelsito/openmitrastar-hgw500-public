# Doom and LED CLI installed in RAM — 2026-10-22

Later owner clarification keeps the original episode1 only, with all wrapper
text and controls in English. The live index is now8,980bytes, SHA256
`f05c849f945e56f4250a7800e627a732e9711746465c8359d5cfeb270d5baa33`.
`outputs/doom/english-live-20261021T222852032297Z/result.json` records installation;
`outputs/doom/router-english-test-20261022-r1/result.json` confirms actual play.
The open browser tab was refreshed and visibly shows English controls.
No fullgame picker, Freedoom assets or commercial game assets were installed.

The requested persistent integration was actually repacked as F373 offline:
combined rootfs7,782,400bytes exceeds the4,587,520-byte window by3,194,880bytes.
No usable flash artifact is available from this composition. The fixed store
and protected firmware are not free space for this request. RAM state remains.

Owner requested actual installation, then clarified the hidden route `/Doom`
without a homepage link, available to clients on the local network. Doom now
works at `http://192.168.1.90/Doom` (redirecting to `/Doom/`). The router serves
static files; the visitor's browser executes the WebAssembly engine.
There is no game account, external game service, or multiplayer server.
The unlinked route is not encryption or authentication. The original management
homepage and login continue serving their original content.

## Physical result

Installation evidence:
`outputs/doom/ram-install-20261021T221151463720Z/result.json`,
status `PASS_DOOM_HTTP_ASSETS_AND_LED_RAM_INSTALLED`.
Ten static files were checked by SHA256 over HTTP from the physical HGW.
The playable bundle is `outputs/doom/browser-20261022-r2-touch/www/Doom`:
5,987,201 bytes; index SHA256
`92e5b55eb9ed45e67c95a153dc0ec0cf13ecfc6e34efe03c89302146b51bdb2c`.
It retains the complete original Doom 1.9 shareware archive, engine/license
records, and upstream source archive. Binary/source exact rebuild correspondence
is not independently proven; the package's PROVENANCE.json preserves that limit.

Actual router browser evidence:
`outputs/doom/router-browser-test-20261022-r2/result.json` and
`touch-real-gesture-result.json`. Doom entered E1M1; movement and firing changed
the game frame. Actual touch gestures also moved the game, without stuck keys.
No external requests, WebSockets or JS errors were observed. Savegame creation
was observed in the browser's virtual filesystem; cross-session save persistence
is not qualified. The existing server's generic WASM MIME type triggers the
engine's supported ArrayBuffer fallback, and actual play passed.

The RAM-mounted corrected `/usr/sbin/om-ledctl` has SHA256
`0b2509b8dbd628174b952d6b115c6e6be3a39f89b96514e2f17290fae5e81753`.
Read-only status works on the target. This installation did not run an LED
identification sweep or change brightness.

## Runtime and recovery

An 8MiB tmpfs holds the current web tree plus Doom under
`/run/openmitrastar/doom-20261022-r1/files`; this is bind-mounted on `/www`.
The corrected LED CLI is also bind-mounted. The installer restarted only the
port80 mini_httpd process with its existing configuration, preserving management
authentication and session files. Its old cwd did not see a newly bound tree,
so the initial HTTP404 attempt was rolled back and retained as failed evidence.

The ARC helper was rebuilt without libc after the first helper contained
unsupported atomic instructions. The rejected run and all builds are retained.
Final helper is 3,136bytes, two identical builds, no `llock`/`scond`, SHA256
`3ed845185777299ca2f2798daa31c2d0d932502e1afdde6341c4c8fb745181b5`.
Final build: `outputs/doom/ram-mount-20261022-r5-nolibc/manifest.json`.

Same F367r9 boot: `5f513265-a294-4366-9567-e1d8af704b6b`.
2.4 GHz ENABLED, 5 GHz PONG/RF1, watchdog00000000 and bounded fatal0.
Store SHA256 `fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873`
and active config SHA256
`073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9`
remain unchanged. After installation MemAvailable was10,456KiB.
Preservation evidence: `outputs/doom/preservation-20261021T221303847992Z`.

No reboot, UART, MTD, bootenv, calibration or radio mutation occurred.
The game and LED CLI are installed for this boot and disappear on power loss.
Boot timing rcS and F372 firmware are still not installed. Persistent firmware
installation still requires exact image gates and verified recovery; the known
mtd3 rootfs/management failure is not waived by generic GO.
The original radio/client/traffic/persistence/release goal remains incomplete.
