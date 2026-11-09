# HGW-500BNA-QCv2 Bootbase one-shot audit

Date: 2026-08-14  
Scope: offline-only audit of the Bootbase one-shot path.  
Target: MitraStar HGW-500BNA-QCv2, Bootbase/U-Boot v36.7.0.30.  

No router access, SSH, reboot, environment write, flash write or network test
was performed during this audit.

## Executive verdict

**NO-GO for unattended execution under the strict guarantee currently stated.**

The decoded Bootbase binary proves all of the following:

1. `run` exists and executes the value of an environment variable through the
   normal command interpreter.
2. The interpreter separates commands on an unescaped `;` outside quotes.
3. The interpreter is fail-fast: a non-zero command return aborts the remaining
   semicolon-separated sequence.
4. `if`, `test`, `true` and `false` are absent from the complete 43-entry
   command table.
5. `&&` and `||` are not parser operators. They would be ordinary token text,
   not conditional control flow.
6. `tftpboot`, `iminfo`, `bootm`, `saveenv`, `setenv` and `bootselect` are real
   command-table entries.

This permits a **conditionally recoverable RAM trial**: restore
`bootcmd=bootselect` and `bootselect=0`, call `saveenv`, then perform TFTP,
`iminfo` and `bootm`. If the disarming `saveenv` succeeds, any later failure can
be recovered by one power cycle because the persistent environment already
selects the known-good LIVE slot.

It does **not** permit an automatic immediate `bootselect` fallback after a
failed `tftpboot`, `iminfo` or rejected `bootm`: fail-fast parsing prevents a
trailing fallback command from running. It also cannot give an unconditional
power-cycle guarantee when the disarming `saveenv` itself fails. A failed
`saveenv` aborts before TFTP, but the persistent primary environment may still
contain `bootcmd=run ram_once` and retry on the next reset.

The chain below is therefore demonstrated only with explicit preconditions. It
is not an execution approval.

## Inputs and integrity

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `work/bootbase-decoded.bin` | 145796 | `20ab45412b973478aa49a3daa31851a49f0deeaa09d07213479b0c3ee7af5f07` |
| `work/bootbase-decoded.disasm.txt` | 1957735 | `65e5f48c30c59be7f787329d9135229afa7cb04dc1125f5e9bfd8fc8322cf150` |
| `recovery/bootbase-analysis/bootbase-strings.txt` | 55474 | `df6a43d3e1ad550b1574a911cc8c269aaf29aed663da6eef5324afd73afa5963` |
| verified `hgw500_mtdblock0.bin` | 131072 | `dc1d3a792a0fc449aeeda23e91805b132846e26e2a802790c90106a278fd9b7d` |
| offline `bootcfg-current/mtd1.bin` | 65536 | `5e29baa87db5a18d0705801572430b75513c88e1ea60554e3701159baa8dc8f0` |
| offline `bootcfg-current/mtd2.bin` | 65536 | `5e29baa87db5a18d0705801572430b75513c88e1ea60554e3701159baa8dc8f0` |
| RAM-only Linux 5.10 uImage | 4053888 | `8893785f5a8644c21b494c71f385ee59c6ee8e19b53996036f7d8bc2d54b7391` |

The GPL path `work/sources/Quantenna-GPL/u-boot` is only a 15-byte pointer
containing `u-boot-2009.06/`; the referenced source directory is absent from
this workspace. Consequently, the decoded device binary is the authoritative
implementation for command semantics in this audit.

## Evidence: command set

`recovery/scripts/bootbase_readonly_report.py:67-94` parses five-word U-Boot
command-table entries and rejects invalid pointers, argument counts and handler
addresses. Running that parser over the pinned decoded binary produced 43
commands:

```text
reset zboot bootm bootd iminfo icache dcache coninfo loadb loady crc32 base
loop mtest sleep bootp tftpboot rarpboot ping saveenv printenv setenv version
echo help boardcfg boardopts lsid msi_cfg pcieboot spi_flash upgradeenv
updatecrc qtn_setmtdparts qtnboot bootselect qtn_upload_file
qtn_upload_file_serial qtn_show_board_config qtn_show_board_database
qtn_netboot hdmaw smi_read
```

Relevant entries:

| Command | Table offset | Handler | Max args |
|---|---:|---:|---:|
| `bootm` | `0x23510` | `0x88017788` | 16 |
| `iminfo` | `0x2354c` | `0x88017100` | 16 |
| `tftpboot` | `0x236b4` | `0x88019398` | 3 |
| `saveenv` | `0x236f0` | `0x8801953c` | 1 |
| `setenv` | `0x23718` | `0x880198e8` | 16 |
| `run` | `0x2372c` | `0x8801c6fc` | 16 |
| `bootselect` | `0x23894` | `0x88023b54` | 16 |

The absence of `if` is not inferred from strings: it is absent from the
complete command table. Since no `if` command exists and there is no hush
parser, `if ... then ... fi` is unsupported.

## Evidence: parser semantics

The normal command interpreter begins at `0x8801c3ec`.

### Semicolon

