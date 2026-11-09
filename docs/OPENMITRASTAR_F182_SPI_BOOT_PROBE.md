# OpenMitraStar F182 SPI boot probe

Date: `2026-09-01`

F182 combines F180's read-only `lyoko_store` layout with the F181 read-only SPI
identity module.

At boot, `S31-spi-probe` loads the module nonfatally and records:

```text
/run/openmitrastar/spi-probe.state
```

Required physical result:

```text
status=loaded
jedec_id=12722200
expected_device=Y
write_capable=N
```

The module has no MTD registration, erase callback, write callback or register
write instruction. `lyoko_store` remains unmounted and read-only. F182 is an
offline candidate and has not been flashed.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f182-spi-probe-boot/build/openmitrastar-linux510-q3-persistent-f182-spi-probe-boot-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `5,111,808` bytes
- SHA-256: `478687593dbe8f18dee036e4ddc41e3cd04ca85353c7db4a96bfb449eaeb160f`
- Candidate CRC32: `5d13c970`
- Full-slot CRC32: `a67f96c2`
- Full-slot SHA-256:
  `48ef46c9a2b7aa8f0c9ec9506187438ad2397b476708ff3f8c0c347c85e359ed`
- Rootfs SHA-256:
  `8cab244896d98526dc4bb9b3ae963a87a940c15e8bb249a2f7a83f6d543ea049`
- Kernel/DTB: byte-identical to F180
- Offline tests: `7 passed`
- Repeated build SHA-256: identical

F182 must be promoted only after F179. Its wrapper refuses a full-slot flash if
the currently booted kernel already exposes `lyoko_store`, because subsequent
updates must preserve that tail with the future prefix-only flasher.

Dry run:

```powershell
.\tools\build_flash_test_f182_spi_probe.ps1 -SkipBuild
```
