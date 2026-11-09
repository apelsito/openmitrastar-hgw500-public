"""Create F367-only composition tools from the preserved R3 composer."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TOOLS=ROOT/'tools'
def put(name,text):
 p=TOOLS/name
 if p.exists():raise ValueError('F367 tool exists '+name)
 p.write_bytes(text.encode())
def main():
 s=(TOOLS/'f366r3_rootfs_worker.py').read_text().replace('from f366r3_runtime_contract import','from f367_runtime_contract import').replace('f366r3','f367').replace('F366R3','F367').replace('qtn_radar_f366','qtn_radar_f367').replace('om-radio5-start-f366-native','om-radio5-start-f367-native').replace('om-radar-engine-f366','om-radar-engine-f367').replace('RADAR_F366_SHA256','RADAR_F367_SHA256').replace('dfs-f366','dfs-f367')
 s=s.replace("('source','qdrv','provider','engine','image','result')","('source','qdrv','provider','engine','supervisor','image','result')").replace("('source-sha','qdrv-sha','provider-sha','engine-sha','build-id')","('source-sha','qdrv-sha','provider-sha','engine-sha','supervisor-sha','build-id')").replace("('source','qdrv','provider','engine')","('source','qdrv','provider','engine','supervisor')")
 s=s.replace("  changes['usr/sbin/om-radar-engine-f367']=(a.engine.read_bytes(),0o755)","  changes['usr/sbin/om-radar-engine-f367']=(a.engine.read_bytes(),0o755)\n  changes['usr/sbin/om-watchdog-supervisor-f367']=(a.supervisor.read_bytes(),0o755)")
 begin=s.index("  profile={");end=s.index("  changes['usr/share/openmitrastar/dfs-f367/profile.json']",begin)
 profile="""  profile={'schema':'openmitrastar.f367-ap-dfs-profile/v1','native_provider':'qtn_radar_f367','provider_telemetry_abi':'openmitrastar.f341-provider/v1','userspace_wire_abi':'F338','device':'/dev/om-radar-f338','provider_license':'GPL','oem_math_location':'separate userspace process','engine_sha256':a.engine_sha,'callback_authority':1,'release_qualified':0,'bootstrap_channel':36,'bootstrap_bandwidth':80,'dfs_channel':52,'dfs_bandwidth':20,'escape_channel':36,'quarantine_ms':1800000,'quarantine_policy':'local conservative policy because NOP is not persisted','cac_ms':70000,'nop_ms':1800000,'watchdog_session_ms':5400000,'health_lease_ms':5000,'five_ghz_boot_pending':True,'automatic_acquisition':False,'automatic_watchdog_arm':False,'physical_acceptance':'CAC_NOP_CLIENT_UNRUN','dirty_unload_supported':False,'software_injection_is_rf_detection':False,'kernel_state':'/sys/module/qdrv/parameters/openmitrastar_dfs_state','kernel_control':'/sys/module/qdrv/parameters/openmitrastar_dfs_control','controller':'om-f367-control','supervisor_path':'/usr/sbin/om-watchdog-supervisor-f367','supervisor_sha256':a.supervisor_sha}
