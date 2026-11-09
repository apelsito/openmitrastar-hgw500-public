# Linux 7.3, 2.4 GHz and Doom: final programmed state

Date: 23 October 2026, Madrid local date.

Later owner-authorized cold boot: PASS, recorded at 00:16:15 UTC on
23 October 2026. After five seconds powered off, normal Bootbase autoboot ran
without any UART commands. A new boot ID, exact kernel/product/PID1, 2.4GHz
AP ENABLED ES/channel1 and exact Doom page over pinned HTTPS were observed.
Readiness was observed 33.469 seconds after first Bootbase UART output;
kernel output appeared at 18.36 seconds. This is one normal cold boot, not
a repeatability or soak campaign. No flash or bootenv writes occurred.
The earlier unrun statements below describe the preceding checkpoint.
Receipt: [Normal cold boot](../outputs/rea/radio73-normal-coldboot-20261023-v1/result.json).

The owner requested the final firmware write and prohibited additional traffic,
radio or stress tests. One firmware-prefix erase and one program operation
completed on physical mtd4/linux_live. There were no bootenv writes or writes
to mtd0/1/2/3/5 or the preserved store tail.

Final immutable image:

- Private file: /workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radio73-2g-doom-autostart-20261023-v4/radio73-2g-doom-autostart.ras.bin
- Bytes: 6,063,274.
- SHA-256: c2d39eb2a2fa19d31e75376435956d90eb5529340e09ced827d9b6e0f20e699d.
- Image CRC32: a05df7ce.
- Full slot CRC32 with preserved store: a0898e79.
- Firmware prefix capacity: 6,160,384 bytes; remaining space: 97,110 bytes.
- Kernel: 7.3.0-openmitrastar-radio73-v1.
- Product: lyoko-linux73-2g-doom-flash-r1.
- Load: 0x8493a000; entry: 0x851b6000.

The written image was compared byte for byte against the RAM source. Protected
partition CRCs and store CRC5d2ee646 matched before and after the write.
The image was then read from mtd4 to RAM, CRC-checked and booted. Pinned SSH
confirmed the exact new PID1 executable, product release, 2.4GHz AP ENABLED
under ES/channel1, and Doom files with their exact hashes. One HTTPS request
confirmed that the new system serves the Doom page with the pinned certificate.

The image contains the whole initramfs. Bootbase loads the firmware from flash
into RAM at boot; the kernel does not need a new SPI/MTD implementation for this
variant. PID1 starts Ethernet management, Dropbear SSH, HTTPS, the nineteen radio
modules, hostapd and WLAN DHCP automatically. Wi-Fi: LYOKO-73-TEST.
WLAN management: https://192.168.73.1/.
Doom: https://192.168.73.1/Doom/index.html.
Ethernet management: https://192.168.1.90/ when eth0 is the selected connector.

The same exact image previously passed actual WPA2 association, automatic DHCP
address192.168.73.20 and four bidirectional GET/POST65536 TLS1.2/TLS1.3 checks.
LYOKO authenticated session/logout and actual HGW HTTPS Doom desktop/touch/
movement/fire/PCM passed before the final program. These campaigns were not
repeated after the owner prohibited further tests.

## Receipt distinction

The original installer returned STOP_FLASH_GATE because the specific UART PID1
marker interleaved with the kernel initmem message. That STOP remains immutable.
It inaccurately retains its default flash_writes=0 aggregate field; the same
receipt explicitly records flash_write_attempted=true and erase_attempted=true,
and the separate writer result proves successful write and byte comparison.

The failure handler tried to establish a fresh Bootbase nonce after the kernel
had already taken control. The nonce request timed out, and no restoration
transfer, erase or program occurred. The candidate remains programmed and
operational. The original UART error is not a kernel crash or flash failure.

The final reconciliation binds the immutable writer result, original STOP,
flash readback/CRC/bootm log and live pinned PID1/hash evidence:

- [Final state](../outputs/rea/radio73-2g-doom-flash-final-20261023-v1/result.json).
- [Writer/readback](../outputs/rea/radio73-2g-doom-flash-physical-20261023-v1/candidate-writer.json).
- [Original installer](../outputs/rea/radio73-2g-doom-flash-physical-20261023-v1/result.json).
- [Flash plan](../outputs/rea/radio73-2g-doom-flash-plan-20261023-v1/plan.json).
- [Pre-flash Wi-Fi/DHCP](../outputs/rea/radio73-autostart-wifi-dhcp-v5.json).
- [Pre-flash Doom](../outputs/doom/radio73-autostart-hgw-https-v6/result.json).

## Limits and continuation

A cold power-on after programming was not observed. No measured autonomous
startup time or persistent cold-boot acceptance is claimed. The observed boot
used the exact programmed flash bytes read to RAM; a later owner power-cycle
is still the missing physical cold-boot observation.

Configuration changes remain volatile in this initial whole-initramfs firmware.
Firmware and game data are programmed and persist across poweroff; the old
store is preserved but not used for new configuration commits in this image.

5GHz is not included in this temporary2g firmware and remains pending. The
R26 source/driver and this thread's common kernel context are preserved for
later integration. Do not wake or message the other chat.

Final UART child and parent are terminal, COM4 is closed and the hardware guard
directory has been released. No additional hardware operations are authorized
by this document. The full original port objective remains incomplete.
