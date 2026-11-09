"""Seal selected SOURCE25 proof/REA/provider files before full compile/review.

Hashes current immutable sources and evidence only. Does not claim historical
precompile pins for proofs that did not have them. No firmware eligibility.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);files={a.candidate/'result.json'}
 for tree in('source','headers'):files.update(x for x in(a.candidate/tree).rglob('*')if x.is_file()and x.suffix in('.c','.h'))
 paths=['outputs/rea/windows-oem-coc491-consumer-20261022T172900Z-r1','outputs/rea/windows-oem-coc491-explicit-work-20261022T173900Z-r2','outputs/rea/windows-oem-coc491-explicit-callback-20261022T174100Z-r1','outputs/rea/coc491-source25-postcompletion-fixture-20261022T181600Z-r1','outputs/rea/coc491-source25-postcompletion-interleaving-20261022T181700Z-r1','outputs/rea/coc491-source25-ioctl-fixture-20261022T181100Z-r1','outputs/rea/coc491-source25-full-abi-20261022T181000Z-r1','outputs/rea/driver5g-ops-20261022-coc25-postcompletion-syntax-r6','outputs/rea/driver5g-ops-20261022-coc25-deferred-syntax-r3','outputs/rea/coc491-explicit-function-analysis-20261022T173800Z-r1']
 for rel in paths:
  folder=ROOT/rel;assert folder.is_dir(),rel;files.update(x for x in folder.rglob('*')if x.is_file())
 files.update(ROOT/x for x in['work/linux510-radio-port/quantenna/platform/ruby/qtn_platform_support.c','work/linux510-radio-port/quantenna/platform/ruby/qtn_pm_qos_compat.c','outputs/rea/driver5g-ops-20261022-legacy23-qualification-r2/result.json','outputs/rea/driver5g-ops-20261022-legacy23-independent-final-review-r1/result.json','tools/prepare_hgw5g_coc491_source.py','tools/prepare_hgw5g_coc491_deferred_source.py','tools/prepare_hgw5g_coc491_coalesced_source.py','tools/prepare_hgw5g_coc491_trigger_snapshot.py','tools/prepare_hgw5g_coc491_postcompletion_channel.py','tools/test_hgw5g_coc491_consumer_fixture.py','tools/test_hgw5g_coc491_interleaving.py','tools/test_hgw5g_coc491_ioctl_fixture.py','tools/witness_hgw5g_coc25_full_abi.py'])
 files.add(Path(__file__));pins={str(x.resolve()):sha(x)for x in files};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='SEALED_SOURCE25_CURRENT_INPUTS_PENDING_FULL_MODULE_DELTA',hardware_accessed=False,firmware_eligible=False,pins=len(pins),candidate=str(a.candidate),proof_scope='Currentproof/source/providerpins beforefullcompile/review; notretroactivefullpinsforthepriorwitness',physical_gates='UNRUN',limits='source25notqualifiedmodule; boot/PM/CSA/RF/traffic/release acceptance unknown');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
