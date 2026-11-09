"""Offline replay of F368 STORE38 failure and the actual TX-off fault chain.

The real producer, consumer, fault and TX-off function bodies are extracted.
Mailbox delivery, descriptor completion and IRQ/time are controlled substitutes.
A late completion writes the descriptor captured at publication, independently
of its subsequent reuse. This exposes an ownership hazard under the stated
injection, not evidence that physical MuC exhibits that completion schedule.
"""
import argparse
from pathlib import Path
import hashlib
import json
import re
import subprocess

from test_f368_txpower_ack import extract, fixture_literal

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/f368-txpower-ack/qdrv/qdrv"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


EVENTS = r'''
struct completion_event {
 struct host_ioctl *slot;
 unsigned command, due, raw;
 bool delivered;
};
static struct completion_event events[8];
static unsigned event_count, stale_completions, off_acks_delivered;
static unsigned raw38, raw26, delay38, delay26;
static bool noack38, noack26;
static bool f367_control_fault;
static struct {bool tx_fault;} qdrv_f338_health;
static struct {struct ieee80211com *ic;bool xmit_stopped;} qdrv_radar_cb;
void qdrv_f367_channel_fault(int error);

static void deliver(struct completion_event *e){
 if(e->delivered)return;
 if(e->slot->ioctl_command!=e->command)stale_completions++;
 e->slot->ioctl_rc=e->raw;
 e->delivered=true;
 if(e->command==26)off_acks_delivered++;
}
static void clock_step(void){
 polls++;
 if(locked)wait_with_lock++;
 if(!irq_enabled)wait_irq_disabled++;
 if(context==1)softirq_seen++;
 jiffies++;
 for(unsigned i=0;i<event_count;i++)
  if(!events[i].delivered&&jiffies>=events[i].due)deliver(&events[i]);
}
static void qdrv_mac_interrupt_muc(struct qdrv_mac *m){
 assert(m==&mac);assert(!irq_enabled&&locked==1);
 struct host_ioctl *slot=NULL;
 for(unsigned i=0;i<4;i++)if(ring[i].ioctl_status!=QTN_HLINK_STATUS_AVAIL){slot=&ring[i];break;}
 assert(slot);assert(command_count<8);
 unsigned command=slot->ioctl_command;
 commands[command_count++]=command;live.tx_if.tx_mbox[0]=0;
 bool absent=command==38?noack38:command==26?noack26:false;
 unsigned delay=command==38?delay38:command==26?delay26:0;
 unsigned raw=command==38?raw38:command==26?raw26:QTN_HLINK_RC_DONE;
 if(!absent){
  assert(event_count<8);
  struct completion_event *e=&events[event_count++];
  *e=(struct completion_event){.slot=slot,.command=command,.due=jiffies+delay,.raw=raw};
  if(!delay)deliver(e);
 }
}
'''

