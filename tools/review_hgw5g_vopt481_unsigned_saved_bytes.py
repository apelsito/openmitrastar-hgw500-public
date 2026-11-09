"""Independent ARCldb-versus-ldb.x counterexample for immutable VOPT481r1."""
import argparse,hashlib,json,subprocess
from pathlib import Path
TEST=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "openmitrastar_vopt481_recovered.h"
static int values[500];static unsigned seen[500];
static int param(void*x,unsigned id,int v){(void)x;assert(id<500);values[id]=v;seen[id]++;return 0;}
static int scs(void*x,unsigned v){(void)x;(void)v;return 1;}
static int ocac(void*x,unsigned v){(void)x;(void)v;return 0;}
static void reassoc(void*x,unsigned a,unsigned b){(void)x;(void)a;(void)b;}
int main(void){struct om_vopt_state s;struct om_vopt_environment e={0,0,0,255};struct om_vopt_provider p={0,param,scs,ocac,0,0,reassoc};om_vopt_initialize(&s,255,255);s.saved_txbf=255;s.saved_probe=128;assert(!om_vopt_apply(&s,0,&e,&p));assert(values[78]==-1&&values[158]==-1&&values[195]==-128&&values[288]==-1&&values[482]==-1);printf("{\"cases\":1,\"saved78_actual\":%d,\"saved78_oem_expected\":255,\"saved195_actual\":%d,\"saved195_oem_expected\":128,\"mode482_actual\":%d,\"mode482_oem_expected\":-1}\n",values[78],values[195],values[482]);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];ev=root/'outputs/rea/windows-oem-vopt481-apply-20261022T200100Z-r1/rea.json';asm=json.loads(ev.read_text())['data']['normalized_result']['assembly'];anchors=['0x711b0: ldb r2, [r2]','0x711d0: ldb r2, [r13]','0x71244: ldb r2, [r2]','0x7125c: ldb r3, [r2]','0x71280: ldb.x r2, [r3, 0xc]'];assert all(x in asm for x in anchors);pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in (Path(__file__),ev,a.compiler,a.candidate/'openmitrastar_vopt481_recovered.c',a.candidate/'openmitrastar_vopt481_recovered.h')};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-r1-signed-counterexample.c';f.write_text(TEST);r=subprocess.run([str(a.compiler),'-std=c11','-O1','-I'+str(a.candidate),str(f),str(a.candidate/'openmitrastar_vopt481_recovered.c'),'-o',str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout);result=dict(status='PASS_REPRODUCED_R1_SIGNED_SAVED_BYTE_MISMATCH_EXACT_ARC_ANCHORS',hardware_accessed=False,firmware_eligible=False,**obs,assembly_anchors=anchors,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest());(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
