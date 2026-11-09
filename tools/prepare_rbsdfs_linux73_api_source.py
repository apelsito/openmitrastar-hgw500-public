"""Source-only timerAPI adaptation usingpinnedlocal7.3reference; nobuildclaim."""
import argparse,hashlib,json,shutil,difflib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 for d in('source','headers'):shutil.copytree(a.parent/d,a.output/d)
 ref=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/realtek-repo/src/linux-7.3/drivers/net/wireless/realtek/rtlwifi/base.c';s=ref.read_text();assert 'timer_delete_sync(&rtlpriv->works.watchdog_timer)'in s and 'timer_container_of(rtlpriv, t,'in s and 'timer_setup(&rtlpriv->works.watchdog_timer'in s
 rel='source/wlan/openmitrastar_rbsdfs_kernel.inc';path=a.output/rel;old=path.read_text();new=old.replace('from_timer(s,timer,timer)','timer_container_of(s,timer,timer)').replace('del_timer_sync(&s->timer)','timer_delete_sync(&s->timer)');assert new!=old;path.write_text(new,newline='\n');r=json.loads((a.parent/'result.json').read_text());changes={**r['changed_sources'],rel:sha(path)};r.update(status='SOURCE_ONLY_LINUX73_RBS_TIMER_API_ADAPTATION_BUILD_UNRUN',target_kernel='7.3',parent_reference=str(a.parent),parent_reference_sha256=sha(a.parent/'result.json'),changed_sources=changes,linux73_reference_pins={str(ref):sha(ref)},timer_api_changes=['from_timer→timer_container_of','del_timer_sync→timer_delete_sync'],prior_linux510_compilation_not_linux73_proof=True,linux73_qdrv_whole_build='UNRUN',linux73_qdrv_target_source_not_discovered=True,real_exact_frame_provider_missing=True);(a.output/'timer-linux73-api.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)));(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in('changed_sources','input_pins')}))
if __name__=='__main__':main()
