"""Derive the qdrv-only R7 build; preserve static helper and all earlier sources."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('R7 anchor '+a[:100])
 return s.replace(a,b,1)
def main():
 s=(ROOT/'tools/build_f367r5_regulatory_component.py').read_text()
 s=once(s,"SOURCE=ROOT/'work/kernel-port/f367r5-regulatory-profile'","SOURCE=ROOT/'work/kernel-port/f367r7-clock-publication'")
 s=once(s,"REUSE=Path('/workspace/OpenMitraStar-build/f367r4/f367r4/rubbish')","unused") if False else s
 s=once(s,"REUSE=Path('/workspace/OpenMitraStar-build/f367r4/f367r4-ack-20260922T150827Z/result.json')","REUSE=ROOT/'outputs/kernel-port/f367r5-qualified-20260922T174654Z/result.json'\nSTATIC=ROOT/'outputs/kernel-port/f367r6-static-qualified-20260922T183736Z/result.json'")
 s=once(s,"ACK_TEST=ROOT/'outputs/preflight/f367r5-regulatory-route-20260922T174157Z/result.json'","ACK_TEST=ROOT/'outputs/preflight/f367r7-clock-publication-20260922T193631Z/result.json'")
 s=once(s,"reuse['status']=='PASS_F367R4_ACK_BUILD_LINK_AND_REPRODUCTION' and test['status']=='PASS_ACTUAL_OEM_REGULATORY_SYSFS_ROUTE'","reuse['status']=='PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION' and test['status']=='PASS_F367R7_DUAL_CLOCK_PUBLICATION'")
 s=once(s,"for path,digest in test['source_pins'].items():require(sha(path)==digest,'ACK test source drift')","""for path,digest in test['source_pins'].items():require(sha(path)==digest,'clock test source drift')
 static=json.loads(STATIC.read_text());require(static['status']=='PASS_OFFLINE_F367R6_STATIC_PROFILE','static helper unqualified')
 require(sha(static['artifact']['path'])==static['artifact']['sha256'],'static helper drift')
 require(test['admission_guard_unchanged'] in (SOURCE/'qdrv/qdrv/qdrv_f367_control.inc').read_text(),'admission predicate changed')""")
 s=s.replace("Path('/workspace/OpenMitraStar-build/f367r5')/('f367r7-clock-'","Path('/workspace/OpenMitraStar-build/f367r7')/('f367r7-clock-'") if False else s
 s=s.replace("Path('/workspace/OpenMitraStar-build/f367r5')","Path('/workspace/OpenMitraStar-build/f367r7')").replace('f367r5-profile-','f367r7-clock-')
 s=once(s,"for sub in ('qdrv','kernel','uapi','userspace'):","for sub in ('qdrv','kernel','uapi'):")
 s=s.replace("linux(REUSE.parent/'a/provider.symvers')","linux(Path(reuse['artifacts']['provider']['path']).parent/'provider.symvers')").replace("linux(REUSE.parent/'a/qtn_radar_f367.ko')","linux(reuse['artifacts']['provider']['path'])")
 start=s.index(' "$tc"gcc -std=gnu11 -Os');end=s.index(' cp "$build/$lane/kernel/qtn_radar_f367.ko"',start);s=s[:start]+s[end:]
 s=s.replace('cmp "$out/a/om-f367-dfs-profile" "$out/b/om-f367-dfs-profile"\n','')
 s=once(s,"'schema':'openmitrastar.f367r7-clock-component/v1','status':'PASS_F367R4_ACK_BUILD_LINK_AND_REPRODUCTION'","'schema':'openmitrastar.f367r7-clock-component/v1','status':'PASS_F367R7_CLOCK_COMPONENTS'")
 s=once(s,"'profile':item(out/'a/om-f367-dfs-profile')","'profile':static['artifact']")
 s=once(s,"'regulatory_test':item(ACK_TEST)","'regulatory_test':reuse['regulatory_test'],'clock_test':item(ACK_TEST),'static_profile_qualification':item(STATIC)")
 (ROOT/'tools/build_f367r7_clock_component.py').write_bytes(s.encode());print('F367R7_COMPONENT_BUILDER_READY')
if __name__=='__main__':main()
