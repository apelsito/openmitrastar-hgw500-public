"""Compile actual cleanup spans and hostlink slot allocator, no hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_hgw5g_beacon_descriptor_lifetime import function

ROOT=Path(__file__).resolve().parents[1]
PRE=r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#ifndef ESHUTDOWN
#define ESHUTDOWN 108
#endif
#define QNET_HLRING_ENTRIES 4
#define QTN_HLINK_STATUS_AVAIL 1U
#define spin_lock_irqsave(x,f) ((void)(x),(f)=0)
#define spin_unlock_irqrestore(x,f) ((void)(x),(void)(f))
#define DBGPRINTF_E(...) ((void)0)
#define DBG_LOG_FUNC_TEST(x) 0
#define QDRV_LF_HLINK 1
struct host_ioctl{unsigned ioctl_status,ioctl_dev;};
struct qdrv_wlan{struct{int hl_flowlock;struct host_ioctl hl_ring[4];}tx_if;unsigned unit;};
struct qdrv_vap{struct qdrv_wlan*parent;unsigned devid;};
static void dump_hring(struct qdrv_wlan*x){(void)x;}
static unsigned args_freed,param_freed,skb_freed,ioctl_freed,publication;
struct qtn_beacon_args{int x;};struct vap{int x;};struct skb{int x;};
static void qdrv_hostlink_free_coherent(void*d,unsigned n,void*p,int h){(void)d;(void)n;(void)p;(void)h;args_freed++;}
static void ieee80211_beacon_destroy_param(struct vap*v){(void)v;param_freed++;}
static void dev_kfree_skb_any(struct skb*s){(void)s;skb_freed++;}
'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 qc=a.candidate/'source/qdrv/qdrv_wlan.c';hc=a.candidate/'source/qdrv/qdrv_hostlink.c';q=qc.read_text();h=hc.read_text()
 host='\n'.join(function(h,n)[2]for n in('static struct host_ioctl *qdrv_alloc_ioctl(','static void qdrv_free_ioctl(','struct host_ioctl *vnet_alloc_ioctl('))
 host+='\nstatic void vnet_free_ioctl(struct host_ioctl*ioctl){if(ioctl){assert(ioctl->ioctl_status!=QTN_HLINK_STATUS_AVAIL);ioctl_freed++;qdrv_free_ioctl(ioctl);}}\n'
 blocks=[]
 for label,marker in [('frame','if (build_error) {'),('preflight','if (preflight) {'),('encode','if (encode) {')]:
  start=q.index(marker,q.index('static int qdrv_wlan_80211_beacon_update_run('));start=q.index('qdrv_hostlink_free_coherent',start) if label=='frame' else q.index('vnet_free_ioctl(ioctl)',start)
  start=q.rfind('\n',0,start)+1;end=q.index('\n\t\t}' if label!='frame'else '\n\t\t}',start)
  body=q[start:end].replace('return build_error;','return error;').replace('return preflight;','return error;').replace('return encode;','return error;')
  blocks.append('static int actual_'+label+'(struct host_ioctl*ioctl,int error){struct qtn_beacon_args a,*bc_args=&a;struct vap v,*vap=&v;struct skb s,*beacon_skb=&s;int args_dma=1;'+body+'}\n')
 # The shutdown span is after every construction check but still unpublished.
 start=q.index('if (txn->dying || txn->qv != qv) {');start=q.index('qdrv_hostlink_free_coherent',start);start=q.rfind('\n',0,start)+1;end=q.index('\n\t}',start)
 block=q[start:end].replace('return -ESHUTDOWN;','return error;')
 blocks.append('static int actual_shutdown(struct host_ioctl*ioctl,int error){struct qtn_beacon_args a,*bc_args=&a;struct vap v,*vap=&v;struct skb s,*beacon_skb=&s;int args_dma=1;'+block+'}\n')
 tests=r'''
int main(void){struct qdrv_wlan w={0};struct qdrv_vap v={&w,7};for(unsigned n=0;n<4;n++)w.tx_if.hl_ring[n].ioctl_status=QTN_HLINK_STATUS_AVAIL;
struct host_ioctl*p=vnet_alloc_ioctl(&v);assert(p&&p->ioctl_status==0);assert(actual_frame(p,-EINVAL)==-EINVAL);
p=vnet_alloc_ioctl(&v);assert(actual_preflight(p,-EINVAL)==-EINVAL);
p=vnet_alloc_ioctl(&v);assert(actual_encode(p,-EIO)==-EIO);
p=vnet_alloc_ioctl(&v);assert(actual_shutdown(p,-ESHUTDOWN)==-ESHUTDOWN);
assert(args_freed==4&&param_freed==4&&skb_freed==4&&ioctl_freed==4&&publication==0);
for(unsigned n=0;n<4;n++)assert(w.tx_if.hl_ring[n].ioctl_status==QTN_HLINK_STATUS_AVAIL);
puts("{\"paths\":4,\"owned_resources_freed_once_each\":true,\"all_hostlink_slots_available\":true,\"publication_zero\":true}");return 0;}
'''
 src=a.output/'actual-cleanup.c';src.write_text(PRE+host+''.join(blocks)+tests);exe=a.output/'fixture.exe';cc=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe'
 built=subprocess.run([str(cc),'-std=c11','-O1','-Wno-unused-function',str(src),'-o',str(exe)],capture_output=True);(a.output/'compile.stderr').write_bytes(built.stderr);assert not built.returncode,built.stderr.decode()
 run=subprocess.run([str(exe)],capture_output=True);(a.output/'stdout').write_bytes(run.stdout);assert not run.returncode,run.stderr.decode()
 result={'status':'PASS_ACTUAL_PREPUBLICATION_HOSTLINK_CLEANUP','hardware_accessed':False,'firmware_eligible':False,'facts':json.loads(run.stdout),'qdrv_source_sha256':hashlib.sha256(qc.read_bytes()).hexdigest(),'hostlink_source_sha256':hashlib.sha256(hc.read_bytes()).hexdigest(),'limits':'Actual cleanup spans/allocator; synthetic resourcefreecallbacks, not fullkernelMuCtiming/lifecycle.'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