"""
 s=s[:begin]+profile+s[end:]
 s=s.replace("'om-f366-diagnostic'", "'om-f367-control'")
 put('f367_rootfs_worker.py',s)
 s=(TOOLS/'build_f366r3_dfs_image.py').read_text().replace('from f366r3_runtime_contract import','from f367_runtime_contract import').replace('f366r3-f365-radar-filter-start-device-bound','f367-f365-ap-dfs-device-bound').replace("BASE='openmitrastar-linux510-f366r3-","BASE='openmitrastar-linux510-f367-").replace('f366r3-fullimage-','f367-fullimage-').replace('tools/f366r3_rootfs_worker.py','tools/f367_rootfs_worker.py').replace('tools/f366r3_runtime_contract.py','tools/f367_runtime_contract.py').replace('work/kernel-port/f366r3','work/kernel-port/f367-functional')
 s=s.replace('PASS_OFFLINE_F366R3_NATIVE_START_COMPONENTS','PASS_F367_BUILD_LINK_AND_REPRODUCTION').replace('PASS_F366R3_RUNTIME_AND_ACTUAL_WATCHDOG_IPC','PASS_F367_ACTUAL_HELPERS_AND_V2_IPC').replace('openmitrastar.f366r3-native-start-image/v1','openmitrastar.f367-ap-dfs-image/v1').replace('PASS_OFFLINE_F366R3_NATIVE_START_IMAGE','PASS_OFFLINE_F367_AP_DFS_IMAGE')
 s=s.replace("ap.add_argument('--readback-result',type=Path,required=True);", "ap.add_argument('--functional-tests-result',type=Path,required=True);ap.add_argument('--supervisor-result',type=Path,required=True);")
 start=s.index(' readback_test=');end=s.index(" for p,h in runtime['source_pins']",start)
 checks=""" functional_path=a.functional_tests_result;functional=json.loads(functional_path.read_text())
 require(functional['status']=='PASS_ACTUAL_CONTEXT_POLICY_CONTROLS_AND_SNAPSHOT' and functional['source_pins']==c['source_pins'],'affected functional source checks required')
 supervisor=json.loads(a.supervisor_result.read_text())
 require(supervisor['status']=='PASS_OFFLINE_F367_SUPERVISOR' and supervisor['reproducible'] and supervisor['wire_version']==2 and supervisor['health_lease_ms']==5000 and supervisor['total_budget_max_ms']==5400000 and supervisor['phase_budget_max_ms']==60000 and supervisor['phase_sequence_max']==128,'supervisor contract mismatch')
 require(sha(supervisor['artifact']['path'])==supervisor['artifact']['sha256']=='ecd861a42812a8516f81e38fdad081089639f77a61c56335bf6c1110a926a477','supervisor artifact drift')
 for path,digest in supervisor['sources'].items():require(sha(path)==digest,'supervisor qualified source drift')
 physical=ROOT/'outputs/acceptance/f366r3-acquisition-addendum-20260922T114659Z/result.json'
 require(sha(physical)=='9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87','R3 acquisition acceptance required')
 accepted=json.loads(physical.read_text())
 require(accepted['status']=='PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM','R3 prerequisite status')
 for path,digest in accepted['evidence'].items():require(sha(path)==digest,'R3 evidence drift')
 campaign={'callback_authority':1,'bootstrap_channel':36,'bootstrap_bandwidth':80,'dfs_channel':52,'dfs_bandwidth':20,'escape_channel':36,'quarantine_ms':1800000,'cac_ms':70000,'nop_ms':1800000,'supervisor_total_ms':5400000,'supervisor':{'path':'/usr/sbin/om-watchdog-supervisor-f367','sha256':supervisor['artifact']['sha256']},'acquisition_acceptance':{'path':str(physical),'sha256':sha(physical)},'commands':{'activate':'om-f367-control activate TOKEN32','status':'om-f367-control status','enter_dfs':'om-f367-control enter-dfs','software_radar':'om-f367-control software-radar','stop':'om-f367-control stop'},'software_injection_is_rf_detection':False}
"""
 s=s[:start]+checks+s[end:]
 s=s.replace('a.components_result,a.runtime_result,readback_test,','a.components_result,a.runtime_result,functional_path,a.supervisor_result,physical,')
 s=s.replace("  for name in ('qdrv','provider','engine'):argv+=['--'+name,linux(c['artifacts'][name]['path']),'--'+name+'-sha',c['artifacts'][name]['sha256']]", "  for name in ('qdrv','provider','engine'):argv+=['--'+name,linux(c['artifacts'][name]['path']),'--'+name+'-sha',c['artifacts'][name]['sha256']]\n  argv+=['--supervisor',linux(supervisor['artifact']['path']),'--supervisor-sha',supervisor['artifact']['sha256']]")
 # Replace diagnostic-only metadata while preserving the actual image layout.
 s=s.replace("classification='F365_WITH_NATIVE_DFS_ACQUISITION_DIAGNOSTIC_AUTHORITY_DISABLED'", "classification='CONTROLLED_AP52_BW20_CAC_NOP_CANDIDATE'")
 start=s.index(",diagnostic={'controller':");end=s.index(",safety={",start)
 s=s[:start]+",campaign=campaign,functional_tests=item(functional_path),supervisor_qualification=item(a.supervisor_result)"+s[end:]
 s=s.replace("'OFFLINE_GO_EXACT_PHYSICAL_GATE_AND_F365_RETURN_PENDING'", "'OFFLINE_GO_CAC_NOP_CLIENT_PHYSICAL_GATE_AND_F365_RETURN_PENDING'")
 s=s.replace("'diagnostic':m['diagnostic']", "'campaign':m['campaign']")
 s=s.replace("(build/'LAYOUT.md').write_text(", "(build/'LAYOUT.md').write_text(")
 start=s.index("  (build/'LAYOUT.md').write_text(");end=s.index("\n  (build/'SHA256SUMS')",start)
 s=s[:start]+"  (build/'LAYOUT.md').write_text('# F367 controlled AP DFS52/20 candidate\\n\\nExact F365 kernel/DT/Ethernet/temperature/journal and F355 lifetime. Proof-bound native callback authority after accepted R3 acquisition. Bootstrap36/80, local1800s quarantine, AP52/20 with full70s CAC, continuous detector continuity, fallback36 and1800s NOP. Separate supervisor90min/HEALTH5s. Bootpending, no auto-arm. Software injection is not RF detection. Root must validate CAC/client/NOP and return exact F365.\\n')"+s[end:]
 put('build_f367_functional_image.py',s)
if __name__=='__main__':main()
