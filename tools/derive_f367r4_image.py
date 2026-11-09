"""Derive the qdrv-ACK-only image composer without changing prior artifacts."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools'
def put(name,s):
 p=TOOLS/name
 if p.exists():raise ValueError('R4 tool exists '+name)
 p.write_bytes(s.encode())
def main():
 s=(TOOLS/'f367r3_rootfs_worker.py').read_text().replace('from f367r3_runtime_contract import','from f367r4_runtime_contract import').replace("runtime_revision='F367r3'","runtime_revision='F367r4'")
 s=s.replace('lock_cleanup_failure_exit=74)',"lock_cleanup_failure_exit=74,hostlink_ack_normalized_commands=[17,35,26],legacy_hostlink_return_unchanged=True)")
 put('f367r4_rootfs_worker.py',s)
 s=(TOOLS/'build_f367r3_lock_image.py').read_text().replace('from f367r3_runtime_contract import','from f367r4_runtime_contract import').replace("BASE='openmitrastar-linux510-f367r3-","BASE='openmitrastar-linux510-f367r4-").replace('f367r3-f365-owned-lock-release-device-bound','f367r4-f365-hostlink-ack-device-bound').replace('f367r3-fullimage-','f367r4-fullimage-').replace('tools/f367r3_rootfs_worker.py','tools/f367r4_rootfs_worker.py').replace('tools/f367r3_runtime_contract.py','tools/f367r4_runtime_contract.py').replace('PASS_F367_BUILD_LINK_AND_REPRODUCTION','PASS_F367R4_ACK_BUILD_LINK_AND_REPRODUCTION').replace('openmitrastar.f367r3-owned-lock-image/v1','openmitrastar.f367r4-hostlink-ack-image/v1').replace('PASS_OFFLINE_F367R3_OWNED_LOCK_IMAGE','PASS_OFFLINE_F367R4_HOSTLINK_ACK_IMAGE')
 s=s.replace("ap.add_argument('--guard-test-result',type=Path,required=True);","ap.add_argument('--guard-test-result',type=Path,required=True);ap.add_argument('--ack-test-result',type=Path,required=True);")
 old=" require(functional['status']=='PASS_ACTUAL_CONTEXT_POLICY_CONTROLS_AND_SNAPSHOT' and normalize(functional['source_pins'])==normalize(c['source_pins']),'affected functional source checks required')"
 check=""" ack_test=json.loads(a.ack_test_result.read_text());require(ack_test['status']=='PASS_REAL_PRODUCER_AND_CHANNEL_TX_CONSUMERS','actual ACK producer/consumer test required')
 for path,digest in ack_test['source_pins'].items():require(sha(path)==digest,'ACK test source drift')
 old_pins=normalize(functional['source_pins']);new_pins=normalize(c['source_pins'])
 changed={name for name in set(old_pins)|set(new_pins) if old_pins.get(name)!=new_pins.get(name)}
 require(functional['status']=='PASS_ACTUAL_CONTEXT_POLICY_CONTROLS_AND_SNAPSHOT' and changed=={'qdrv/qdrv/qdrv_hostlink.c'},'only ACK producer may differ from existing functional qualification')
 require(ack_test['source_pins'][str(ROOT/'work/kernel-port/f367r4-hostlink-ack/qdrv/qdrv/qdrv_hostlink.c')]==new_pins['qdrv/qdrv/qdrv_hostlink.c'],'new ACK producer not test-bound')"""
 if s.count(old)!=1:raise ValueError('functional qualification anchor')
 s=s.replace(old,check)
 s=s.replace('work/kernel-port/f367-functional','work/kernel-port/f367r4-hostlink-ack')
 s=s.replace("original_dir=DEVICE/'firmware/f367r2-f365-protected-preamble-device-bound'","original_dir=DEVICE/'firmware/f367r3-f365-owned-lock-release-device-bound'").replace("sha(original_dir/'manifest.json')=='c2ba47c911d135bfdfcfc317cac6182025a3f5fff13da0cbef9aed2360d1d659'","sha(original_dir/'manifest.json')=='22d3ee5485ca30606b79981ec7b7ab6ab70c4874a2f9d9d1db58620ca9a5289e'")
 s=s.replace("[('qdrv','/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'),('provider'", "[('provider'")
 s=s.replace("campaign.update(runtime_revision='F367r3'","campaign.update(runtime_revision='F367r4',hostlink_ack_delta_test=item(a.ack_test_result),hostlink_ack_commands=[17,35,26],shell_runtime_reused_from='F367r3'")
 s=s.replace('a.guard_test_result,physical,SOURCE','a.guard_test_result,a.ack_test_result,physical,SOURCE')
 s=s.replace("ROOT/'tools/f367r2_runtime_contract.py',", "ROOT/'tools/f367r2_runtime_contract.py',ROOT/'tools/f367r3_runtime_contract.py',")
 s=s.replace("'scope':'shell only; all F367 binary artifacts reused exactly'","'scope':'only qdrv ACK producer changed; other binaries and shell reused by SHA'")
 s=s.replace("'# F367r3 owned lock release; protected preamble;", "'# F367r4 hostlink ACK return correction; owned lock/protected preamble unchanged;")
 put('build_f367r4_ack_image.py',s)
if __name__=='__main__':main()