`work/bootbase-decoded.disasm.txt:8954-8969` compares input bytes with `0x3b`
(`;`) while tracking quoting/escaping, terminates the current command and moves
to the next command. This demonstrates ordered semicolon execution.

### Fail-fast return handling

`work/bootbase-decoded.disasm.txt:9112-9124` calls the selected command handler,
tests its return value and branches to the failure exit when it is non-zero.
The failure exit sets the interpreter result to `-1` at lines 9131-9135.

Therefore this Bootbase behaves as follows:

```text
command_1; command_2; command_3

command_1 rc != 0  -> stop; command_2 and command_3 are not run
command_1 rc == 0  -> run command_2
```

This is not POSIX-shell `;` behavior. It is equivalent to fail-fast chaining
for these U-Boot commands.

### `run`

The `run` handler at `0x8801c6fc` is shown in
`work/bootbase-decoded.disasm.txt:9142-9169`. It resolves each named variable,
passes its value recursively to `0x8801c3ec`, and returns failure immediately
when the nested interpreter returns `-1`. `run first fallback` therefore cannot
be used to ignore a failed `first` variable and invoke `fallback`.

### No `&&` or `||`

The parser block at `work/bootbase-decoded.disasm.txt:8954-9084` has explicit
handling for semicolon, backslash, single quote, dollar expansion and
parenthesis/brace delimiters. It does not recognize byte `0x26` (`&`) or byte
`0x7c` (`|`) as operators. `&&`/`||` are not control-flow constructs in this
binary.

## Evidence: command return propagation

### `saveenv`

`work/bootbase-decoded.disasm.txt:5637-5648` calls the SPI environment writer at
`0x88022b2c` and maps its result to command return `0` on success and `1` on
failure. Because the interpreter is fail-fast, a failed disarming `saveenv`
prevents all TFTP activity.

The environment analysis in
`outputs/kernel-port/BOOTBASE_RECOVERY_ANALYSIS.md:230-270` shows that Bootbase
uses MTD1 as primary, MTD2 only when primary CRC validation fails, and ordinary
`saveenv` writes the primary copy. It does not select the newest copy by a
generation counter.

### `tftpboot`

The command entry and wrapper are documented in
`recovery/bootbase-analysis/bootbase-functions.md:5-16` and
`recovery/bootbase-analysis/ethernet-rx-path-analysis.md:42-50`.
The wrapper at `0x88019398` calls the common network command path at
`0x88019138` with mode 3. In
`work/bootbase-decoded.disasm.txt:5394-5402`, a negative network-loop result is
converted to command failure `1`; the wrapper propagates that result at lines
5511-5518. A failed TFTP therefore aborts the one-shot sequence.

### `iminfo`

The handler starts at `0x88017100`. In
`work/bootbase-decoded.disasm.txt:3228-3254`, it validates each requested image,
accumulates a failure result and returns non-zero when validation fails. A bad
magic/header/data image therefore prevents `bootm` from being called.

### `bootm`

The handler is the real command-table entry at `0x88017788`. The independently
audited Bootbase flow in
`outputs/kernel-port/BOOTBASE_RECOVERY_ANALYSIS.md:122-180` demonstrates the
critical boundary: a rejected image makes `bootm` return; a successful handoff
does not return to the interpreter. No Linux health acknowledgement, boot
counter or timeout exists after handoff.

## Environment dump result

The two newest local environment snapshots are dated 2026-07-26. They are not
a claim about the router's live state on 2026-08-14.

Both `outputs/kernel-port/bootcfg-current/mtd1.bin` and `mtd2.bin` are byte-for-
byte identical and parse as:

```text
size                  65536
CRC range             blob[4:0x6000]
stored CRC32          0x48faf9ec
calculated CRC32      0x48faf9ec
CRC valid             yes
bootcmd               bootselect
bootselect            0
ipaddr                192.168.1.200
serverip              192.168.1.150
loadaddr               0x83000000
trial_once             setenv bootcmd bootselect; setenv bootselect 1;
                       saveenv; setenv bootselect 0; bootselect
```

The retained `trial_once` variable is inert because `bootcmd=bootselect`.

The older verified factory dump has two identical, CRC-valid environments with
`bootcmd=bootselect` and `bootselect=1`. This explains why historical documents
can disagree: they describe different offline captures. No offline snapshot may
replace a fresh read-only preflight immediately before execution.

## Contract-emulator result and boundary

Running `tools/bootbase_contract_emulator.py` against the verified partition
set returned:

```text
result                 PASS
primary CRC            valid
backup CRC             valid
redundant values       match
bootselect             1
selected slot          linux_safety
fallback slot          linux_live
safety slot contract   accepted
live slot contract     accepted
```

Using the newer offline environment with the same verified slots selects LIVE
and accepts its image contract.

This result cannot prove one-shot command behavior. The emulator explicitly
limits itself in `tools/bootbase_contract_emulator.py:2-12` and
`:318-344` to environment CRC, slot order and OEM RAS/uImage validation. It does
not execute ARC instructions, model `saveenv`, run TFTP or emulate the command
parser.

## RAM uImage contract

The proposed RAM-only image has a valid standard legacy uImage header:

