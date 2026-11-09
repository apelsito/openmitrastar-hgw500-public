"""Create the stage-lock-only R3 composer, with exact R2 evidence reuse."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools'
def put(name,s):
 p=TOOLS/name
 if p.exists():raise ValueError('immutable R3 tool exists '+name)
 p.write_bytes(s.encode())
def main():
 s=(TOOLS/'f367r2_rootfs_worker.py').read_text().replace('from f367r2_runtime_contract import','from f367r3_runtime_contract import').replace("runtime_revision='F367r2'","runtime_revision='F367r3'")
 s=s.replace('foreground_preamble_health=True)',"foreground_preamble_health=True,ipc_lock_release='owned-marker-checked-empty-directory',requires_rmdir=False,lock_cleanup_failure_exit=74)")
 put('f367r3_rootfs_worker.py',s)
 s=(TOOLS/'build_f367r2_preamble_image.py').read_text().replace('from f367r2_runtime_contract import','from f367r3_runtime_contract import').replace("BASE='openmitrastar-linux510-f367r2-","BASE='openmitrastar-linux510-f367r3-").replace('f367r2-f365-protected-preamble-device-bound','f367r3-f365-owned-lock-release-device-bound').replace('f367r2-fullimage-','f367r3-fullimage-').replace('tools/f367r2_rootfs_worker.py','tools/f367r3_rootfs_worker.py').replace('tools/f367r2_runtime_contract.py','tools/f367r3_runtime_contract.py').replace('PASS_F367R2_SHELL_LIFECYCLE_AND_FAILURE_EOF','PASS_F367R3_OWNED_LOCK_WITH_REUSED_R2_RUNTIME').replace('openmitrastar.f367r2-protected-preamble-image/v1','openmitrastar.f367r3-owned-lock-image/v1').replace('PASS_OFFLINE_F367R2_PROTECTED_PREAMBLE_IMAGE','PASS_OFFLINE_F367R3_OWNED_LOCK_IMAGE')
 old=" require(guard['stage_sha256']==runtime['helpers']['usr/sbin/om-f367-stage'] and preamble['helpers']==runtime['helpers'],'revision helper test binding mismatch')"
 replacement=""" require(sha(a.preamble_test_result)==runtime['reused_preamble']['sha256'] and sha(a.guard_test_result)==runtime['reused_guard']['sha256'],'exact R2 qualification reuse required')
 stage_key='usr/sbin/om-f367-stage'
 require(guard['stage_sha256']==runtime['previous_stage_sha256'] and {k:v for k,v in preamble['helpers'].items() if k!=stage_key}=={k:v for k,v in runtime['helpers'].items() if k!=stage_key},'non-lock runtime changed')
 for record in (runtime['reused_runtime'],runtime['delta_test'],runtime['target_probe'],runtime['probe_package']):require(sha(record['path'])==record['sha256'],'lock qualification evidence drift')
 target_probe=json.loads(Path(runtime['target_probe']['path']).read_text());delta=json.loads(Path(runtime['delta_test']['path']).read_text())
 require(runtime['target_probe']['sha256']=='b211f67850e14413837f6a2c6ebc9292f139dceba7bae3d3cbf4f66f7f4f5ea5' and target_probe['status']=='PASS' and target_probe['exit_code']==0,'exact target ash cleanup PASS required')
 require(delta['status']=='PASS_OWNED_LOCK_RELEASE_REAL_IPC_WITHOUT_RMDIR' and delta['stage_sha256']==runtime['helpers'][stage_key] and delta['path_has_rmdir'] is False,'lock delta IPC/absence test required')"""
 if s.count(old)!=1:raise ValueError('R2 qualification anchor drift')
 s=s.replace(old,replacement)
 s=s.replace("original_dir=DEVICE/'firmware/f367-f365-ap-dfs-device-bound'","original_dir=DEVICE/'firmware/f367r2-f365-protected-preamble-device-bound'").replace("sha(original_dir/'manifest.json')=='a335d25b1717a9e672684c41636293b73fea1937f56a6f1747486a78d406a8dc'","sha(original_dir/'manifest.json')=='c2ba47c911d135bfdfcfc317cac6182025a3f5fff13da0cbef9aed2360d1d659'")
 s=s.replace("campaign.update(runtime_revision='F367r2'","campaign.update(runtime_revision='F367r3',lock_cleanup_failure_exit=74,lock_release_target_probe=runtime['target_probe'],lock_release_delta_test=runtime['delta_test']")
 s=s.replace("ROOT/'tools/f367_runtime_contract.py',", "ROOT/'tools/f367_runtime_contract.py',ROOT/'tools/f367r2_runtime_contract.py',")
 s=s.replace("'# F367r2 protected preamble;", "'# F367r3 owned lock release; protected preamble;")
 put('build_f367r3_lock_image.py',s)
if __name__=='__main__':main()
