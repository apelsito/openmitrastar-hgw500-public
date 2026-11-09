"""Actual R26 AuC prepare/hash/lease/clear/load/enable flow; fake MMIO, real host SHA256."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from test_linux73_firmware_loader_bounds import PRE
from test_linux73_r24_load_pipeline import EXTRA
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
HARNESS=r'''
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define DBGPRINTF_E(...) ((void)0)
#define DBGPRINTF(...) ((void)0)
#define CONFIG_ARC_AUC_BASE 0x472000U
#define CONFIG_ARC_AUC_SIZE 0x1ca000U
#define CONFIG_ARC_AUC_SRAM_BASE 0x40000U
#define CONFIG_ARC_AUC_SRAM_SIZE 0x30000U
typedef int(*qdrv_fw_prepare_fn)(const struct om73_sram_writer_token*,void*);
static unsigned enabled,registered,prepare_entered,first_map_checks;
static unsigned required_preflight_checks=8;
struct ieee80211com{unsigned unused;};struct qdrv_wlan{struct ieee80211com ic;};
struct qdrv_cb{struct device*dev;char*auc_firmware;struct{void*data;}macs[1];};
static struct{struct{unsigned auc_config;}auc;}shared;
static unsigned global_auc_config=7;
#define qtn_mproc_sync_shared_params_get() (&shared)
static void hal_enable_auc(void){enabled++;assert(!active);}
static void qdrv_auc_update_multicast_stats(void*c,uint8_t n){(void)c;(void)n;}
static void tqe_reg_multicast_tx_stats(void(*fn)(void*,uint8_t),void*c){assert(fn==qdrv_auc_update_multicast_stats&&c);registered++;assert(enabled);}
'''
TEST=r'''
static int positive_prepare(const struct om73_sram_writer_token*w,void*c){(void)c;assert(active&&w==token_identity);prepare_entered++;return 1;}
static int negative_prepare(const struct om73_sram_writer_token*w,void*c){(void)c;assert(active&&w==token_identity);prepare_entered++;return-EIO;}
static char*read_carrier(const char*name,size_t*n){FILE*f=fopen(name,"rb");assert(f&&!fseek(f,0,SEEK_END));long size=ftell(f);assert(size>0);rewind(f);char*b=malloc(size);assert(b&&fread(b,1,size,f)==(size_t)size);fclose(f);*n=size;return b;}
static void reset_auc(void){reset_pipeline();enabled=registered=prepare_entered=first_map_checks=0;}
static unsigned cases;
int main(int argc,char**argv){assert(argc==2);size_t n;char*b=read_carrier(argv[1],&n);struct qdrv_wlan qw={0};struct qdrv_cb qcb={NULL,"selected",{{&qw}}};u32 entry;char*m=malloc(n);assert(m);
/* Normal init proves the prepare callback and install share onelease. */
reset_auc();requested_data=(void*)b;requested_size=n;assert(!qdrv_auc_init(&qcb)&&enabled==1&&registered==1&&requests==1&&releases==1&&begins==1&&ends==1&&hashes==1&&!active);assert(first_map_checks==required_preflight_checks+4&&maps==12&&unmaps==12);cases++;
/* Exact profile rejection occurs before clearcallback/maps/core-enable. */
unsigned mutate[]={0,4,5,6,16,18,20,24,28,40,42,44,52,340,355,356,3118,3822,30474};
for(unsigned i=0;i<ARRAY_SIZE(mutate);i++){memcpy(m,b,n);m[mutate[i]]^=1;reset_auc();requested_data=(void*)m;requested_size=n;assert(qdrv_auc_init(&qcb)==-1&&!enabled&&!registered&&!maps&&!zeros&&hashes==1&&ends==1&&releases==1);cases++;}
reset_auc();requested_data=(void*)b;requested_size=n-1;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,auc_clear_mem,NULL)==-EKEYREJECTED&&entry==0xdeadbeef&&!hashes&&!maps&&ends==1);cases++;
/* Last clearspan overlapsactiveheap: all4spanschecked BEFOREfirstclear map. */
reset_auc();requested_data=(void*)b;requested_size=n;pool_start=0x88040000;pool_end=0x88040008;entry=0xdeadbeef;int rc=qdrv_fw_load_auc_prepared(NULL,"selected",&entry,auc_clear_mem,NULL);assert(rc==-EBUSY&&entry==0xdeadbeef&&!maps&&!enabled);cases++;
/* Fail specificallyonfourthpreparecheckafterallloadsegments checked. */
reset_auc();requested_data=(void*)b;requested_size=n;fail_check_at=required_preflight_checks+4;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,auc_clear_mem,NULL)==-EBUSY&&entry==0xdeadbeef&&!maps&&checks==required_preflight_checks+4&&!enabled);cases++;
/* Maprefusal for eachclear: noinstallmaps/enable; entry remainsprivate. */
for(unsigned fail=1;fail<=4;fail++){reset_auc();requested_data=(void*)b;requested_size=n;fail_map_at=fail;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,auc_clear_mem,NULL)==-ENOMEM&&entry==0xdeadbeef&&maps==fail&&unmaps==fail-1&&ends==1&&releases==1&&!active&&!enabled);cases++;}
/* Actualinit propagatespreparemappingfail andmustneverenableAuC. */
for(unsigned fail=1;fail<=12;fail++){reset_auc();requested_data=(void*)b;requested_size=n;fail_map_at=fail;assert(qdrv_auc_init(&qcb)==-1&&!enabled&&!registered&&maps==fail&&ends==1&&releases==1&&!active);cases++;}
/* Callbackreturncontract: positiveunexpected cannotpublishuninitializedentry. */
reset_auc();requested_data=(void*)b;requested_size=n;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,positive_prepare,NULL)==-EPROTO&&entry==0xdeadbeef&&prepare_entered==1&&!maps&&ends==1);cases++;
reset_auc();requested_data=(void*)b;requested_size=n;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,negative_prepare,NULL)==-EIO&&entry==0xdeadbeef&&prepare_entered==1&&!maps&&ends==1);cases++;
reset_auc();requested_data=(void*)b;requested_size=n;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,NULL,NULL)==-EINVAL&&entry==0xdeadbeef&&!requests&&!maps);cases++;
for(unsigned failure=0;failure<3;failure++){reset_auc();requested_data=(void*)b;requested_size=n;fail_request=failure==0;fail_begin=failure==1;fail_end=failure==2;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,auc_clear_mem,NULL)<0&&entry==0xdeadbeef&&!enabled);if(failure<2)assert(!maps);else assert(maps==12&&active&&ends==1);cases++;}
reset_auc();requested_data=(void*)b;requested_size=n;pool_start=0x88012000;pool_end=0x88020000;entry=0xdeadbeef;assert(qdrv_fw_load_auc_prepared(NULL,"selected",&entry,auc_clear_mem,NULL)>0&&entry==0xe5000000&&maps==12&&first_map_checks==12&&!active);cases++;
free(b);free(m);printf("{\"actual_AuC_prepared_pipeline_cases\":%u,\"clear_span_checks_before_first_map\":4,\"loader_destinations_checked_first\":8,\"positive_callback_rejected\":true,\"hash_backend\":\"OpenSSL SHA256 host\"}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);fw=a.candidate/'source/qdrv/qdrv_fw.c';auc=a.candidate/'source/qdrv/qdrv_auc.c';t=fw.read_text();at=auc.read_text();sigs=['static int qdrv_fw_check_info(','static int qdrv_fw_physical_range(','static int qdrv_fw_segment_address(','static int qdrv_fw_preflight(','static int qdrv_fw_writer_preflight(','static int qdrv_fw_install_segment(','static int qdrv_fw_install(','int qdrv_fw_load_prepared(','int qdrv_fw_load_auc_prepared('];funcs=[function(t,s)for s in sigs];funcs.extend(function(at,s)for s in ['static int auc_clear_addr_range(','static int auc_clear_mem(','int qdrv_auc_init(']);version=re.findall(r'#define\s+QDRV_BLD_VER\s+\(?(0x[0-9a-fA-F]+)',(a.candidate/'source/qdrv/qdrv_bld.h').read_text())[-1];prefix=re.sub(r'#define QDRV_BLD_VER 0x[0-9a-fA-F]+U','#define QDRV_BLD_VER '+version+'U',PRE);prefix=prefix.replace('static unsigned maps,unmaps,copies,zeros,fail_map_at;static size_t mapping_size;','static unsigned maps,unmaps,copies,zeros,fail_map_at;static size_t mapping_size;\nstatic unsigned active;\nstatic unsigned checks,first_map_checks;');prefix=prefix.replace('maps++;if(fail_map_at==maps)','assert(active);if(!maps)first_map_checks=checks;maps++;if(fail_map_at==maps)');extra=EXTRA.replace('hashes,checks,','hashes,');har=HARNESS.replace('prepare_entered,first_map_checks','prepare_entered');f=a.output/'actual-r26-auc.c';f.write_text(prefix+extra+har+(a.candidate/'source/qdrv/om73_fw_profiles.h').read_text()+'\n'.join(funcs)+TEST);binary=a.output/'fixture';cmd=['gcc','-O1','-g','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(f),'-lcrypto','-o',str(binary)];r=subprocess.run(cmd,capture_output=True);(a.output/'compile.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr.decode();carrier=ROOT/'work/hgw500-rootfs-live/squashfs-root/etc/firmware/auc_driver.nomu.0.bin';r=subprocess.run([str(binary),str(carrier)],capture_output=True);(a.output/'run.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(p):sha(p)for p in[Path(__file__),fw,auc,a.candidate/'source/qdrv/qdrv_fw.h',a.candidate/'source/qdrv/om73_fw_profiles.h',carrier,f,binary]};result={'status':'PASS_R26_ACTUAL_AUC_PREPARED_HASH_LEASE_CLEAR_LOAD_ENABLE_PIPELINE','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'sanitizers':['address','undefined'],'limits':['ActualR26preparecallback/fullqdrv_auc_init plusloaderC; realOpenSSLSHA256 host. Sharedparams/address/MMIO/resources/leasefake.','Hash andfullloaderdestinations thenall4clearspanscheckedbeforeanyclearmap; initdoesnotenableAuConanyrejection/failure.','Mapfailmayleaveearlierclearwrites; entryneverpublishedandnoenable, noatomicphysicalrollbackclaim.','ExternalNETSS/TQE/allproducerquiescence notprovenbythisfixture; resetlocaladapter sourceonly.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
