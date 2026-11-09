"""Derive new F366r2-only builders/tests; original F366 pins stay unchanged."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools'
def put(name,s):
 p=TOOLS/name
 if p.exists():raise ValueError('immutable generated F366r2 tool exists '+name)
 p.write_bytes(s.encode())
def main():
 s=(TOOLS/'build_f366_dfs_components.py').read_text()
 s=s.replace("SOURCE=ROOT/'work/kernel-port/f366'","SOURCE=ROOT/'work/kernel-port/f366r2'")
 s=s.replace("Path('/workspace/OpenMitraStar-build/f366')","Path('/workspace/OpenMitraStar-build/f366r2')").replace('f366-components-','f366r2-components-')
 s=s.replace('PASS_OFFLINE_NATIVE_DFS_DIAGNOSTIC_COMPONENTS','PASS_OFFLINE_F366R2_NATIVE_START_COMPONENTS').replace('openmitrastar.f366-native-components/v1','openmitrastar.f366r2-native-components/v1')
 s=s.replace("qc.assert_profile(qc.inspect(out/'a/qdrv.ko'),qc.inspect(baseline))", "candidate_profile=qc.inspect(out/'a/qdrv.ko');require(candidate_profile['parameters'].pop('openmitrastar_native_radar_diagnostic',None)==0o400,'exact diagnostic parameter missing');qc.assert_profile(candidate_profile,qc.inspect(baseline))\n require(sha(out/'a/qtn_radar_f366.ko')=='a92a14b119857c8ab0680bdc1b51538b11e1459de9b36e157f894589aa2ecd39','F366 provider bytes changed')")
 s=s.replace("source=json.loads((SOURCE/'source-manifest.json').read_text());", "gate=ROOT/'outputs/preflight/f366r2-start-gate-20260922T101019Z/result.json';gate_record=json.loads(gate.read_text());require(gate_record['status']=='PASS_ACTUAL_QDRV_NATIVE_START_ADMISSION' and gate_record['source']['sha256']==sha(SOURCE/'qdrv/qdrv/qdrv_control.c'),'native start gate not qualified')\n source=json.loads((SOURCE/'source-manifest.json').read_text());")
 s=s.replace("'f355_lifetime_preserved':True,'authority_compiled_off'", "'f355_lifetime_preserved':True,'native_start_gate':item(gate),'native_start_parameter_added':{'name':'openmitrastar_native_radar_diagnostic','mode':'0400','default':0},'authority_compiled_off'")
 put('build_f366r2_dfs_components.py',s)
 s=(TOOLS/'test_f366_runtime.py').read_text().replace('from f366_runtime_contract import','from f366r2_runtime_contract import').replace("('f366-runtime-'","('f366r2-runtime-'")
 s=s.replace("'openmitrastar.f366-runtime-tests/v1'","'openmitrastar.f366r2-runtime-tests/v1'").replace('PASS_F366_RUNTIME_AND_ACTUAL_WATCHDOG_IPC','PASS_F366R2_RUNTIME_AND_ACTUAL_WATCHDOG_IPC')
 s=s.replace("ROOT/'tools/f366_runtime_contract.py'","ROOT/'tools/f366r2_runtime_contract.py'")
 anchor=" (out/'harness.py').write_bytes(harness.encode())"
 patch=''' harness=harness.replace('schema=openmitrastar.f341-provider/v1\\n','schema=openmitrastar.f341-provider/v1\\nstarted=1\\nhardware_dirty=1\\n')
 harness=harness.replace('"$OM_F366_STAGE" complete radio-nondfs\\n','"$OM_F366_STAGE" complete radio-nondfs\\n"$OM_F366_STAGE" begin native-radar 30000\\n"$OM_F366_STAGE" complete native-radar\\n')
 harness=harness.replace('--request 5 BEGIN pipeline-observe','--request 6 BEGIN pipeline-observe').replace('--request 5 CEASE','--request 6 CEASE')
 regression=""" import shutil
 shutil.rmtree(state);trace.unlink()
 saved_native=fake_native.read_text();saved_status=(provider/'status').read_bytes();fake_native.write_text(saved_native.replace('started=1','started=0'))
 p=run('om-f366-diagnostic','activate','f'*32)
 check(p.returncode==58 and 'reason=native-not-started' in p.stdout and 'OMF366_STATUS index=' not in p.stdout)
 fake_native.write_text(saved_native);(provider/'status').write_bytes(saved_status)
