# HGW500 Quantenna 5 GHz source recovery — 22 October 2026

Owner requested REA recovery of the complete driver operation set, an independent
private GitHub repository, exact original sources/comments and an HTTPS-only
client-side desktop. The work is offline. No device SSH, radio mutation, UART,
reboot, flash, boot environment or protected-partition access was performed.

## Repository and preserved base

Independent checkout: `repos/openmitrastar-hgw500-quantenna-5ghz-driver`.
GitHub: `apelsito/openmitrastar-hgw500-quantenna-5ghz-driver`, private.
Latest verified pushed checkpoint: `48e5286` (private GitHub).
Original Quantenna-GPL commit is pinned as a full submodule:
`116a8b0cd80d75e6bc3b8d21646f9c7fa4ce1cf9`. It preserves46,770 Git objects/files
and598,076,127 source/carrier bytes: old kernel, bootloader, Buildroot, radio,
host and config trees. Eight case-only kernel filenames collide on Windows;
their exact original Git blobs remain intact. Use a case-sensitive Linux
filesystem for their full checkout. This is not complete OEM v37.4.0.89 source.

All35018 C/C++ files were catalogued from original Git blobs:1331535 comments,
104725712 exact raw bytes. Each record was replayed against its compressed raw
stream and SHA256. Other file languages stay preserved, not parsed as C.
The radio/port catalog separately retains24362 comments. No original comment,
copyright notice or line ending was removed. Git conversion is disabled.
Owner-local firmware images, modules, keys/calibration and personalized data
are excluded from Git. Modules/carriers used for REA remain local.

## Exact operation recovery

The real OEM WEXT table contains607 private records. F365 contains566:563 OEM
matches,44 absent and3 port additions. Older suffix-based inventories did not
enumerate the whole OEM table. Exact32-bit iw_handler_def layouts, all symbols,
allocated-data relocations and WEXT slots are now retained in the repository.
Original OEM callbacks and getter/setter dispatch were analysed with REA using
an isolated ARC700 ABI3 lane. Analysis-only ELFs have synthetic addresses and
must never be installed or packaged as firmware.

Seven-entry complete QDRV/WLAN candidate is built twice and offline qualified:

* QDRV684108bytes, SHA256
  `dd8f29a1dccb9a01236eb4577f8909088eb544eac872593d4696bf1585cfad06`.
* WLAN629496bytes, SHA256
  `461c23d2d29833216bb3e7b10afba51531b33cae73e7d0ed6c929482e1faec92`.

Qualification: `outputs/rea/driver5g-ops-20261022-seven-pair-qualification-r5`.
Build: `outputs/rea/driver5g-ops-20261022-seven-module-pair-r2`.
All2208 input pins, raw data/BSS/strings, executable bytes outside the intended
getter changes (including unsymbolized holes), symbols and relocation contracts
pass.327681 actual-function/ARC ABI checks and5 parsed-module fault tests pass.
This uses F364/F365 baseline QDRV, without F370 observational counters.

The seven records are parameter246 setter/getter aliases, getter450 observed
constant70, getters496/497 observed constant8, and named CCA getters331/275.
The port uses its named fields and independently measured ARC offsets, never
copied OEM raw offsets.37 OEM records remain; two are unsupported even in OEM.

Further source branches remain separate: device mode, max system bandwidth,
faithful unsupported returns, BBDF private append and check-current-channel.
The14-record branch now passes its full34-QDRV/19-WLAN unit x2 rebuild and
whole-module qualification: QDRV684756bytes3e76821b...cf06 and WLAN629984bytes
46075f1f...cb79.7faultchecks and independent review pass. Final receipt
`outputs/rea/driver5g-ops-20261022-fourteen-full-qualification-r5` binds17inputs
and known fixtures.1502host-accessible pins rechecked;718Linux-only pins remain
verified in the earlier Linux run, not freshly claimed on Windows.30OEM table
gaps remain;12functional operations+2faithfulunsupported responses recovered.
The15-record pair now also qualifies offline, adding464fieldsetter with actual
ARCblockdecode19488/4B,131074hostsourcechecks and7negative gates. QDRVunchanged
qualified14baseline; all19WLAN units rebuiltx2,629896byteseac8c063...f946.
Table581records13functional+2unsupported,29OEMgaps. Separate offsetcompiler
witnessfailedWSL butactualCunit/moduleandfocusedGhidra case write proved.
The NAC getter guard is a separate prototype with lifetime/snapshot limits.
Do not describe these as the accepted7-record module pair or a full release.

Windows isolatedARC/Ghidra lane is now real-verified without installed-runtime
orCodex changes. MuCcodewindow remains exact, flags0/machine93 preserved.
NAC452B,dynSIFS304B,RTS248B,SETdispatcher7148B and nestedSIFSget/set functions
were analysed. New18source candidate adds463/498 with fullu32wire transport;
1,048,576state/forward fixturecases passed, but106Cbuild is blocked by concrete
WSLI/O5 user/locale failures. Baselinequalified15 remains authoritative.
TQE4LHOSTwriters have a separate common IRQpublication prototype/164actualbody
and headerprimitivecases; unboundedIRQwaits and foreignbankwriter collision
keep itNO_GO_MODULE. No universalarbitration or physical claim is made.

## Portable builds and client desktop

Independent repository TQE build passed twice byte-identical to the baseline:
35552bytes, SHA256
`bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f`.
52functions/464RELA/275symbols; exact executed builder is retained and pinned.
Portable WLAN complete x2 build now passes:629180bytes,
`7b0e504e6aee9b763757ea59268b21ebf2f18cdaf6a3c30f52ca43970a6f8dc0`,
all959functions/9543RELA/2250symbols match with declared source-version metadata
delta. Its current scoped builder and6685 input pins were verified unchanged.
Portable QDRV now also passes x2:684660bytes SHA256
`c8b924ccbf8b85616136fef11fb091e8975c67fb7dc499bddcaef38804c29688`,831functions,
14034RELA/1932symbols/312852codebytes equivalent;onlysrcversion differs.
Thus allthree independent repository baseline builds have individual evidence.
WSL transport0x8007274c and excessive input-tree discovery were observed;
discovery is narrowed and no WSL reset or unrelated process termination occurred.

Client desktop shell10168bytes: actual loopback HTTPS/browser PASS for notes,
Snake, windows, same-origin assets and HTTP refusal. No HTTP listener was
created. Certificates used by local tests were temporary and removed. The
router will serve HTTPS assets; games execute in the client. No Docker/native
desktop is installed on the HGW. Doom HTTPS asset packaging remains pending.

## Unfinished gates

Do not close the full driver or Linux5.10 mission. Remaining operations need
their firmware/host consumers, typed ABI and whole-module proof. Universal TQE
arbitration, native radar, WPA2 client/traffic, persistent cold boot, preserved
rollback and fatal-free soak remain distinct physical gates. No new runtime
or firmware candidate from this work has been installed on the physical unit.
