"""Derive the live F358-only profile from the validated F356 lifecycle."""
from pathlib import Path
import ast,os
ROOT=Path(__file__).resolve().parents[1]
def main():
 source=(ROOT/'tools/f356_observe_executor.py').read_text(encoding='utf-8')
 run=source[source.index('def run('):source.index('\ndef load_plan(')]
 run=run.replace(',ram_boot=boot_ram','').replace('ram_identity','active_identity').replace('openmitrastar.f356-observe-result','openmitrastar.f359-observe-result')
 start=run.index("        event('baseline');");end=run.index('        before_reset=len(uart.reset_times);uart.invalidate_prompt()',start)
 run=run[:start]+'''        event('baseline');require(host.guard(),'lease');baseline=host.identity('f358');require(host.initial_binding(baseline),'initial_nonce_boot_mismatch');result['baseline']=baseline;result['initial_watchdog']=host.preflight()
        result['platform_before']=host.platform('f358',out/'platform-before');current=host.identity('f358');require(current['boot_id']==baseline['boot_id'],'boot_changed_before_observe');active_identity=baseline
        result['storage']=host.storage_gate();result['devtmpfs']=host.devtmpfs_ready();uart.open();before_reset=len(uart.reset_times);disk_floor();host.stage(run_id);result['watchdog_profile']=host.inspect_current()
        event('owner-start');disk_floor();owner_launch_attempted=True;reboot_started=True;release_verified=False;pid=host.launch_owner(token);owner=wait_owner(host,token,baseline['boot_id'],pid);result['owner_idle']=owner
'''+run[end:]
 run=run.replace('previous.wait_reset(','wait_reset(').replace('previous.return_f340(','return_f358(').replace('readonly-f340-return','readonly-f358-return').replace('PASS_F356_READONLY_OBSERVE_AND_F340_RETURN','PASS_F359_READONLY_OBSERVE_AND_F358_RETURN').replace('FAIL_OBSERVE_WITH_F340_RETURN','FAIL_OBSERVE_WITH_F358_RETURN')
 header=(ROOT/'tools/f359_executor_header.inc').read_text(encoding='utf-8');footer=(ROOT/'tools/f359_executor_footer.inc').read_text(encoding='utf-8')
 text=header+'\n'+run+'\n'+footer;ast.parse(text);path=ROOT/'tools/f359_observe_executor.py';tmp=path.with_suffix('.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,path);print('F359_LIVE_PROFILE_READY_NO_RAMBOOT_NO_TFTP')
if __name__=='__main__':main()
