"""Only F363 integration checks; reuse the qualified F339 conversion core."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess
from test_f355_lifetime import extract
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'work/kernel-port/versions/f363-temperature-diagnostic';Q=ROOT/'work/linux510-radio-port/quantenna-f363-temperature/qdrv/qdrv_wlan.c'
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include "topaz_temp_core.h"
#define __iomem
#define PAGE_SIZE 4096
#define GFP_KERNEL 0
#define IORESOURCE_MEM 0
#define CAP_SYS_RAWIO 1
#define scnprintf snprintf
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define IS_ERR(p) ((intptr_t)(p)<0 && (intptr_t)(p)>-4096)
#define PTR_ERR(p) ((intptr_t)(p))
#define ERR_PTR(e) ((void*)(intptr_t)(e))
struct device{void*of_node;void*data;};struct platform_device{struct device dev;};struct device_attribute{int unused;};
struct resource{unsigned long start,size;};struct hwmon_chip_info{int unused;};
struct topaz_sensor{void*regs;struct f339_temp_io io;bool activation_attempted;int activation_error;};
static struct topaz_sensor *active_sensor,*registered_sensor,allocation;
static struct resource resource={0xe0000108,12};static struct hwmon_chip_info sensor_chip;static void*sensor_groups;
static struct device hwmon;static unsigned words[3],writes,reads,values[8],write_fail,checks,clock_us,locks,hwmon_calls,warnings,schedules;
static bool cap=true,target=true,property=true;static int sensor_lock;
#define C(v) do{checks++;assert(v);}while(0)
static void mutex_lock(int*p){(void)p;assert(!locks);locks++;}
static void mutex_unlock(int*p){(void)p;assert(locks==1);locks--;}
static unsigned readl(void*p){ptrdiff_t offset=(char*)p-(char*)words;C(offset==8);reads++;return words[2];}
static void writel(unsigned v,void*p){ptrdiff_t offset=(char*)p-(char*)words;C(offset==0);values[writes++]=v;words[0]=v;}
static uint64_t ktime_get(void){return clock_us;}
static uint64_t ktime_to_us(uint64_t t){return t;}
static void usleep_range(unsigned a,unsigned b){(void)b;clock_us+=a;}
static void*dev_get_drvdata(struct device*d){return d->data;}
static void platform_set_drvdata(struct platform_device*p,void*d){p->dev.data=d;}
static void*platform_get_drvdata(struct platform_device*p){return p->dev.data;}
static bool capable(int c){assert(c==CAP_SYS_RAWIO);return cap;}
static int kstrtouint(const char*s,unsigned base,unsigned*v){char*end;unsigned long x=strtoul(s,&end,base);if(end==s||(*end&&strcmp(end,"\n"))||x>UINT32_MAX)return -EINVAL;*v=(unsigned)x;return 0;}
static bool of_machine_is_compatible(const char*s){C(!strcmp(s,"mitrastar,hgw-500bna-qcv2"));return target;}
static bool of_property_read_bool(void*n,const char*s){(void)n;C(!strcmp(s,"openmitrastar,experimental-temperature-control"));return property;}
static struct resource*platform_get_resource(struct platform_device*p,unsigned t,unsigned i){(void)p;(void)t;C(i==0);return &resource;}
static unsigned long resource_size(struct resource*r){return r->size;}
static void*devm_kzalloc(struct device*d,size_t n,int f){(void)d;(void)f;C(n==sizeof(allocation));memset(&allocation,0,sizeof(allocation));return &allocation;}
static void*devm_platform_ioremap_resource(struct platform_device*p,unsigned i){(void)p;C(i==0);return words;}
static struct device*devm_hwmon_device_register_with_info(struct device*d,const char*n,void*data,struct hwmon_chip_info*c,void*g){(void)d;(void)c;(void)g;C(!strcmp(n,"topaz_internal"));hwmon.data=data;hwmon_calls++;return &hwmon;}
struct work_struct{int unused;};struct delayed_work{struct work_struct work;};struct temp_info{int temp_index,real_temp;};
struct qdrv_wlan{struct{struct temp_info temp_info;struct delayed_work bbrf_cal_work;}tx_power_cal_data;};
static struct temp_info shared_temp,*p_muc_temp_index=&shared_temp;
static unsigned jiffies;
#define QDRV_TEMP_CAL_PERIOD 100
#define pr_warn_ratelimited(...) do{warnings++;}while(0)
static void schedule_delayed_work(struct delayed_work*w,unsigned when){(void)w;C(when==jiffies+QDRV_TEMP_CAL_PERIOD);schedules++;}
'''
TEST=r'''
int main(void){struct platform_device p={0};char text[64];int temp=777;struct f339_temp_sample sample;struct qdrv_wlan qw={0};unsigned old_reads;
 C(!sensor_probe(&p));C(writes==0&&reads==0&&hwmon_calls==1&&registered_sensor==&allocation&&active_sensor==NULL);
 C(topaz_read_internal_temp_sens(&temp)==-ENODEV&&temp==777&&!reads&&!writes);
 C(sample_sensor(&allocation,&sample)==-ENODEV&&!reads);
 enabled_show(&hwmon,NULL,text);C(!strcmp(text,"0\n"));activation_attempted_show(&hwmon,NULL,text);C(!strcmp(text,"0\n"));activation_error_show(&hwmon,NULL,text);C(!strcmp(text,"-19\n"));C(!reads&&!writes);
 qw.tx_power_cal_data.temp_info=(struct temp_info){7,25};shared_temp=(struct temp_info){7,25};
 qdrv_get_internal_temp(&qw.tx_power_cal_data.bbrf_cal_work.work);C(qw.tx_power_cal_data.temp_info.temp_index==7&&shared_temp.real_temp==25&&warnings==1&&schedules==1&&!reads);
 cap=false;C(experimental_enable_store(&hwmon,NULL,"1\n",2)==-EPERM&&!writes&&!allocation.activation_attempted);cap=true;
 C(experimental_enable_store(&hwmon,NULL,"0\n",2)==-EINVAL&&!writes&&!allocation.activation_attempted);
 C(experimental_enable_store(&hwmon,NULL,"1\n",2)==2);C(writes==3&&values[0]==2&&values[1]==0xfffffffeU&&values[2]==1&&!reads);
 C(experimental_enable_store(&hwmon,NULL,"1\n",2)==-EALREADY&&writes==3);
 words[2]=0x1000|3800;C(topaz_read_internal_temp_sens(&temp)==0&&temp==-40);
 qdrv_get_internal_temp(&qw.tx_power_cal_data.bbrf_cal_work.work);C(shared_temp.temp_index==0&&shared_temp.real_temp==-40&&schedules==2);
 words[2]=0x1000|3400;temp=777;C(topaz_read_internal_temp_sens(&temp)==-ERANGE&&temp==777);qdrv_get_internal_temp(&qw.tx_power_cal_data.bbrf_cal_work.work);C(shared_temp.real_temp==-40&&warnings==2&&schedules==3);
 words[2]=3800;temp=777;C(topaz_read_internal_temp_sens(&temp)==-ETIMEDOUT&&temp==777&&clock_us>=100000);
 old_reads=reads;C(!sensor_remove(&p));C(active_sensor==NULL&&registered_sensor==NULL);C(topaz_read_internal_temp_sens(&temp)==-ENODEV&&reads==old_reads);C(experimental_enable_store(&hwmon,NULL,"1\n",2)==-ENODEV&&writes==3);
 resource.size=16;C(sensor_probe(&p)==-EINVAL&&writes==3&&reads==old_reads);resource.size=12;property=false;C(sensor_probe(&p)==-EPERM&&writes==3&&reads==old_reads);
 C(!locks);printf("F363_INTEGRATION_PASS checks=%u default_sensor_accesses=0 activation_writes=3 hardware=0 f339_full_oracle_reused=1\n",checks);return 0;}
'''
def main():
 if shutil.disk_usage(ROOT).free<=500*1024*1024:raise RuntimeError('C space guard')
 out=Path('/workspace/OpenMitraStar-build/f363')/('f363-integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 driver=(S/'temp_sens.c').read_text();names=('sensor_read','sensor_write','sensor_now','sensor_sleep','sample_sensor','topaz_read_internal_temp_sens','enabled_show','activation_attempted_show','activation_error_show','experimental_enable_store','sensor_probe','sensor_remove')
 (out/'test.c').write_bytes((PRE+''.join(extract(driver,n) for n in names)+extract(Q.read_text(),'qdrv_get_internal_temp')+TEST).encode())
 (out/'topaz_temp_core.h').write_bytes((S/'topaz_temp_core.h').read_bytes())
 (out/'run.sh').write_bytes((f"set -eu\ncc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-variable '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n").encode())
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'status':'PASS_F363_DRIVER_CONSUMER_INTEGRATION' if not p.returncode else 'FAIL','stdout':p.stdout,'stderr':p.stderr,'core_sha256':hashlib.sha256((S/'topaz_temp_core.h').read_bytes()).hexdigest(),'driver_sha256':hashlib.sha256((S/'temp_sens.c').read_bytes()).hexdigest(),'qdrv_sha256':hashlib.sha256(Q.read_bytes()).hexdigest(),'full_f339_oracle_reexecuted':False,'hardware_actions':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