```text
file                   linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage
file size              4,053,888 bytes
payload size           4,053,824 bytes
magic                  0x27051956
header CRC             0xce5c6a6d (matches)
payload CRC            0x96a72303 (matches)
OS / arch / type       Linux(5) / ARC(23) / kernel(2)
compression            none(0)
load                   0x8493a000
entry                  0x84ab0000
staging                0x87000000..0x873ddb80
destination            0x8493a000..0x84d17b40
```

Staging and destination do not overlap. This proves the legacy uImage and
address arithmetic, not EMAC operation or Linux execution on the board.

## Demonstrated conditional candidate

Candidate environment:

```text
ram_once=setenv bootcmd bootselect; setenv bootselect 0; saveenv; setenv ipaddr 192.168.1.200; setenv serverip 192.168.1.43; tftpboot 0x87000000 linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage; iminfo 0x87000000; bootm 0x87000000
bootcmd=run ram_once
```

`ram_once` is 222 bytes, below the interpreter's 255-byte command limit shown
at `work/bootbase-decoded.disasm.txt:8936-8942`. Every command is within its
command-table maximum argument count.

The server address `192.168.1.43` is taken from the handoff document and is not
live-verified by this offline audit. It must be replaced if the isolated TFTP
interface uses another address.

The ordering is deliberate:

1. Restore ordinary `bootcmd=bootselect` in RAM.
2. Select known-good LIVE (`bootselect=0`) in RAM.
3. Persist those fallback values before touching the network.
4. Apply `ipaddr` and `serverip` only after `saveenv`, so the lab addresses are
   transient and are not included in the saved fallback environment.
5. Load the standard uImage at non-overlapping staging address `0x87000000`.
6. Validate it with `iminfo`.
7. Hand off with `bootm`.

### Outcome matrix

| Event | Bootbase result | Persistent fallback | Recovery |
|---|---|---|---|
| `saveenv` succeeds, TFTP fails | sequence aborts at `tftpboot`; prompt | LIVE/default saved | power cycle boots OEM LIVE |
| TFTP succeeds, `iminfo` fails | sequence aborts at `iminfo`; prompt | LIVE/default saved | power cycle boots OEM LIVE |
| `bootm` rejects/returns | sequence aborts at `bootm`; prompt | LIVE/default saved | power cycle boots OEM LIVE |
| `bootm` hands off, Linux hangs | Bootbase cannot observe failure | LIVE/default saved | power cycle boots OEM LIVE |
| `saveenv` fails | sequence aborts before TFTP | **not proven** | one-shot may repeat; strict guarantee fails |

Appending `; bootselect` does not repair the first three rows: the fail-fast
interpreter never reaches it after a non-zero return. On successful `bootm`, it
also never returns. The candidate therefore guarantees power-cycle fallback
only after successful disarming persistence, not immediate fallback.

## Audit of `prepare_bootbase_one_shot_pty.py`

The current tool must not be used for this RAM-TFTP route.

1. Lines 45-59 generate a slot trial ending in `bootselect`; they do not create
   a TFTP/`iminfo`/`bootm` chain.
2. Lines 75-82 accept `qtnboot` as an existing state even though `qtnboot` is a
   destructive repair path and should be a hard stop for this workflow.
3. Lines 126-150 only look for expected strings and two MD5-looking values.
   They do not parse the resulting environment CRC or prove MTD2 remains the
   known-good fallback.
4. `--commit` is allowed without `--reboot` (lines 121-155), leaving a dormant
   persistent one-shot that may fire during an unrelated later reboot.
5. It has no 255-byte command-length check and no uImage/TFTP address contract.
6. Its restore path updates primary state but does not enforce redundant-copy
   mirroring.
7. It cannot close the disarming-`saveenv` failure window described above.

The script remains useful as historical evidence for the prior slot trial, but
it is not an executor for the RAM-only candidate.

## Required gates before any execution

The following are mandatory and remain incomplete under this offline-only
audit:

1. Read-only live identity proof for the exact HGW-500BNA-QCv2.
2. Fresh read-only decode of MTD1 and MTD2 with valid CRC, identical complete
   contents and known-good `bootcmd=bootselect,bootselect=0`.
3. Proof that the currently selected LIVE slot is the running known-good OEM.
4. Isolated-interface TFTP preflight with the exact pinned image and no host
   route ambiguity.
5. A deliberate decision accepting the narrow `saveenv` failure window, or a
   new mechanism that can verify the saved primary before handoff.
6. A new executor with separate `inspect`, `stage`, `verify` and `reboot`
   phases; no combined implicit commit/reboot operation.
7. Explicit operator authorization immediately before the environment write
   and reboot.

Until those gates are met, the operational verdict remains **NO-GO**.

## Offline reproduction commands

These commands read local files only:

```powershell
python tools/bootbase_contract_emulator.py `
  --parts-dir hgw500bna-qcv2-firmware-dump-verified

Get-FileHash -Algorithm SHA256 `
  outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage

rg -n "^8801c3ec:|^8801c6fc:|^88019398:|^88017100:|^88017788:" `
  work/bootbase-decoded.disasm.txt
```

No command in this document was executed against the router.
