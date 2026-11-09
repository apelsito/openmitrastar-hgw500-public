"""Derive a shell-only revision composer, reusing every F367 binary by SHA."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools'
def put(name,s):
 p=TOOLS/name
 if p.exists():raise ValueError('revision tool exists '+name)
 p.write_bytes(s.encode())
def main():
 s=(TOOLS/'f367_rootfs_worker.py').read_text().replace('from f367_runtime_contract import','from f367r2_runtime_contract import')
 s=s.replace("  changes['usr/share/openmitrastar/dfs-f367/profile.json']", "  profile.update(runtime_revision='F367r2',preamble_phase_ms=30000,module_load_phase_ms=30000,keeper_ack_required_before_module_load=True,foreground_preamble_health=True)\n  changes['usr/share/openmitrastar/dfs-f367/profile.json']")
 put('f367r2_rootfs_worker.py',s)
 s=(TOOLS/'build_f367_functional_image.py').read_text().replace('from f367_runtime_contract import','from f367r2_runtime_contract import').replace("BASE='openmitrastar-linux510-f367-","BASE='openmitrastar-linux510-f367r2-").replace('f367-f365-ap-dfs-device-bound','f367r2-f365-protected-preamble-device-bound').replace('f367-fullimage-','f367r2-fullimage-').replace('tools/f367_rootfs_worker.py','tools/f367r2_rootfs_worker.py').replace('tools/f367_runtime_contract.py','tools/f367r2_runtime_contract.py').replace('PASS_F367_ACTUAL_HELPERS_AND_V2_IPC','PASS_F367R2_SHELL_LIFECYCLE_AND_FAILURE_EOF').replace('openmitrastar.f367-ap-dfs-image/v1','openmitrastar.f367r2-protected-preamble-image/v1').replace('PASS_OFFLINE_F367_AP_DFS_IMAGE','PASS_OFFLINE_F367R2_PROTECTED_PREAMBLE_IMAGE')
 s=s.replace("ap.add_argument('--supervisor-result',type=Path,required=True);", "ap.add_argument('--supervisor-result',type=Path,required=True);ap.add_argument('--preamble-test-result',type=Path,required=True);ap.add_argument('--guard-test-result',type=Path,required=True);")
 anchor=" for p,h in runtime['source_pins'].items():require(sha(p)==h,'runtime qualification drift')"
 extra=""" preamble=json.loads(a.preamble_test_result.read_text());guard=json.loads(a.guard_test_result.read_text())
 require(preamble['status']=='PASS_REAL_PREAMBLE_AND_IPCV2_PROTECTION' and guard['status']=='PASS_DISTINCT_PHASE_AND_HEALTH_REJECTIONS','targeted revised preamble/guard tests required')
 require(guard['stage_sha256']==runtime['helpers']['usr/sbin/om-f367-stage'] and preamble['helpers']==runtime['helpers'],'revision helper test binding mismatch')
 for path,digest in preamble['source_pins'].items():require(sha(path)==digest,'preamble test source drift')
 original_dir=DEVICE/'firmware/f367-f365-ap-dfs-device-bound'
 original_manifest=json.loads((original_dir/'manifest.json').read_text())
 require(sha(original_dir/'manifest.json')=='a335d25b1717a9e672684c41636293b73fea1937f56a6f1747486a78d406a8dc','original sealed F367 manifest drift')
 for component,path in [('qdrv','/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'),('provider','/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qtn_radar_f367.ko'),('engine','/usr/sbin/om-radar-engine-f367')]:require(c['artifacts'][component]['sha256']==original_manifest['runtime_bindings'][path],'binary changed in shell-only revision '+component)
 require(supervisor['artifact']['sha256']==original_manifest['runtime_bindings']['/usr/sbin/om-watchdog-supervisor-f367'],'supervisor changed in shell-only revision')
 campaign.update(runtime_revision='F367r2',startup_phases=['preamble','module-load','core-start','vap-create','radio-nondfs','native-radar'],preamble_phase_ms=30000,module_load_phase_ms=30000,foreground_preamble_health=True,keeper_ack_required_before_module_load=True)
"""
 s=s.replace(anchor,anchor+'\n'+extra)
 s=s.replace('a.supervisor_result,physical,SOURCE', 'a.supervisor_result,a.preamble_test_result,a.guard_test_result,physical,SOURCE')
 s=s.replace("ROOT/'tools/f366_runtime_contract.py',", "ROOT/'tools/f367_runtime_contract.py',ROOT/'tools/f366_runtime_contract.py',")
 s=s.replace("physical_validation={'status':'UNRUN'", "revision={'scope':'shell only; all F367 binary artifacts reused exactly','previous_manifest_sha256':sha(original_dir/'manifest.json'),'preamble_test':item(a.preamble_test_result),'guard_test':item(a.guard_test_result)},physical_validation={'status':'UNRUN'")
 s=s.replace("'# F367 controlled AP DFS52/20 candidate", "'# F367r2 protected preamble; unchanged AP DFS52/20 candidate")
 put('build_f367r2_preamble_image.py',s)
if __name__=='__main__':main()
