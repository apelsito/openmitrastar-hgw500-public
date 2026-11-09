"""File-only full-port checkpoint; never authorizes or accesses hardware.

The older F314-F319 audit and its historical output remain untouched. Current
components and the selected installation record are kept separate from client,
RF, persistence and release acceptance.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
REVISIONS = {'F361': 'F361', 'F362': 'F362', 'F363': 'F363r2', 'F364': 'F364r3'}


def mapping(value):
    return value if isinstance(value, dict) else {}


def read_record(selected):
    """Hash the same bytes that were parsed; incomplete live records stay unaccepted."""
    observation = {'path': str(selected) if selected else None,
                   'record_status': 'NOT_PRESENT', 'accepted': False, 'reasons': []}
    if selected is None:
        return observation, None
    try:
        raw = Path(selected).read_bytes()
        observation['sha256'] = hashlib.sha256(raw).hexdigest()
        record = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(record, dict):
            raise ValueError('record is not an object')
    except FileNotFoundError:
        return observation, None
    except (ValueError, OSError):
        observation.update(record_status='UNREADABLE_RECORD', reasons=['result JSON unavailable or invalid'])
        return observation, None
    observation['record_status'] = record.get('status', 'STATUS_MISSING')
    return observation, record


def platform_pass(platform):
    checks = mapping(platform).get('checks')
    return (mapping(platform).get('schema') == 'openmitrastar.f214-device-postflash/v1'
            and platform.get('status') == 'PASS' and isinstance(checks, dict)
            and len(checks) == 27 and all(value is True for value in checks.values()))


def thermal_default_pass(row):
    row = mapping(row)
    return (row.get('module_version') == 363 and row.get('enabled') is False
            and row.get('activation_attempted') is False and row.get('activation_error') == -19
            and row.get('cached_status_only') is True and row.get('sensor_mmio_requested') is False)


def image_verified(image, status, schema=None, product_version=None):
    artifact = mapping(image.get('artifact'))
    try:
        raw = Path(artifact['path']).read_bytes()
        return (image.get('status') == status and (schema is None or image.get('schema') == schema)
                and (product_version is None or image.get('product_version') == product_version)
                and image.get('bootbase') == 'PASS'
                and image.get('slot_fit') is True and len(raw) == artifact['bytes']
                and hashlib.sha256(raw).hexdigest() == artifact['sha256'])
    except (KeyError, OSError, TypeError):
        return False


def inspect_installation(version, selected, image):
    """Read the selected/latest record, without treating absence or failure as PASS."""
    key = version.lower()
    if selected is None:
        runs = sorted(path for path in Path('/workspace/OpenMitraStar', key+'-evidence').glob(key+'-install-*') if path.is_dir())
        selected = runs[-1]/'result.json' if runs else None
    observation, record = read_record(selected)
    observation['baseline_promoted'] = False
    observation['candidate_revision'] = REVISIONS[version]
    observation['candidate_product_version'] = image.get('product_version')
    if record is None:
        return observation, None, None
    writer, store = mapping(record.get('writer')), mapping(record.get('store_after'))
    config, identity = mapping(record.get('configuration_boot')), mapping(record.get(key+'_identity'))
    platform_path = selected.parent/('platform-'+key)/'status.json'
    platform_observation, platform = read_record(platform_path)
    checks = {
        'explicit_installation_pass': record.get('schema') == 'openmitrastar.'+key+'-install-result/v1'
            and record.get('status') == 'PASS_'+version+'_PRESERVED_JOURNAL',
        'exact_candidate_readback': writer.get('image') == image['artifact']['sha256']
            and writer.get('bytes') == image['artifact']['bytes'] and writer.get('byte_compare') is True
            and writer.get('full_slot_crc32') == image['full_slot']['crc32'],
        'preserved_seq2_store': store.get('sha256') == image['preserved_store']['sha256']
            and store.get('bytes') == image['preserved_store']['bytes'],
        'saved_configuration_loaded': config.get('source') == 'journal' and config.get('sequence') == 2
            and config.get('active_sha256') == '073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9',
        'candidate_kernel_identity': identity.get('uts') == '#358 @1790006400'
            and identity.get('f340') == 'F340_WATCHDOG_BASELINE' and bool(identity.get('boot_id')),
        'platform_pass': platform_pass(platform)
            and mapping(record.get('platform')).get('sha256') == platform_observation.get('sha256'),
        'finished_and_contained': record.get('containment_confirmed') is True
            and record.get('retain_lease_required') is False
            and record.get('flash_command_in_flight') is False,
    }
    if version in ('F363', 'F364'):
        checks['temperature_cached_default_only'] = thermal_default_pass(record.get('thermal_default'))
    observation.update(checks=checks, accepted=all(checks.values()), baseline_promoted=all(checks.values()),
                       reasons=[name for name, passed in checks.items() if not passed])
    if isinstance(platform, dict):
        observation['platform'] = platform_observation
    return observation, record, platform


def inspect_f362_installation(selected, image):
    return inspect_installation('F362', selected, image)


def inspect_temperature(selected, installation, installation_record, image):
    """Accept only the actual F363 activation campaign, never image/driver tests."""
    observation, record = read_record(selected)
    observation.update(tested_firmware=REVISIONS['F363'], tested_product_version=image.get('product_version'), calibration_accepted=False,
                       new_conversion_per_read_proven=False)
    if record is None:
        return observation
    baseline = mapping(record.get('baseline'))
    returned = mapping(record.get('return_identity'))
    identity = mapping(mapping(installation_record).get('f363_identity'))
    samples = record.get('samples')
    reset_count = mapping(record.get('uart_epoch')).get('reset_signatures')
    def valid_sample(sample):
        sample = mapping(sample)
        temp, low, high = (sample.get(name) for name in ('temp_upper_mc', 'interval_lower_mc', 'interval_upper_mc'))
        return (all(type(value) is int for value in (temp, low, high))
                and -40000 <= temp <= 125000 and temp % 5000 == 0
                and -40000 <= high <= 125000 and high % 5000 == 0 and low == high-5000
                and sample.get('independent_reads') is True and sample.get('calibration_verified') is False)
    checks = {
        'real_campaign_pass': record.get('schema') == 'openmitrastar.f363-temperature-activation-result/v1'
            and record.get('status') == 'PASS_F363_SENSOR_SAMPLES_AND_AUTONOMOUS_RETURN',
        'bound_to_accepted_f363_boot': installation['accepted'] and bool(identity.get('boot_id'))
            and baseline.get('boot_id') == identity.get('boot_id') and baseline.get('uts') == '#358 @1790006400',
        'single_successful_activation': record.get('activation_attempts') == 1
            and record.get('activation') == dict(activation_rc='0', enabled='1', activation_attempted='1', activation_error='0'),
        'three_independent_read_pairs': isinstance(samples, list) and len(samples) == 3
            and all(valid_sample(sample) for sample in samples),
        'watchdog_owned_before_activation': all(mapping(record.get(name)).get('hardware_arm_confirmed') is True
            and mapping(record.get(name)).get('fd_held') is True
            and mapping(record.get(name)).get('first_pet_confirmed') is True for name in ('owner_arm', 'owner_begin')),
        'autonomous_return': record.get('baseline_returned') is True and record.get('software_recovery') is False
            and mapping(record.get('owner_cease')).get('state') == 'ceased-fd-held'
            and bool(returned.get('boot_id')) and returned.get('boot_id') != baseline.get('boot_id')
            and returned.get('uts') == '#358 @1790006400'
            and type(reset_count) is int and reset_count >= 1
            and mapping(record.get('uart_epoch')).get('fatal_seen') is False,
        'cached_default_restored': thermal_default_pass(record.get('thermal_after')),
        'configuration_and_store_preserved': mapping(record.get('store_after')).get('sha256') == image['preserved_store']['sha256']
            and mapping(record.get('configuration_after')).get('active_sha256') == '073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9',
        'contained_and_owner_released': record.get('containment_confirmed') is True
            and record.get('retain_lease_required') is False and record.get('guardian_may_remain_armed') is False,
        'bounded_non_radio_scope': all(record.get(name) is False for name in ('flash_writes', 'radio_actions', 'bootbase_commands', 'autoboot_intercept')),
    }
    for phase in ('before', 'after'):
        platform_observation, platform = read_record(Path(selected).parent/('platform-'+phase)/'status.json')
        checks['platform_'+phase] = (platform_pass(platform)
            and mapping(record.get('platform_'+phase)).get('sha256') == platform_observation.get('sha256'))
    observation.update(checks=checks, accepted=all(checks.values()),
                       reasons=[name for name, passed in checks.items() if not passed],
                       artifact_sha256=image['artifact']['sha256'],
                       installation_result_sha256=installation.get('sha256'),
                       samples=samples, return_boot_id=returned.get('boot_id'))
    return observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wifi-policy', choices=('deferred', 'not-provided'), default='not-provided')
    parser.add_argument('--f362-install-result', type=Path,
                        help='Optional real F362 installer result; absence/failure retains the F361 accepted baseline')
    parser.add_argument('--f363-install-result', type=Path,
                        help='Optional real F363-family installer result bound to the exact F363r2 image')
    parser.add_argument('--f364-install-result', type=Path,
                        help='Optional real F364-family installer result bound to the exact F364r3 image')
    parser.add_argument('--f363-sensor-result', type=Path,
                        help='Explicit real F363 sensor campaign on accepted F363r2; image qualification is insufficient')
    args = parser.parse_args()
    paths = {
        'installation': Path('/workspace/OpenMitraStar/f361-evidence/f361-install-20260921T192436Z-34833167/result.json'),
        'platform': Path('/workspace/OpenMitraStar/f361-evidence/f361-install-20260921T192436Z-34833167/platform-f361/status.json'),
        'persistence': Path('/workspace/OpenMitraStar/f360-evidence/f360-save-20260921T183947Z-b2328b27/result.json'),
        'normal_config_commit': ROOT/'outputs/handoff-live/f361-normal-save-20260921T193655Z/result.json',
        'autonomous_boot': ROOT/'outputs/handoff-live/f361-autoboot-20260921T194036Z/result.json',
        'current_store_capture': DEVICE/'analysis/f361-store-seq2-20260921T193734Z/result.json',
        'physical_flash_identification': Path('/workspace/OpenMitraStar/f359-evidence/f359-observe-20260921T180806Z-10cd4f98/result.json'),
        'no_xip_regression': ROOT/'outputs/preflight/f358-map-resource-20260921T173857Z/result.json',
        'previous_failed_spi_probe': ROOT/'outputs/handoff-live/f349-passive-20260921T162050Z-0cb97d7b/result.json',
        'watchdog_cessation': ROOT/'outputs/handoff-live/f336-ram-20260921T133950Z-51c6016b/result.json',
        'dfs_image': ROOT/'outputs/preflight/f341-fullimage-20260921T135223Z/result.json',
        'dfs_real_cpu_math': ROOT/'outputs/handoff-live/f338-ram-math-20260921T133822Z/result.json',
        'temperature_driver': ROOT/'outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z/result.json',
        'wps_control': ROOT/'outputs/kernel-port/f335-wps-control-20260921T125655Z/result.json',
        'wps_negative_status': ROOT/'outputs/handoff-live/f335-status-compat-20260921T130439Z/result.json',
        'journal': ROOT/'outputs/kernel-port/f342-config-journal-20260921T141638Z/result.json',
        'journal_review': ROOT/'outputs/preflight/f342-readonly-review-20260921T141855Z/result.json',
        'supplicant': ROOT/'outputs/userspace/f344-wpa-final-20260921T145403Z/manifest.json',
        'mode_components': ROOT/'outputs/handoff/f344-mode-components-20260921T162648Z/manifest.json',
        'spi_protocol': ROOT/'outputs/kernel-port/f345-protocol-20260921T141539Z/result.json',
        'spi_passive_module': ROOT/'outputs/kernel-port/f347-passive-spi-control-20260921T145647Z/result.json',
        'flash_reader_arbitration': ROOT/'outputs/preflight/f348-qualified-20260921T154126Z/result.json',
        'flash_provider_model': ROOT/'outputs/preflight/f350-provider-tests-20260921T161200Z/result.json',
        'flash_provider_qualification': ROOT/'outputs/preflight/f350-qualified-20260921T161419Z/result.json',
        'journal_cli': ROOT/'outputs/userspace/f351-journal-cli-20260921T162420Z/result.json',
        'journal_cli_real_arc_negative': ROOT/'outputs/handoff-live/f351-negative-arc-20260921T164227Z/result.json',
        'dual_ethernet': ROOT/'outputs/kernel-port/f352-qualified-20260921T163718Z/result.json',
        'dual_ethernet_image': DEVICE/'analysis/f362-fullimage-20260921T200242Z/result.json',
        'temperature_image': DEVICE/'analysis/f363r2-fullimage-20260921T211851Z/result.json',
        'lifetime_image': DEVICE/'analysis/f364r3-fullimage-20260921T212001Z/result.json',
        'historical_f363_image': DEVICE/'analysis/f363-fullimage-20260921T204859Z/result.json',
        'historical_f363_failed_installation': Path('/workspace/OpenMitraStar/f363-evidence/f363-install-20260921T210511Z-7e8c7914/result.json'),
        'historical_f364_image': DEVICE/'analysis/f364-fullimage-20260921T205724Z/result.json',
        'historical_f364r2_image': DEVICE/'analysis/f364r2-fullimage-20260921T211441Z/result.json',
        'ethernet_management_traffic': ROOT/'outputs/handoff-live/f362-management-stream-20260921T202006Z/result.json',
        'serial_recovery_probe': Path('/workspace/OpenMitraStar/f362-uart-evidence/f362-uart-20260921T200416Z-9cbb58e8/result.json'),
        'radio_restart_audit': ROOT/'outputs/preflight/f353-radio-epoch-20260921T163701Z/result.json',
        'radio_lifetime': Path('/workspace/OpenMitraStar-build/f355/f355-qualified-20260921T170051Z/result.json'),
        'original_empty_store_backup': DEVICE/'analysis/f356-store-readonly-20260921T165949Z/result.json',
        'current_config_contract': DEVICE/'analysis/f360-config-contract-20260921T182515Z/manifest.json',
        'parity_inventory': ROOT/'outputs/port-parity/hgw500-20260921T095258Z/PARITY.md',
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit('Missing checkpoint evidence: '+', '.join(missing))
    evidence = {name: json.loads(path.read_text(encoding='utf-8-sig')) for name, path in paths.items() if path.suffix == '.json'}
    install, platform = evidence['installation'], evidence['platform']
    if install['status'] != 'PASS_F361_PRESERVED_JOURNAL' or platform['status'] != 'PASS':
        raise SystemExit('Selected physical installation is not accepted')
    persistence = evidence['persistence']
    if persistence['status'] != 'PASS_F360_CONFIG_SAVED_AND_PERSISTED' or not persistence['return']['persisted_expected_record']:
        raise SystemExit('Selected physical persistence record is not accepted')
    if evidence['normal_config_commit']['status'] != 'PASS_REAL_NORMAL_CONFIG_COMMIT' or evidence['autonomous_boot']['status'] != 'PASS_AUTONOMOUS_REBOOT_WITH_SAVED_CONFIG':
        raise SystemExit('Normal configuration commit/autonomous boot is not accepted')
    images = {version: evidence[name] for version, name in (
        ('F362', 'dual_ethernet_image'), ('F363', 'temperature_image'), ('F364', 'lifetime_image'))}
    offline = {version: image_verified(images[version], status, schema, product) for version, status, schema, product in (
        ('F362', 'PASS_OFFLINE_DUAL_ETHERNET_IMAGE', 'openmitrastar.f362-image-build/v1',
         'lyoko-foundation-6.9.10-f362-dual-ethernet-device'),
        ('F363', 'PASS_OFFLINE_TEMPERATURE_OWNER_IMAGE', 'openmitrastar.f363r2-temperature-owner-image/v1',
         'lyoko-foundation-6.9.11-f363r2-temperature-owner-device'),
        ('F364', 'PASS_OFFLINE_LIFETIME_START_HASH_FIXED_IMAGE', 'openmitrastar.f364r3-lifetime-image/v1',
         'lyoko-foundation-6.9.12-f364r3-lifetime-device'))}
    uart = evidence['serial_recovery_probe']
    uart_pass = (uart.get('status') == 'PASS_SERIAL_SYSRQ_AND_AUTONOMOUS_F361_RETURN'
                 and uart.get('new_reset_signature') is True and uart.get('sysrq_dispatch_seen') is True
                 and uart.get('wire', {}).get('break_cleared') is True and uart.get('wire', {}).get('b_written') is True
                 and uart.get('containment_confirmed') is True and uart.get('retain_lease_required') is False
                 and uart.get('before', {}).get('boot_id') != uart.get('after', {}).get('boot_id')
                 and uart.get('after', {}).get('ready') == 'ready'
                 and uart.get('after', {}).get('source') == 'journal' and uart.get('after', {}).get('sequence') == '2')
    installations, records, platforms = {}, {}, {}
    installed = 'F361'
    for version, image in images.items():
        observation, candidate_record, candidate_platform = inspect_installation(
            version, getattr(args, version.lower()+'_install_result'), image)
        if not offline[version]:
            observation.update(accepted=False, baseline_promoted=False)
            observation['reasons'].append('offline_candidate_not_verified')
        installations[version], records[version], platforms[version] = observation, candidate_record, candidate_platform
        if observation['accepted']:
            installed, platform = version, candidate_platform
    for version, observation in installations.items():
        observation['baseline_promoted'] = version == installed
    installed_revision = REVISIONS[installed]
    f362_install = installations['F362']
    traffic = evidence['ethernet_management_traffic']
    f362_traffic_pass = (f362_install['accepted']
                    and traffic.get('status') == 'PASS_F362_EXISTING_MANAGEMENT_LINK_1MIB_EACH_DIRECTION'
                    and traffic.get('installation_result_sha256') == f362_install.get('sha256')
                    and traffic.get('containment_confirmed') is True
                    and traffic.get('pc_to_hgw', {}).get('sha256_match') is True
                    and traffic.get('hgw_to_pc', {}).get('sha256_match') is True
                    and traffic.get('before', {}).get('boot_id') == mapping(records['F362']).get('f362_identity', {}).get('boot_id')
                    and traffic.get('after', {}).get('boot_id') == traffic.get('before', {}).get('boot_id'))
    traffic_pass = installed == 'F362' and f362_traffic_pass
    sensor = inspect_temperature(args.f363_sensor_result, installations['F363'], records['F363'], images['F363'])
    sensor['direct_current_image_acceptance'] = sensor['accepted'] and installed == 'F363'
    runtime_scope = ('Verified '+installed_revision+' installation/readback/platform and preserved configuration; normal SAVE and autonomous reboot history is F361 predecessor evidence'
                     if installed != 'F361' else 'Last accepted baseline is F361 installation, normal commit and autonomous reboot; newer images remain separate candidates/attempts')
    if installed in ('F363', 'F364'):
        runtime_scope += '; F362 traffic is predecessor evidence only; no direct traffic test on '+installed_revision
    runtime_scope += '; this file-only audit does not assert current device reachability'
    temperature_acceptance = ('REAL_F363r2_SENSOR_READS_AND_AUTONOMOUS_RETURN_PASS' if sensor['direct_current_image_acceptance']
                              else 'F363r2_COMPONENT_PRECEDENT_ONLY_NO_DIRECT_CURRENT_IMAGE_SENSOR_TEST' if sensor['accepted']
                              else 'NOT_RUN_ON_SENSOR' if sensor['record_status'] == 'NOT_PRESENT' else 'SENSOR_RESULT_NOT_ACCEPTED')
    phy = 'USER_DEFERRED' if args.wifi_policy == 'deferred' else 'NOT_RUN_POLICY_NOT_PROVIDED'
    rows = [
        {'function': 'Linux 5.10 persistent image and management', 'implementation': installed_revision+'_INSTALLED', 'acceptance': 'INSTALL_READBACK_AND_PLATFORM_PASS_'+installed_revision if installed != 'F361' else 'PLATFORM_AND_AUTONOMOUS_REBOOT_PASS_F361', 'remaining': 'Final cold-power-cycle and release soak; F361 autonomous boot is predecessor evidence on newer images'},
        {'function': 'Watchdog', 'implementation': 'F358_DRIVER_AND_BOUNDED_OWNER_AVAILABLE', 'acceptance': 'GUARDED_RESET_AND_RETURN_OBSERVED_F360', 'remaining': 'Production service policy and CPU/bus-halt recovery unverified; F343 deliberate-stop preparation was automatically rejected and is not to be retried'},
        {'function': 'Native DFS pipeline and CAC consumer', 'implementation': 'F341_FULL_DIAGNOSTIC_IMAGE_OFFLINE_PASS', 'acceptance': 'F338_REAL_ARC_MATH_PASS_ONLY', 'remaining': phy+'; acquisition, RF, CAC/NOP/CSA and authority acceptance are not complete'},
        {'function': 'WPS', 'implementation': 'F335_CONTROL_AND_STARTUP_OFFLINE_PASS', 'acceptance': 'NEGATIVE_BASELINE_STATUS_COMPATIBILITY_ONLY', 'remaining': phy+'; enrollment, physical button/LED behavior and final image integration'},
        {'function': 'AP / STA / repeater', 'implementation': 'F344_MODES_OFFLINE; F355_LIFETIME_IN_F364r3_'+('INSTALLED' if installed == 'F364' else 'OFFLINE_IMAGE' if offline['F364'] else 'IMAGE_UNVERIFIED'), 'acceptance': 'MODE_PARITY_INCOMPLETE', 'remaining': 'F364r3 integrates only the lifetime fix, not F344 modes; safe transition after published CSA still requires a proven hardware epoch; no hot restart; '+phy},
        {'function': 'Configuration persistence', 'implementation': 'F361_INTEGRATION_RETAINED_IN_'+installed_revision, 'acceptance': installed_revision+'_PRESERVED_STORE_AND_BOOT_LOAD_PASS_F361_NORMAL_SAVE_HISTORY' if installed != 'F361' else 'REAL_SAVE_LOAD_RETENTION_NORMAL_COMMIT_AND_AUTONOMOUS_BOOT_PASS_F361', 'remaining': 'Power-cut acceptance and settings outside the 22 managed keys; advanced 5 GHz/credentials are not declared persistent'},
        {'function': 'Internal temperature', 'implementation': 'F339_CORE_F363r2_INTEGRATION_'+('INSTALLED_IN_'+installed_revision if installed in ('F363', 'F364') else 'OFFLINE_IMAGE' if offline['F363'] else 'IMAGE_UNVERIFIED'), 'acceptance': temperature_acceptance, 'remaining': 'Experimental activation stays explicit; calibration, physical temperature accuracy and fresh conversion per read are unproven'},
        {'function': 'Both Ethernet ports and bridge', 'implementation': 'F352_INTEGRATION_INSTALLED_IN_'+installed_revision if installed != 'F361' else ('F362_FULL_IMAGE_OFFLINE_PASS' if offline['F362'] else 'F362_OFFLINE_EVIDENCE_NOT_VERIFIED'), 'acceptance': 'ACTIVE_ETH1_MANAGEMENT_1MIB_EACH_DIRECTION_PASS_ON_CURRENT_F362' if traffic_pass else ('CURRENT_IMAGE_PLATFORM_PASS; F362_TRAFFIC_PRECEDENT_ONLY' if f362_traffic_pass else 'DIRECT_TRAFFIC_NOT_ACCEPTED'), 'remaining': 'No traffic acceptance is inherited across images; second physical connector and simultaneous bidirectional forwarding remain untested'},
        {'function': 'UART BREAK + b reset and autonomous baseline return', 'implementation': 'F362_SERIAL_SYSRQ_PROBE', 'acceptance': 'PASS_ON_F361_WITH_SEQ2_CONFIG' if uart_pass else 'NOT_ACCEPTED', 'remaining': 'This proves serial SysRq on responsive F361 Linux; it does not prove recovery from bus/CPU lockup, mtd3 safety boot or F362 Ethernet failure'},
        {'function': 'VLAN / multicast / IPv6 / QoS / controls', 'implementation': 'EXISTING_COMPONENTS_IN_PARITY_INVENTORY', 'acceptance': 'FINAL_MATRIX_NOT_COMPLETE', 'remaining': 'Complete and validate the exact product matrix, including TQE acceleration/QoS; SSH success does not prove all features'},
        {'function': 'Preserved OEM mtd3 safety boot', 'implementation': 'F337_READ_ONLY_BOOT_PLAN_ONLY', 'acceptance': 'NOT_PROVEN', 'remaining': 'Qualify actual preserved safety boot; F321 recovery is a separate verified path'},
    ]
    report = {
        'schema': 'openmitrastar.full-oem-port-checkpoint/v1',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'overall_status': 'IN_PROGRESS', 'release_complete': False,
        'hardware_access': False, 'execution_authority_determined': False,
        'installed_firmware': installed_revision, 'installed_kernel': '5.10.260-openmitrastar-radiohw',
        'installed_product_version': images[installed]['product_version'] if installed != 'F361' else 'lyoko-foundation-6.9.9-f361-config-persistence-device',
        'baseline_semantics': 'last accepted installation evidence, not a live hardware observation',
        'runtime_scope': runtime_scope,
        'mutable_store': {'sequence': 2, 'slot': 1, 'payload_bytes': 586, 'store_crc32': '5d2ee646',
                          'full_slot_crc32': images[installed]['full_slot']['crc32'] if installed != 'F361' else '815b9440',
                          'firmware_prefix_crc32': images[installed]['prefix_crc32'] if installed != 'F361' else '4cb7f99e'},
        'f362': {'offline_image_verified': offline['F362'], 'artifact': images['F362']['artifact'],
                 'serial_recovery_on_f361_accepted': uart_pass, 'installation': f362_install,
                 'active_management_traffic_accepted': f362_traffic_pass,
                 'traffic_applies_to_current_image': traffic_pass},
        'f363': {'candidate_revision': 'F363r2', 'product_version': images['F363']['product_version'],
                 'offline_image_verified': offline['F363'], 'artifact': images['F363']['artifact'],
                 'installation': installations['F363'], 'sensor': sensor},
        'f364': {'candidate_revision': 'F364r3', 'product_version': images['F364']['product_version'],
                 'offline_image_verified': offline['F364'], 'artifact': images['F364']['artifact'],
                 'installation': installations['F364'], 'hardware_epoch_or_hot_restart_proven': False},
        'historical_rejected_candidates': {
            revision: {'artifact': evidence[name]['artifact'], 'baseline_promoted': False,
                       'current_disposition': 'NO_GO_HISTORICAL_ONLY', 'reason': reason}
            for revision, name, reason in (
                ('F363', 'historical_f363_image', 'Physical platform failed; S16 temperature owner rejected by radio dirty-module gate; restored F362'),
                ('F364', 'historical_f364_image', 'Stale qdrv hash literal and inherited F363 temperature-owner rejection'),
                ('F364r2', 'historical_f364r2_image', 'Inherited F363 temperature-owner rejection'))},
        'direct_current_image_acceptance': {'installation_and_platform': True,
                 'ethernet_traffic': traffic_pass, 'sensor_reads': sensor['direct_current_image_acceptance'],
                 'normal_config_commit': installed == 'F361',
                 'autonomous_reboot': installed == 'F361' or sensor['direct_current_image_acceptance']},
        'physical_precedents': {'normal_config_commit_and_autoboot': 'F361',
                 'management_traffic': 'F362' if f362_traffic_pass else None,
                 'temperature_read_pairs': 'F363r2' if sensor['accepted'] else None},
        'physical_observation_time': platform['generated_at'],
        'current_image_watchdog': ('LAST_ACCEPTED_SENSOR_RETURN_OBSERVED_INACTIVE' if sensor['direct_current_image_acceptance']
                                  else 'NOT_INFERRED_FROM_UNACCEPTED_SENSOR_CAMPAIGN' if sensor['record_status'] != 'NOT_PRESENT' and not sensor['accepted']
                                  else 'LAST_ACCEPTED_INSTALLATION_OBSERVED_INACTIVE'),
        'wifi_acceptance_policy': args.wifi_policy,
        'requirements': rows,
        'source_records': {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'record_status': evidence[name].get('status') if name in evidence else 'REFERENCE_INVENTORY'} for name, path in paths.items()},
        'warnings': ['Offline checks do not establish physical acceptance', 'The historical F314-F319 audit is not a current installation or permission claim'],
    }
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'outputs/audit'/('hgw-full-port-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    lines = ['# HGW full OEM port checkpoint', '',
             'Overall: **IN PROGRESS**. Last accepted installation: **'+installed_revision+'**. F361 normal managed-config SAVE/autonomous boot history is retained. Full hardware/radio parity remains open.', '',
             'Installation evidence: '+', '.join(REVISIONS[version]+' `'+str(row['record_status'])+'` (accepted `'+str(row['accepted'])+'`)' for version, row in installations.items())+'. No live hardware access.', '',
             'F363, F364 and F364r2 are historical NO-GO images and cannot promote the selected baseline.', '',
             'Direct current-image traffic: `'+str(traffic_pass)+'`; direct current-image sensor reads: `'+str(sensor['direct_current_image_acceptance'])+'`. Historical proofs are retained with their tested firmware.', '',
             '| Function | Implementation | Acceptance | Remaining |', '|---|---|---|---|']
    for row in rows:
        lines.append('| '+' | '.join(row[k] for k in ('function','implementation','acceptance','remaining'))+' |')
    (out/'STATUS.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'result': str(out/'result.json'), 'status_document': str(out/'STATUS.md'), 'overall_status': report['overall_status'], 'hardware_access': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
