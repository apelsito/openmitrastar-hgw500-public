# F370 complete QDRV module - 2026-10-21

F370 is now a complete offline-linked QDRV module on the exact F365/F364
lineage. It has not been loaded on the physical HGW and is not a firmware image.
F369 STORE38 remains a separate correctness candidate.

The accepted module is:

`outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/a/qdrv.ko`

- Bytes: 686144.
- SHA256: `d5e1f58303eaaa02123e0cf6352bd40c40df3027be300d2a1143b07f54a05dae`.
- Two complete candidate compilations are byte-identical.
- Complete baseline was compiled once with retained ARC flags, the recovered
  Linux 5.10.260 headers, and the retained F363 generated ABI context.
- Parent: `/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z/a/qdrv/qdrv.ko`,
  685332 bytes, SHA256
  `cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01`.
  F365 reuses this QDRV; its separate diagnostic build changes temp_sens only.
- Dependency closure uses retained kernel Module.symvers and the original
  F364 dependencies.symvers. No F367 provider is added.

The full baseline reconstruction gate passes 831 functions/312852 executable
section bytes, 1932 symbols, all 14034 RELA records, every nonstring allocated
data section, and BSS size/alignment. Reconstructed file paths differ in literal
`__FILE__` strings: the explicit `/f364-qdrv/qdrv` mapping is normalized to the
retained source path; all string content and every relocation destination match
after only that declared substitution. Build-id/sourceversion metadata differs
and is not treated as executable equivalence. Every other baseline module
metadata field is checked. This is ET_REL static equivalence, not runtime proof.

369 imports and 15 exports are unchanged. The public parameters added are
`openmitrastar_auc_raw_ok`, `openmitrastar_auc_raw_other`,
`openmitrastar_auc_busy_free`, `openmitrastar_auc_return_success`.
Each is uint and its complete kernel_param record has permissions 0444.
The actual-function ownership/result/saturation fixture remains 12 cases/87
checks; counters are approximate with concurrent callers and do not prove RF
delivery or improve the queue policy by themselves.

Qualification evidence:

`outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/qualification-20261021T222300Z/result.json`

`outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/qualification-20261021T222300Z/full-baseline-comparison.json`

Builders are `tools/build_f370_qdrv_module.py` and
`tools/qualify_f370_qdrv_module.py`; immutable executed copies are retained in
the build directory. Earlier failed verification attempts remain retained;
their failures were verifier public-name/ARC32 struct-layout issues and are
not rewritten into successful results. The first linked build also included
an extra intermediate build-id note; revision2 uses the retained linker flags.

REA also analyzed the exact candidate through the project-local ARC700/Ghidra
lane, under `rea-candidate-r2/`. Its complete 1708-byte
`qdrv_tx_sch_enqueue_to_node` body shows tqe_tx, guarded saturating counters,
the existing BUSY skb free, and the existing success return. This supports the
source fixture and module audit; pseudocode is derived, not original source.
The first REA attempt used the installed Ghidra without the project ARC700
language and failed import; the corrected attempt used the already prepared
ARC700 lab and succeeded. Original module and derived target hashes stayed
unchanged.

The candidate code delta audit additionally separates the actual inlined AuC
change from six other changed functions. Every other changed instruction is an
existing counter's BSS offset shifted by exactly 16 bytes due to four new uint
counters, or the original BUG_ON source line moving from 2147 to 2178 after 31
inserted lines. Their operational source and remaining masked instruction bytes
are unchanged. Exact instruction pairs are retained under
`candidate-anchor-code-differences.json`; conclusion is in
`candidate-code-delta-audit.json`. The final pinned evidence manifest is
`module-evidence-manifest-r4.json` in the module output directory.

`rea-linked/qdrv-ANALYSIS_ONLY-NOT_FIRMWARE.elf` uses synthetic external
addresses and must never be installed, booted, packaged or flashed.

Physical gates remain UNRUN for F370: immutable full-image packaging, current
physical binding/protection/readback/recovery contract, persistence, client
AUTH/ASSOC/AUTHORIZED, useful bidirectional traffic, fatal-free soak and release
acceptance. No device, Ethernet, UART, runtime, bootenv or flash action was
performed by this module build.
