# HGW LED control and boot measurements — 2026-10-21

The owner declined the Wi-Fi client test today. The earlier "does not appear"
reply is not a performed scan or a proven visibility failure. Client visibility,
association and bidirectional traffic remain UNRUN. This PC currently exposes
Ethernet and virtual network adapters, with no Wi-Fi adapter available.

## Current observation

Pinned read-only SSH confirms the same F367r9 boot
`5f513265-a294-4366-9567-e1d8af704b6b`, Linux 5.10.260, ready state,
2.4 GHz ENABLED, 5 GHz hostapd PONG/RF1 and bounded fatal count0.
The two Wi-Fi LED class requests are255; signalB/G/R and stage0 are0.
This does not disprove the owner's visible lower lights: the recovery driver
has no electrical brightness getter. Its two GPIO9 class devices can maintain
independent cached requests. No raw GPIO, /dev/mem or identification sweep ran.

Evidence: `outputs/rea/arc700-20261021-r2/led-boot-readonly-20261021T214901920214Z`.
The first read-only probe stopped at an unsupported BusyBox `sed` option;
its incomplete result is preserved separately. The corrected probe completed.

## LED candidate

Exact source SHA256 `0df28604268964c7a99c26f831d94d4e7ae1a06bce86189b1bb97567ae711b47`
matches the running CLI and preserved F365/F367r9 images.
The new CLI fixes unresolved stage0 listing, boot wrongly mapped to redGPIO7,
normalized rather than exact brightness restoration, continued identification
after signals, and false success after restore errors. It reports cached
requests and GPIO9 alias coherence, and rejects incomplete/ambiguous snapshots.

Candidate:
`outputs/rea/arc700-20261021-r2/led-cli-candidate-r2-20261021T215300Z/om-ledctl`,
SHA256 `0b2509b8dbd628174b952d6b115c6e6be3a39f89b96514e2f17290fae5e81753`.
25 fake-file assertions PASS; actual target `/bin/ash` list/status also PASS
without installing or writing LEDs:
`outputs/rea/arc700-20261021-r2/led-cli-target-readonly-20261021T215603033826Z`.
Hardware write/restore paths still require their own physical gate.
The kernel GPIO9 ownership issue and visible lower-light cause remain unresolved.

## Boot timing candidate

The current rcS processes services sequentially and records start/end without
time. The live script SHA256 matches the offline source:
`2435abe03da459ff82f8ca77bf2a447f30c043c9e69c6da1a411702dfafc0592`.
No usable service-duration records remain in current logread.

An offline timing-only rcS candidate adds uptime reads using shell builtins and
separate timing records. It preserves original log messages, service order,
exit-status capture, entropy failure handling and retry deadlines.
Candidate SHA256 `d5870a307ee1514689ca134cb51a25effdc932ccaa715168737cdedf65e30653`:
`outputs/rea/arc700-20261021-r2/boot-timing-candidate-20261021T215129281623Z/rcS`.
Syntax and fake healthy/radio-failure/entropy-failure comparisons PASS:
`outputs/rea/arc700-20261021-r2/boot-timing-tests-20261021T215700Z`.
The first fixture incorrectly used an ordinary file as console, truncating logs;
it is retained. Corrected fixture uses captured stdout. No physical speed gain
is claimed; a future versioned image and boot measurement are needed.

Existing sealed F372 image, manifest and install plan remain unchanged.
These LED/timing candidates are not installed or full-image releases.
No reboot, flash, UART operation, radio mutation or bootenv write occurred.
