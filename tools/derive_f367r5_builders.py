"""Derive the R5 builders while preserving every earlier sealed builder."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('builder anchor '+a[:90])
 return s.replace(a,b,1)
def main():
 p=ROOT/'tools/build_f367r4_ack_component.py';s=p.read_text()
 s=s.replace('f367r4-hostlink-ack','f367r5-regulatory-profile').replace('f367r4-ack-','f367r5-profile-').replace("Path('/workspace/OpenMitraStar-build/f367r4')","Path('/workspace/OpenMitraStar-build/f367r5')")
 s=s.replace("REUSE=Path('/workspace/OpenMitraStar-build/f367-functional/f367-functional-components-20260922T120217Z/result.json')","REUSE=Path('/workspace/OpenMitraStar-build/f367r4/f367r4-ack-20260922T150827Z/result.json')")
 s=once(s,"ACK_TEST=ROOT/'outputs/preflight/f367r5-regulatory-profile-20260922T150651Z/result.json'","ACK_TEST=ROOT/'outputs/preflight/f367r5-regulatory-route-20260922T174157Z/result.json'")
 s=s.replace("reuse['status']=='PASS_F367_BUILD_LINK_AND_REPRODUCTION' and test['status']=='PASS_REAL_PRODUCER_AND_CHANNEL_TX_CONSUMERS'","reuse['status']=='PASS_F367R4_ACK_BUILD_LINK_AND_REPRODUCTION' and test['status']=='PASS_ACTUAL_OEM_REGULATORY_SYSFS_ROUTE'")
 s=s.replace("if name!='qdrv/qdrv/qdrv_hostlink.c':","if name!='qdrv/qdrv/qdrv_f367_control.inc':")
 s=once(s,"for sub in ('qdrv','kernel','uapi'):shutil.copytree(SOURCE/sub,out/'source'/sub)","for sub in ('qdrv','kernel','uapi','userspace'):shutil.copytree(SOURCE/sub,out/'source'/sub)\n for path,digest in {**source['userspace_pins'],**source['producer_and_layout_pins']}.items():require(sha(path)==digest,'OEM producer/layout drift')")
 a=s.index(' # Run the exact qualified F338 readiness/availability');b=s.index(' q=shlex.quote;',a)
 s=s[:a]+" # The unchanged readiness/lifetime source and R4 machine-code qualification are reused.\n"+s[b:]
 a=s.index('cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic "$out/source/qdrv/tests/test_ready.c"');b=s.index('for lane in a b; do',a)
 s=s[:a]+s[b:]
 s=once(s,' mkdir "$out/$lane"',''' mkdir "$out/$lane"
 "$tc"gcc -std=gnu11 -Os -Wall -Wextra -Werror -fno-ident -Wl,--build-id=none -s "$build/$lane/userspace/om-f367-dfs-profile.c" -o "$out/$lane/om-f367-dfs-profile"
 "$tc"readelf -h -l -d "$out/$lane/om-f367-dfs-profile" > "$out/$lane/profile-elf.txt"''')
 s=once(s,'cmp "$out/a/qdrv.ko" "$out/b/qdrv.ko"','cmp "$out/a/qdrv.ko" "$out/b/qdrv.ko"\ncmp "$out/a/om-f367-dfs-profile" "$out/b/om-f367-dfs-profile"')
 s=s.replace("'schema':'openmitrastar.f367r4-ack-component/v1','status':'PASS_F367R4_ACK_BUILD_LINK_AND_REPRODUCTION'","'schema':'openmitrastar.f367r5-regulatory-component/v1','status':'PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION'")
 s=once(s,"'engine':item(ENGINE)","'engine':item(ENGINE),'profile':item(out/'a/om-f367-dfs-profile')")
 s=s.replace("'readiness_tests':(out/'ready-tests.log').read_text().strip(),'shutdown_tests':(out/'shutdown-tests.log').read_text().strip()","'readiness_tests':reuse['readiness_tests'],'shutdown_tests':reuse['shutdown_tests'],'reused_r4_component':item(REUSE),'regulatory_test':item(ACK_TEST),'userspace_pins':source['userspace_pins'],'producer_and_layout_pins':source['producer_and_layout_pins']")
 (ROOT/'tools/build_f367r5_regulatory_component.py').write_bytes(s.encode())
 s=(ROOT/'tools/f367r4_rootfs_worker.py').read_text().replace('f367r4_runtime_contract','f367r5_runtime_contract').replace("runtime_revision='F367r4'","runtime_revision='F367r5'")
 s=s.replace("'engine','supervisor','image'","'engine','supervisor','profile','image'").replace("'engine-sha','supervisor-sha','build-id'","'engine-sha','supervisor-sha','profile-sha','build-id'").replace("'source','qdrv','provider','engine','supervisor')","'source','qdrv','provider','engine','supervisor','profile')")
 s=once(s,"changes['usr/sbin/om-radar-engine-f367']=(a.engine.read_bytes(),0o755)","changes['usr/sbin/om-radar-engine-f367']=(a.engine.read_bytes(),0o755)\n  changes['usr/sbin/om-f367-dfs-profile']=(a.profile.read_bytes(),0o755)")
 s=once(s,"profile.update(runtime_revision=", "profile.update(regulatory_publication='OEM_SUBIO14_SINGLE_CHANNEL52_BEFORE_NATIVE_START',active_channel_mask_unchanged=True,profile_helper='/usr/sbin/om-f367-dfs-profile',profile_helper_sha256=a.profile_sha,target52_readback_before_prepare=True,runtime_revision=")
 (ROOT/'tools/f367r5_rootfs_worker.py').write_bytes(s.encode())
 s=(ROOT/'tools/build_f367r4_ack_image.py').read_text().replace('f367r4','f367r5').replace('F367R4','F367R5').replace('f367r5-hostlink-ack','f367r5-regulatory-profile').replace('f367r5-f365-hostlink-ack','f367r5-f365-regulatory-profile')
 s=s.replace('PASS_F367R5_ACK_BUILD_LINK_AND_REPRODUCTION','PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION')
 s=once(s,"ap.add_argument('--ack-test-result',type=Path,required=True);a=ap.parse_args()","ap.add_argument('--ack-test-result',type=Path,required=True);ap.add_argument('--regulatory-test-result',type=Path,required=True);a=ap.parse_args()")
 s=s.replace("changed=={'qdrv/qdrv/qdrv_hostlink.c'}","changed=={'qdrv/qdrv/qdrv_hostlink.c','qdrv/qdrv/qdrv_f367_control.inc'}")
 s=s.replace("ROOT/'work/kernel-port/f367r5-regulatory-profile/qdrv/qdrv/qdrv_hostlink.c'","ROOT/'work/kernel-port/f367r4-hostlink-ack/qdrv/qdrv/qdrv_hostlink.c'")
 anchor="supervisor=json.loads(a.supervisor_result.read_text())"
 s=once(s,anchor,"""regulatory=json.loads(a.regulatory_test_result.read_text())
 require(regulatory['status']=='PASS_ACTUAL_OEM_REGULATORY_SYSFS_ROUTE' and all(x['passed'] for x in regulatory['helper_route']),'complete regulatory/PREPARE route proof required')
 require(sha(a.regulatory_test_result)==c['regulatory_test']['sha256'],'component regulatory proof mismatch')
 for path,digest in regulatory['source_pins'].items():require(sha(path)==digest,'regulatory proof source drift')
 supervisor=json.loads(a.supervisor_result.read_text())""")
 s=s.replace("original_dir=DEVICE/'firmware/f367r3-f365-owned-lock-release-device-bound'","original_dir=DEVICE/'firmware/f367r4-f365-hostlink-ack-device-bound'")
 s=s.replace('22d3ee5485ca30606b79981ec7b7ab6ab70c4874a2f9d9d1db58620ca9a5289e','49212304d4ee05b3f9899ad6baedd1609dd1d17a41b785da8aba21618c98ef25')
 s=s.replace("runtime_revision='F367r4'","runtime_revision='F367r5'")
 s=once(s,"campaign.update(runtime_revision=","campaign.update(regulatory_profile_test=item(a.regulatory_test_result),regulatory_publication='OEM_SUBIO14_SINGLE_CHANNEL52_BEFORE_NATIVE_START',target52_readback_before_prepare=True,regulatory_profile_helper={'path':'/usr/sbin/om-f367-dfs-profile','sha256':c['artifacts']['profile']['sha256']},runtime_revision=")
 s=once(s,"for name,data in overlay().items():require(hashlib.sha256(data).hexdigest()==runtime['helpers'][name],'helper changed after tests '+name)","""for name,data in overlay().items():
  digest=hashlib.sha256(data).hexdigest()
  if name in ('usr/sbin/om-f367-control','usr/libexec/openmitrastar/f367-shell-common'):
   require(regulatory['source_pins'][str(ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay'/name)]==digest,'new helper not route-qualified')
  else:require(digest==runtime['helpers'][name],'unrelated shell change '+name)""")
 s=s.replace("a.ack_test_result,physical","a.ack_test_result,a.regulatory_test_result,physical")
 s=once(s,"build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]","inputs.update({**c['userspace_pins'],**c['producer_and_layout_pins']})\n inputs[str(ROOT/'tools/f367r4_runtime_contract.py')]=sha(ROOT/'tools/f367r4_runtime_contract.py')\n build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]")
 s=s.replace("for name in ('qdrv','provider','engine'):","for name in ('qdrv','provider','engine','profile'):")
 s=s.replace('openmitrastar.f367r5-hostlink-ack-image/v1','openmitrastar.f367r5-regulatory-profile-image/v1').replace('PASS_OFFLINE_F367R5_HOSTLINK_ACK_IMAGE','PASS_OFFLINE_F367R5_REGULATORY_PROFILE_IMAGE')
 s=s.replace('only qdrv ACK producer changed; other binaries and shell reused by SHA','OEM regulatory publication before native start; cached target readback and precise PREPARE rejection; R4 ACK and other binaries preserved')
 s=s.replace('# F367r4 hostlink ACK return correction; owned lock/protected preamble unchanged; unchanged AP DFS52/20 candidate','# F367r5 OEM regulatory publication; existing timers and R4 ACK preserved')
 (ROOT/'tools/build_f367r5_regulatory_image.py').write_bytes(s.encode())
 print('F367R5_BUILDERS_DERIVED')
if __name__=='__main__':main()
