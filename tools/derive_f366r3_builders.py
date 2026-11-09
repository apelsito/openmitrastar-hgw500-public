"""Derive isolated R3 qualification/composition tools from preserved R2 tools."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools'
def put(name,s):
 p=TOOLS/name
 if p.exists():raise ValueError('R3 generated tool already exists '+name)
 p.write_bytes(s.encode())
def rename(s):return s.replace('f366r2','f366r3').replace('F366R2','F366R3')
def main():
 s=rename((TOOLS/'build_f366r2_dfs_components.py').read_text())
 s=s.replace('f366r3-start-gate-20260922T101019Z','f366r3-guard-20260922T111743Z').replace('PASS_ACTUAL_QDRV_NATIVE_START_ADMISSION','PASS_ACTUAL_QDRV_GUARD_AND_RADAR_BW_PRODUCER')
 s=s.replace("ENGINE=DEVICE/", "REUSE=Path('/workspace/OpenMitraStar-build/f366r2/f366r2-components-20260922T101129Z/result.json')\nENGINE=DEVICE/",1)
 anchor=" for n,h in source['source_pins'].items():require(sha(SOURCE/n)==h,'F366 source drift '+n)"
 s=s.replace(anchor,anchor+"\n reuse=json.loads(REUSE.read_text());require(reuse['status']=='PASS_OFFLINE_F366R2_NATIVE_START_COMPONENTS','provider reuse result not qualified')\n for n,h in source['producer_evidence'].items():require(sha(n)==h,'R3 producer evidence drift')\n for n,h in source['source_pins'].items():\n  if n.startswith(('kernel/','uapi/')):require(reuse['source_pins'].get(n)==h,'provider source changed '+n)\n for name in ('provider','engine'):require(sha(reuse['artifacts'][name]['path'])==reuse['artifacts'][name]['sha256'],'reused component changed')")
 line=next(line for line in s.splitlines() if line.startswith(' SOURCE_DATE_EPOCH=1790006400 make '))
 replacement=' cp {q(linux(REUSE.parent/\'a/provider.symvers\'))} "$build/$lane/kernel/Module.symvers"\n cp {q(linux(REUSE.parent/\'a/qtn_radar_f366.ko\'))} "$build/$lane/kernel/qtn_radar_f366.ko"'
 s=s.replace(line,replacement)
 s=s.replace("'kernel_recompiled':False,", "'kernel_recompiled':False,'provider_recompiled':False,'unchanged_provider_reuse':item(REUSE),")
 put('build_f366r3_dfs_components.py',s)
 s=rename((TOOLS/'test_f366r2_runtime.py').read_text())
 s=s.replace(" result['source_pins'][str(ROOT/'tools/f366_runtime_contract.py')]=sha(ROOT/'tools/f366_runtime_contract.py')", " result['source_pins'][str(ROOT/'tools/f366_runtime_contract.py')]=sha(ROOT/'tools/f366_runtime_contract.py')\n result['source_pins'][str(ROOT/'tools/f366r2_runtime_contract.py')]=sha(ROOT/'tools/f366r2_runtime_contract.py')")
 s=s.replace(" (out/'harness.py').write_bytes(harness.encode())", " harness=harness.replace(\" check(text.count('openmitrastar_native_radar_diagnostic=1')==3)\",\" check(text.count('openmitrastar_native_radar_diagnostic=1')==3)\\n check(text.index('wifi0 radar_bw 80')<text.index(\\\"control_set 'radar enable eu'\\\"))\")\n (out/'harness.py').write_bytes(harness.encode())")
 put('test_f366r3_runtime.py',s)
 s=rename((TOOLS/'test_f366r2_start_readback.py').read_text())
 s=s.replace(".replace('/usr/sbin/om-f366-stage','\"$FIX/stage\"')", ".replace('/usr/sbin/om-f366-stage','\"$FIX/stage\"').replace('/usr/sbin/iwpriv-qtn','\"$FIX/iwpriv\"')")
 s=s.replace("('set -eu\\nrefuse()", "('set -eu\\nstate=\"$FIX\"\\nrefuse()")
 s=s.replace("control_set(){ [ \"$1\"", "control_set(){ [ \"$(cat \\\"$FIX/filter\\\")\" = 80 ]; [ \"$1\"")
 s=s.replace("('never-started',0,'0',True,31,'f366-native-not-started')", "('never-started',0,'0',True,31,'f366-native-not-started'),('setter-failed',1,'0',True,31,'f366-native-radar-bw-set')")
 s=s.replace("  env=dict(os.environ,FIX=str(p)", "  (p/'iwpriv').write_text('#!/bin/sh\\n'+('exit 19\\n' if name=='setter-failed' else '[ \\\"$1 $2 $3\\\" = \\\"wifi0 radar_bw 80\\\" ] || exit 18\\nprintf \\\"80\\\\n\\\" >\\\"$FIX/filter\\\"\\n'));(p/'iwpriv').chmod(0o755)\n  env=dict(os.environ,FIX=str(p)")
 s=s.replace("  assert (p/'calls').read_text().splitlines()==['called']", "  calls=(p/'calls').read_text().splitlines() if (p/'calls').exists() else []\n  assert calls==([] if name=='setter-failed' else ['called'])")
 s=s.replace("'never-started':0}", "'never-started':0,'setter-failed':0}")
 s=s.replace("activation_count=1,waits=waits", "activation_count=len(calls),waits=waits")
 put('test_f366r3_start_readback.py',s)
 s=rename((TOOLS/'f366r2_rootfs_worker.py').read_text())
 s=s.replace("native_start_phase_ms=30000)", "native_start_phase_ms=30000,radar_filter_setter='iwpriv-qtn wifi0 radar_bw 80',radar_filter_producer='IEEE80211_PARAM_RADAR_BW=235 RAM assignment',guard_snapshot='OMF366_NATIVE_GUARD revision=3 cached RAM only')")
 put('f366r3_rootfs_worker.py',s)
 s=rename((TOOLS/'build_f366r2_dfs_image.py').read_text())
 s=s.replace("readback_test=ROOT/'outputs/preflight/f366r3-readback-20260922T101600Z/result.json'", "readback_test=Path(a.readback_result)")
 s=s.replace("a=ap.parse_args()", "ap.add_argument('--readback-result',type=Path,required=True);a=ap.parse_args()")
 s=s.replace("ROOT/'tools/f366_runtime_contract.py',ROOT/'work/kernel-port/f366r3/source-manifest.json'", "ROOT/'tools/f366_runtime_contract.py',ROOT/'tools/f366r2_runtime_contract.py',ROOT/'work/kernel-port/f366r3/source-manifest.json'")
 s=s.replace('f366r3-f365-native-start-device-bound','f366r3-f365-radar-filter-start-device-bound')
 put('build_f366r3_dfs_image.py',s)
if __name__=='__main__':main()
