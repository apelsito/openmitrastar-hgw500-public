"""Persist the F353 read-only OEM/ELF audit; no build, reset or device access."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
from elftools.elf.elffile import ELFFile
from prepare_f344_csa_policy import closing
from f331_oem_postfilter_projection import linux

ROOT = Path(__file__).resolve().parents[1]
GUARD = 500 * 1024 * 1024
PRIVATE = Path.home() / '.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
CLOSURE = PRIVATE / 'f344-closure-20260921T162003Z'
OEM = ROOT / 'work/sources/Quantenna-GPL'
QDRV = ROOT / 'work/linux510-radio-port/quantenna-f344-modes/qdrv'
PEERS = ROOT / 'work/linux510-radio-port/quantenna-f344-peers'
MODULE_SHA = '8d6d95da33805f27edc23ad2ccd1dfc2cab946e3c72206fec0795f6e66e65b51'
F344_MANIFEST = ROOT / 'outputs/handoff/f344-mode-components-20260921T162648Z/manifest.json'
F344_MANIFEST_SHA = 'fffd6643a7db9f186aefa02e06f29995f8742ad7f91f824a34f8cb80ecf84401'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard():
    free = shutil.disk_usage(ROOT).free
    if free <= GUARD:
        raise RuntimeError('F353 persistence stopped: C: free space is below 500 MiB')
    return free


def function_evidence(path, name):
    source = path.read_text()
    pattern = r'^(?:static\s+)?[^;{}\n]*\b' + re.escape(name) + r'\([^;{}]*\)\s*\{'
    match = re.search(pattern, source, re.M)
    if not match:
        raise ValueError('Function not found: ' + str(path) + ':' + name)
    end = closing(source, match.start()) + 1
    content = source[match.start():end]
    return {
        'path': str(path.relative_to(ROOT)), 'function': name,
        'line_start': source.count('\n', 0, match.start()) + 1,
        'line_end': source.count('\n', 0, end) + 1,
        'file_sha256': sha(path),
        'excerpt_sha256': hashlib.sha256(content.encode()).hexdigest(),
        'excerpt': content,
    }


def span_evidence(path, label, first, last):
    lines = path.read_text().splitlines()
    content = '\n'.join(lines[first - 1:last]) + '\n'
    return {'path': str(path.relative_to(ROOT)), 'function': label,
            'line_start': first, 'line_end': last, 'file_sha256': sha(path),
            'excerpt_sha256': hashlib.sha256(content.encode()).hexdigest(),
            'excerpt': content}


def main():
    free_before = guard()
    closure = json.loads((CLOSURE / 'manifest.json').read_text())
    module = Path(closure['modules']['qdrv']['path'])
    if sha(module) != MODULE_SHA or sha(F344_MANIFEST) != F344_MANIFEST_SHA:
        raise ValueError('The immutable F344 binding changed')
    specs = {
        'oem_hal_muc': (OEM / 'drivers/qdrv/qdrv_hal.c', 'hal_disable_muc'),
        'oem_hal_dsp': (OEM / 'drivers/qdrv/qdrv_hal.c', 'hal_disable_dsp'),
        'oem_hal_auc': (OEM / 'drivers/qdrv/qdrv_hal.c', 'hal_disable_auc'),
        'oem_hal_reset': (OEM / 'drivers/qdrv/qdrv_hal.c', 'hal_reset'),
        'oem_soc_stop': (OEM / 'drivers/qdrv/qdrv_soc.c', 'qdrv_soc_exit'),
        'oem_soc_start': (OEM / 'drivers/qdrv/qdrv_soc.c', 'qdrv_soc_init'),
        'oem_reset_vector': (OEM / 'common/topaz_reset.h', 'topaz_set_reset_vec'),
        'port_hal_dsp': (QDRV / 'qdrv_hal.c', 'hal_disable_dsp'),
        'port_hal_auc': (QDRV / 'qdrv_hal.c', 'hal_disable_auc'),
        'port_auc_start': (QDRV / 'qdrv_auc.c', 'qdrv_auc_init'),
        'port_auc_stop': (QDRV / 'qdrv_auc.c', 'qdrv_auc_exit'),
        'port_auc_unmap': (QDRV / 'qdrv_auc.c', 'qdrv_auc_stats_unmap'),
        'port_auc_setup': (QDRV / 'qdrv_auc.c', 'qdrv_auc_stats_setup'),
        'port_soc_stop': (QDRV / 'qdrv_soc.c', 'qdrv_soc_exit'),
        'port_revoke_shared': (QDRV / 'qdrv_soc.c', 'qdrv_soc_revoke_params'),
        'port_hostlink_stop': (QDRV / 'qdrv_hostlink.c', 'qdrv_hostlink_exit'),
        'port_mac_stop': (QDRV / 'qdrv_mac.c', 'qdrv_mac_exit'),
        'port_wlan_stop': (QDRV / 'qdrv_wlan.c', 'qdrv_wlan_exit'),
        'port_module_exit': (QDRV / 'qdrv_module.c', 'qdrv_module_exit'),
        'port_sequential_gate': (QDRV / 'qdrv_control.c', 'qdrv_sequential_precheck'),
        'port_mode_gate': (QDRV / 'qdrv_control.c', 'f344_control_vap_admit'),
        'port_radar_stop': (QDRV / 'qdrv_radar.c', 'qdrv_radar_exit'),
        'port_radar_start': (QDRV / 'qdrv_radar.c', 'qdrv_radar_init'),
        'port_rx_stop': (QDRV / 'qdrv_rx.c', 'qdrv_rx_exit'),
        'tqe_stats_register': (PEERS / 'platform/topaz/switch_tqe.c', 'tqe_reg_multicast_tx_stats'),
        'tqe_port_remove': (PEERS / 'platform/topaz/switch_tqe.c', 'tqe_port_remove_handler'),
    }
    evidence = {key: function_evidence(*spec) for key, spec in specs.items()}
    evidence['reset_bits'] = span_evidence(OEM / 'common/ruby_platform.h', 'reset bits', 352, 370)
    evidence['auc_reset_bit'] = span_evidence(OEM / 'common/topaz_platform.h', 'AuC reset bit', 45, 51)
    evidence['tqe_stats_consumer'] = span_evidence(PEERS / 'platform/topaz/switch_tqe.c', 'WMAC multicast callback', 522, 533)
    evidence['shared_registry'] = span_evidence(OEM / 'include/qtn/mproc_sync_base.h', 'firmware/host shared parameter registry', 138, 161)
    evidence['oem_reload_ethernet'] = span_evidence(ROOT / 'work/hgw500-rootfs-live/squashfs-root/scripts/qtn_wds_ext.sh', 'OEM reload powers Ethernet PHYs', 62, 90)
    witnesses = {}
    with module.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name('.symtab')
        for name in ('hal_disable_auc', 'hal_disable_dsp', 'hal_disable_muc'):
            rows = symbols.get_symbol_by_name(name)
            if len(rows or []) != 1:
                raise ValueError('Ambiguous ELF symbol: ' + name)
            sym = rows[0]
            section = elf.get_section(sym['st_shndx'])
            raw = section.data()[sym['st_value']:sym['st_value'] + sym['st_size']]
            witnesses[name] = {'bytes': len(raw), 'raw_hex': raw.hex(),
                               'section': section.name, 'offset': sym['st_value'],
                               'sha256': hashlib.sha256(raw).hexdigest()}
    if any(witnesses[n]['bytes'] != 2 or witnesses[n]['raw_hex'] != 'e07e'
           for n in ('hal_disable_auc', 'hal_disable_dsp')):
        raise ValueError('No-op ELF witness differs from the read-only audit')
    objdump = ROOT / 'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-objdump'
    for name, row in witnesses.items():
        command = ['wsl.exe', '-d', 'podman-mem9-tidb', '-u', 'root', '-e',
                   linux(objdump), '-dr', '--disassemble=' + name, linux(module)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise ValueError('ELF disassembly failed: ' + name)
        row['disassembly'] = result.stdout
    findings = [
        {'id': 'F353-01', 'title': 'AuC and DSP stop do not retire those processors',
         'proven': 'OEM and port have empty AuC stop and disabled ARC DSP reset; final F344 ELF bodies are exactly j_s [blink].',
         'limit': 'No alternate processor-retirement acknowledgement was proved. The disabled DSP branch was neither enabled nor executed.',
         'evidence': ['oem_hal_auc', 'oem_hal_dsp', 'port_hal_auc', 'port_hal_dsp', 'port_auc_stop']},
        {'id': 'F353-02', 'title': 'TQE keeps a callback and AuC statistics retain stale mappings',
         'proven': 'AuC init registers a callback with &qw->ic. Its exit does not revoke it. Unmap leaves both static pointers non-NULL, while setup remaps only NULL pointers.',
         'limit': 'Reachability of a particular multicast path depends on runtime configuration; no live use-after-free is claimed.',
         'evidence': ['port_auc_start', 'port_auc_stop', 'port_auc_unmap', 'port_auc_setup', 'tqe_stats_register', 'tqe_stats_consumer']},
        {'id': 'F353-03', 'title': 'Stop return does not prove resource retirement',
         'proven': 'SoC exit discards subordinate return codes, clears resource bits and frees shared DMA; MAC exit can return an error before IRQ release. The added radar gate is a real earlier error check, but does not cover all resources.',
         'limit': 'The existing order and flush calls are not proof that every external TQE/firmware consumer has stopped.',
         'evidence': ['oem_soc_stop', 'port_soc_stop', 'port_mac_stop', 'port_revoke_shared', 'port_hostlink_stop', 'shared_registry']},
        {'id': 'F353-04', 'title': 'Current rmmod path is unsuitable for warm restart',
         'proven': 'With sequential bringup started and F344 mode enabled, the command gate rejects bare stop. Module exit logs the stop failure and continues to free its private control block.',
         'limit': 'F344 does not use this unload path. This audit does not execute it or offer it as recovery.',
         'evidence': ['port_module_exit', 'port_sequential_gate', 'port_mode_gate']},
        {'id': 'F353-05', 'title': 'A fresh radio must retain outstanding NOP deadlines',
         'proven': 'Radar exit deletes nonoccupancy timers and clears its control block; init sets up fresh timers. These routines contain no remaining-deadline handoff.',
         'limit': 'No claim is made about every external OEM daemon. This is a required missing contract for the proposed in-port restart.',
         'evidence': ['port_radar_stop', 'port_radar_start']},
        {'id': 'F353-06', 'title': 'Reset writes and an Ethernet-excluding bit mask are insufficient epoch proof',
         'proven': 'MuC stop requests only MUC bit 11. Restart hal_reset uses NETSS|MAC|BB (0x4180), excluding ENET0/1 bits. The generic helper has an Amber-conditional bus-flush path, not a universal retirement acknowledgement.',
         'limit': 'No MMIO was read or written, and no isolation of the shared TQE/Ethernet datapath was demonstrated. The OEM WDS reload script explicitly powers Ethernet PHYs, so it cannot be copied for uninterrupted management.',
         'evidence': ['oem_hal_muc', 'oem_hal_reset', 'oem_reset_vector', 'reset_bits', 'auc_reset_bit', 'port_rx_stop', 'tqe_port_remove', 'oem_reload_ethernet']},
    ]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'outputs/preflight' / ('f353-radio-epoch-' + stamp)
    guard()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'source-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    (out / 'elf-evidence.json').write_text(json.dumps(witnesses, indent=2) + '\n')
    lines = [
        '# F353 — full radio/MuC epoch audit', '',
        '**Outcome: NO_GO_RESTART_BOUNDARY_NOT_PROVEN.** This is a persisted',
        'read-only source/ELF analysis, not an implemented or tested radio reset.',
        'F344 remains immutable. Wi-Fi/RF/client execution remains USER_DEFERRED.', '',
        'The OEM sequence was recovered: SoC init resets NETSS/MAC/BB, publishes',
        'new shared parameters, initializes MAC/hostlink and starts DSP, MuC and',
        'AuC. Exit attempts the reverse resource release, then revokes shared DMA.',
        'That sequence does not establish the ownership boundary needed to reuse',
        'a CSA descriptor safely after a full restart. COMPLETE is not an epoch token.', '',
        '## Findings', '',
    ]
    for finding in findings:
        lines += ['### ' + finding['id'] + ' — ' + finding['title'], '',
                  finding['proven'], '', finding['limit'], '', 'Source anchors:', '']
        for key in finding['evidence']:
            row = evidence[key]
            lines.append('- `' + row['path'].replace('\\', '/') + ':' + str(row['line_start']) +
                         '–' + str(row['line_end']) + '` — `' + row['function'] + '`.')
        lines.append('')
    lines += ['## Compiled evidence', '',
              'The inspected qdrv is the already-built F344 module (no new build):',
              '`' + str(module) + '`, SHA-256 `' + MODULE_SHA + '`.', '',
              '`hal_disable_auc` and `hal_disable_dsp` each contain two bytes,',
              '`e0 7e`, disassembled as `j_s [blink]`. `hal_disable_muc` is a',
              'distinct 14-byte function. Source inspection establishes its reset',
              'request; neither disassembly nor write ordering proves hardware quiescence.', '',
              '## What can be reused, and what remains required', '',
              'The existing radar shutdown has genuine joins for retry/work, OCAC IRQ',
              'and tasklet, CAC/DFS/NOP timers and the provider lifetime. Linux IRQ',
              'release and existing WLAN work flushes are useful parts of teardown.',
              'They must not be described as stopping independent AuC/DSP processors.', '',
              'A future implementation needs a demonstrated processor/DMA retirement',
              'contract, revocation and join of TQE callbacks before freeing `qw`,',
              'correct nulling/recreation of mapped statistics, checked resource teardown,',
              'a typed lifecycle entry point that does not misuse rmmod, retention of',
              'remaining NOP deadlines, and a radio-only reset with Ethernet ownership',
              'preserved. No firmware/wire layout change or guessed reset is proposed.', '',
              'No variant of F344 is promoted by F353. The next implementation is to',
              'be selected from these findings, not inferred from a successful stop return.', '',
              '## Evidence and operational boundary', '',
              '- Result: `' + str((out / 'result.json').relative_to(ROOT)).replace('\\', '/') + '`.',
              '- `source-evidence.json` contains complete excerpts, original line ranges,',
              '  whole-file SHA-256 and excerpt SHA-256 for both OEM and port sources.',
              '- `elf-evidence.json` contains symbol offsets, bytes, hashes and objdump output.',
              '- This persistence checks C: free space >500 MiB before and after writing.',
              '- No compiler, router, UART, SSH, AELITA, reset, flash or RF operation ran.',
              '- F344 manifest remains SHA-256 `' + F344_MANIFEST_SHA + '`.', '']
    doc = '\n'.join(lines)
    (out / 'REPORT.md').write_text(doc)
    canonical = ROOT / 'docs/OPENMITRASTAR_F353_RADIO_EPOCH_AUDIT.md'
    if canonical.exists():
        raise ValueError('F353 canonical report already exists; do not overwrite it')
    canonical.write_text(doc)
    free_after = guard()
    if sha(F344_MANIFEST) != F344_MANIFEST_SHA or sha(module) != MODULE_SHA:
        raise ValueError('F344 immutable binding changed during persistence')
    result = {
        'schema': 'openmitrastar.f353-radio-epoch-audit/v1',
        'status': 'NO_GO_RESTART_BOUNDARY_NOT_PROVEN',
        'evidence_validation': 'PASS_SOURCE_AND_EXISTING_ELF_BINDINGS',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'findings': findings,
        'source_evidence': {'path': str(out / 'source-evidence.json'), 'sha256': sha(out / 'source-evidence.json'), 'anchors': len(evidence)},
        'elf_evidence': {'path': str(out / 'elf-evidence.json'), 'sha256': sha(out / 'elf-evidence.json'), 'module_sha256': MODULE_SHA},
        'report': {'path': str(out / 'REPORT.md'), 'sha256': sha(out / 'REPORT.md')},
        'canonical_report': {'path': str(canonical), 'sha256': sha(canonical)},
        'f344_closure': {'path': str(CLOSURE / 'manifest.json'), 'sha256': sha(CLOSURE / 'manifest.json')},
        'f344_manifest_unchanged': {'path': str(F344_MANIFEST), 'sha256': sha(F344_MANIFEST)},
        'disk_guard': {'minimum_free_bytes': GUARD, 'free_before': free_before, 'free_after': free_after},
        'new_build': False, 'new_driver_variant': False, 'hardware_access': False,
        'wire_abi_changed': False, 'reset_executed': False, 'firmware_epoch_proven': False,
        'wifi_physical': 'USER_DEFERRED',
    }
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'sha256': sha(out / 'result.json'),
                      'status': result['status'], 'anchors': len(evidence),
                      'report': str(canonical), 'free_after': free_after}, indent=2))


if __name__ == '__main__':
    main()
