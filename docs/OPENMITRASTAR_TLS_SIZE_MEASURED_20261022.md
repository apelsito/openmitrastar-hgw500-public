# Actual F372 TLS replacement size measurement — 2026-10-22

The existing ARC700 wolfSSL trial saves **360,448 bytes (352 KiB)** in the
complete F372 SquashFS rootfs. This is a measured combined-rootfs saving,
not an estimate made by adding individual compressed file sizes.

No hardware access, runtime installation, firmware composition, flash, reboot,
network listener or recovery operation was performed. The rootfs products are
private analysis files and are not firmware release artifacts.

| Item | Bytes |
| --- | ---: |
| Original F372 rootfs | 3,809,280 |
| Unmodified control repack | 3,809,280 |
| Same F372 with the TLS executable substituted | 3,448,832 |
| **Actual complete rootfs saving** | **360,448** |
| Existing permitted rootfs window | 4,587,520 |
| Headroom before substitution | 778,240 |
| Headroom after substitution | 1,138,688 |
| Old `mini_httpd-tls` executable, uncompressed | 1,300,436 |
| Existing wolfSSL trial executable, uncompressed | 463,384 |
| Raw executable difference | 837,052 |

The raw binary saving overstates the actual flash saving by 476,604 bytes.
Both executables compress; the relevant measurement is the complete rootfs.

## Exact inputs and checks

The source is the sealed F372 image
`e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9`,
manifest `e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5`.
The control repack reproduces the original rootfs **byte for byte**, including
its SHA-256
`fdffe1ad2798fb8938a847bcc1736fe370cd017a1a71c90b66097aaeac5441b6`.

The trial is the existing
`outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial/mini_httpd-wolfssl`,
SHA-256 `b105f5c80010b2cb09120e9c7b6dbee0cd2f4ea67be9834d66015f96b0102575`.
The analysis rootfs SHA-256 is
`7a762d94d01b4802cbd18fe76afa110f37d584c4399f52a6b76dbd874df8aaef`.

The only changed rootfs entry is `usr/sbin/mini_httpd-tls`. All **466 other
entries** retain their content, file type, modes, owners, symlinks and hardlinks.
Complete inventories were checked before and after each pack/extract roundtrip.
All five inherited artifact catalogs pass: radio2g12, radio5g40, storage12,
temperature5 and watchdog2. None binds the substituted TLS executable, so no
catalog or inherited runtime-binding entry required a change. HTTP, HTTPS
configuration, web UI, drivers, firmware, regulatory inputs and identity remain
present and unchanged. Existing sealed source files were rehashed afterwards.

The measurement uses the same pinned `mksquashfs`/`unsquashfs` binaries as F373,
XZ/128KiB blocks, `-all-root`, no xattrs/exports, epoch1790006400, and one
processor. One unmodified control and one changed repack were executed; there
was no repeated trial build or physical test.

Reproduce with `python tools/measure_f372_tls_repack.py`. Each run creates a
new private timestamped analysis directory; existing outputs are refused.

Public receipt:
`outputs/inventory/tls-size-20261022T092507734208Z/result.json`, SHA-256
`147e7cf46d89907182c3da29afbd688a04ce3c19c16ddec78d9dc3149ac24795`.
Private complete result:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f372-tls-size-20261022T092507734208Z/result.json`,
SHA-256 `8b1b21feeedfd7aabd5fee98961c60dbead07778438234dd2fddf6c921abbf7b`.
Tool SHA-256:
`87d1c4546db078eafee826f355f95a08276635b21ef572e12d863f7ed3414836`.

## Qualification limits and Doom

This trial retains **mini_httpd 1.19** and substitutes a newer TLS library,
wolfSSL 5.9.2. It is not a newer HTTP implementation or a comprehensive security
review. Its prior ARC qualification is `OFFLINE_LINK_PASS`. Physical ARC
TLS/CGI interoperability, RAM use and handshake or startup speed remain unproven.
The inherited OpenSSL-oriented TLS configuration was deliberately unchanged
to isolate binary size; this analysis is not an operational HTTPS candidate.

The actual complete F373 Doom/LED/timing rootfs previously measured 7,782,400
bytes, exceeding the same window by 3,194,880 bytes. **The TLS saving measured
here does not solve that packaging problem.** Merely subtracting this F372
saving would project 7,421,952 bytes, still 2,834,432 bytes over the window;
that arithmetic is not a measured F373+TLS co-repack. A complete integration
must be measured separately, with all required game, music, driver, license
and management features preserved. Store or protected partitions are not
additional firmware capacity.