CASES = r'''
static unsigned cases;
static void setup(unsigned store_raw,unsigned store_delay,bool store_absent,
                  unsigned off_raw,unsigned off_delay,bool off_absent){
 memset(&live,0,sizeof(live));memset(&mac,0,sizeof(mac));memset(ring,0,sizeof(ring));
 memset(events,0,sizeof(events));memset(commands,0,sizeof(commands));
 memset(&qdrv_radar_cb,0,sizeof(qdrv_radar_cb));memset(&qdrv_f338_health,0,sizeof(qdrv_f338_health));
 for(unsigned i=0;i<4;i++)ring[i].ioctl_status=QTN_HLINK_STATUS_AVAIL;
 oldchan=(struct ieee80211_channel){.ic_ieee=36};
 newchan=(struct ieee80211_channel){.ic_ieee=52,.ic_maxpower_normal=21};
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
 printf("CASE name=%s ticks=%u command_count=%u cmd0=%u cmd1=%u control_fault=%u tx_fault=%u xmit_stopped=%u off_ack_delivered=%u stale_completions=%u radar_after=%u\n",
 label,jiffies-loop_start,command_count,commands[0],commands[1],f367_control_fault,
 qdrv_f338_health.tx_fault,qdrv_radar_cb.xmit_stopped,off_acks_delivered,stale_completions,after_radar);
}
static void check_fault_chain(void){
 CHECK(command_count==2&&commands[0]==38&&commands[1]==26);
 CHECK(f367_control_fault&&!after_radar);
 CHECK(!wait_with_lock&&!wait_irq_disabled);
 CHECK(ring[0].ioctl_arg1==0);
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

 setup(1,0,true,1,0,false);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault&&jiffies-loop_start==51);
 report("store_timeout_off_done");

 setup(1,0,true,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault&&jiffies-loop_start==102);
 report("store_timeout_off_timeout");

 setup(1,55,false,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(stale_completions==1&&off_acks_delivered==0&&jiffies-loop_start==55);
 CHECK(qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault);
 report("late_store_done_falsely_confirms_off");

 setup(2,55,false,1,0,true);qdrv_set_channel(&live.ic);check_fault_chain();
 CHECK(stale_completions==1&&off_acks_delivered==0&&jiffies-loop_start==55);
 CHECK(!qdrv_radar_cb.xmit_stopped&&qdrv_f338_health.tx_fault);
 report("late_store_err_rejects_off");

 setup(1,10,false,1,0,true);qdrv_set_channel(&live.ic);
 CHECK(command_count==2&&commands[1]==17&&!stale_completions);
 CHECK(jiffies-loop_start==10&&!f367_control_fault&&after_radar==1);
 report("store_delayed_before_deadline_ok");

 setup(1,0,false,1,0,false);mac.dead=true;qdrv_set_channel(&live.ic);
 CHECK(!command_count&&f367_control_fault&&qdrv_f338_health.tx_fault&&!qdrv_radar_cb.xmit_stopped);
 report("dead_mac_store_and_off_rejected");

 setup(1,0,false,1,0,false);
 for(unsigned i=0;i<4;i++)ring[i].ioctl_status=0;
 qdrv_set_channel(&live.ic);
 CHECK(!command_count&&f367_control_fault&&qdrv_f338_health.tx_fault&&!qdrv_radar_cb.xmit_stopped);
 report("no_descriptor_store_and_off_rejected");

 printf("F368_TXOFF_FAULT_PASS cases=%u checks=%u stale_hazard_reproduced=1 hardware=0\n",cases,checks);
 return 0;
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = {name: SOURCE / name for name in (
        "qdrv_hostlink.c", "qdrv_wlan.c", "qdrv_radar.c",
        "qdrv_f338_availability.inc", "qdrv_f367_control.inc")}
    texts = {name: path.read_text() for name, path in paths.items()}
    host = texts["qdrv_hostlink.c"]
    pre = fixture_literal("PRE")
    for name in ("clock_step", "qdrv_mac_interrupt_muc", "qdrv_f367_channel_fault"):
        original = extract(pre, name).rstrip()
        assert pre.count(original) == 1
        pre = pre.replace(original, "")
    position = pre.index("static bool in_irq(void)")
    pre = pre[:position] + EVENTS + pre[position:]
    pre += "\n#define F367R9_NO_RESULT 0\n#define qdrv_f367r9_hostlink_trace_arm(...) do{}while(0)\n#define qdrv_f367r9_boundary(...) do{}while(0)\n"
    constants = "#define HZ 100ul\n"
    api = ROOT / "work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h"
    glob = ROOT / "work/sources/Quantenna-GPL/include/qtn/qtn_global.h"
    for path, names in ((api, ("QTN_HLINK_RC_DONE", "QTN_HLINK_RC_ERR", "QTN_HLINK_STATUS_AVAIL", "IOCTL_DEV_STORE_TXPOW", "IOCTL_DEV_CHANGE_CHANNEL", "IOCTL_DEV_BEACON_START", "IOCTL_DEV_XMITCTL")),
                        (glob, ("QTN_CALSTATE_PROD", "QTN_CALSTATE_DEFAULT"))):
        text = path.read_text()
        for name in names:
            constants += re.search(r"^#define\s+" + name + r"\s+[^\n]+", text, re.M)[0] + "\n"
    macro = host[host.index("#define QDRV_IOCTL_EVNT_TIMEOUT"):host.index("/* F367r4:")]
    macro = "\n".join(line for line in macro.splitlines() if "OMF367R9_MACRO" not in line) + "\n"
    functions = [("qdrv_hostlink.c", name) for name in (
        "qdrv_alloc_ioctl", "qdrv_free_ioctl", "qdrv_completed_ack_result",
        "qdrv_send_ioctl_owned", "qdrv_send_ioctl", "qdrv_send_ioctl_ack",
        "qdrv_hostlink_store_txpow", "qdrv_hostlink_setchan", "qdrv_hostlink_xmitctl")]
    functions += [("qdrv_radar.c", "sys_raw_disable_xmit"),
                  ("qdrv_f338_availability.inc", "qdrv_f338_force_tx_off"),
                  ("qdrv_f367_control.inc", "qdrv_f367_channel_fault"),
                  ("qdrv_wlan.c", "qdrv_set_channel")]
    bodies = "\n".join(extract(texts[source], name) for source, name in functions)
    code = constants + pre + macro + bodies + CASES
    (args.output / "test.c").write_text(code)
    command = ["/usr/bin/gcc", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-but-set-variable",
               "-Wno-unused-parameter", "-Wno-pointer-to-int-cast", "-Wno-int-to-pointer-cast",
               str(args.output / "test.c"), "-o", str(args.output / "test")]
    compiled = subprocess.run(command, capture_output=True)
    (args.output / "compile.stdout").write_bytes(compiled.stdout)
    (args.output / "compile.stderr").write_bytes(compiled.stderr)
    run = None if compiled.returncode else subprocess.run([str(args.output / "test")], capture_output=True)
    if run:
        (args.output / "stdout").write_bytes(run.stdout)
        (args.output / "stderr").write_bytes(run.stderr)
    result = {
        "schema": "openmitrastar.f368-txoff-fault-test/v1",
        "status": "PASS_HAZARD_REPRODUCED" if run and run.returncode == 0 else "FAIL_TEST",
        "promotion": "NO_GO",
        "hardware_accessed": False,
        "physical_stale_completion_proven": False,
        "driver_sources_modified": False,
        "compile_exit_code": compiled.returncode,
        "run_exit_code": run.returncode if run else None,
        "stdout": run.stdout.decode() if run else None,
        "source_pins": {str(path): sha(path) for path in (*paths.values(), api, glob, Path(__file__), ROOT / "tools/test_f368_txpower_ack.py", ROOT / "tools/test_f367r8_csa_hostlink_wait.py")},
        "actual_extracted_functions": [name for _, name in functions],
        "finding": "A timed-out STORE38 descriptor is freed and reused for XMITCTL26. Injected late DONE for STORE38 can falsely confirm TX-off without an OFF ACK. The control fault remains latched; this test does not prove RF silence or physical MuC timing.",
        "injection": "STORE38 dequeues immediately but its completion writes its captured descriptor at tick55. STORE38 deadline is tick51. XMITCTL26 reuses that descriptor and never acknowledges. No source function is changed; only the mailbox/completion/time fixture is substituted.",
        "fixture_limits": "Host gcc with substitute structure layouts, one thread, deterministic ticks and immediate mailbox dequeue; R9 diagnostics are no-ops. No physical timing, DMA coherency, concurrency, ARC execution or RF behavior claim.",
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "source_pins"}))
    if compiled.returncode:
        print(compiled.stderr.decode()[-5000:])
    elif run.returncode:
        print(run.stderr.decode()[-5000:])
    return 0 if result["status"] == "PASS_HAZARD_REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
