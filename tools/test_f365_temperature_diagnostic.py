"""Test only F365 instrumentation with real driver functions and fake MMIO."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

from test_f355_lifetime import extract
from test_f363_temperature_integration import PRE

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'work/kernel-port/versions/f365-temperature-data-diagnostic'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linux(path):
    path = Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]


TEST = r'''
static void reset_reads(void){reads=0;clock_us=0;clock_calls=0;stream_count=0;}
static void no_io_snapshot(void){char buf[1024];unsigned r=reads,w=writes,t=clock_calls;
 C(diag_hwmon_show(&hwmon,NULL,buf)>0);C(strstr(buf,"openmitrastar.f365-temperature-access/v1")!=NULL);
 C(diag_legacy_show(&hwmon,NULL,buf)>0);C(reads==r&&writes==w&&clock_calls==t);}
int main(void){
 struct platform_device p={0};struct f339_temp_sample sample,sentinel;
 struct f365_temp_diag retained;char text[1024];long value=777;int temp=777,ret;
 unsigned traced_reads,traced_us;struct f365_temp_diag invalid_clock={0};
 memset(&sentinel,0x5a,sizeof(sentinel));
 C(sensor_probe(&p)==0);C(reads==0&&writes==0&&registered_sensor==&allocation&&active_sensor==NULL);
 no_io_snapshot();C(diag_hwmon_show(&hwmon,NULL,text)>0);C(strstr(text,"\"first_word\":null")!=NULL&&strstr(text,"\"complete\":0")!=NULL);
 C(sensor_hwmon_read(&hwmon,hwmon_temp,hwmon_temp_input,0,&value)==-ENODEV&&value==777);
 C(allocation.hwmon_diag.error==-ENODEV&&allocation.hwmon_diag.read_count==0&&allocation.hwmon_diag.complete);
 C(topaz_read_internal_temp_sens(&temp)==-ENODEV&&temp==777);C(allocation.legacy_diag.error==-ENODEV&&reads==0&&writes==0);no_io_snapshot();
 C(experimental_enable_store(&hwmon,NULL,"1\n",2)==2);C(writes==3&&values[0]==2&&values[1]==0xfffffffeU&&values[2]==1&&reads==0);
 C(experimental_enable_store(&hwmon,NULL,"1\n",2)==-EALREADY&&writes==3);

 reset_reads();words[2]=0xd80;sample=sentinel;
 ret=sample_sensor(&allocation,&sample,F365_INPUT);C(ret==-ETIMEDOUT&&!memcmp(&sample,&sentinel,sizeof(sample)));
 C(reads==1001&&clock_us==100000&&writes==3);
 C(allocation.hwmon_diag.first_word==0xd80&&allocation.hwmon_diag.last_word==0xd80&&allocation.hwmon_diag.read_count==reads);
 C(allocation.hwmon_diag.error==-ETIMEDOUT&&allocation.hwmon_diag.elapsed_valid&&allocation.hwmon_diag.elapsed_us==clock_us&&allocation.recording==NULL);
 traced_reads=reads;traced_us=clock_us;retained=allocation.hwmon_diag;no_io_snapshot();
 reset_reads();sample=sentinel;C(f339_temp_read(&allocation.io,&sample)==-ETIMEDOUT);C(reads==traced_reads&&clock_us==traced_us&&!memcmp(&sample,&sentinel,sizeof(sample)));
 C(!memcmp(&retained,&allocation.hwmon_diag,sizeof(retained)));

 reset_reads();words[2]=0x1000|3600;temp=777;C(topaz_read_internal_temp_sens(&temp)==20&&temp==60);
 C(reads==1&&allocation.legacy_diag.error==0&&allocation.legacy_diag.first_word==words[2]);
 C(!memcmp(&retained,&allocation.hwmon_diag,sizeof(retained)));no_io_snapshot();

 reset_reads();stream_count=3;stream_words[0]=0xd80;stream_words[1]=0xd81;stream_words[2]=0x1e00;
 value=777;C(sensor_hwmon_read(&hwmon,hwmon_temp,hwmon_temp_input,0,&value)==0);
 C(reads==3&&allocation.hwmon_diag.operation==F365_INPUT&&allocation.hwmon_diag.first_word==0xd80&&allocation.hwmon_diag.last_word==0x1e00);
 C(allocation.hwmon_diag.read_count==3&&allocation.hwmon_diag.elapsed_us==200);
 traced_reads=reads;traced_us=clock_us;reset_reads();stream_count=3;
 C(f339_temp_read(&allocation.io,&sample)==0&&reads==traced_reads&&clock_us==traced_us&&sample.upper_mc==value);no_io_snapshot();

 reset_reads();words[2]=0x1fff;value=777;C(sensor_hwmon_read(&hwmon,hwmon_temp,hwmon_temp_input,0,&value)==-ERANGE&&value==777);
 C(reads==1&&allocation.hwmon_diag.error==-ERANGE&&allocation.hwmon_diag.first_word==0x1fff&&allocation.hwmon_diag.last_word==0x1fff);no_io_snapshot();
 reset_reads();words[2]=0x1000|3700;C(interval_show(&hwmon,NULL,text)>0);C(reads==1&&allocation.hwmon_diag.operation==F365_INTERVAL&&allocation.hwmon_diag.error==0);
 C(diag_hwmon_show(&hwmon,NULL,text)>0&&strstr(text,"\"operation\":\"interval\"")!=NULL);no_io_snapshot();
 C(writes==3&&allocation.recording==NULL&&!locks);
 f365_diag_finish(&invalid_clock,-EIO,10,9);C(invalid_clock.complete&&!invalid_clock.elapsed_valid&&invalid_clock.elapsed_us==0&&invalid_clock.error==-EIO);
 C(sensor_remove(&p)==0);C(active_sensor==NULL&&registered_sensor==NULL);
 printf("F365_DIAGNOSTIC_PASS checks=%u direct_core_io_equivalent=1 separate_caches=1 diagnostic_sensor_accesses=0 diagnostic_clock_reads=0 startup_writes=3\n",checks);
 return 0;
}
'''


def main():
    assert shutil.disk_usage(ROOT).free > 500*1024*1024
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path('/workspace/OpenMitraStar-build/f365')/('f365-diagnostic-tests-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    driver = (SOURCE/'temp_sens.c').read_text()
    assert sha(SOURCE/'topaz_temp_core.h') == 'cc86ae1c45828f66681d7eb8a78ea31955770d77135319e380e1987f5bb93a3c'
    begin = driver.index('struct topaz_sensor {'); end = driver.index('};', begin)+2
    prefix = PRE.replace('#include "topaz_temp_core.h"', '#include "topaz_temp_core.h"\n#include "temp_diag.h"\ntypedef uint32_t u32;\nenum hwmon_sensor_types {hwmon_temp};\nenum {hwmon_temp_input=1};')
    old_struct = 'struct topaz_sensor{void*regs;struct f339_temp_io io;bool activation_attempted;int activation_error;};'
    assert prefix.count(old_struct) == 1
    prefix = prefix.replace(old_struct, driver[begin:end])
    prefix = prefix.replace('static unsigned readl(void*p)', 'static unsigned stream_words[4],stream_count,clock_calls;\nstatic unsigned readl(void*p)')
    prefix = prefix.replace('reads++;return words[2];', 'reads++;return stream_count?stream_words[reads<=stream_count?reads-1:stream_count-1]:words[2];')
    prefix = prefix.replace('static uint64_t ktime_get(void){return clock_us;}', 'static uint64_t ktime_get(void){clock_calls++;return clock_us;}')
    names = ('sensor_read','sensor_write','sensor_now','sensor_sleep','sample_locked','sample_sensor',
             'topaz_read_internal_temp_sens','sensor_hwmon_read','interval_show','diag_show',
             'diag_hwmon_show','diag_legacy_show','experimental_enable_store','sensor_probe','sensor_remove')
    code = prefix+''.join(extract(driver,name) for name in names)+TEST
    (out/'test.c').write_bytes(code.encode())
    for name in ('topaz_temp_core.h','temp_diag.h'):
        shutil.copyfile(SOURCE/name,out/name)
    script = ('set -eu\ncc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-variable -Wno-unused-function '
              + linux(out/'test.c')+' -o '+linux(out/'test')+'\n'+linux(out/'test')+'\n')
    (out/'run.sh').write_bytes(script.encode())
    run = subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],
                         capture_output=True,text=True,timeout=30)
    result = dict(schema='openmitrastar.f365-diagnostic-tests/v1',
                  status='PASS_DIAGNOSTIC_NO_ADDITIONAL_SENSOR_IO' if run.returncode == 0 else 'FAIL',
                  stdout=run.stdout,stderr=run.stderr,source_sha256=sha(SOURCE/'temp_sens.c'),
                  core_sha256=sha(SOURCE/'topaz_temp_core.h'),diag_sha256=sha(SOURCE/'temp_diag.h'),
                  fake_mmio=True,hardware_actions=False,full_f339_oracle_reexecuted=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
    return run.returncode != 0


if __name__ == '__main__':
    raise SystemExit(main())
