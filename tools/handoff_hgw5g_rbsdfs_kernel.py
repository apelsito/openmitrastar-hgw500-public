"""Immutable offlineRBSkernelhandoff pins boundedPASS andexactremainingblockers."""
import argparse,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(s):
 s=str(s).replace('\\','/')
 if os.name!='nt':
  if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
  return Path(s)if s.startswith('/')else ROOT/s
 if s.startswith('/mnt/c/'):s='C:/'+s[7:]
 if s.startswith('/mnt/d/'):s='D:/'+s[7:]
 return Path(s)if ':'in s else ROOT/s
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--local-only',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);pins={};unverified={};receipts={};dirs={'syntax':'rbsdfs466468-kernel-four-arc-20261023T004400Z-r2','abi':'rbsdfs466468-kernel-abi-20261023T005000Z-r1','bridge':'rbsdfs466468-kernel-r4-fixture-20261023T004400Z-r1','send':'rbsdfs466468-whole-qdrv-send-20261023T004800Z-r2','provider':'rbsdfs466468-kernel-provider-audit-20261023T005200Z-r2'}
 for key,name in dirs.items():
  d=ROOT/'outputs/rea'/name;r=json.loads((d/'result.json').read_text());assert r['status'].startswith('PASS_');receipts[key]=r
  for path in d.rglob('*'):
   if path.is_file():pins[str(path)]=sha(path)
  for original,h in json.loads((d/'input-pins.json').read_text()).items():
   path=norm(original)
   if a.local_only and not path.is_file():unverified[original]=h;continue
   assert sha(path)==h;pins[str(path)]=h
 src=json.loads((a.candidate/'result.json').read_text());pins[str(a.candidate/'result.json')]=sha(a.candidate/'result.json')
 for rel,h in src['changed_sources'].items():path=a.candidate/rel;assert sha(path)==h;pins[str(path)]=h
 pins[str(Path(__file__))]=sha(Path(__file__));assert all(sha(p)==h for p,h in pins.items());(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'linux-pins-not-reread.json').write_text(json.dumps(unverified,indent=2)+'\n');abi=receipts['abi'];delta=abi['host_delta'];r=dict(status='PASS_LOCAL_SOURCE_RBS_KERNEL_PRIOR_ARC_ABI_PROVIDER_BLOCKED'if unverified else'PASS_SOURCE_ONLY_RBS_KERNEL_TYPED_TIMER_OWNERSHIP_ARC_ABI_PROVIDER_BLOCKED',hardware_accessed=False,firmware_eligible=False,qualified_ops_added=0,source_private_ops_added=4,candidate=str(a.candidate),abi_append_bytes=delta,old_fields_checked=abi['old_members_checked'],bridge_fixture_cases=receipts['bridge']['cases'],whole_qdrv_send_cases=receipts['send']['cases'],arc_units=4,current_local_inputs_verified=len(pins),prior_linux_inputs_not_reread=len(unverified),all_inputs_verified=len(pins)if not unverified else None,real_frame_provider_bound=False,full_modules_built=False,missing=src['missing'],limits=src['limits']);(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 doc=f'''# RBS466/468 kernel source handoff

Candidate: `{a.candidate}`. Four private source records added; **zero complete operations promoted**. This is a source-only Linux bridge atop qualified weather34.

The recovered OEM core C/header stay byte-identical. Scalar ops retain bool466, range1..1000/delay500 for468. The kernel bridge owns appended IC state, IRQ lock, timer, initialization, stop/join/resume, RBS radar and MBS CSA producer hooks, and the actual QDRV 802.11 send gate. Captured pre-stop-CAC context reaches the direct MBS producer; scan-done uses false. No STAstrict aliases or global TX-enable calls were introduced.

Provider search inspected the actual QDRV send-to-netqueue/MuC descriptor path. IOCTL_DEV_XMITCTL26 accepts a radio-wide boolean. Shared host descriptors expose six flags for AMSDU/NAV/retry/return and SKB metadata exposes no CAC frame-grant token. None of those inspected interfaces implements an exact single-frame CAC grant/revoke. The required immutable provider remains NULL; absent-provider admission refuses before core allowance mutation/publication.

Before open-window or per-frame grant, the bridge calls real QDRV F355 retention. Callbacks must be IRQ-safe, non-sleeping and non-reentrant. Provider send1 consumes skb only; after confirmed completion the bridge releases the node once outside its lock. Unknown publication retains node and opaque frame identity, refuses retry/resume, and makes ifdetach/inner/outer QDRV exits stop before freeing IC. Forced unload remains unsupported.

Verification: actual core/kernel bridge **{receipts['bridge']['cases']:,} cases**, including all1000 delay values, missing-provider no mutation, early/exact timer expiry, join outside lock, F355 failure, unknown retention and no resume. Whole actual QDRV send body **6 cases** verifies ordinary enqueue, refusal, success node release, unknown grant, unknown revoke and grant denial. Radio/netqueue/provider/timers/refcounts are explicit fakes. No actual asynchronous provider is bound.

ARC compilation PASS for qdrv_wlan/qdrv_radar/ieee80211/ieee80211_wireless with5680 immutable input pins. Full ARC ABI witnesses {abi['old_members_checked']['ieee80211com']} IC /210VAP/72QDRV old fields; **IC state appends {delta} bytes**, and all enclosing QDRV suffix offsets shift exactly by {delta}. Wire/VAP sizes remain unchanged. Reusing old complete modules is forbidden; all header consumers need a full paired rebuild and strict global audit before promotion.

Adapter differences are explicit: MBS frame-only window is timer bounded although OEM MBS branch has no timer. On stored/current channel mismatch, faithful OEM expiry performs no global disable, then the adapter revokes only its frame-window bookkeeping. These are narrower adapter semantics, never full OEM instruction equality. Core allowance remains separate from frame grant.

Remaining blockers:

'''+''.join('- '+x+'\n'for x in src['missing'])+'''
No hardware, RF, calibration, client AUTH/ASSOC/AUTHORIZED, traffic, persistent boot, rollback or release acceptance. Four original RBS records remain missing from the complete-operation ledger.
'''
 if unverified:doc+='\nFinal local handoff hashes all accessible local pins. WSL returned Service/0x8007274c before the final reseal: '+str(len(unverified))+' Linux-path pins are retained from completed ARC/ABI receipts and were not reread now. This is not a complete fresh dependency reseal.\n'
 (a.output/'HANDOFF.md').write_text(doc);print(json.dumps(r))
if __name__=='__main__':main()
