# Original Doom episode 1 music — installed and verified in RAM

Parent installed both qualified artifacts on the same HGW boot on2026-10-22.
Installation: `outputs/doom/music-install-20261022T093244020769Z/result.json`.
Actual router browser gate: `outputs/doom/music-http-20261022-r1/result.json`,
`PASS_HTTP_ORIGINAL_MUSIC_PCM_AND_GAMEPLAY`:269,312 actualPCM samples,
269,060 nonzero, RMS0.025687, OPL initialized, movement/fire changed,
noJavaScript errors/external requests. This proves browser audio output,
not a human listening through physical speakers.
Both artifacts are bind-mounted from `/tmp/openmitrastar-doom-music-20261022-r1`
over the existing RAM-served paths. Previous game bytes remain intact beneath.
The source-equivalent patch is served as `/Doom/source-equivalent.patch`.
No flash, reboot, radio mutation or persistent installation occurred.
Earlier candidate-only statements below describe qualification history.

The original Doom 1.9 shareware WAD already contains MUS scores and GENMIDI
instrument data. The wrapper deliberately disabled music through `-nomusic`,
`music_volume 0`, and `snd_musicdevice 0`. Enabling the existing OPL backend
with configuration alone stalls the pinned WASM engine during startup.

The failing configuration-only runs are retained under
`outputs/doom/music-pcm-test-20261022-r3` and `music-pcm-test-20261022-r4-pump`.
Both were bounded and stopped their own local test browser process tree.
No router access, firmware write, or runtime radio changes were performed.

## Cause and repair

The exact pinned upstream archive
`cloudflare/doom-wasm@65e0d3ae2ffa604155eebd96ed40da6567bd08f4`, SHA256
`9be6e02bb1f4f4b00f73d21b0c1ba4f2b8087e3c6cb1f477435baa390b3aa482`,
implements OPL chip detection by waiting for an OPL callback through
`SDL_CondWait`. The synchronous browser startup cannot advance its own audio
callback during this wait. The shipped WASM disassembly has exactly one
`OPL_Delay` callsite, inside `OPL_Detect`.

The candidate replaces this startup delay with a private zeroed buffer mixed
through the existing compiled OPL callback. This advances the same emulator's
clock and callback queue without waiting for browser audio. Playback continues
through the existing SDL Web Audio implementation. Scores, instruments, engine
JS, game state, controls, and runtime music scheduling are unchanged.

`tools/build_doom_opl_startup.py` transforms the exact pinned WASM. Independent
builds produce identical WASM SHA256
`eb47045e861708f4263f994610ed2e58ab63838aff738e3577cca9b68797c20e`,
2,291,176 bytes. Out of 2,631 defined function bodies, exactly one changes:
`OPL_Delay` (defined index 1096; global function index 1355). Type, import,
export, table, data, memory, element and global sections remain byte-identical.
WABT validation passes. The additional WASM size is 8,009 bytes; the music index
is 11 bytes smaller than the previous English index.

The minimal English index is 8,969 bytes, SHA256
`5c8c0c9949161f0d5af4d020c6a8f4b6add20f4548bfe4abf5dac18eaa0efacc`.
It removes `-nomusic`, sets `music_volume 8`, and selects device 3 (SoundBlaster
OPL). No recordings, extra sound banks, or external music requests are needed.

Frozen playable candidate:
`outputs/doom/music-opl-qualified-20261022-r1`.
Identical rebuilds: `music-opl-qualified-20261022-r2` and
`music-opl-qualified-20261022-r3-sourcepatch`.
The third includes a real source-equivalent unified patch that passes
`git apply --check` against exact archived source. This is a supplied source
repair and artifact transformation; a complete source-to-binary rebuild is
not independently demonstrated. Existing engine GPL and upstream provenance
requirements continue to apply.

## Actual browser audio and gameplay evidence

`outputs/doom/music-pcm-test-20261022-r7-qualified/result.json`, SHA256
`dc2f18a1a5b2e1f6ae30a7a177b65df8af993938e6399663a51e58b9328fb748`,
reports `PASS_ORIGINAL_WAD_MUSIC_ACTUAL_PCM`. Ten checks pass:

- fully muted fixture produces 200,704 actual PCM samples, all zero;
- E1M1 with SFX muted produces 159,109 nonzero samples, RMS 0.012817;
- E1M2 with SFX muted produces 197,140 nonzero samples, RMS 0.011095;
- the two track outputs differ, and both initialize the actual OPL SDL driver;
- the default unmodified launch produces music PCM and movement/firing work;
- all AudioContexts run, no JavaScript errors or external requests occur.

The captures observe the actual SDL audio output callback at 96,000 Hz. They
prove rendered music PCM independently of sound effects. They do not claim
that a human listened through physical loudspeakers. The optional favicon
404 is unrelated to music and game assets.

## Deployment gate

Both the index and WASM must be replaced together. Configuration alone is
explicitly NO_GO. No physical installation was performed by this subtask.
The parent installer must verify exact old and new hashes, deploy into RAM
without radio/reboot/flash changes, and verify the physical router's HTTP
assets and actual browser PCM.

`node tools/observe_doom_music_http.js http://192.168.1.90/Doom/ NEW_OUTPUT`
performs read-only HTTP asset pinning, audio capture, and gameplay checks.
It does not modify router files. Firmware persistence and radio acceptance
remain separate unfinished gates.
