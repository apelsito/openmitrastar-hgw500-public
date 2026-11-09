"""One 1 MiB SSH stream per direction on installed F364; no remote files.

Default invocation is local-only. Root may execute after a completed accepted
F364 installation. This probes the existing management link, never the second
physical connector or simultaneous-port forwarding. No RF/config/UART actions.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import time

DEVICE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
KNOWN_HOSTS = Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f364r3-f363r2-lifetime-device-bound/known_hosts.f364')
VERSION = 'lyoko-foundation-6.9.12-f364r3-lifetime-device'
IMAGE_SHA = 'ee6b7d09fd9e2dc5e0009d6756910510409ae13fb17108089a4caf7043056a15'
LENGTH = 1024*1024
STREAM_DEADLINE = 60
COUNTERS = ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets',
            'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped')


class ProbeFailure(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise ProbeFailure(reason)


def snapshot_command():
    lines = [
        'set -e',
        "printf 'boot_id='; cat /proc/sys/kernel/random/boot_id",
        "printf 'kernel='; uname -r",
        "printf 'uts='; uname -v",
        "printf 'version='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release",
        "printf 'ready='; cat /run/openmitrastar/boot-state",
    ]
    for port in ('eth0', 'eth1'):
        lines += [
            f'test -r /sys/class/net/{port}/lyoko_emac_port_stats',
            f'test -e /sys/class/net/br0/brif/{port}',
            f"printf '{port}.carrier='; cat /sys/class/net/{port}/carrier",
        ]
        for counter in COUNTERS:
            lines.append(f"printf '{port}.{counter}='; cat /sys/class/net/{port}/statistics/{counter}")
    return '\n'.join(lines)


def parse_snapshot(content):
    require(len(content) < 8192, 'snapshot_size')
    try:
        pairs = [line.split('=', 1) for line in content.decode('ascii').splitlines()]
    except UnicodeError:
        raise ProbeFailure('snapshot_encoding') from None
    require(all(len(pair) == 2 for pair in pairs), 'snapshot_format')
    require(len({pair[0] for pair in pairs}) == len(pairs), 'snapshot_duplicate')
    rows = dict(pairs)
    expected = {'boot_id', 'kernel', 'uts', 'version', 'ready'}
    expected.update(port+'.'+name for port in ('eth0', 'eth1') for name in ('carrier', *COUNTERS))
    require(set(rows) == expected, 'snapshot_fields')
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', rows['boot_id']), 'boot_id')
    require(rows['kernel'] == '5.10.260-openmitrastar-radiohw' and rows['uts'] == '#358 @1790006400'
            and rows['version'] == VERSION and rows['ready'] == 'ready', 'f364_identity_or_readiness')
    ports = {}
    for port in ('eth0', 'eth1'):
        require(rows[port+'.carrier'] in ('0', '1'), 'carrier_format')
        ports[port] = {'carrier': int(rows[port+'.carrier']), 'driver_marker': 'F352', 'bridge': 'br0'}
        for name in COUNTERS:
            require(re.fullmatch(r'[0-9]{1,20}', rows[port+'.'+name]), 'counter_format')
            ports[port][name] = int(rows[port+'.'+name])
    return {**{name: rows[name] for name in ('boot_id', 'kernel', 'uts', 'version', 'ready')}, 'ports': ports}


class Transport:
    def __init__(self):
        self.children = []
        self.events = []

    def argv(self, command):
        return [str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),
                '-F', os.devnull, '-T', '-x', '-b', '192.168.1.49',
                '-i', str(Path.home()/'.ssh/id_ed25519'),
                '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                '-o', 'ConnectTimeout=8', '-o', 'ConnectionAttempts=1',
                '-o', 'Compression=no', '-o', 'ClearAllForwardings=yes',
                '-o', 'PermitLocalCommand=no', '-o', 'ProxyCommand=none',
                '-o', 'ProxyJump=none', '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                '-o', 'StrictHostKeyChecking=yes', '-o', 'GlobalKnownHostsFile='+os.devnull,
                '-o', 'UserKnownHostsFile='+str(KNOWN_HOSTS), '-o', 'LogLevel=ERROR',
                'root@192.168.1.90', command]

    @staticmethod
    def reap(process):
        if process.poll() is None:
            process.kill()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            return False
        return process.poll() is not None

    def contain(self):
        results = [self.reap(process) for process in self.children]
        return all(results)

    def ssh(self, label, command, data=b'', timeout=20):
        require(isinstance(data, bytes) and 0 < timeout <= STREAM_DEADLINE, 'transport_contract')
        require(all(process.poll() is not None for process in self.children), 'previous_ssh_active')
        start = time.monotonic()
        process = subprocess.Popen(self.argv(command), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.children.append(process)
        event = {'label': label, 'deadline_seconds': timeout, 'compression': False}
        self.events.append(event)
        try:
            output, errors = process.communicate(data, timeout=timeout)
            event.update(exit_code=process.returncode, elapsed_seconds=round(time.monotonic()-start, 6),
                         stdin_bytes=len(data), stdout_bytes=len(output), stderr_bytes=len(errors),
                         stderr_sha256=hashlib.sha256(errors).hexdigest())
            require(process.returncode == 0, label+'_ssh_failed')
            require(not errors, label+'_unexpected_stderr')
            return output, event['elapsed_seconds']
        except subprocess.TimeoutExpired:
            event.update(timed_out=True, elapsed_seconds=round(time.monotonic()-start, 6))
            raise ProbeFailure(label+'_deadline') from None
        finally:
            event['process_reaped'] = self.reap(process)
            require(event['process_reaped'], label+'_containment_failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--installation-result', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raw = args.installation_result.read_bytes()
    install = json.loads(raw)
    require(install.get('status') == 'PASS_F364_PRESERVED_JOURNAL'
            and install.get('schema') == 'openmitrastar.f364-install-result/v1', 'accepted_f364_installation_required')
    require(install.get('writer', {}).get('image') == IMAGE_SHA
            and install.get('writer', {}).get('byte_compare') is True, 'installed_image_binding')
    require(install.get('containment_confirmed') is True and install.get('retain_lease_required') is False
            and install.get('flash_command_in_flight') is False, 'installer_must_have_finished')
    installed_boot = install.get('f364_identity', {}).get('boot_id')
    require(isinstance(installed_boot, str) and KNOWN_HOSTS.is_file(), 'installation_identity_or_known_hosts')
    if not args.execute:
        print(json.dumps({'status': 'OFFLINE_READY', 'hardware_access': False,
                          'bytes_per_direction': LENGTH, 'stream_deadline_seconds': STREAM_DEADLINE,
                          'compression': False, 'second_connector_tested': False}))
        return 0
    require(os.name == 'nt' and args.output_dir is not None, 'windows_output_required')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    host = Transport()
    result = {'schema': 'openmitrastar.f364-management-stream/v1', 'status': 'FAILED',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'installation_result': str(args.installation_result.resolve()),
              'installation_result_sha256': hashlib.sha256(raw).hexdigest(),
              'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'known_hosts_sha256': hashlib.sha256(KNOWN_HOSTS.read_bytes()).hexdigest(),
              'scope': 'one existing Ethernet management path over SSH',
              'bytes_per_direction': LENGTH, 'stream_deadline_seconds': STREAM_DEADLINE,
              'compression': False, 'remote_files_created': False, 'radio_actions': False,
              'configuration_actions': False, 'uart_actions': False,
              'second_connector_tested': False, 'simultaneous_port_forwarding_tested': False,
              'raw_link_throughput_claimed': False}
    try:
        before_raw, _ = host.ssh('before', snapshot_command())
        before = parse_snapshot(before_raw)
        result['before'] = before
        require(before['boot_id'] == installed_boot, 'boot_changed_since_installation')
        payload = os.urandom(LENGTH)
        expected = hashlib.sha256(payload).hexdigest()
        uploaded, elapsed = host.ssh('pc_to_hgw', 'exec sha256sum', payload, STREAM_DEADLINE)
        require(re.fullmatch(rb'[0-9a-f]{64}  -\n', uploaded), 'upload_digest_format')
        observed = uploaded[:64].decode('ascii')
        result['pc_to_hgw'] = {'bytes': LENGTH, 'payload': 'host_random_in_memory',
                              'local_sha256': expected, 'remote_sha256': observed,
                              'sha256_match': observed == expected, 'elapsed_seconds': elapsed}
        require(observed == expected, 'upload_hash_mismatch')
        downloaded, elapsed = host.ssh('hgw_to_pc', 'exec dd if=/dev/zero bs=4096 count=256 2>/dev/null',
                                      timeout=STREAM_DEADLINE)
        observed = hashlib.sha256(downloaded).hexdigest()
        expected = hashlib.sha256(b'\0'*LENGTH).hexdigest()
        result['hgw_to_pc'] = {'bytes': len(downloaded), 'payload': 'dev_zero_stream',
                              'expected_sha256': expected, 'local_sha256': observed,
                              'sha256_match': observed == expected, 'elapsed_seconds': elapsed}
        require(len(downloaded) == LENGTH and observed == expected, 'download_size_or_hash_mismatch')
        after_raw, _ = host.ssh('after', snapshot_command())
        after = parse_snapshot(after_raw)
        result['after'] = after
        require(after['boot_id'] == before['boot_id'], 'boot_changed_during_streams')
        delta = {port: {name: after['ports'][port][name]-before['ports'][port][name]
                        for name in COUNTERS} for port in ('eth0', 'eth1')}
        result['counter_delta'] = delta
        require(all(value >= 0 for counters in delta.values() for value in counters.values()), 'counter_reset')
        active = [port for port in ('eth0', 'eth1')
                  if before['ports'][port]['carrier'] == after['ports'][port]['carrier'] == 1
                  and delta[port]['rx_bytes'] >= LENGTH and delta[port]['tx_bytes'] >= LENGTH]
        result['management_port_with_bidirectional_byte_evidence'] = active
        require(len(active) == 1, 'single_management_port_not_established')
        require(delta[active[0]]['rx_errors'] == delta[active[0]]['tx_errors'] == 0, 'new_management_link_errors')
        result['status'] = 'PASS_F364_EXISTING_MANAGEMENT_LINK_1MIB_EACH_DIRECTION'
    except Exception as error:
        result['error'] = str(error) if isinstance(error, ProbeFailure) else type(error).__name__
    finally:
        # A failed stream is never retried. If its SSH process is reaped, make
        # one bounded observation so failure evidence can still show boot/link state.
        if 'before' in result and 'after' not in result and host.contain():
            try:
                after_raw, _ = host.ssh('after_failure', snapshot_command())
                result['after'] = parse_snapshot(after_raw)
                result['boot_unchanged_after_failure'] = result['after']['boot_id'] == result['before']['boot_id']
            except Exception as error:
                result['after_failure_error'] = str(error) if isinstance(error, ProbeFailure) else type(error).__name__
        result['containment_confirmed'] = host.contain()
        result['transport'] = host.events
        result['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
        if not result['containment_confirmed']:
            result['status'] = 'FAIL_SSH_CONTAINMENT'
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')
    print(json.dumps({'status': result['status'], 'result': str(out/'result.json'),
                      'second_connector_tested': False, 'containment_confirmed': result['containment_confirmed']}))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
