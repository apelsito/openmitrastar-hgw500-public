"""Adapt the established live lifecycle to one first SAVE and durable readback."""
from pathlib import Path
import ast,os
ROOT=Path(__file__).resolve().parents[1]
def main():
 src=(ROOT/'tools/f359_observe_executor.py').read_text(encoding='utf-8');run=src[src.index('def run('):src.index('\ndef load_plan(')]
 run=run.replace('openmitrastar.f359-observe-result','openmitrastar.f360-save-result').replace('flash_program_commands=False','flash_program_commands=True').replace('observe_attempted','save_attempted').replace('observe_pass','save_pass')
 run=run.replace("result['storage']=host.storage_gate();", "result['storage']=host.storage_gate();result['current_payload']=host.current_payload();result['store_before']=host.store_snapshot('before');require(result['store_before']['all_pair_ff'] and result['store_before']['store_sha256']==plan['expected']['original']['store_sha256'],'store_not_original_ff');")
 start=run.index("        event('load-readonly-provider');");end=run.index("        event('unload-after-clean-release');",start)
 run=run[:start]+'''        event('load-program-provider');disk_floor();result['provider_load_attempted']=True;result['provider']=protocol.loaded(host.load_provider(),active_identity['boot_id'])
        event('single-save');disk_floor();result['save_attempted']=True;result['save_response']=protocol.saved(host.save_config(),plan['payload'])
        require(len(uart.reset_times)==before_reset,'reset_during_save');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_during_save')
        event('load-readback');result['load_readback_attempted']=True;result['load_readback']=protocol.loaded_payload(host.load_config(),plan['payload']);result['save_pass']=True
        require(len(uart.reset_times)==before_reset,'reset_during_readback');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_during_readback')
'''+run[end:]
 # No OBSERVE ioctl is issued, so there is no OMF356-observe marker to wait for.
 a=run.index('        if observe_start is not None:');b=run.index('\n    try:\n',a)+1;run=run[:a]+run[b:]
 a=run.index('        if observe_start is not None:');b=run.index('        diagnostic()',a);run=run[:a]+run[b:]
 run=run.replace("return_f358(uart,host,plan,active_identity['boot_id'],out)","return_after_save(uart,host,plan,active_identity['boot_id'],out,expected_saved=True)")
 run=run.replace("return_f358(uart,host,plan,(active_identity or baseline)['boot_id'],out)","return_after_save(uart,host,plan,(active_identity or baseline)['boot_id'],out,expected_saved=False)")
 run=run.replace('PASS_F359_READONLY_OBSERVE_AND_F358_RETURN','PASS_F360_CONFIG_SAVED_AND_PERSISTED').replace('FAIL_OBSERVE_WITH_F358_RETURN','FAIL_SAVE_WITH_F358_RETURN_NO_REERASE')
 text=(ROOT/'tools/f360_executor_header.inc').read_text(encoding='utf-8')+'\n'+run+'\n'+(ROOT/'tools/f360_executor_footer.inc').read_text(encoding='utf-8');ast.parse(text)
 path=ROOT/'tools/f360_save_executor.py';tmp=path.with_suffix('.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,path);print('F360_ONE_SAVE_PROFILE_READY_NO_REERASE')
if __name__=='__main__':main()
