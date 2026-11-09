"""Immutable F372 install preparation. File reads only; no hardware executor.

Validates real candidate, exact F365 return, source provenance and Bootbase.
Offline validation and an owner receipt alone never confer physical GO.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import zlib
from pathlib import Path

from bootbase_contract_emulator import image_to_dict, validate_bootbase_slot
from f346_install_contract import protected_backups

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / '.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
FIRMWARE = DEVICE / 'firmware'
LIVE, PREFIX, SLOT, STORE, STORE_BYTES = 0x7e0000, 0x5e0000, 0x7a0000, 0xdc0000, 0x1c0000
LOAD, READBACK, SCRATCH = 0x83000000, 0x86000000, 0x84000000
PNP = r'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'
PLAN_SCHEMA = 'openmitrastar.f372-install-contract-plan/v1'
AUTH_SCHEMA = 'openmitrastar.f372-exact-owner-authorization/v1'
BOOTARGS = 'earlycon=uart8250,mmio32,0xf0000000 console=ttyS0,115200n8 root=31:3 rootfstype=squashfs ro rootwait init=/sbin/init panic=10'
OWNER = ROOT / 'outputs/locks/f301-physical-radio.lock/owner.json'
OWNER_SHA = '37c47a29576b1da2743057d974e1ec3850965c98eef956ba04ff2973e21b1b48'
OLD_PLAN = ROOT / 'outputs/preflight/f367r9-campaign-20260922T224746Z/plan.json'
OLD_PLAN_SHA = '178f62662d01d20388f5e029bd54e452f45a84ce67829b4d0d5eecb1d46f13fa'
SAFETY_HISTORY = ROOT / 'outputs/recovery/mtd3-current-evidence-20260901/result.json'
SAFETY_HISTORY_SHA = '1fc190e9e920b5afde938ae26be6bb6d450813b4b931e250f0c3eccbc1fa57e7'
SPECS = {
    'f372': dict(directory='f372-f371-auc-tqe-observation-device-bound', bytes=5382144,
        sha256='e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9',
        manifest_sha256='e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5',
        version='lyoko-foundation-6.12.3-f372-auc-tqe-observation-device',
        prefix_crc32='7b60a3c8', full_slot_crc32='9a81d387', known_hosts='known_hosts.f372'),
    'f365': dict(directory='f365-f364r3-temperature-data-device-bound', bytes=5382144,
        sha256='43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355',
        manifest_sha256='a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c',
        version='lyoko-foundation-6.9.13-f365-temperature-data-device',
        prefix_crc32='b858f5da', full_slot_crc32='118901d4', known_hosts='known_hosts.f365'),
    'f367r9': dict(directory='f367r9-f365-transition-observation-device-bound', bytes=5468160,
        sha256='6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440',
        manifest_sha256='eff3e150b7c9a03d1cac95fe3ffae3fff374180ce0ff58215acf9ff230181858',
        version='lyoko-foundation-6.11.8-f367r9-transition-observation-device',
        prefix_crc32='2eb9b399', full_slot_crc32='4fa4640f', known_hosts='known_hosts.f367'),
}
PROOFS = {
    'image_build': (DEVICE/'analysis/f372-fullimage-20261021T193818Z/result.json',
        '1dbe7893d65f5848714d0db26bcb075934737d16ca23ffcde5267f88665aa14b',
        'PASS_OFFLINE_F372_AUC_TQE_OBSERVATION_IMAGE'),
    'packaged_module': (ROOT/'outputs/rea/arc700-20261021-r2/f372-packaging-verification-20261021T194000Z/result.json',
        '2ae693b9e643df009575ff5206c8c3346a4f9265d53c6c594c21e39329eb1b19',
        'PASS_EXACT_PACKAGED_MODULE_AND_METADATA'),
    'rea_provenance': (ROOT/'outputs/rea/arc700-20261021-r2/f372-rea-provenance-20261021T194100Z/result.json',
        '1633f5847147e0306d961d5c955fc4ba8c04f14ee36a8e9da44c25311543bdc0',
        'PASS_REA_EXACT_PACKAGED_QDRV_PROVENANCE'),
}
WRITER_SOURCES = (
    'f365_install_executor.py', 'f365_install_contract.py', 'f365_hardware_context.ps1',
    'assert_f365_context.ps1', 'f367r9_return_f365.py', 'f367_uart_capture_r2.py',
    'f336_wdt_ram_executor.py', 'f362_recovery_delta.py', 'f319_uart_guard.ps1',
    'f319_recovery_guard.ps1', 'f321_ssh_guard.ps1', 'f325_scoped_tftp.py',
    'f325_ethernet_server_process.py', 'f325_ethernet_ram_gate.py',
    'f325_existing_permission_contract.py', 'f346_install_contract.py',
    'bootbase_contract_emulator.py',
)


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crc(data):
    return f'{zlib.crc32(data) & 0xffffffff:08x}'


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate_json_field')
        out[key] = value
    return out


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def local_path(value, *, exists=True):
    p = Path(value)
    require(p.is_absolute() and p.drive.lower() in ('c:', 'd:'), 'absolute_local_path')
    require('..' not in p.parts and not str(p).startswith('\\\\'), 'local_path_scope')
    for ancestor in (p, *p.parents):
        if ancestor.exists():
            attributes = getattr(ancestor.stat(follow_symlinks=False), 'st_file_attributes', 0)
            require(not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, 'local_path_reparse')
    if exists:
        require(p.is_file(), 'local_file_missing')
    return p


def artifact(row):
    p = Path(row['path'])
    if not p.is_absolute():
        p = ROOT/p
    p = local_path(p)
    require(p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], 'artifact_drift')
    return dict(path=str(p), bytes=row['bytes'], sha256=row['sha256'])


def store_and_images():
    folder = FIRMWARE/SPECS['f372']['directory']
    require(sha(folder/'manifest.json') == SPECS['f372']['manifest_sha256'], 'candidate_manifest')
    candidate_manifest = read(folder/'manifest.json')
    store = artifact(candidate_manifest['preserved_store'])
    body = Path(store['path']).read_bytes()
    require(store['bytes'] == STORE_BYTES and store['sha256'] ==
            'fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873'
            and crc(body) == '5d2ee646', 'preserved_store')
    store['crc32'] = crc(body)
    result = {}
    for name, spec in SPECS.items():
        directory = FIRMWARE/spec['directory']
        manifest = directory/'manifest.json'
        require(sha(manifest) == spec['manifest_sha256'], 'manifest_'+name)
        m = read(manifest)
        p = directory/m['artifacts']['webformat']['file']
        require(p.parent == directory and p.is_file(), 'image_path_'+name)
        data = p.read_bytes()
        require(len(data) == spec['bytes'] and sha(p) == spec['sha256'], 'image_'+name)
        require(len(data) <= PREFIX, 'store_overlap_'+name)
        contract = image_to_dict(validate_bootbase_slot(name, data, SLOT))
        require(contract['accepted_by_contract'] and contract['header']['load'] == '0x8493a000'
                and contract['header']['entry'] == '0x8493e000', 'bootbase_'+name)
        prefix = data + b'\xff'*(PREFIX-len(data))
        full = prefix + body
        require(crc(prefix) == spec['prefix_crc32'] and crc(full) == spec['full_slot_crc32'], 'slot_crc_'+name)
        result[name] = dict(spec, directory=str(directory), path=str(p),
            manifest_path=str(manifest), kernel_build='#358', marker='F340_WATCHDOG_BASELINE',
            known_hosts_path=str(directory/spec['known_hosts']), crc32=crc(data),
            full_slot_sha256=hashlib.sha256(full).hexdigest(), bootbase=contract,
            full_slot_scope='checksum model only; never a write artifact')
    hosts = [Path(row['known_hosts_path']).read_bytes() for row in result.values()]
    require(hosts[0] == hosts[1] == hosts[2], 'known_hosts_identity_changed')
    require(candidate_manifest['artifacts']['full_slot']['sha256'] == result['f372']['full_slot_sha256'], 'candidate_fullslot_sha')
    recovery = candidate_manifest['recovery']
    require(recovery['image'] == result['f365']['path'] and recovery['sha256'] == result['f365']['sha256']
            and recovery['full_slot_crc32_with_preserved_store'] == result['f365']['full_slot_crc32'], 'manifest_fallback')
    return store, result, candidate_manifest


def validate_provenance(m):
    pins = dict(m['source']['inputs'])
    for name, digest in pins.items():
        require(sha(name) == digest, 'candidate_source_drift:'+name)
    refs, reports = {}, {}
    for name, (p, digest, status) in PROOFS.items():
        require(sha(p) == digest, 'proof_drift_'+name)
        r = read(p)
        require(r['status'] == status and r.get('hardware_accessed', r.get('hardware_actions')) is False, 'proof_scope_'+name)
        for path, source_sha in r.get('source_pins', {}).items():
            require(sha(path) == source_sha, 'proof_source_drift:'+path)
            pins[path] = source_sha
        refs[name] = dict(path=str(p), sha256=digest, status=status)
        reports[name] = r
    qref = artifact(m['evidence']['complete_qdrv_qualification'])
    q = read(qref['path'])
    require(q['status'] == 'PASS_OFFLINE_COMPLETE_MODULE' and q['reproducible'] is True
            and q['hardware_accessed'] is False and q['inputs_unchanged'] is True
            and q['full_baseline_comparison_status'] == 'PASS_FULL_BASELINE_RECONSTRUCTION', 'qdrv_qualification')
    require(q['imports_unchanged'] == 369 and q['exports_unchanged'] == 15, 'qdrv_abi')
    module = artifact(m['evidence']['qualified_qdrv'])
    require(module['sha256'] == 'd5e1f58303eaaa02123e0cf6352bd40c40df3027be300d2a1143b07f54a05dae'
            and module['bytes'] == 686144 and q['module']['sha256'] == module['sha256'], 'qdrv_exact')
    require(reports['packaged_module']['packaged_module_sha256'] == module['sha256']
            and reports['packaged_module']['permissions'] == '0444'
            and reports['packaged_module']['catalog_runtime_bindings_exact'] is True, 'packaged_module_scope')
    require(reports['rea_provenance']['packed_module_sha256'] == module['sha256']
            and reports['rea_provenance']['analysis_only_target_never_load'] is True, 'rea_scope')
    for row in m['evidence'].values():
        ref = artifact(row)
        pins[ref['path']] = ref['sha256']
    refs['qdrv_qualification'] = qref
    return refs, pins


def recovery_history(protected):
    require(sha(SAFETY_HISTORY) == SAFETY_HISTORY_SHA, 'safety_history_hash')
    r = read(SAFETY_HISTORY)
    safety = next(row for row in protected['parts'] if row['partition'] == 'mtd3')
    require(r['schema'] == 'openmitrastar.mtd3-recovery-evidence/v1'
            and r['status'] == 'RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE'
            and r['recovery_ready'] is False and r['mtd3']['sha256'] == safety['sha256']
            and r['checks']['management_proven'] is False and r['checks']['ssh_proven'] is False, 'safety_history_scope')
    contract = image_to_dict(validate_bootbase_slot('preserved_physical_mtd3', Path(safety['path']).read_bytes(), SLOT))
    return dict(path=str(SAFETY_HISTORY), sha256=SAFETY_HISTORY_SHA, status=r['status'],
        historical=True, current_recovery_ready='UNPROVEN', kernel_contract=contract,
        consequence='Bootbase kernel PASS does not prove rootfs/management recovery; require fresh manual mtd3 PASS before GO')


def authorization_scope(plan):
    return dict(device_id='hgw500bna-qcv2-a2-primary', host='192.168.1.90',
        image_path=plan['images']['f372']['path'], image_sha256=plan['images']['f372']['sha256'],
        image_bytes=plan['images']['f372']['bytes'], manifest_sha256=plan['images']['f372']['manifest_sha256'],
        physical_write_target='mtd4/linux_live', offset=LIVE, erase_bytes=PREFIX, erase_end_exclusive=STORE,
        rollback_path=plan['images']['f365']['path'], rollback_sha256=plan['images']['f365']['sha256'],
        rollback_bytes=plan['images']['f365']['bytes'], preserved_store_sha256=plan['store']['sha256'],
        uart_port='COM4', uart_pnp_device_id=PNP,
        actions=['one_controlled_ssh_reboot_to_fresh_bootbase', 'one_f372_prefix_install',
                 'boot_written_f372', 'conditional_exact_f365_prefix_return_and_boot'],
        exclusions=['protected_partitions', 'store_write', 'persistent_bootenv',
                    'serial_reset_fallback', 'manual_power_cycle', 'radio_reconfiguration'])


def scope_sha(scope):
    return hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def validate_owner_receipt(receipt, expected_scope):
    """Validate receipt structure/binding; human-message provenance is separate.

    This function does not create authorizations and cannot establish that a
    quoted message came from the owner. Root must verify its actual provenance.
    """
    require(isinstance(receipt, dict), 'authorization_not_receipt')
    require(receipt.get('schema') == AUTH_SCHEMA and receipt.get('authority') == 'human_user', 'authorization_schema')
    require(receipt.get('decision') == 'AUTHORIZE_EXACT_SCOPE' and receipt.get('scope') == expected_scope,
            'authorization_exact_scope')
    require(receipt.get('scope_sha256') == scope_sha(expected_scope), 'authorization_scope_sha')
    message = receipt.get('owner_message', {})
    require(isinstance(message, dict) and isinstance(message.get('reference'), str)
            and len(message['reference'].strip()) > 0 and isinstance(message.get('text'), str)
            and len(message['text'].strip()) > 0, 'authorization_human_message_reference')
    require(receipt.get('reviewed_scope_sha256') == scope_sha(expected_scope), 'authorization_review_binding')
    require(receipt.get('hardware_actions_already_performed') is False, 'authorization_execution_scope')
    return dict(status='EXACT_SCOPE_RECEIPT_STRUCTURALLY_VALID_OWNER_PROVENANCE_REQUIRED',
                scope_sha256=scope_sha(expected_scope), confers_physical_go=False)


def validate_plan_scope(plan):
    require(plan['schema'] == PLAN_SCHEMA and plan['status'] == 'PASS_OFFLINE_CONTRACT_PHYSICAL_NO_GO', 'plan_schema')
    require(plan['hardware_actions'] is False and plan['executor_implemented'] is False
            and plan['physical_go'] is False, 'file_only_boundary')
    require(plan['write_target'] == 'physical_mtd4/linux_live'
            and (plan['offset'], plan['erase_bytes'], plan['erase_end_exclusive'], plan['slot_bytes'], plan['store_bytes'])
            == (LIVE, PREFIX, STORE, SLOT, STORE_BYTES), 'physical_prefix_scope')
    require(plan['offset'] + plan['erase_bytes'] == plan['erase_end_exclusive']
            and plan['offset'] + plan['slot_bytes'] == 0xf80000, 'region_end')
    require([p['partition'] for p in plan['protected']['parts']] == ['mtd0', 'mtd1', 'mtd2', 'mtd3', 'mtd5'], 'protected_scope')
    for name, spec in SPECS.items():
        row = plan['images'][name]
        require(all(row[key] == spec[key] for key in ('bytes', 'sha256', 'manifest_sha256', 'prefix_crc32', 'full_slot_crc32')), 'plan_exact_image_'+name)
    require(plan['host_binding']['uart_port'] == 'COM4' and plan['host_binding']['uart_pnp_device_id'] == PNP
            and plan['host_binding']['server_ipv4'] == '192.168.1.49'
            and plan['host_binding']['client_ipv4'] == '192.168.1.90'
            and plan['host_binding']['interface_index'] == 18, 'host_scope')
    require(plan['owner_authorization_scope'] == authorization_scope(plan)
            and plan['owner_authorization_scope_sha256'] == scope_sha(authorization_scope(plan)), 'review_scope')
    require(plan['recovery']['current_recovery_ready'] == 'UNPROVEN'
            and plan['fresh_physical_gates']['manual_mtd3_recovery'] == 'MISSING_REQUIRED_PASS', 'recovery_no_go')
    require(plan['writer_reuse']['unchanged_old_executor_permitted'] is False
            and plan['writer_reuse']['redundant_backup_copy_permitted'] is False, 'writer_adaptation_boundary')
    return plan


def prepare_contract():
    store, images, m = store_and_images()
    proofs, pins = validate_provenance(m)
    protected = protected_backups()
    recovery = recovery_history(protected)
    require(sha(OWNER) == OWNER_SHA and sha(OLD_PLAN) == OLD_PLAN_SHA, 'retained_parent_or_campaign_changed')
    old = read(OLD_PLAN)
    writer_pins = {}
    for name in WRITER_SOURCES:
        p = ROOT/'tools'/name
        digest = sha(p)
        if str(p) in old['sources']:
            require(digest == old['sources'][str(p)], 'historical_writer_drift:'+name)
        pins[str(p)] = digest
        writer_pins[str(p)] = digest
    for row in images.values():
        for field in ('path', 'manifest_path', 'known_hosts_path'):
            pins[row[field]] = sha(row[field])
    for ref in proofs.values():
        pins[ref['path']] = ref['sha256']
    pins.update({str(OWNER): OWNER_SHA, str(OLD_PLAN): OLD_PLAN_SHA,
        str(SAFETY_HISTORY): SAFETY_HISTORY_SHA, store['path']: store['sha256'],
        protected['manifest']: protected['sha256']})
    for row in protected['parts']:
        pins[row['path']] = row['sha256']
    pins[str(Path(__file__).resolve())] = sha(__file__)
    pins[str(ROOT/'tools/prepare_f372_install.py')] = sha(ROOT/'tools/prepare_f372_install.py')
    plan = dict(schema=PLAN_SCHEMA, status='PASS_OFFLINE_CONTRACT_PHYSICAL_NO_GO',
        hardware_actions=False, physical_go=False, executor_implemented=False,
        images=images, store=store, protected=protected, recovery=recovery, proofs=proofs, sources=pins,
        write_target='physical_mtd4/linux_live', offset=LIVE, erase_bytes=PREFIX,
        erase_end_exclusive=STORE, slot_bytes=SLOT, store_bytes=STORE_BYTES,
        erased_prefix_crc32=crc(b'\xff'*PREFIX), bootargs=BOOTARGS,
        host_binding=dict(uart_port='COM4', uart_pnp_device_id=PNP, interface_index=18,
            server_ipv4='192.168.1.49', client_ipv4='192.168.1.90', freshness='UNRUN_BY_THIS_OFFLINE_CONTRACT'),
        retained_parent=dict(owner_path=str(OWNER), owner_sha256=OWNER_SHA,
            old_port='COM3', preserve_without_rewrite=True, old_pid_is_not_live_authority=True),
        writer_reuse=dict(source_hashes=writer_pins, reuse_functions=['write_image', 'domain',
            'flash_crc', 'boot_written'], unchanged_old_executor_permitted=False,
            redundant_backup_copy_permitted=False, adaptations_required=[
                'COM4 nonce/PnP/lease context and retained-parent child ownership',
                'F367r9 live baseline with F365 rollback and F372 candidate, not F364',
                'Reference existing exact F365 image without Host.backup_reference copying',
                'Fresh authorized controlled reboot and fresh Bootbase proof',
                'No BREAK+b serial fallback without separately reviewed owner authority',
                'Reviewed one-file TFTP exposure/permission, guard and containment on Ethernet18']),
        fresh_physical_gates=dict(exact_owner_authorization='MISSING_REQUIRED_RECEIPT_AND_HUMAN_PROVENANCE',
            executor_review='MISSING_REQUIRED_REVIEW', manual_mtd3_recovery='MISSING_REQUIRED_PASS',
            uart_nonce_and_retained_parent_child='UNRUN', pinned_ssh_identity='UNRUN',
            management_and_watchdog_baseline='UNRUN', protected_physical_readback='UNRUN',
            current_f367r9_fullslot_readback='UNRUN', current_store_readback='UNRUN',
            reviewed_transport_exposure_and_permission='UNRUN', fresh_bootbase_domain='UNRUN'),
        execution_sequence=[
            'Verify exact scope owner receipt against original human authorization.',
            'Require fresh proven recovery and reviewed F372 executor before physical GO.',
            'Bind current SSH boot and COM4 nonce under retained-parent child lease; preserve parent.',
            'Check live management/watchdog/store, exact images and all frozen sources.',
            'One authorized SSH reboot into continuously observed fresh Bootbase; no bootenv persistence.',
            'Read protected physical partitions, full current F367r9 slot and store; abort on mismatch.',
            'Transfer exact F372 only via reviewed scoped transport; verify RAM CRC and Bootbase iminfo.',
            'Erase exactly 0x7e0000+0x5e0000, verify blank prefix and unchanged store immediately.',
            'Program exact 5382144-byte F372; byte compare and fullslot CRC9a81d387, protected/store readbacks.',
            'Boot written F372, validate new boot/version, management/2.4GHz/5GHz and immutable runtime bindings.',
            'If a qualified fault requires return, restore exact F365 prefix once only after fresh domain/store checks.',
            'Stop and retain lease after ambiguous write/transport/recovery; no automatic retry.',
        ],
        acceptance_pending=['persistent repeated cold boot', 'manual protected mtd3 recovery',
            '2.4 GHz WPA2 client and bidirectional traffic', '5 GHz real-client visibility and WPA2 authorization',
            '5 GHz useful bidirectional traffic, reconnection and fatal-free soak', 'release manifest and final acceptance'],
        forbidden_targets=['physical_mtd0', 'physical_mtd1', 'physical_mtd2', 'physical_mtd3',
            'physical_mtd5', 'logical_mtd6/rootfs_live', 'store_0xdc0000_0x1c0000'],
        limits=['Linux logical mtd3=rootfs and mtd4=store are not physical flash-number mappings.',
            'Checksum full-slot models must never be written as firmware files.',
            'No new backup or firmware copy created; existing private references remain immutable.',
            'F370 counters are measurements, not performance acceptance.',
            'Historical mtd3 kernel contract PASS coexists with rootfs/management NO_GO.',
            'Owner message receipt structure is insufficient without trusted human-message provenance.'])
    plan['owner_authorization_scope'] = authorization_scope(plan)
    plan['owner_authorization_scope_sha256'] = scope_sha(plan['owner_authorization_scope'])
    return validate_plan_scope(plan)


def load_plan(path, digest):
    require(sha(local_path(path)) == digest, 'plan_sha256')
    plan = validate_plan_scope(read(path))
    for name, expected in plan['sources'].items():
        require(sha(name) == expected, 'frozen_source_drift:'+name)
    store, images, _ = store_and_images()
    require(plan['store'] == store and plan['images'] == images, 'recomputed_image_binding')
    return plan
