"""Seal an offline, bounded mailbox/CAC search without promoting driver ops."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUC_SHA = '71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4'
MAP_SHA = 'f5878c74735e08516b4345e36a30e9a5c9f610c7439b471bf8cb2b9264722906'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dossier(path):
    found = []
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('pseudocode'), str) and value.get('procedure'):
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(json.loads(path.read_text()))
    assert found, path
    return max(found, key=lambda value: len(value['pseudocode']))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), args.output
    args.output.mkdir(parents=True)
    source = ROOT / 'work/rc1-radio-drivers-20260824-extract/openmitrastar-linux510-radio-drivers-product-rc1-20260824/radio5g/firmware/qtn_driver.qtn_ruby.0.bin'
    mapping = ROOT / 'outputs/rea/rbs-muc-loaded-segments-20261023T004700Z-r1'
    elf = mapping / 'muc-LOADED-SEGMENTS-ANALYSIS_ONLY.elf'
    assert sha(source) == MUC_SHA and sha(elf) == MAP_SHA
    pins = {}
    def pin(path):
        pins[str(path)] = sha(path)
    for path in (source, elf, mapping/'result.json', mapping/'muc-all-payload-disassembly.txt', Path(__file__)):
        pin(path)
    functions = {}
    queries = {
        'mailbox_init': ('rbs-muc-mailbox-init-fullmap-20261023T005400Z-r1', '0xf0bdc', 348),
        'response_message_post': ('rbs-muc-hostmsg-reap-fullmap-20261023T005700Z-r1', '0xefe3c', 380),
        'name_tx_restrict_actual_global_time': ('rbs-muc-tx-restrict-fullmap-20261023T010100Z-r1', '0x12dbb4', 20),
        'name_scheduler_actual_rx_tqe': ('rbs-muc-scheduler-sram-fullmap-20261023T010400Z-r1', '0x800239d8', 416),
        'tx_queue_setup_cleanup': ('rbs-muc-tx-setup-fullmap-20261023T010700Z-r1', '0x12a34c', 386),
        'actual_tasklet_scheduler': ('rbs-muc-actual-tasklet-scheduler-20261023T011000Z-r1', '0x80023900', 216),
        'actual_netdev_init_callback': ('rbs-muc-real-netdev-tx-callback-20261023T011300Z-r1', '0x10862c', 1024),
        'name_mgmt_xmit_actual_sync_auc_ipc': ('rbs-muc-mgmt-xmit-fullmap-20261023T011600Z-r1', '0x1563ac', 420),
    }
    for key, (dirname, address, size) in queries.items():
        directory = ROOT/'outputs/rea'/dirname
        receipt = json.loads((directory/'result.json').read_text())
        assert receipt['exit_code'] == 0 and receipt['target_unchanged']
        assert receipt['target_sha256'] == MAP_SHA
        assert sha(directory/'rea.json') == receipt['rea_output_sha256']
        function = dossier(directory/'rea.json')
        assert function['procedure']['address'] == address
        if size is not None:
            assert function['procedure']['body']['total_bytes'] == size
        target = args.output/(key+'.pseudocode.c')
        target.write_text(function['pseudocode'])
        functions[key] = {
            'address': address, 'body': function['procedure']['body'],
            'rea_sha256': receipt['rea_output_sha256'],
            'pseudocode_sha256': sha(target),
            'started_utc': receipt['started_utc'], 'finished_utc': receipt['finished_utc'],
            'callees': [{'address': item['address'], 'name': item['name']} for item in function.get('callees', [])],
            'warnings_retained': True,
        }
        pin(directory/'rea.json'); pin(directory/'result.json')
    raw = source.read_bytes()
    symbols = []
    wanted = {b'uc_hostif_init_mbox', b'uc_scheduler', b'qtn_tx_restrict_process', b'uc_hostif_getsemaphore', b'uc_hostif_release_semaphore', b'qtn_framedesc_acquire', b'qtn_auc_tqe_handle_lhost_mgmt'}
    for offset in range(0xec000, 0xf0240, 4):
        nameptr, address = struct.unpack_from('<II', raw, offset)
        nameoff = nameptr - 0xe0000 + 131796
        if 0 <= nameoff < len(raw):
            name = raw[nameoff:nameoff+100].split(b'\0')[0]
            if name in wanted:
                symbols.append({'original_table_offset': hex(offset), 'name': name.decode(), 'name_address': hex(nameptr), 'target_address': hex(address), 'authority': 'original metadata hint; independently verify body'})
    assert len(symbols) == len(wanted)
    (args.output/'original-symbol-hints.json').write_text(json.dumps(symbols, indent=2)+'\n')
    driver = ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver/src/linux-7.3-r20'
    rbs = driver/'source/wlan/openmitrastar_rbsdfs_kernel.inc'
    tx = driver/'source/qdrv/qdrv_tx.c'
    desc = ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver/vendor/port-context/include/qtn/lhost_muc_comm.h'
    assert 's->provider=NULL;' in rbs.read_text()
    assert 'qdrv_hostlink_xmitctl' not in rbs.read_text()
    for path in (rbs, tx, desc, ROOT/'tools/derive_rbs_muc_loaded_segments.py', ROOT/'outputs/rea/rbs-muc-exactframe-provider-audit-20261023T002500Z-r1/result.json'):
        pin(path)
    disasm = (mapping/'muc-all-payload-disassembly.txt').read_text()
    windows = {'mailbox_records': (0xf0ba4, 0xf0d38), 'ioctl_consumer': (0xf11c8, 0xf131c), 'descriptor_completion': (0xe7b84, 0xe7c74), 'semaphore_functions_actual': (0xf13bc, 0xf1404), 'tasklet_scheduler': (0x80023900, 0x800239d8)}
    for key, (begin, end) in windows.items():
        lines = []
        for line in disasm.splitlines():
            try:
                address = int(line.split(':', 1)[0].strip(), 16)
            except ValueError:
                continue
            if begin <= address < end:
                lines.append(line)
        assert lines
        (args.output/(key+'.gnu-assembly.txt')).write_text('\n'.join(lines)+'\n')
    result = {
        'status': 'PASS_BOUNDED_FULL_MUC_PAYLOAD_SEARCH_PROVIDER_UNRESOLVED',
        'hardware_accessed': False, 'firmware_eligible': False,
        'qualified_ops_added': 0, 'adapter_added': False, 'source_muc_sha256': MUC_SHA,
        'analysis_map_sha256': MAP_SHA, 'fresh_functions': functions,
        'mailbox_contract': {'mailbox_count': 130, 'mailbox_bytes': 520, 'netdev_mailbox_pointer_offset': '0x2c', 'netdev_records_pointer_offset': '0x44', 'record_bytes': 32, 'mailbox0_type': 6, 'mailbox1_type': 1, 'node_mailbox_indices': '2..129; type1'},
        'verified_paths': [
            'Host qdrv_tx_muc_post_hostdesc publishes management descriptor physical address in mailbox1 under semmap; chains hd_nextpa when occupied.',
            '0xf0ba4 initializes per-mailbox record status/semaphore and head/tail fields; it is initialization, not packet transmit.',
            '0xf11c8 selects record0, consumes ioctl linked list using descriptor+28 and netdev callback+124; it is not mailbox1 TX ingress.',
            '0xefe3c posts a 40-byte response/control message into shared6003a3c8/cc and raises host interrupt; not a frame-bound grant.',
            '0xe7b84 reads hd_muc_txdone_cb+48 and flags+448 (ARC ld.as112) and handles NO_RETURN/IMM_RETURN descriptor completion.',
            '0x80023900 schedules pending tasklets by callback pointers; the callbacks and runtime ordering are not resolved by its loop alone.',
            '0x800239d8 polls TQE and moves RX software-ring records to TQE; no management CAC authorization observed.',
            '0x12a34c clears TX queue state and invokes HAL setup/reset; it is not an exact-frame grant.',
            '0x10862c is radio/netdev initialization and channel/reset setup; the earlier tx callback filename is a discovery label, not established TX ingress.',
            '0x1563ac writes a synchronous AuC IPC command record via18c260, rings e0000178 and waits for command completion with loopout/halt handling; it is not the management-frame TQE publisher.',
        ],
        'label_corrections': [
            'Original name uc_scheduler points800239d8 but instructions and embedded diagnostic string identify RXsoft-ring-to-TQE; actual tasklet loop80023900.',
            'Original name qtn_tx_restrict_process points12dbb4 but exact20-byte body returns global20fd44 times10.',
            'Original getsemaphore pointsf13f4 but body is semaphore release tail-call; actual semaphore acquire spin startsf13bc.',
            'Original release_semaphore pointsf1404 but body begins host-interface information setup.',
            'Original qtn_framedesc_acquire109450 had BA diagnostic body in preceding receipt; names are not sufficient function qualification.',
            'Original qtn_auc_tqe_mgmt_xmit points1563ac but its diagnostic strings/body identify qtn_mproc_sync_auc_ipc_wait_done; command-specific callers/AuC consumer remain unqualified.',
        ],
        'physical_load_map_correction': 'Segment3 VA80020000 has paddr46e004; map it at46e004, never overlay segment2 at80020000. Segment5 exact bytes also appear at a declared6003a3c0 virtual alias; cache/hardware alias proof remains unrun.',
        'bounded_negative': 'No exact-frame CAC provider contract established in examined queue/init/completion/TQE/tasklet paths. This is not proof of absence in the full MuC or AuC firmware.',
        'remaining': [
            'Identify actual mailbox1 descriptor consumer and admission callback, including any AuC or shared-firmware ownership.',
            'Map frame identity/channel/role/deadline from host TX descriptor to scheduling, grant/revoke and completion.',
            'Resolve runtime initialized callbacks and SRAM relocation/aliases without confusing original metadata with code.',
            'AuC default e1fd397e and nomu c10018f4 remain distinct; neither received instruction analysis in this lane.',
        ],
        'provider_source_state': 'R20 reference providerNULL, no globalTX fallback; R24 sources were not edited.',
        'no_active_jobs_expected': True,
    }
    assert all(sha(path) == digest for path, digest in pins.items())
    (args.output/'input-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'provider_found': False, 'qualified_ops_added': 0, 'result_sha256': sha(args.output/'result.json'), 'input_pins_sha256': sha(args.output/'input-pins.json')}))

if __name__ == '__main__':
    main()
