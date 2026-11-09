# Topaz UART physical backup (read-only)

This tooling creates a fresh, current-unit physical backup before any flash
write. It uses only these Bootbase primitives:

```text
spi_flash read <physical-offset> 0x83000000 <chunk-size>
md.l 0x83000000 <word-count>
```

It never emits `spi_flash write`, `spi_flash erase`, `saveenv`, or any other
mutating command. The runner has a command allow/deny guard and the source can
be audited before use.

Physical layout:

| MTD | Offset | Size | Name |
| --- | ---: | ---: | --- |
| mtd0 | `0x000000` | `0x020000` | uboot |
| mtd1 | `0x020000` | `0x010000` | uboot_env |
| mtd2 | `0x030000` | `0x010000` | uboot_env_bak |
| mtd3 | `0x040000` | `0x7a0000` | linux_safety |
| mtd4 | `0x7e0000` | `0x7a0000` | linux_live |
| mtd5 | `0xf80000` | `0x080000` | data |

`mtd6` is intentionally excluded. It is a logical rootfs view inside a Linux
slot and is not additional physical storage.

At an already acquired `topaz>` prompt, with COM3 not owned by another process:

```powershell
powershell -ExecutionPolicy Bypass -File tools\capture_topaz_physical_flash_readonly.ps1 -Port COM3
```

The default is 4096-byte chunks. Each chunk is captured into a temporary log,
validated exactly, and only then appended to the partition transcript. A bad
UART block is retained under `chunks/<partition>/rejected/` and retried up to
three times.

Resume the same session without rereading completed partitions:

```powershell
& tools\capture_topaz_physical_flash_readonly.ps1 `
  -Port COM3 `
  -SessionDir outputs\flash-backups\hgw500-physical-uart-<timestamp> `
  -PartitionIndexes @(3,4,5) `
  -ChunkBytes 4096 `
  -MaxRetries 3
```

The runner scans complete command-framed records and resumes from the first
missing physical byte. `-ResumeBytes` is available only with one selected
partition and cannot skip beyond the automatically verified prefix.

The command prints `CAPTURE_SESSION=<absolute-path>`. Reconstruct and validate:

```powershell
python tools\parse_topaz_physical_flash.py --capture-dir "<CAPTURE_SESSION>" --baseline-dir hgw500bna-qcv2-firmware-dump-verified
```

Success requires all of:

```text
PARSE_PARTITION_PASS mtd=0..5
PHYSICAL_BACKUP_PASS size=16777216 sha256=<hash>
```

The reconstructed folder contains six partition images, the exact 16 MiB
physical image, `manifest.json`, and `SHA256SUMS.txt`. The manifest records
baseline equality per partition when `--baseline-dir` is supplied. Differences
are evidence, not an automatic failure: in particular `linux_live` and data may
legitimately have changed.

Do not flash merely because this backup succeeds. This is only the backup gate;
candidate equivalence, exact target selection, recovery, and rollback gates are
separate requirements.