"""
 harness=harness.replace(' before=trace.read_bytes();p=run(',regression+' before=trace.read_bytes();p=run(')
 harness=harness.replace(" check(text.count('complete radio-nondfs')==1 and 'channel=36' in text)"," check(text.count('complete radio-nondfs')==1 and 'channel=36' in text)\\n check(text.index('verify native-radar')<text.index(\\\"control_set 'radar enable eu'\\\")<text.index(\\\"grep -qx 'started=1'\\\"))\\n check(text.count('openmitrastar_native_radar_diagnostic=1')==3)")
'''
 s=s.replace(anchor,patch+anchor)
 anchor=" (ipcdir/'harness.py').write_bytes(ipc.encode());"
 patch=''' ipc=ipc.replace('schema=openmitrastar.f341-provider/v1\\n','schema=openmitrastar.f341-provider/v1\\nstarted=1\\nhardware_dirty=1\\n')
 ipc=ipc.replace('"$OM_F366_STAGE" complete radio-nondfs\\n','"$OM_F366_STAGE" complete radio-nondfs\\n"$OM_F366_STAGE" begin native-radar 30000\\n"$OM_F366_STAGE" complete native-radar\\n')
 ipc=ipc.replace("['phase_sequence']==5","['phase_sequence']==6").replace("'phase_sequences':[1,2,3,4,5]","'phase_sequences':[1,2,3,4,5,6]")
'''
 s=s.replace(anchor,patch+anchor)
 s=s.replace(" if not run.returncode and not irun.returncode:"," result['source_pins'][str(ROOT/'tools/f366_runtime_contract.py')]=sha(ROOT/'tools/f366_runtime_contract.py')\n if not run.returncode and not irun.returncode:")
 put('test_f366r2_runtime.py',s)
 s=(TOOLS/'f366_rootfs_worker.py').read_text().replace('from f366_runtime_contract import','from f366r2_runtime_contract import').replace("'f366-rootfs-'","'f366r2-rootfs-'").replace('PASS_F366_NATIVE_DIAGNOSTIC_ROOTFS','PASS_F366R2_NATIVE_START_ROOTFS')
 s=s.replace("  changes['usr/share/openmitrastar/dfs-f366/profile.json']", "  profile.update(revision='366r2',native_start_command='radar enable eu',native_start_parameter='openmitrastar_native_radar_diagnostic=1',native_start_once_per_module=True,native_start_context='AP channel36 bandwidth80',native_start_readback=['started=1','hardware_dirty=1','hardware_ready=1'],native_start_phase_ms=30000)\n  changes['usr/share/openmitrastar/dfs-f366/profile.json']")
 s=s.replace('  shutil.copyfile(packed,a.image)', "  stale=[name for name,row in after.items() if row['type']=='file' and old_qdrv.encode() in (verified/name).read_bytes()]\n  assert not stale,stale\n  qdrv_bindings=[name for name,row in after.items() if row['type']=='file' and a.qdrv_sha.encode() in (verified/name).read_bytes()]\n  assert set(qdrv_bindings)=={CONTRACT,ARTIFACTS_PATH,'usr/libexec/openmitrastar/om-radio5-start-f366-native'},qdrv_bindings\n  shutil.copyfile(packed,a.image)")
 put('f366r2_rootfs_worker.py',s)
 s=(TOOLS/'build_f366_dfs_image.py').read_text().replace('from f366_runtime_contract import','from f366r2_runtime_contract import')
 s=s.replace("BASE='openmitrastar-linux510-f366-","BASE='openmitrastar-linux510-f366r2-").replace('f366-f365-native-dfs-diagnostic-device-bound','f366r2-f365-native-start-device-bound').replace('f366-fullimage-','f366r2-fullimage-')
 s=s.replace('PASS_OFFLINE_NATIVE_DFS_DIAGNOSTIC_COMPONENTS','PASS_OFFLINE_F366R2_NATIVE_START_COMPONENTS').replace('PASS_F366_RUNTIME_AND_ACTUAL_WATCHDOG_IPC','PASS_F366R2_RUNTIME_AND_ACTUAL_WATCHDOG_IPC')
 s=s.replace('work/kernel-port/f366/', 'work/kernel-port/f366r2/').replace("work/kernel-port/f366'","work/kernel-port/f366r2'")
 s=s.replace('tools/f366_rootfs_worker.py','tools/f366r2_rootfs_worker.py').replace('tools/f366_runtime_contract.py','tools/f366r2_runtime_contract.py')
 s=s.replace('openmitrastar.f366-native-dfs-image/v1','openmitrastar.f366r2-native-start-image/v1').replace('PASS_OFFLINE_NATIVE_DFS_DIAGNOSTIC_IMAGE','PASS_OFFLINE_F366R2_NATIVE_START_IMAGE')
 s=s.replace("SOURCE/'manifest.json',ROOT/'work/kernel-port/f366r2/source-manifest.json'","SOURCE/'manifest.json',ROOT/'tools/f366_runtime_contract.py',ROOT/'work/kernel-port/f366r2/source-manifest.json'")
 put('build_f366r2_dfs_image.py',s)
if __name__=='__main__':main()
