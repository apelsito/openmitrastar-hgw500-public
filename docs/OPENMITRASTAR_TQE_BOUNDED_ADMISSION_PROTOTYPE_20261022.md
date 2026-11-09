# TQE transmit admission prototype — 22 October 2026

Status: **SOURCE_ONLY_PROTOTYPE; NO_GO_MODULE**. No hardware, UART, module
loading, radio changes, firmware packaging, reboot or flash occurred.

The exact active-lineage `switch_tqe.ko` is pinned to SHA-256
`bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f`
(35,552 bytes). Existing REA evidence at
`outputs/rea/arc700-20261021-r2/tqe-rea-tx/rea.json` is pinned to
`78d2ca5480dc79eb643bdb8d7f1cff1bd3436b327a4bd0174ac550cf127c69dd`.
Its synthetic linked ELF is analysis-only and must never enter a firmware.

REA assembly identifies `kfree_skb` at `0x10f8e`, the READY bit read at
`0x1100c`, and the backwards conditional jump at `0x11010` returning to
`0x11002`. The first descriptor writes follow this loop; TXSTART occurs at
`0x1106c`. This proves an unbounded polling path after consumption in the
shipped artifact. It does not prove a physical incident. The pseudocode moves
some descriptor writes; assembly is used for ordering.

The corresponding source is
`work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c`,
SHA-256 `929d89801045c2b5f421d4d40ca312c32feaf93612de6a575b9b362ab97d9aef`.
The critical function corresponds to the assembly, but full module baseline
reconstruction/equivalence is **unproven**. No replacement `.ko` is produced.

## Change and ownership

The isolated source candidate moves READY admission before HBM allocation,
copy, `hbm_no_free`, cache mutation and skb consumption. READY is tested at most
1,024 times with `cpu_relax()`. A permanently busy device therefore returns
`NETDEV_TX_BUSY` with original skb/HBM ownership unchanged. There is no
`NETDEV_TX_BUSY` return after `kfree_skb`.

For the PCIe configuration, the candidate makes one call to the existing
`_qtn_mproc_3way_tqe_sem_down` primitive, which itself allows at most 65,535
claim attempts. It does not invoke the legacy wrapper which retries forever.
Preowned LHOST is refused rather than treated as an acquired lock. Successful
claims are recorded and released independently of a later `tqe_sem_en` change;
lost ownership produces a warning and does not release another processor's
lock. The previous local IRQ state is restored on every acquired exit.

After admitted transmit, direct HBM data follows the existing `hbm_no_free`
transfer and copy-out follows the existing allocation/copy/free/TXSTART path.
NO_HBM returns BUSY with skb untouched. Oversize still consumes skb and
returns OK. The existing qdrv caller deliberately frees BUSY skb and returns
`NET_XMIT_SUCCESS`; this prototype preserves that policy and therefore does
not resolve BUSY-related packet loss or prove improved throughput.

An initially considered consumed-skb timeout with `topaz_hbm_release_buf_safe`
was rejected: that helper eventually invokes `__topaz_hbm_wait`, which remains
unbounded. Moving admission before allocation avoids needing a new HBM
cleanup path on this timeout. The candidate **does not** bound existing HBM
allocation/filter loops or MMIO bus stalls.

## Reproducible outputs and fault fixture

Builder: `tools/prepare_tqe_bounded_admission_prototype.py`. It hashes the
original module/source and checks exact retained REA assembly anchors before
creating a new output directory; it never edits baseline sources.

Two independently generated candidates, under
`outputs/rea/arc700-20261021-r2/tqe-bounded-admission-20261022-r1` and `-r2`,
have the same SHA-256:
`89590cd3df726d20bfeb9091aef79cd350fa9b43b5ce0ba3446742e045712e9d`.

`tools/test_tqe_bounded_admission_prototype.py` extracts the candidate's actual
admission functions, `tqe_tx_buf`, `tqe_tx`, and actual OEM semaphore primitives.
It compiles them with fake skb/HBM/MMIO on REA-Linux GCC using address and
undefined-behavior sanitizers. This is an offline C function fixture, not a
kernel module build or a handwritten behavioral substitute.

Latest result:
`outputs/rea/arc700-20261021-r2/tqe-bounded-admission-tests-20261022-r4/result.json`.
Both configurations PASS: **15 local cases / 92 checks**, **23 PCIe cases /
153 checks**, **38 cases / 245 checks** total. The earlier two runs produced
identical candidate/harness hashes and outcomes before adding the counterexample.

Cases cover immediate READY, the last admitted poll, first excluded poll,
permanently busy, NO_HBM, direct/copy payloads, shared refs, VLAN copy, oversize,
prior IRQ state, foreign/stale semaphore ownership, eventual acquisition,
NO_HBM/oversize release, `tqe_sem_en` changing and lost semaphore ownership.
The exact qdrv BUSY-free policy is exercised without double-free.

## Explicit counterexample and remaining qualification

The latest fixture also reproduces a **collision with a noncooperating foreign
CPUIF writer** which publishes between admission and TXSTART. Its PASS means
that the hazard is captured, not that concurrent operation is safe. Local IRQ
exclusion cannot stop a different CPU or a processor ignoring the semaphore.

Other writers in the same baseline include `topaz_tqe_xmit`, `tqe_push_mcast`
and `topaz_swfwd_tqe_xmit`. Universal arbitration, call contexts, reentrancy,
SMP and the hold interval across HBM calls must be qualified before any module
promotion. Physical latency/poll thresholds are not measured; 1,024 is a
prototype operation budget, not an asserted hardware timing specification.

The next module step requires exact full baseline reproduction and a coherent
arbitration contract across every participating CPUIF writer. This prototype
must not be packaged, installed or described as a finished driver fix.
