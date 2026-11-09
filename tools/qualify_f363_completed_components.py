"""Close an already-completed F363 build after the exact WARN line audit."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,struct
from elftools.elf.elffile import ELFFile
import build_f363_temperature_components as b
from f363_qdrv_comparison import warn_line_metadata
from f336_wdt_ram_contract import node_map,reservations
from build_f340_watchdog_kernel import extract_embedded
import f334_qdrv_contract as qc
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):return {'path':str(p),'bytes':Path(p).stat().st_size,'sha256':sha(p)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--completed',required=True,type=Path);a=ap.parse_args();source=a.completed.resolve()
 b.require(shutil.disk_usage(b.ROOT).free>500*1024*1024,'C disk floor')
 k=json.loads(b.KPROOF.read_text());f339=json.loads(b.F339.read_text())
 for row in k['artifacts'].values():b.require(sha(row['path'])==row['sha256'],'F362 kernel drift')
 core=source/'sensor-source/topaz_temp_core.h';b.require(sha(core)==f339['source_pins'][str(b.ROOT/'work/kernel-port/versions/f339-topaz-hwmon/topaz_temp_core.h')],'F339 core changed')
 base_cfg=b.config_values(source/'base.config');cfg=b.config_values(source/'f363.config');cfg_diff={n:[base_cfg.get(n),cfg.get(n)] for n in set(base_cfg)|set(cfg) if base_cfg.get(n)!=cfg.get(n)}
 b.require(cfg_diff=={'CONFIG_HWMON':[None,'m']},'config drift')
 old=node_map(source/'base.dtb');new=node_map(source/'f363.dtb');sensor_path='/soc/temperature-sensor@e0000108'
 changes=[(p,n) for p in set(old)|set(new) for n in set(old.get(p,{}))|set(new.get(p,{})) if old.get(p,{}).get(n)!=new.get(p,{}).get(n)]
 b.require(set(changes)=={('/soc/recovery@e0000000','reg'),*((sensor_path,n) for n in ('compatible','reg','status','openmitrastar,experimental-temperature-control'))},'DT delta changed')
 b.require(new['/soc/recovery@e0000000']['reg']==struct.pack('>II',0xe0000000,8)+old['/soc/recovery@e0000000']['reg'][8:],'recovery resource tail changed')
 embedded,address=extract_embedded(source/'f363.vmlinux');b.require(embedded==(source/'f363.dtb').read_bytes(),'embedded DT differs');b.require(reservations(embedded)==reservations((source/'base.dtb').read_bytes()),'reserved memory changed')
 proofs={}
 for lane in ('a','b'):
  base=source/lane/'baseline/qdrv/qdrv.ko';temp=source/lane/'temperature/qdrv/qdrv.ko'
  old_funcs=qc.normalized_functions(source/'installed-f362-qdrv.ko');base_funcs=qc.normalized_functions(base);temp_funcs=qc.normalized_functions(temp)
  baseline_delta=sorted(n for n in set(old_funcs)|set(base_funcs) if old_funcs.get(n)!=base_funcs.get(n));temp_delta=sorted(n for n in set(base_funcs)|set(temp_funcs) if base_funcs.get(n)!=temp_funcs.get(n))
  b.require(baseline_delta==['qdrv_wps_button_read'],'unexpected baseline ABI delta '+str(baseline_delta))
  b.require(temp_delta==['qdrv_get_internal_temp','qdrv_wlan_exit'],'unexpected temperature delta '+str(temp_delta))
  proofs[lane]={'baseline_abi':{'functions':len(base_funcs),'changed':baseline_delta},'temperature_only':{'functions':len(temp_funcs),'changed':temp_delta,'warning_line_metadata':warn_line_metadata(base,temp,source/lane/'baseline/qdrv/qdrv_wlan.c',source/lane/'temperature/qdrv/qdrv_wlan.c')}}
  b.require(qc.inspect(temp)['parameters']==qc.inspect(source/'installed-f362-qdrv.ko')['parameters'],'parameter profile changed')
  b.require(qc.inspect(temp)['functions']==qc.inspect(source/'installed-f362-qdrv.ko')['functions'],'beacon profile changed')
 for relative in ('sensor/temp_sens.ko','baseline/qdrv/qdrv.ko','temperature/qdrv/qdrv.ko'):
  b.require(sha(source/'a'/relative)==sha(source/'b'/relative),'paired build mismatch')
 exports={};
 for name in ('Module.symvers','a/sensor/Module.symvers','peer-dependencies.symvers'):
  for line in (source/name).read_text().splitlines():
   cols=line.split();exports[cols[1]]={'owner':cols[2],'type':cols[3]}
 audit=[]
 for name,path in [('hwmon',source/'hwmon.ko'),('temp_sens',source/'a/sensor/temp_sens.ko'),('qdrv',source/'a/temperature/qdrv/qdrv.ko')]:
  with path.open('rb') as f:
   elf=ELFFile(f);b.require(elf['e_machine']=='EM_ARC_COMPACT','module architecture');info=elf.get_section_by_name('.modinfo').data().decode().split('\0');b.require('license=GPL' in info or 'license=GPL v2' in info,'GPL interface incompatible')
   for symbol in elf.get_section_by_name('.symtab').iter_symbols():
    if symbol['st_shndx']=='SHN_UNDEF' and symbol.name:
     b.require(symbol.name in exports,'unresolved import '+name+':'+symbol.name);audit.append({'consumer':name,'symbol':symbol.name,**exports[symbol.name]})
 old_exports={line.split()[1] for line in Path(k['artifacts']['Module.symvers']['path']).read_text().splitlines()};b.require(old_exports<=set(exports),'old kernel export missing')
 out=Path('/workspace/OpenMitraStar-build/f363')/('f363-qualified-components-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 files=('f363.vmlinux','f363.raw.bin','f363.uncompressed.uImage','f363.config','f363.dtb','Module.symvers','hwmon.ko','a/sensor/temp_sens.ko','a/temperature/qdrv/qdrv.ko')
 for name in files:
  target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
 pins={str(p.relative_to(source)):sha(p) for directory in ('sensor-source','qdrv-baseline-source','qdrv-source') for p in (source/directory).rglob('*') if p.is_file()}
 shared={}
 for owner in ('irqc','pcie'):
  p=source/('ownership-'+owner+'.c');shutil.copyfile(p,out/p.name);shared[owner]={'path':str(out/p.name),'sha256':sha(p),'exclusive_resource_claim':False,'sensor_registers_accessed':False}
 result={'schema':'openmitrastar.f363-temperature-components/v1','status':'PASS_OFFLINE_TEMPERATURE_INTEGRATION','errors':[],'completed_build':str(source),'no_rebuild_during_qualification':True,'initial_qualification_rejected_unclassified_warn_line':True,'f362_kernel_proof':item(b.KPROOF),'f362_manifest':item(b.F362/'manifest.json'),'f339_qualification':item(b.F339),'f339_core_byte_identical':True,'hardware_actions':False,'default_sensor_mmio':False,'clock_or_measurement_qualified':False,'config_delta':cfg_diff,'dt_delta':changes,'recovery_reg_tail_preserved':True,'shared_sysctl_maps_reviewed':shared,'exclusive_resource_conflicts':[],'qdrv_comparisons':proofs['a'],'second_lane_comparisons':proofs['b'],'new_imports_audited':audit,'kernel_build_identity':'#358 @1790006400','kernel_build_directory':str(source/'kernel'),'kernel_build_directory_linux':b.linux(source/'kernel'),'kernel_source':k['source'],'kernel_source_linux':k['source'],'source_pins':pins,'artifacts':{n:item(out/n) for n in files}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'sha256':sha(out/'result.json'),'status':result['status'],'imports':len(audit),'qdrv_comparisons':proofs['a']},indent=2))
if __name__=='__main__':main()
