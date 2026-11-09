"""F367 install, one native acquisition and unconditional exact F365 return.

Default/import are file-only. The PowerShell owner supplies the fresh hardware
lease/nonce. Flash, Bootbase, scoped TFTP and serial recovery are unchanged F365
implementations. Diagnostic output is persisted before the watchdog reset.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
import queue
import re
import secrets
import subprocess
import threading
import time

import f365_install_executor as writer
import f365_install_contract as baseline
import f346_powershell as desktop_ps
from f365_failure_snapshot import save_failure_snapshot
from f366_dfs_campaign import strict_object
import f367_campaign as campaign_logic
import f367_aelita_dispatcher as clients
from f366r3_reset_observation import Uart
import f366_evidence_r2 as evidence_redactor

Failure, require = writer.Failure, writer.require
ROOT = baseline.ROOT
EVIDENCE_ROOT = Path('/workspace/OpenMitraStar/f367-campaign')
SUPERVISOR_SHA = '015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904'


def pending_command():
    return r'''set -eu
printf 'boot='; cat /run/openmitrastar/boot-state
printf 'radio2='; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'
for pair in 'bridge2:/sys/class/net/br0/brif/wlan0' 'qdrv:/sys/module/qdrv' 'provider:/sys/module/qtn_radar_f367' 'wifi0:/sys/class/net/wifi0' 'owner:/run/openmitrastar/watchdog/owner.lock' 'socket:/run/openmitrastar/watchdog/supervisor.sock'; do
 key=${pair%%:*}; path=${pair#*:}; if [ -e "$path" ]; then printf '%s=1\n' "$key"; else printf '%s=0\n' "$key"; fi
done
printf 'fatal='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|VFS: Unable to mount root' || true
'''


def pending_response(raw):
    pairs = [line.split('=', 1) for line in raw.decode('ascii').splitlines()]
    require(all(len(pair) == 2 for pair in pairs), 'pending_response')
    rows = strict_object(pairs)
    require(rows == dict(boot='ready', radio2='ENABLED', bridge2='1', qdrv='0', provider='0', wifi0='0', owner='0', socket='0', fatal='0'), 'native_boot_not_pending_or_management_unhealthy')
    return dict(status='PASS_F367_PENDING_MANAGEMENT', checks=9, acquisition_started=False, radio2_enabled=True, wifi0_created=False)


class Host(writer.Host):
    def __init__(self,plan,out):
        super().__init__(plan,out);self.operation_started=time.monotonic()
    def _guard(self, network):
        for path, digest in self.plan['sources'].items():
            require(baseline.sha(path) == digest, 'source_drift')
        args = [desktop_ps.executable(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'tools/assert_f367_context.ps1')]
        if network:
            args.append('-CheckNetwork')
        result = subprocess.run(args, env=desktop_ps.environment(), capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0 and result.stdout.strip() == b'PASS_F367_CAMPAIGN_CONTEXT' and not result.stderr

    def initial_binding(self, identity):
        return json.loads(os.environ.get('OM_F367_CONTEXT', '{}')).get('initial_boot_id') == identity['boot_id']

    def backup_reference(self):
        image = self.plan['images']['f365']
        require(baseline.sha(image['path']) == image['sha256'], 'fallback_reference_changed')
        # The immutable private full image plus fresh pre-write physical CRC
        # below form the rollback binding; do not call this a fresh raw dump.
        return dict(path=image['path'], sha256=image['sha256'], fresh_physical_dump=False)

    def pending(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                return pending_response(self.ssh(pending_command()))
            except (Failure, ValueError):
                time.sleep(2)
        raise Failure('f367_pending_management_timeout')

    def components(self):
        bindings = self.plan['runtime_bindings']
        paths = list(bindings)
        require(all(re.fullmatch(r'/[A-Za-z0-9_./-]+', p) and '..' not in p.split('/') for p in paths), 'runtime_binding_path')
        lines = self.ssh('sha256sum ' + ' '.join(paths), timeout=30).decode('ascii').splitlines()
        require(len(lines) == len(paths) and all(line.split() == [bindings[path], path] for line, path in zip(lines, paths)), 'installed_f367_runtime_hash')
        return dict(status='PASS', count=len(paths))

    def raw_control(self, action, token=None, expected_rejection=None):
        require(action in ('activate', 'enter-dfs', 'software-radar', 'stop'), 'control_action')
        if action == 'activate': require(token and re.fullmatch('[0-9a-f]{32}', token), 'activation_token')
        else: require(token is None, 'unexpected_control_token')
        require(self.network_guard(), 'control_network_guard')
        command='/usr/sbin/om-f367-control '+action+(' '+token if token else '')
        started=time.monotonic();started_utc=datetime.now(timezone.utc).isoformat()
        process=subprocess.Popen(self.ssh_argv(command),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(process)
        timed_out=False;kill_error=None;timeout=210 if action=='activate' else 30
        try:out,err=process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            try:process.kill()
            except OSError as error:kill_error=type(error).__name__
            try:out,err=process.communicate(timeout=3)
            except subprocess.TimeoutExpired as error:
                out=error.output or b'';err=error.stderr or b''
        receipt=dict(schema='openmitrastar.f367-control-receipt/v1',action=action,started_at_utc=started_utc,
                     ended_at_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-started,3),
                     exit_code=process.returncode,timed_out=timed_out,timeout_seconds=timeout,kill_error=kill_error,
                     local_transport_contained=process.poll() is not None,streams={})
        for source,data in (('stdout',out),('stderr',err)):
            lines=[]
            for raw in data.splitlines(keepends=True):
                original_bytes=len(raw)
                if token:raw=raw.replace(token.encode(),b'[token-redacted]')
                raw=re.sub(rb'(?i)("?(?:token|nonce|secret)"?\s*[:=]\s*)("[^"]*"|[^\s,}]+)',rb'\1"[token-redacted]"',raw)
                item=evidence_redactor.redacted_event(raw)
                item['bytes']=original_bytes
                if item['kind'] in ('diagnostic','sensitive'):lines.append(item)
                if len(lines)>=512:break
            receipt['streams'][source]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),lines=lines,raw_saved=False)
        directory=self.out/'control';directory.mkdir(parents=True,exist_ok=True)
        path=directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+action+'.json')
        with path.open('x',encoding='ascii') as stream:
            stream.write(json.dumps(receipt,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
        receipt_ref=dict(receipt_path=str(path),receipt_sha256=baseline.sha(path))
        require(receipt['local_transport_contained'],'control_transport_containment')
        require(not timed_out,'control_timeout_'+action)
        require(len(out)<=262144 and len(err)<=65536,'control_output_limit')
        text=out.decode('ascii',errors='replace')
        if expected_rejection:
            require(process.returncode!=0 and 'OMF367_REJECT reason='+expected_rejection in text,'expected_rejection_missing')
            return dict(action=action,rejected=True,reason=expected_rejection,**receipt_ref)
        require(process.returncode==0,'control_failed_'+action)
        return dict(action=action,exit_code=0,stdout_bytes=len(out),stderr_bytes=len(err),**receipt_ref)

    def activate(self, token):
        self.diagnostic_started=time.monotonic();self.owner_token=token
        result=self.raw_control('activate',token)
        result['owner']=self.owner_status(initial=True)
        return result
    def owner_status(self, initial=False):
        raw=self.ssh('/usr/sbin/om-watchdog-supervisor-f367 --status '+self.owner_token,timeout=12)
        row=json.loads(raw.decode('ascii'),object_pairs_hook=strict_object)
        require(row.get('schema')=='openmitrastar.f367-supervisor-state/v1' and row.get('nonce')==self.owner_token and row.get('boot_id')==self.installed_receipt['boot_id'],'owner_epoch')
        require(row.get('peer_verified') is True and row.get('fd_held') is True and row.get('hardware_arm_confirmed') is True and row.get('first_pet_confirmed') is True and row.get('error') is False,'owner_not_verified_armed')
        require(row.get('state') in ('phase-active','waiting-phase') and 0<row['phase_sequence']<=128,'owner_inactive')
        if initial:self.owner_total_deadline=row['session_deadline_monotonic_ms']
        else:require(row['session_deadline_monotonic_ms']==self.owner_total_deadline,'owner_total_deadline_changed')
        public={key:value for key,value in row.items() if key!='nonce'}
        with (self.out/'owner-observations.jsonl').open('a',encoding='ascii') as stream:
            stream.write(json.dumps(public)+'\n');stream.flush()
        return public
    def control(self, action, expected_rejection=None):
        return self.raw_control(action,expected_rejection=expected_rejection)
    def snapshot(self):
        raw=self.ssh('/usr/sbin/om-f367-control status',timeout=15)
        row=campaign_logic.normalize_snapshot(json.loads(raw.decode('ascii'),object_pairs_hook=strict_object))
        self.owner_status()
        return row
    def record(self, label, row):
        allowed=set(campaign_logic.COMMON)|set(campaign_logic.PROVIDER_FIELDS)|{'schema','cac_started_ms','cac_deadline_ms','cac_min_ms','nop_started_ms','nop_deadline_ms','action','rejected','reason'}
        safe={key:value for key,value in row.items() if key in allowed and (type(value) in (int,bool) or key in ('schema','action','reason'))}
        with (self.out/'campaign-snapshots.jsonl').open('a',encoding='ascii') as stream:
            stream.write(json.dumps(dict(stage=label,host_monotonic_ms=round(time.monotonic()*1000),snapshot=safe))+'\n');stream.flush();os.fsync(stream.fileno())
        save(self.out/'campaign-progress.json',dict(stage=label,host_monotonic_ms=round(time.monotonic()*1000),snapshot=safe))
    def campaign(self, token, uart, output):
        result={};self.stop_attempted=False
        def client(label, ready):
            return clients.run(self,self.plan,self.out/('client-'+label),ready)
        machine=campaign_logic.Campaign(self,self.record,client)
        uart.invalidate_prompt();uart.stop_autoboot(120)
        intercept_stop=threading.Event()
        def retain_interceptor():
            while not intercept_stop.wait(30):
                # Extend observation admission only, never any kernel/WDT timer.
                # Keep the original byte floor and duplicate suppression intact.
                uart.auto_until=time.monotonic()+120
                uart.autoboot=True
        interceptor=threading.Thread(target=retain_interceptor,name='F367-UART-admission',daemon=True)
        self.threads.append(interceptor);interceptor.start()
        self.campaign_partial=machine.result
        try:
            result=machine.run(token)
            return result
        finally:
            # Save partial state before requesting any stop/reset.
            save(self.out/'campaign-before-stop.json',machine.result)
            intercept_stop.set();interceptor.join(timeout=2)
            require(not interceptor.is_alive(),'interceptor_not_contained')
            self.stop_attempted=True
            try:
                uart.stop_autoboot(120)
                self.stop_result=self.control('stop')
                save(self.out/'stop.json',self.stop_result)
            except Exception as error:
                self.stop_result=dict(confirmed=False,error=type(error).__name__)
                save(self.out/'stop.json',self.stop_result)


def save(path, result):
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')


def run(plan, out, host_factory=Host, uart_factory=Uart, server_factory=writer.ScopedTftpProcess):
    host = host_factory(plan, out)
    uart = uart_factory(plan, host.guard, out)
    result = dict(schema='openmitrastar.f367-campaign-result/v1', status='FAILED', stage='baseline', target='mtd4/linux_live', erase_bytes=baseline.PREFIX,
                  activation_attempts=0, callback_authority=1, dfs_transmission_allowed=True, radar_rf_acceptance=False,
                  wifi_client_tests=False, provider_unload_attempted=False, watchdog_may_remain_armed=False,
                  rollback_attempted=False, flash_command_in_flight=False)
    original = None
    store_crc = None
    reboot_started = False
    diagnostic_pass = False
    restore_started = False
    reset_before = 0

    def event(stage):
        result['stage'] = stage
        save(out/'progress.json', dict(stage=stage, monotonic_ms=round(time.monotonic()*1000)))

    def restore():
        nonlocal restore_started
        require(not uart.write_in_flight, 'ambiguous_flash_no_recovery')
        require(not restore_started, 'no_second_restore_attempt')
        restore_started = True
        require(host.contain(), 'prior_helpers_not_contained')
        if not uart.has_prompt():
            if result['activation_attempts']:
                # STOP has requested ABORT/CEASE. Give the owned watchdog a
                # bounded reset opportunity, then use one serial recovery.
                deadline = time.monotonic()+120
                while time.monotonic() < deadline and not uart.has_prompt():
                    uart.stop_autoboot(120)
                    try:
                        uart.wait_prompt(min(45, max(1, deadline-time.monotonic())))
                    except Failure as error:
                        if str(error) != 'topaz_prompt_timeout':
                            raise
                if not uart.has_prompt():
                    result['software_recovery'] = True
                    host.reboot_to_prompt(uart, software_recovery=True)
            else:
                host.reboot_to_prompt(uart, software_recovery=True)
        require(uart.has_prompt(), 'fresh_bootbase_missing')
        result['post_reset_watchdog'] = writer.base.inactive_hardware(uart)
        result['watchdog_may_remain_armed'] = False
        if result['activation_attempts']:
            result['watchdog_reset_observed'] = len(uart.reset_times) > reset_before and not result.get('software_recovery', False)
        require(store_crc is not None, 'original_store_unknown')
        writer.domain(uart, plan, store_crc)
        mutated = uart.erase_requested or uart.write_requested
        if mutated:
            result['rollback_attempted'] = True
            event('restore-f365')
            result['restore_writer'] = writer.write_image(uart, host, plan, plan['images']['f365'], out/'restore', store_crc, server_factory)
        event('boot-f365-return')
        result['returned_identity'] = writer.boot_written(uart, host, plan, 'f365', original['boot_id'], prefix_only=not mutated)
        result['return_platform'] = host.platform('f365', out/'platform-f365-return')
        result['returned_watchdog'] = host.watchdog_inactive()
        result['returned_store'] = host.verify_store()
        result['returned_configuration'] = host.verify_configuration()
        result['returned_ethernet'] = host.verify_ethernet()
        result['returned_thermal'] = host.verify_thermal_disabled()
        result['baseline_returned'] = True

    try:
        require(host.guard(), 'lease')
        original = host.identity('f365')
        require(host.initial_binding(original), 'initial_nonce_boot_mismatch')
        result['baseline'] = original
        result['baseline_watchdog'] = host.watchdog_inactive()
        result['store_before'] = host.verify_store()
        result['configuration_before'] = host.verify_configuration()
        result['rollback_reference'] = host.backup_reference()
        result['client_readonly_preflight'] = clients.preflight(host,plan)
        uart.open()
        reboot_started = True
        event('bootbase-preflight')
        host.reboot_to_prompt(uart)
        writer.base.inactive_hardware(uart)
        writer.selector(uart)
        result['protected_before'] = writer.protected(uart, plan)
        store_crc = writer.flash_crc(uart, baseline.STORE, baseline.STORE_BYTES, plan['store']['crc32'])
        result['store_crc32'] = store_crc
        result['current_f365_crc32'] = writer.flash_crc(uart, baseline.LIVE, baseline.SLOT, plan['images']['f365']['full_slot_crc32'])
        event('install-f367')
        result['writer'] = writer.write_image(uart, host, plan, plan['images']['f367'], out/'install', store_crc, server_factory)
        event('boot-f367')
        result['f367_identity'] = writer.boot_written(uart, host, plan, 'f367', original['boot_id'])
        event('f367-pending-preflight')
        result['pending_management'] = host.pending()
        result['runtime_hashes'] = host.components()
        result['configuration_boot'] = host.verify_configuration()
        result['ethernet'] = host.verify_ethernet()
        result['thermal_default'] = host.verify_thermal_disabled()
        result['store_pre_activation'] = host.verify_store()
        result['watchdog_pre_activation'] = host.watchdog_inactive()
        require(host.identity('f367')['boot_id'] == result['f367_identity']['boot_id'], 'boot_changed_before_activation')
        require(time.monotonic()-host.operation_started<=900,'installation_used_owner_return_reserve')
        reset_before = len(uart.reset_times)
        event('f367-dfs-campaign')
        result['activation_attempts'] = 1
        result['watchdog_may_remain_armed'] = True
        host.installed_receipt=dict(image_sha256=plan['images']['f367']['sha256'],version=plan['images']['f367']['version'],boot_id=result['f367_identity']['boot_id'],writer=result['writer'],same_hardware_lease=True)
        result['campaign'] = host.campaign(secrets.token_hex(16), uart, out/'campaign.log')
        save(out/'campaign-before-return.json', result['campaign'])
        require(result['campaign']['status'] == 'PASS_F367_DFS_SOFTWARE_CONTROL_AND_CLIENT_TRAFFIC', 'campaign_evidence_failed')
        require(not uart.fatal, 'fatal_during_native_acquisition')
        diagnostic_pass = True
    except Exception as error:
        result['error'] = str(error) if isinstance(error, (Failure,campaign_logic.CampaignError)) else type(error).__name__
    finally:
        if hasattr(host,'campaign_partial'):
            result['campaign_partial']=host.campaign_partial
            result['wifi_client_tests']=bool(host.campaign_partial.get('clients'))
        # This snapshot is local and best-effort before any return/reset action.
        result['failure_snapshot_written'] = save_failure_snapshot(out, result)
        if reboot_started and original is not None and not uart.write_in_flight:
            try:
                restore()
                result['diagnostic_reset_signatures'] = max(0, len(uart.reset_times)-reset_before) if result['activation_attempts'] else 0
                result['status'] = 'PASS_F367_DFS_SOFTWARE_CONTROL_WITH_F365_RETURN' if diagnostic_pass and result.get('watchdog_reset_observed') else 'FAIL_F367_WITH_F365_RETURN'
                event('complete-f365-returned')
            except Exception as error:
                result['recovery_error'] = str(error) if isinstance(error, (Failure,campaign_logic.CampaignError)) else type(error).__name__
                result['status'] = 'FAILED_RECOVERY_UNPROVEN_NO_RETRY'
        elif reboot_started:
            result['status'] = 'STOP_UNCERTAIN_NO_AUTOMATIC_WRITE'
        try:
            result['children_contained'] = host.contain()
        except Exception:
            result['children_contained'] = False
        result['break_cleanup_verified'] = writer.clear_pending_break(uart)
        try:
            result['uart'] = uart.close()
        except Exception:
            result['uart'] = {}
        result['containment_confirmed'] = result['children_contained'] and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
        try:
            result['final_domain_guard'] = host.guard() is True
        except Exception:
            result['final_domain_guard'] = False
        result['flash_command_in_flight'] = uart.write_in_flight
        result['serial_recovery'] = getattr(uart, 'serial_recovery_record', {})
        result['retain_lease_required'] = not result['containment_confirmed'] or uart.write_in_flight or not result['final_domain_guard'] or result['watchdog_may_remain_armed'] or bool(result['serial_recovery'].get('break_attempted') and not result['serial_recovery'].get('break_cleared'))
        if result['uart'].get('reader_error') or not result['containment_confirmed'] or not result['final_domain_guard']:
            result['status'] = 'FAILED_CONTAINMENT_OR_UART'
        save(out/'result.json', result)
    print(json.dumps(dict(status=result['status'], result=str(out/'result.json'))), flush=True)
    return int(result['status'] != 'PASS_F367_DFS_SOFTWARE_CONTROL_WITH_F365_RETURN')


def load_plan(path, digest):
    require(baseline.sha(path)==digest,'plan_hash');plan=json.loads(Path(path).read_text(encoding='ascii'),object_pairs_hook=strict_object)
    require(plan['schema']=='openmitrastar.f367-campaign-plan/v1' and plan['status']=='PASS_OFFLINE_REVIEWED_EXECUTOR','plan_scope')
    require(plan['images']['f365']==baseline.images()['f365'] and set(plan['images'])=={'f365','f367'},'fallback_scope')
    require(plan['store']==baseline.store_binding() and plan['protected']==baseline.protected_backups() and plan['bootargs']==baseline.BOOTARGS,'storage_contract')
    require(plan['known_hosts']==plan['images']['f365']['known_hosts_path'] and Path(plan['evidence_root']).resolve()==EVIDENCE_ROOT.resolve(),'execution_scope')
    require(plan['watchdog_session_ms']==5400000 and plan['outer_timeout_seconds']==7500 and plan['context_ttl_seconds']==7800 and plan['always_restore_f365'] is True,'horizon_scope')
    require(plan['runtime_bindings']['/usr/sbin/om-watchdog-supervisor-f367']==plan['supervisor']['sha256'],'supervisor_binding')
    require(plan['supervisor']['sha256']=='ecd861a42812a8516f81e38fdad081089639f77a61c56335bf6c1110a926a477','qualified_supervisor')
    for file,expected in plan['sources'].items():require(baseline.sha(file)==expected,'source_drift')
    image=plan['images']['f367'];require(baseline.sha(image['path'])==image['sha256'] and Path(image['path']).stat().st_size==image['bytes'],'candidate_hash')
    return plan


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.plan, args.plan_sha256)
    if not args.execute:
        print('{"status":"OFFLINE_VALID","hardware_actions":false}')
        return 0
    require(os.environ.get('OM_F367_CONTEXT') and args.output_dir and args.output_dir.is_dir() and args.output_dir.resolve().parent == EVIDENCE_ROOT.resolve(), 'owning_launcher_required')
    return run(plan, args.output_dir)


if __name__ == '__main__':
    raise SystemExit(main())
