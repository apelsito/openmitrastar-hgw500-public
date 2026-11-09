"""Accept only the measured F321 profile and known target-kernel WPS ABI delta."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,subprocess
import f334_qdrv_contract as elf
import build_f334_qdrv_profile as build

def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args();out=args.output.resolve()
    assert out.parent==build.ROOT/'outputs/kernel-port'
    old=elf.inspect(build.BASELINE);new=elf.inspect(out/'baseline.ko');candidate=elf.inspect(out/'external-a.ko')
    elf.assert_profile(new,old);elf.assert_profile(candidate,old)
    assert build.sha(out/'external-a.ko')==build.sha(out/'external-b.ko')
    before=elf.normalized_functions(build.BASELINE);after=elf.normalized_functions(out/'baseline.ko')
    changed=[key for key in sorted(before.keys()|after.keys()) if before.get(key)!=after.get(key)]
    assert len(before)==len(after)==783 and changed==['qdrv_wps_button_read'],changed
    assert before[changed[0]]=={'bytes':266,'relocation_masked_sha256':'531e1719edf70a524dd8bf7a7cf15245f6519e1c3c92c7057cf20fff18309a79'}
    assert after[changed[0]]=={'bytes':266,'relocation_masked_sha256':'433c0671319bdd429f257e6d84cc5387f729b2d47316102346440c038367973f'}
    kernel=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.vmlinux'
    assert build.sha(kernel)=='8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc'
    objdump=build.linux(build.ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-objdump')
    text=subprocess.check_output(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',objdump,'-d','--disassemble=recalc_sigpending_tsk',build.linux(kernel)],text=True)
    assert all('[r0,'+str(i)+']' in text for i in (182,183,190,191))
    (out/'kernel-task-signal-layout.txt').write_text(text,encoding='ascii')
    assert build.sha(out/'kernel.config')==build.CONFIG_SHA
    for kind in ('baseline','external-a','external-b'):
        commands=(out/(kind+'-compile-commands.txt')).read_text()
        lines=[line for line in commands.splitlines() if ' -c ' in line and not '.mod.c' in line]
        assert len(lines)>=30
        assert all(all(flag in line for flag in ('-DOPENMITRASTAR_QDRV_V89_PAIR=1','-DOPENMITRASTAR_SWITCH_EMAC_PORT=1','-DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1')) for line in lines)
    imports=(out/'external-a-imports.txt').read_text()
    for symbol in ('radar_start','radar_stop','radar_register','radar_enable','radar_disable','radar_set_chan','radar_set_bw','detect_drv_sample_loc_get'):
        assert (' U '+symbol+'\n') in imports
    assert any('qtn_radar_shadow_f315' in value for value in candidate['modinfo'] if value.startswith('depends='))
    shutil.copyfile(out/'external-a.ko',out/'qdrv-f334-external-radar.ko')
    shutil.copyfile(build.PROVIDER,out/'qtn_radar_shadow_f315.ko')
    result={'schema':'openmitrastar.f334-qdrv-profile/v1','status':'PASS_OFFLINE_DIAGNOSTIC_MODULE','created_at_utc':datetime.now(timezone.utc).isoformat(),
      'baseline_full_text_equal':False,'baseline_function_comparison':{'count':783,'relocation_masked_equal':782,'changed':changed,
      'qualification':'Only known WPS task_struct signal offsets differ; new182/190 match exact installed F321 kernel; old168/176 not forced'},
      'kernel_config_sha256':build.CONFIG_SHA,'kernel_vmlinux_sha256':build.sha(kernel),
      'provider':{'file':'qtn_radar_shadow_f315.ko','sha256':build.PROVIDER_SHA,'changed':False},
      'qdrv':{'file':'qdrv-f334-external-radar.ko','sha256':candidate['sha256'],'bytes':candidate['bytes'],'reproducible':True},
      'parameter_contract':candidate['parameters'],'tqe_permission_0700_preserved_as_in_F321':True,
      'authority':{'radar_start':False,'radar_get_status':False,'callbacks':0,'dfs_tx':False},
      'sources':[{'path':str(p.relative_to(build.ROOT)),'sha256':build.sha(p)} for p in sorted(build.SOURCE.rglob('*')) if p.is_file()],
      'hardware_actions':False,'physical_acceptance':False,'firmware_created':False}
    with (out/'manifest.json').open('x',encoding='ascii') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    (out/'qualification.json').write_text(json.dumps({'status':'PASS_PROFILE_AND_TARGET_ABI','sources_compared':783,'normalized_equal':782,'qdrv':result['qdrv'],'hardware_actions':False},indent=2)+'\n',encoding='ascii')
    print(json.dumps({'status':result['status'],'output':str(out),'qdrv':result['qdrv']},indent=2))

if __name__=='__main__':main()
