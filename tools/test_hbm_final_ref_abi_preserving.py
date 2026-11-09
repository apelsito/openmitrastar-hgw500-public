"""Actual typed ABI-preserving finalref function fixture, fake bank progress.

Normalreference states preserve originalec/fc reset; prebankrefusal doesnotreset;
postpublicationtimeout retains resetmetadata with quarantine and never retry.
No claims about original voidcaller fence, hardwaregeneration or HBM module.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from test_hbm_final_ref_source import PRE

TEST=r'''
int main(void){unsigned cases=0;for(unsigned ec=1;ec<=135;ec++)for(unsigned fc=0;fc<ec;fc++){
 counters[2]=ec;counters[1]=fc;admits=releases=0;admit_ok=0;omhbm_quarantined=false;release_result=OMHBM_OK;enum omhbm_result r=omhbm_final_ref_preserve_abi(counters);
 if(fc+1<ec)assert(r==OMHBM_OK&&counters[1]==fc+1&&!admits&&!releases);else assert(r==OMHBM_REFUSED&&counters[1]==fc&&counters[2]==ec&&admits==1&&!releases);assert(!irq);cases++;}
for(unsigned ec=1;ec<=135;ec++)for(unsigned result=1;result<=2;result++){
 counters[2]=ec;counters[1]=ec-1;admits=releases=0;admit_ok=1;omhbm_quarantined=false;release_result=result;assert(omhbm_final_ref_preserve_abi(counters)==result&&counters[1]==0&&counters[2]==1&&releases==1);if(result==2){assert(omhbm_quarantined);assert(omhbm_final_ref_preserve_abi(counters)==OMHBM_REFUSED&&releases==1);}cases++;}
printf("{\"cases\":%u}\n",cases);return0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();text=(a.candidate/'typed-final-ref-preserve-abi.h').read_text();pre=PRE.replace('static unsigned irq,admit_ok,release_result,admits,releases,cancels;','static unsigned irq,admit_ok,release_result,admits,releases,cancels;static bool omhbm_quarantined;').replace('releases++;return release_result;','releases++;if(release_result==OMHBM_PUBLISHED_UNKNOWN)omhbm_quarantined=true;return release_result;');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-finalref-abi.c';f.write_text((pre+text+TEST).replace('return0','return 0').replace('return1','return 1'));b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();res={'status':'PASS_ACTUAL_TYPED_FINALREF_ORIGINAL_METADATA_ABI_PRE_POST_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'normal_recycle_ec1_fc0_kept':True,'prepublication_refusal_no_reset':True,'postrelease_unknown_keeps_reset_and_quarantine':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'Hardwarebankcallbacks fake; originalvoidcaller/globalfence/modulepins/ABA generations unresolved. No module orphysicalacceptance.'};(a.output/'result.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
if __name__=='__main__':main()
