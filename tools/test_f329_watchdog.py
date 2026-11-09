"""Execute actual F329 C functions with bounded fake MMIO, then audit ownership.

The harness substitutes kernel services. It proves source-level behavior only,
not bus decoding, clock frequency, electrical reset or autonomous hardware.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/versions/f329-watchdog"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"


def function(source, name):
    match = re.search(r"^(?:static )?[^;{}\n]*\b" + name + r"\([^;{}]*\)\s*\{", source, re.M)
    if not match:
        raise AssertionError(name)
    start = source.index("{", match.start())
    level = 1
    end = start + 1
    while level:
        level += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define __iomem
#define GFP_KERNEL 0
#define BIT(n) (1UL << (n))
#define MSEC_PER_SEC 1000
#define DIV_ROUND_UP(a,b) (((a)+(b)-1)/(b))
#define do_div(a,b) ((a) /= (b))
#define swap(a,b) do { __typeof__(a) tmp=(a); (a)=(b); (b)=tmp; } while(0)
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define IS_ERR(p) ((intptr_t)(p)<0 && (intptr_t)(p)>-4096)
#define PTR_ERR(p) ((intptr_t)(p))
#define ERR_PTR(e) ((void*)(intptr_t)(e))
#define IORESOURCE_MEM 1
#define EPROBE_DEFER 517
#define IRQF_SHARED 1
#define IRQF_TRIGGER_RISING 2
#define WDOG_HW_RUNNING 0
#define WDOG_ACTIVE 1
#define THIS_MODULE NULL
#define WDIOF_KEEPALIVEPING 1
#define WDIOF_SETTIMEOUT 2
#define WDIOF_MAGICCLOSE 4
#define WDIOF_PRETIMEOUT 8
#define WATCHDOG_NOWAYOUT 1
struct device_node { int unused; };
struct device { struct device_node *of_node; void *data; };
struct resource { unsigned long start, end; };
struct platform_device { struct device dev; const char *name; struct resource res; void *data; };
struct clk { int unused; };
struct reset_control { int unused; };
struct watchdog_device;
struct watchdog_info { unsigned options; const char *identity; };
struct watchdog_ops {
 void *owner;
 int (*start)(struct watchdog_device*);
 int (*stop)(struct watchdog_device*);
 int (*ping)(struct watchdog_device*);
 int (*set_timeout)(struct watchdog_device*, unsigned);
 int (*set_pretimeout)(struct watchdog_device*, unsigned);
 unsigned (*get_timeleft)(struct watchdog_device*);
 int (*restart)(struct watchdog_device*, unsigned long, void*);
};
struct watchdog_device {
 struct watchdog_info const *info;
 struct watchdog_ops const *ops;
 unsigned timeout, pretimeout, min_timeout, max_timeout, max_hw_heartbeat_ms;
 unsigned long status;
 struct device *parent;
 bool nowayout;
};
static uint32_t mmio[8];
struct event { unsigned off; uint32_t value; };
static struct event writes[64];
static unsigned nwrite, nread, nmap, nregister, nreset, nirq, ndelay;
static bool machine_ok, gate, map_busy;
static unsigned long clock_rate;
static unsigned requested_timeout;
static int register_error;
static struct clk fake_clk;
static struct device_node fake_node;
static void *allocation;
static void clear_fake(void) {
 free(allocation); allocation=NULL;
 memset(mmio,0,sizeof(mmio)); memset(writes,0,sizeof(writes));
 nwrite=nread=nmap=nregister=nreset=nirq=ndelay=0;
 machine_ok=gate=true; map_busy=false; clock_rate=125000000;
 requested_timeout=8; register_error=0;
}
static unsigned mmio_offset(void *p) {
 intptr_t off=(char*)p-(char*)mmio;
 assert(off>=0 && off<32 && off%4==0);
 return off;
}
static uint32_t readl(void *p) { ++nread; return mmio[mmio_offset(p)/4]; }
static void writel(uint32_t val, void *p) {
 unsigned off=mmio_offset(p); assert(nwrite<64);
 writes[nwrite++]=(struct event){off,val}; mmio[off/4]=val;
}
static void set_bit(unsigned b,unsigned long *p){*p|=BIT(b);}
static int watchdog_active(struct watchdog_device *w){return !!(w->status&BIT(WDOG_ACTIVE));}
static int watchdog_hw_running(struct watchdog_device *w){return !!(w->status&BIT(WDOG_HW_RUNNING));}
static void mdelay(unsigned n){ndelay+=n;}
static void *devm_kzalloc(struct device*d,size_t n,int f){return allocation=calloc(1,n);}
static struct resource *platform_get_resource(struct platform_device*p,int t,unsigned n){return &p->res;}
static unsigned long resource_size(struct resource*r){return r->end-r->start+1;}
static bool of_device_is_compatible(struct device_node*n,const char*s){return true;}
static bool of_machine_is_compatible(const char*s){return machine_ok;}
static bool of_property_read_bool(struct device_node*n,const char*s){return gate;}
static void *devm_platform_ioremap_resource(struct platform_device*p,unsigned n){nmap++;return map_busy?ERR_PTR(-EBUSY):mmio;}
static struct clk *devm_clk_get(struct device*d,const char*s){return &fake_clk;}
static struct clk *devm_clk_get_optional(struct device*d,const char*s){return NULL;}
static int clk_prepare_enable(struct clk*c){return 0;}
static void clk_disable_unprepare(struct clk*c){}
static unsigned long clk_get_rate(struct clk*c){return clock_rate;}
static struct reset_control *devm_reset_control_get_optional_shared(struct device*d,const char*s){nreset++;return NULL;}
static int reset_control_assert(struct reset_control*r){if(r)nreset++;return 0;}
static int reset_control_deassert(struct reset_control*r){if(r)nreset++;return 0;}
static int platform_get_irq_optional(struct platform_device*p,unsigned n){nirq++;return -ENXIO;}
static int dw_wdt_irq(int i,void*d){return 0;}
static int devm_request_irq(struct device*d,int i,void*fn,int f,const char*n,void*arg){nirq++;return 0;}
static struct device_node *dev_of_node(struct device*d){return d->of_node;}
static int of_property_read_variable_u32_array(struct device_node*n,const char*k,u32*out,int lo,int hi){return -EINVAL;}
#define dev_warn(...) ((void)0)
#define dev_err(...) ((void)0)
static void watchdog_set_drvdata(struct watchdog_device*w,void*d){}
static void watchdog_set_nowayout(struct watchdog_device*w,bool b){w->nowayout=b;}
static int watchdog_init_timeout(struct watchdog_device*w,unsigned n,struct device*d){
 if(requested_timeout && (requested_timeout<w->min_timeout || (w->max_timeout && requested_timeout>w->max_timeout)))return -EINVAL;
 if(requested_timeout)w->timeout=requested_timeout;
 return 0;
}
static void platform_set_drvdata(struct platform_device*p,void*d){p->data=d;}
static void *platform_get_drvdata(struct platform_device*p){return p->data;}
static void watchdog_set_restart_priority(struct watchdog_device*w,unsigned n){}
static int watchdog_register_device(struct watchdog_device*w){nregister++;return register_error;}
static void watchdog_unregister_device(struct watchdog_device*w){nregister--;}
'''

TESTS = r'''
static unsigned passed;
static struct platform_device device(void) {
 struct platform_device p={.name="topaz-watchdog",.dev={.of_node=&fake_node},.res={0xf4000000,0xf400001f}};
 return p;
}
static struct dw_wdt *probe(struct platform_device*p) {
 assert(dw_wdt_drv_probe(p)==0); assert(nwrite==0); assert(nread==1);
 assert(nirq==0 && nreset==0 && nregister==1);
 return p->data;
}
#define TEST(label, body) do { clear_fake(); body; ++passed; printf("PASS %s\n",label); } while(0)
int main(void) {
 TEST("probe_without_experiment_never_maps_or_reads", {
  struct platform_device p=device();gate=false;
  assert(dw_wdt_drv_probe(&p)==-EPERM);assert(!nmap&&!nread&&!nwrite);
 });
 TEST("wrong_machine_never_maps_or_reads", {
  struct platform_device p=device();machine_ok=false;
  assert(dw_wdt_drv_probe(&p)==-EPERM);assert(!nmap&&!nread&&!nwrite);
 });
 TEST("alias_address_rejected_before_mmio", {
  struct platform_device p=device();p.res.start=0xe40c0000;p.res.end=0xe40c001f;
  assert(dw_wdt_drv_probe(&p)==-EINVAL);assert(!nmap&&!nread&&!nwrite);
 });
 TEST("oversized_resource_rejected", {
  struct platform_device p=device();p.res.end=0xf40000ff;
  assert(dw_wdt_drv_probe(&p)==-EINVAL);assert(!nmap&&!nread&&!nwrite);
 });
 TEST("existing_owner_rejected_no_shared_mmio", {
  struct platform_device p=device();map_busy=true;
  assert(dw_wdt_drv_probe(&p)==-EBUSY);assert(!nread&&!nwrite);
 });
 TEST("unqualified_clock_rejected_no_mmio", {
  struct platform_device p=device();clock_rate=250000000;
  assert(dw_wdt_drv_probe(&p)==-EINVAL);assert(!nread&&!nwrite);
 });
 TEST("zero_clock_rejected_no_mmio", {
  struct platform_device p=device();clock_rate=0;
  assert(dw_wdt_drv_probe(&p)==-EINVAL);assert(!nread&&!nwrite);
 });
 TEST("normal_probe_readonly_no_autoarm", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(d->wdd.timeout==8 && d->wdd.max_timeout==17 && d->wdd.nowayout);
  assert(!d->wdd.status);assert(d->rmod==DW_WDT_RMOD_RESET);
 });
 TEST("prearmed_watchdog_not_adopted_or_retimed", {
  struct platform_device p=device();mmio[0]=3;
  assert(dw_wdt_drv_probe(&p)==-EBUSY);assert(nread==1&&!nwrite&&!nregister);
 });
 TEST("invalid_timeout_fails_probe_without_writes", {
  struct platform_device p=device();requested_timeout=18;
  assert(dw_wdt_drv_probe(&p)==-EINVAL);assert(!nwrite&&!nregister);
 });
 TEST("registration_failure_leaves_disarmed", {
  struct platform_device p=device();register_error=-ENOMEM;
  assert(dw_wdt_drv_probe(&p)==-ENOMEM);assert(!nwrite&&mmio[0]==0);
 });
 TEST("start_has_exact_low_torr_kick_enable_sequence", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(dw_wdt_start(&d->wdd)==0);assert(nwrite==3);
  assert(writes[0].off==4&&writes[0].value==14);
  assert(writes[1].off==12&&writes[1].value==0x76);
  assert(writes[2].off==0&&writes[2].value==1);
  assert(watchdog_hw_running(&d->wdd));
 });
 TEST("start_rejects_invalid_timeout_without_writes", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);d->wdd.timeout=18;
  assert(dw_wdt_start(&d->wdd)==-EINVAL);assert(!nwrite);
 });
 TEST("ping_only_writes_restart_magic", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(dw_wdt_ping(&d->wdd)==0);assert(nwrite==1&&writes[0].off==12&&writes[0].value==0x76);
 });
 TEST("timeout_rounding_all_supported_user_seconds", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  for(unsigned n=1;n<=17;n++) {nwrite=0;assert(!dw_wdt_set_timeout(&d->wdd,n));
   unsigned top=writes[0].value;assert(top<=15);
   assert((1ULL<<(16+top))/125000000>=n);
   if(top)assert((1ULL<<(15+top))/125000000<n);
  }
 });
 TEST("timeout_out_of_range_rejected", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(dw_wdt_set_timeout(&d->wdd,0)==-EINVAL);
  assert(dw_wdt_set_timeout(&d->wdd,18)==-EINVAL);
  assert(dw_wdt_set_timeout(&d->wdd,UINT_MAX)==-EINVAL);assert(!nwrite);
 });
 TEST("active_timeout_change_pings_once", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);set_bit(WDOG_ACTIVE,&d->wdd.status);
  assert(!dw_wdt_set_timeout(&d->wdd,4));assert(nwrite==2);
  assert(writes[0].off==4&&writes[0].value==13&&writes[1].off==12);
 });
 TEST("stop_refuses_and_never_pretends_to_disable", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);mmio[0]=1;
  assert(dw_wdt_stop(&d->wdd)==-EBUSY);assert(!nwrite&&mmio[0]==1);
 });
 TEST("no_magicclose_or_pretimeout_claim", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(!(d->wdd.info->options&(WDIOF_MAGICCLOSE|WDIOF_PRETIMEOUT)));
  assert(dw_wdt_set_pretimeout(&d->wdd,1)==-EOPNOTSUPP);assert(!nwrite);
 });
 TEST("get_timeleft_uses_only_counter_in_reset_mode", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);mmio[2]=250000000;nread=0;
  assert(dw_wdt_get_timeleft(&d->wdd)==2);assert(nread==1&&!nwrite);
 });
 TEST("restart_arms_reset_mode_if_inactive", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(!dw_wdt_restart(&d->wdd,0,NULL));assert(mmio[0]==1&&mmio[1]==0&&ndelay==500);
 });
 TEST("restart_pings_if_already_active", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);mmio[0]=3;
  assert(!dw_wdt_restart(&d->wdd,0,NULL));assert(mmio[0]==1&&mmio[1]==0&&mmio[3]==0x76);
 });
 TEST("active_remove_refuses_without_unregister_or_writes", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);set_bit(WDOG_HW_RUNNING,&d->wdd.status);
  assert(dw_wdt_drv_remove(&p)==-EBUSY);assert(nregister==1&&!nwrite);
  d->wdd.status=BIT(WDOG_ACTIVE);
  assert(dw_wdt_drv_remove(&p)==-EBUSY);assert(nregister==1&&!nwrite);
 });
 TEST("inactive_remove_cleans_up_without_arming", {
  struct platform_device p=device();probe(&p);
  assert(!dw_wdt_drv_remove(&p));assert(!nregister&&!nwrite);
 });
 TEST("clock_derived_top15_budget_is_not_20_seconds", {
  struct platform_device p=device();struct dw_wdt*d=probe(&p);
  assert(d->wdd.max_hw_heartbeat_ms==17179);
 });
 clear_fake();printf("TOTAL %u PASS\n",passed);return 0;
}
'''


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / f"outputs/preflight/f329-watchdog-tests-{stamp}"
    out.mkdir(parents=True)
    src = (SOURCE / "drivers/watchdog/dw_wdt.c").read_text()
    # Extract executable functions verbatim from the production driver. No
    # reimplemented timeout/arm/probe algorithms in the test harness.
    consts = "\n".join(line for line in src.splitlines() if (line.startswith("#define WDOG_") or line.startswith("#define DW_WDT_") or line.startswith("#define to_dw_wdt")) and not line.endswith("\\"))
    defs = src[src.index("static const u32 dw_wdt_fix_tops"):src.index("static bool nowayout")]
    structs = src[src.index("enum dw_wdt_rmod"):src.index("#define to_dw_wdt")]
    functions = ("dw_wdt_is_enabled", "dw_wdt_update_mode", "dw_wdt_find_best_top", "dw_wdt_get_min_timeout", "dw_wdt_get_max_timeout_ms", "dw_wdt_get_timeout", "dw_wdt_ping", "dw_wdt_set_timeout", "dw_wdt_set_pretimeout", "dw_wdt_arm_system_reset", "dw_wdt_start", "dw_wdt_stop", "dw_wdt_restart", "dw_wdt_get_timeleft", "dw_wdt_handle_tops", "dw_wdt_init_timeouts")
    info_ops = src[src.index("static const struct watchdog_info dw_wdt_ident"):src.index("static irqreturn_t dw_wdt_irq")]
    code = PRELUDE + consts + "\n" + defs + structs + "\nstatic bool nowayout=true;\n"
    code += "\n".join(function(src, name) for name in functions)
    code += "\n"+info_ops+"\nstatic void dw_wdt_dbgfs_init(struct dw_wdt*d){}\nstatic void dw_wdt_dbgfs_clear(struct dw_wdt*d){}\n"
    code += function(src,"dw_wdt_drv_probe")+"\n"+function(src,"dw_wdt_drv_remove")+TESTS
    (out / "harness.c").write_text(code, newline="\n")
    ws = WS_ROOT + "/" + out.relative_to(ROOT).as_posix()
    reset=(SOURCE/"arch/arc/kernel/reset.c").read_text()
    restart_harness = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#define __iomem
static jmp_buf done;
static unsigned count, handlers, with_handler;
static uintptr_t address[8];
static uint32_t value[8];
static void writel(uint32_t v,void*p){assert(count<8);address[count]=(uintptr_t)p;value[count++]=v;}
static void do_kernel_restart(char*s){assert(count==0);handlers++;if(with_handler)writel(0x76,(void*)0xf400000c);}
static void mb(void){}
static void cpu_relax(void){longjmp(done,1);}
'''+function(reset,"machine_restart")+r'''
int main(void) {
 for(with_handler=0;with_handler<2;with_handler++){
  count=handlers=0;if(!setjmp(done))machine_restart(NULL);
  assert(handlers==1&&count==6+with_handler);
  unsigned b=with_handler;
  assert(address[b]==0xf4000000&&value[b]==1);
  assert(address[b+1]==0xf4000004&&value[b+1]==8);
  assert(address[b+2]==0xf400000c&&value[b+2]==0x76);
  assert(address[b+3]==0xe0000000&&value[b+3]==UINT32_MAX);
  assert(address[b+4]==0xe0000004&&value[b+4]==0);
  assert(address[b+5]==0xe0000000&&value[b+5]==0);
 }
 puts("TOTAL 2 RESTART FALLBACK PASS");return 0;
}
'''
    (out/"restart_harness.c").write_text(restart_harness,newline="\n")
    command = f"set -eu\ngcc -std=gnu11 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -fno-omit-frame-pointer -g '{ws}/harness.c' -o '{ws}/harness'\n'{ws}/harness'\ngcc -std=gnu11 -Wall -Wextra -Wno-unused-parameter '{ws}/restart_harness.c' -o '{ws}/restart-harness'\n'{ws}/restart-harness'\n"
    (out/"test.sh").write_text(command, newline="\n")
    p = subprocess.run(["wsl.exe","-d",DISTRO,"-u","root","-e","bash",ws+"/test.sh"], capture_output=True,text=True)
    (out/"tests.log").write_text(p.stdout+p.stderr)
    failures=[]
    if p.returncode: failures.append("C harness failed")
    if "TOTAL 25 PASS" not in p.stdout: failures.append("missing 25 behavior cases")
    if "TOTAL 2 RESTART FALLBACK PASS" not in p.stdout: failures.append("missing terminal fallback cases")
    recovery=(SOURCE/"drivers/misc/qtn-topaz-recovery.c").read_text()
    reset=(SOURCE/"arch/arc/kernel/reset.c").read_text()
    dts=(SOURCE/"arch/arc/boot/dts/topaz_mitrastar_squashfs.dts").read_text()
    checks={
        "terminal_oem_fallback_after_owner_handlers": reset.index("do_kernel_restart(__unused)") < reset.index("writel(1, watchdog + 0x00)"),
        "recovery_delegates_watchdog_resource": 'if (!of_property_read_bool(dev->of_node, "quantenna,separate-watchdog"))' in recovery and "if (rec->wdt)" in recovery,
        "exactly_one_dt_watchdog_region":dts.count("0xf4000000")==1,
        "watchdog_dt_disabled": bool(re.search(r'watchdog@f4000000\s*\{.*?status = "disabled";',dts,re.S)),
        "experiment_property_absent":not re.search(r'^\s*quantenna,watchdog-experiment\s*;',dts,re.M),
        "canary_removed_from_dt":"mitrastar,product-watchdog-canary;" not in dts,
        "no_sysfs_unbind":".suppress_bind_attrs = true" in src,
        "no_optional_reset_controller_on_topaz":"dw_wdt->rst = topaz ? NULL :" in src,
        "no_probe_comp_params_read_for_topaz":"if (dw_wdt->topaz) {\n\t\ttops = dw_wdt_fix_tops;\n\t\tgoto handle_tops;" in src,
    }
    failures += [key for key,value in checks.items() if not value]
    result={"schema":"openmitrastar.f329-watchdog-tests/v1","status":"PASS_OFFLINE_BEHAVIOR" if not failures else "FAIL", "c_behavior_cases":25 if "TOTAL 25 PASS" in p.stdout else None,"restart_fallback_cases":2 if "TOTAL 2 RESTART FALLBACK PASS" in p.stdout else None,"static_contracts":checks,"failures":failures,"driver_sha256":hashlib.sha256(src.encode()).hexdigest(),"hardware_touched":False,"mmio":"bounded host simulation; actual driver C functions","hardware_timing_measured":False,"hardware_reset_proven":False}
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"output":str(out),**result}))
    return int(bool(failures))


if __name__=="__main__":raise SystemExit(main())
