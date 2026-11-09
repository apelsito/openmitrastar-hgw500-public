"""Replay F368r2 STORE38 quarantine with independent physical ring slots.

Imports only the explicit fixture templates and extraction helper from the F368
test. The changed driver source and all failure-chain bodies are extracted from
the separately versioned F368r2 source. No hardware operation is performed.
"""
import argparse
from pathlib import Path
import hashlib
import json
import re
import subprocess

import test_f368_txoff_fault as prior

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/f368r2-txpower-quarantine/qdrv/qdrv"
BASE = ROOT / "work/kernel-port/f368-txpower-ack/qdrv/qdrv"

CASES = r'''
static unsigned cases;
static void setup(unsigned store_raw,unsigned store_delay,bool store_absent,
                  unsigned off_raw,unsigned off_delay,bool off_absent){
 memset(&live,0,sizeof(live));memset(&mac,0,sizeof(mac));memset(ring,0,sizeof(ring));
 memset(events,0,sizeof(events));memset(commands,0,sizeof(commands));
 memset(&qdrv_radar_cb,0,sizeof(qdrv_radar_cb));memset(&qdrv_f338_health,0,sizeof(qdrv_f338_health));
 for(unsigned i=0;i<4;i++)ring[i].ioctl_status=QTN_HLINK_STATUS_AVAIL;
 oldchan=(struct ieee80211_channel){.ic_ieee=36};newchan=(struct ieee80211_channel){.ic_ieee=52,.ic_maxpower_normal=21};
 live.mac=&mac;live.unit=0;live.rf_chipid=4;live.tx_if.hl_ring=ring;live.tx_if.hl_ring_dma=0x100000;
 live.ic.ic_curchan=&newchan;live.ic.ic_vaps.first=&vap;
 live.ic.ic_chan_compare_equality=equal;live.ic.ic_chan_switch_record=record;
 qdrv_radar_cb.ic=&live.ic;f367_control_fault=false;
 shared.calstate=QTN_CALSTATE_DEFAULT;jiffies=100;loop_start=jiffies;
 context=1;irq_enabled=true;locked=lock_max=wait_with_lock=wait_irq_disabled=0;
 polls=sleeps=delays=after_radar=command_count=event_count=0;
 stale_completions=off_acks_delivered=0;
 raw38=store_raw;delay38=store_delay;noack38=store_absent;
 raw26=off_raw;delay26=off_delay;noack26=off_absent;
}
static void report(const char *label){
 cases++;
 printf("CASE name=%s ticks=%u command_count=%u cmd0=%u cmd1=%u control_fault=%u tx_fault=%u xmit_stopped=%u off_ack_delivered=%u stale_completions=%u radar_after=%u store_slot=%u off_slot=%u store_quarantined=%u\n",
 label,jiffies-loop_start,command_count,commands[0],commands[1],f367_control_fault,
 qdrv_f338_health.tx_fault,qdrv_radar_cb.xmit_stopped,off_acks_delivered,stale_completions,after_radar,
 command_count?published_slots[0]:99,command_count>1?published_slots[1]:99,
 ring[0].ioctl_status!=QTN_HLINK_STATUS_AVAIL);
}
static void check_fault_chain(void){
 CHECK(command_count==2&&commands[0]==38&&commands[1]==26);
 CHECK(f367_control_fault&&!after_radar);
 CHECK(!wait_with_lock&&!wait_irq_disabled);
}
static void check_quarantine(void){
 CHECK(ring[0].ioctl_status!=QTN_HLINK_STATUS_AVAIL&&ring[0].ioctl_command==38);
 CHECK(ring[1].ioctl_command==26&&ring[1].ioctl_arg1==0);
 CHECK(published_slots[0]==0&&published_slots[1]==1);
 CHECK(!stale_completions);
}
int main(void){
 setup(1,0,false,1,0,false);qdrv_set_channel(&live.ic);
 CHECK(command_count==2&&commands[0]==38&&commands[1]==17);
 CHECK(!f367_control_fault&&!qdrv_f338_health.tx_fault&&after_radar==1);
 report("store_done_channel_changed");

 setup(3,0,false,1,0,false);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault&&off_acks_delivered==1);
 report("store_done_err_off_done");

 setup(2,0,false,2,0,false);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault&&off_acks_delivered==1);
 report("store_err_off_err");

 setup(2,0,false,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault&&jiffies-loop_start==51);
 report("store_err_off_timeout");

 setup(1,0,true,1,0,false);qdrv_set_channel(&live.ic);check_fault_chain();check_quarantine();
 CHECK(qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault&&jiffies-loop_start==51);
 report("store_timeout_distinct_off_done");

 setup(1,0,true,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();check_quarantine();
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault&&jiffies-loop_start==102);
 report("store_timeout_distinct_off_timeout");

 setup(1,55,false,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();check_quarantine();
 CHECK(events[0].delivered&&events[0].slot==&ring[0]&&off_acks_delivered==0);
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault&&jiffies-loop_start==102);
 report("late_store_done_cannot_confirm_off");

 setup(2,55,false,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();check_quarantine();
 CHECK(events[0].delivered&&off_acks_delivered==0);
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault&&jiffies-loop_start==102);
 report("late_store_err_cannot_complete_off");

 setup(1,55,false,1,10,false);qdrv_set_channel(&live.ic);check_fault_chain();check_quarantine();
 CHECK(event_count==2&&events[0].slot!=events[1].slot&&events[1].slot==&ring[1]);
 CHECK(events[0].delivered&&events[1].delivered&&off_acks_delivered==1);
 CHECK(qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault&&jiffies-loop_start==61);
 report("late_store_done_only_real_off_confirms");

 setup(2,55,false,1,10,false);qdrv_set_channel(&live.ic);check_fault_chain();check_quarantine();
 CHECK(events[0].delivered&&off_acks_delivered==1);
 CHECK(qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault&&jiffies-loop_start==61);
 report("late_store_err_cannot_reject_real_off");

 setup(1,10,false,1,0,true);qdrv_set_channel(&live.ic);
 CHECK(command_count==2&&commands[1]==17&&!stale_completions);
 CHECK(jiffies-loop_start==10&&!f367_control_fault&&after_radar==1);
 report("store_delayed_before_deadline_ok");

 setup(1,0,false,1,0,false);mac.dead=true;qdrv_set_channel(&live.ic);
 CHECK(!command_count&&f367_control_fault&&qdrv_f338_health.tx_fault&&!qdrv_radar_cb.xmit_stopped);
 CHECK(ring[0].ioctl_status==QTN_HLINK_STATUS_AVAIL);
 report("dead_mac_no_unpublished_quarantine");

 setup(1,0,false,1,0,false);for(unsigned i=0;i<4;i++)ring[i].ioctl_status=0;
 qdrv_set_channel(&live.ic);
 CHECK(!command_count&&f367_control_fault&&qdrv_f338_health.tx_fault&&!qdrv_radar_cb.xmit_stopped);
 report("full_ring_failclosed");

 setup(1,55,false,1,0,false);for(unsigned i=1;i<4;i++)ring[i].ioctl_status=0;
 qdrv_set_channel(&live.ic);
 CHECK(command_count==1&&commands[0]==38);
 CHECK(f367_control_fault&&qdrv_f338_health.tx_fault&&!qdrv_radar_cb.xmit_stopped);
 CHECK(ring[0].ioctl_status!=QTN_HLINK_STATUS_AVAIL&&jiffies-loop_start==51);
 while(jiffies<155)clock_step();
 CHECK(events[0].delivered&&ring[0].ioctl_status!=QTN_HLINK_STATUS_AVAIL&&!qdrv_radar_cb.xmit_stopped);
 report("quarantine_exhausts_ring_off_rejected");

 setup(1,0,false,1,0,false);live.tx_if.tx_mbox[0]=1;
 CHECK(qdrv_hostlink_store_txpow(&live,21)==-1);
 CHECK(!command_count&&ring[0].ioctl_status==QTN_HLINK_STATUS_AVAIL&&jiffies-loop_start==51);
 report("unpublished_timeout_released");

 setup(1,0,false,1,0,false);
 CHECK(qdrv_hostlink_send_ioctl_args(&live,6,0,0)==1);
 CHECK(ring[0].ioctl_status==QTN_HLINK_STATUS_AVAIL);
 report("legacy_raw_done_unchanged");

 printf("F368R2_TXOFF_FAULT_PASS cases=%u checks=%u stale_off_confirmation=0 hardware=0\n",cases,checks);
 return 0;
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    names = ("qdrv_hostlink.c", "qdrv_wlan.c", "qdrv_radar.c", "qdrv_f338_availability.inc", "qdrv_f367_control.inc")
    paths = [SOURCE / name for name in names]
    texts = {path.name: path.read_text() for path in paths}
    host = texts["qdrv_hostlink.c"]
    old = (BASE / "qdrv_hostlink.c").read_text()
    original = prior.extract(old, "qdrv_hostlink_store_txpow")
    candidate = prior.extract(host, "qdrv_hostlink_store_txpow")
    before = "/* F368: command 38 must acknowledge before channel transition. */\n\treturn qdrv_send_ioctl_ack(qw, ioctl);"
    after = "/* F368r2: keep a published timeout descriptor out of reuse.\n\t * Late STORE38 completion must not acknowledge a later TX-off. */\n\treturn qdrv_send_ioctl_owned(qw, ioctl, true, NULL, true);"
    assert candidate.replace(after, before) == original
    assert host.replace(candidate, original) == old
    for name in names[1:]:
        assert texts[name] == (BASE / name).read_text()
    pre = prior.fixture_literal("PRE")
    for name in ("clock_step", "qdrv_mac_interrupt_muc", "qdrv_f367_channel_fault"):
        body = prior.extract(pre, name).rstrip()
        assert pre.count(body) == 1
        pre = pre.replace(body, "")
    events = prior.EVENTS
    old_select = "for(unsigned i=0;i<4;i++)if(ring[i].ioctl_status!=QTN_HLINK_STATUS_AVAIL){slot=&ring[i];break;}"
    new_select = "unsigned wire=live.tx_if.tx_mbox[0];unsigned offset=wire-(unsigned)live.tx_if.hl_ring_dma;\n assert(offset%sizeof(struct host_ioctl)==0&&offset/sizeof(struct host_ioctl)<4);\n slot=&ring[offset/sizeof(struct host_ioctl)];assert(slot->ioctl_status!=QTN_HLINK_STATUS_AVAIL);"
    assert events.count(old_select) == 1
    events = events.replace(old_select, new_select)
    events = events.replace("static unsigned event_count, stale_completions, off_acks_delivered;", "static unsigned event_count, stale_completions, off_acks_delivered;\nstatic unsigned published_slots[8];")
    events = events.replace("commands[command_count++]=command;", "published_slots[command_count]=(unsigned)(slot-ring);commands[command_count++]=command;")
    position = pre.index("static bool in_irq(void)")
    pre = pre[:position] + events + pre[position:]
    pre += "\n#define F367R9_NO_RESULT 0\n#define qdrv_f367r9_hostlink_trace_arm(...) do{}while(0)\n#define qdrv_f367r9_boundary(...) do{}while(0)\n"
    constants = "#define HZ 100ul\n"
    api = ROOT / "work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h"
    glob = ROOT / "work/sources/Quantenna-GPL/include/qtn/qtn_global.h"
    for path, macros in ((api, ("QTN_HLINK_RC_DONE", "QTN_HLINK_RC_ERR", "QTN_HLINK_STATUS_AVAIL", "IOCTL_DEV_STORE_TXPOW", "IOCTL_DEV_CHANGE_CHANNEL", "IOCTL_DEV_BEACON_START", "IOCTL_DEV_XMITCTL")), (glob, ("QTN_CALSTATE_PROD", "QTN_CALSTATE_DEFAULT"))):
        text = path.read_text()
        for name in macros:
            constants += re.search(r"^#define\s+" + name + r"\s+[^\n]+", text, re.M)[0] + "\n"
    macro = host[host.index("#define QDRV_IOCTL_EVNT_TIMEOUT"):host.index("/* F367r4:")]
    macro = "\n".join(line for line in macro.splitlines() if "OMF367R9_MACRO" not in line) + "\n"
    functions = [("qdrv_hostlink.c", name) for name in ("qdrv_alloc_ioctl", "qdrv_free_ioctl", "qdrv_completed_ack_result", "qdrv_send_ioctl_owned", "qdrv_send_ioctl", "qdrv_send_ioctl_ack", "qdrv_hostlink_store_txpow", "qdrv_hostlink_setchan", "qdrv_hostlink_xmitctl", "qdrv_hostlink_send_ioctl_args")]
    functions += [("qdrv_radar.c", "sys_raw_disable_xmit"), ("qdrv_f338_availability.inc", "qdrv_f338_force_tx_off"), ("qdrv_f367_control.inc", "qdrv_f367_channel_fault"), ("qdrv_wlan.c", "qdrv_set_channel")]
    code = constants + pre + macro + "\n".join(prior.extract(texts[source], name) for source, name in functions) + CASES
    (args.output / "test.c").write_text(code)
    command = ["/usr/bin/gcc", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-unused-parameter", "-Wno-pointer-to-int-cast", "-Wno-int-to-pointer-cast", str(args.output / "test.c"), "-o", str(args.output / "test")]
    compiled = subprocess.run(command, capture_output=True)
    (args.output / "compile.stdout").write_bytes(compiled.stdout)
    (args.output / "compile.stderr").write_bytes(compiled.stderr)
    run = None if compiled.returncode else subprocess.run([str(args.output / "test")], capture_output=True)
    if run:
        (args.output / "stdout").write_bytes(run.stdout)
        (args.output / "stderr").write_bytes(run.stderr)
    result = {
        "schema": "openmitrastar.f368r2-txoff-fault-test/v1",
        "status": "PASS_OFFLINE_QUARANTINE" if run and run.returncode == 0 else "FAIL_TEST",
        "promotion": "NO_GO_PHYSICAL",
        "hardware_accessed": False,
        "source_delta_verified": True,
        "compile_exit_code": compiled.returncode,
        "run_exit_code": run.returncode if run else None,
        "stdout": run.stdout.decode() if run else None,
        "source_pins": {str(path): prior.sha(path) for path in (*paths, BASE / "qdrv_hostlink.c", api, glob, Path(__file__), ROOT / "tools/test_f368_txoff_fault.py", ROOT / "tools/test_f368_txpower_ack.py", ROOT / "tools/test_f367r8_csa_hostlink_wait.py")},
        "actual_extracted_functions": [name for _, name in functions],
        "finding": "Published STORE38 timeout retains its slot. Late DONE/ERR cannot complete or reject OFF on a distinct slot. Ring exhaustion rejects OFF and latches fault. Legacy raw DONE and unpublished timeout free behavior remain unchanged.",
        "limits": "Substitute four-slot wire ring, one thread, deterministic ticks, immediate mailbox dequeue; R9 diagnostics no-ops. Does not prove physical MuC timing, DMA coherency, ARC execution, RF silence or recovery. Retained descriptor is not reclaimed; supported lifetime is reboot-only. Other raw producers are unchanged and are not covered by this STORE38 correction.",
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "source_pins"}))
    if compiled.returncode:
        print(compiled.stderr.decode()[-5000:])
    elif run.returncode:
        print(run.stderr.decode()[-5000:])
    return 0 if result["status"] == "PASS_OFFLINE_QUARANTINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
