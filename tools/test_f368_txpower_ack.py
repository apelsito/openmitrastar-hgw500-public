"""Replay actual STORE38/channel17 producers and channel callback offline.

Uses the established CSA fixture. Mailbox, IRQ and time are controlled
substitutes; this is neither an ARC execution oracle nor physical timing.
"""
import argparse
import ast
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work/kernel-port/f368-txpower-ack/qdrv/qdrv'
BASE = ROOT / 'work/kernel-port/f367r9-transition-observation/qdrv/qdrv'

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def extract(text, name):
    match = re.search(r'\b' + name + r'\([^;{}()]*\)\s*\{', text)
    if not match:
        raise ValueError(name)
    start = text.rfind('\n', 0, match.start()) + 1
    depth = 0
    for i in range(text.index('{', match.start()), len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if depth == 0:
            return text[start:i+1] + '\n'
    raise ValueError('unterminated ' + name)

def fixture_literal(name):
    tree = ast.parse((ROOT/'tools/test_f367r8_csa_hostlink_wait.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(name)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    hostlink = (SOURCE/'qdrv_hostlink.c').read_text()
    wlan = (SOURCE/'qdrv_wlan.c').read_text()
    old_h = (BASE/'qdrv_hostlink.c').read_text()
    old_w = (BASE/'qdrv_wlan.c').read_text()
    # Exact source delta before executing the modified functions.
    old_producer = extract(old_h, 'qdrv_hostlink_store_txpow')
    new_producer = extract(hostlink, 'qdrv_hostlink_store_txpow')
    assert new_producer.replace('/* F368: command 38 must acknowledge before channel transition. */\n\treturn qdrv_send_ioctl_ack(qw, ioctl);', 'return qdrv_send_ioctl(qw, ioctl);') == old_producer
    assert wlan.replace('qdrv_f367r9_boundary("store38.after",observed_rc);\n\t if(observed_rc){qdrv_f367_channel_fault(observed_rc);return;}}', 'qdrv_f367r9_boundary("store38.after",observed_rc);}') == old_w
    assert hostlink.replace(new_producer, old_producer) == old_h

    glob = (ROOT/'work/sources/Quantenna-GPL/include/qtn/qtn_global.h').read_text()
    api = (ROOT/'work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h').read_text()
    constants = '#define HZ 100ul\n'
    for text, names in ((glob, ('QTN_CALSTATE_PROD','QTN_CALSTATE_DEFAULT')),
                        (api, ('QTN_HLINK_RC_DONE','QTN_HLINK_RC_ERR','QTN_HLINK_STATUS_AVAIL','IOCTL_DEV_STORE_TXPOW','IOCTL_DEV_CHANGE_CHANNEL','IOCTL_DEV_BEACON_START'))):
        for name in names:
            constants += re.search(r'^#define\s+' + name + r'\s+[^\n]+', text, re.M)[0] + '\n'
    pre = fixture_literal('PRE')
    pre += '\n#define F367R9_NO_RESULT 0\n#define qdrv_f367r9_hostlink_trace_arm(...) do{}while(0)\n#define qdrv_f367r9_boundary(...) do{}while(0)\n'
    pre = pre.replace('static unsigned commands[8]', 'static unsigned injected_raw=1; static bool alloc_failure;\nstatic unsigned commands[8]')
    pre = pre.replace('pending->ioctl_rc=QTN_HLINK_RC_DONE;', 'pending->ioctl_rc=injected_raw;')
    pre = pre.replace('pending->ioctl_rc=pending->ioctl_command==stalled_command?0:QTN_HLINK_RC_DONE;', 'pending->ioctl_rc=pending->ioctl_command==stalled_command?0:injected_raw;')
    macro = hostlink[hostlink.index('#define QDRV_IOCTL_EVNT_TIMEOUT'):hostlink.index('/* F367r4:')]
    # Diagnostic-only R9 calls are fixture no-ops; timeout and producer logic
    # remain the actual source. Save the stripped fixture for review.
    macro = '\n'.join(line for line in macro.splitlines() if 'OMF367R9_MACRO' not in line) + '\n'
    names = ('qdrv_alloc_ioctl','qdrv_free_ioctl','qdrv_completed_ack_result','qdrv_send_ioctl_owned','qdrv_send_ioctl','qdrv_send_ioctl_ack','qdrv_hostlink_store_txpow','qdrv_hostlink_setchan')
    bodies = '\n'.join(extract(hostlink,n) for n in names)
    bodies = bodies.replace('/* Search for an empty IOCTL */', 'if(alloc_failure){spin_unlock_irqrestore(&qw->tx_if.hl_flowlock, flags);return NULL;}\n\t/* Search for an empty IOCTL */')
    original_test = fixture_literal('TEST')
    reset = extract(original_test, 'reset').replace('static void reset(', 'static void setup(')
    reset = reset.replace('CHECK(', 'assert(')
    reset = reset.replace('live.ic.ic_timer_csa.function=ieee80211_finish_csa_timer;', 'live.ic.ic_timer_csa.function=NULL;')
    test = r'''
static void run_case(unsigned raw,unsigned stall,unsigned delay,unsigned cal,bool dead,bool fail){
 setup(cal,stall,delay,false,false);injected_raw=raw;alloc_failure=fail;mac.dead=dead;
 qdrv_set_channel(&live.ic);
}
int main(void){
 CHECK(QTN_CALSTATE_DEFAULT==3);
 run_case(1,0,0,3,false,false);CHECK(command_count==2&&commands[0]==38&&commands[1]==17);CHECK(!faults&&after_radar==1);
 run_case(3,0,0,3,false,false);CHECK(command_count==1&&commands[0]==38);CHECK(faults==1&&last_fault==-EIO&&!after_radar);
 run_case(2,0,0,3,false,false);CHECK(command_count==1);CHECK(faults==1&&last_fault==-EIO&&!after_radar);
 run_case(0,38,0,3,false,false);CHECK(jiffies-loop_start==51);CHECK(command_count==1&&faults==1&&last_fault==-1&&!after_radar);
 run_case(0,38,0,1,false,false);CHECK(jiffies-loop_start==5001);CHECK(command_count==1&&faults==1&&!after_radar);
 run_case(1,38,10,3,false,false);CHECK(jiffies-loop_start==10);CHECK(command_count==2&&!faults&&after_radar==1);
 run_case(3,38,10,3,false,false);CHECK(jiffies-loop_start==10);CHECK(command_count==1&&faults==1&&last_fault==-EIO&&!after_radar);
 run_case(1,0,0,3,true,false);CHECK(!command_count);CHECK(faults==1&&last_fault==-ENODEV&&!after_radar);
 run_case(1,0,0,3,false,true);CHECK(!command_count);CHECK(faults==1&&last_fault==-ENOMEM&&!after_radar);
 run_case(1,17,0,3,false,false);CHECK(command_count==2);CHECK(faults==1&&last_fault==-1&&!after_radar);
 setup(3,0,0,false,false);injected_raw=1;alloc_failure=false;CHECK(qdrv_hostlink_store_txpow(&live,21)==0);CHECK(ring[0].ioctl_arg1==4&&ring[0].ioctl_arg2==21);
 setup(3,0,0,false,false);injected_raw=1;CHECK(qdrv_hostlink_send_ioctl_args_FIXTURE==0);
 printf("F368_TXPOWER_ACK_PASS checks=%u hardware=0 reset_cause_proven=0\n",checks);return 0;
}
'''
    # The generic raw API remains raw DONE=1; verify its actual wrapper.
    generic = extract(hostlink,'qdrv_hostlink_send_ioctl_args')
    test = test.replace('qdrv_hostlink_send_ioctl_args_FIXTURE==0', 'qdrv_hostlink_send_ioctl_args(&live,6,0,0)==1')
    code = constants + pre + macro + bodies + generic + extract(wlan,'qdrv_set_channel') + reset + test
    (args.output/'test.c').write_text(code)
    compiler = '/usr/bin/gcc'
    compile_result = subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-but-set-variable','-Wno-pointer-to-int-cast','-Wno-int-to-pointer-cast',str(args.output/'test.c'),'-o',str(args.output/'test')],capture_output=True)
    (args.output/'compile.stderr').write_bytes(compile_result.stderr)
    if compile_result.returncode:
        print(compile_result.stderr.decode()[-5000:]);return 1
    run = subprocess.run([str(args.output/'test')],capture_output=True)
    (args.output/'stdout').write_bytes(run.stdout);(args.output/'stderr').write_bytes(run.stderr)
    result = {'schema':'openmitrastar.f368-txpower-ack-test/v1','status':'PASS' if run.returncode==0 else 'FAIL',
              'source_delta_verified':True,'stdout':run.stdout.decode(),'exit_code':run.returncode,
              'source_pins':{str(p):digest(p) for p in (Path(__file__),SOURCE/'qdrv_hostlink.c',SOURCE/'qdrv_wlan.c',BASE/'qdrv_hostlink.c',BASE/'qdrv_wlan.c',ROOT/'tools/test_f367r8_csa_hostlink_wait.py')},
              'hardware_accessed':False,'physical_reset_cause_proven':False,
              'fixture_boundaries':'mailbox, IRQ/time, allocator-failure injection, radar callbacks and R9 trace no-ops; actual producer/consumer function bodies'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return run.returncode

if __name__=='__main__':
    raise SystemExit(main())
