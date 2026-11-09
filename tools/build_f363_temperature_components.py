"""Build the F363 temperature integration against exact F362 inputs; no hardware."""
from pathlib import Path
from datetime import datetime,timezone
import copy,hashlib,json,shlex,shutil,struct,subprocess
from elftools.elf.elffile import ELFFile
from dtb_find_nodes import parse
from f336_wdt_ram_contract import serialize,node_map,reservations
from build_f340_watchdog_kernel import extract_embedded
import f334_qdrv_contract as qc
from f363_qdrv_comparison import warn_line_metadata
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
KPROOF=DEVICE/'analysis/f362-dual-ethernet-kernel-20260921T200040Z/result.json'
F362=DEVICE/'firmware/f362-f361-dual-ethernet-device-bound'
F339=ROOT/'outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z/result.json'
SOURCE=ROOT/'work/kernel-port/versions/f363-temperature-diagnostic'
QBASE=ROOT/'work/linux510-radio-port/quantenna-f334-f321-profile'
QSRC=ROOT/'work/linux510-radio-port/quantenna-f363-temperature'
DEPS=ROOT/'outputs/kernel-port/f334-qdrv-profile-20260921T105936Z/dependencies.symvers'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def item(p):return {'path':str(p),'bytes':Path(p).stat().st_size,'sha256':sha(p)}
def config_values(p):
 return dict(line.split('=',1) for line in Path(p).read_text().splitlines() if line.startswith('CONFIG_') and '=' in line)
def main():
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 k=json.loads(KPROOF.read_text());require(k['status']=='PASS_OFFLINE_DT_ONLY_KERNEL','F362 kernel unqualified')
 for row in k['artifacts'].values():require(sha(row['path'])==row['sha256'],'F362 artifact drift')
 old_dtb=Path(k['artifacts']['f362.dtb']['path']);old_cfg=Path(k['artifacts']['f362.config']['path'])
 f339=json.loads(F339.read_text());require(f339['status']=='PASS_OFFLINE_HWMON_OEM_ORACLE','F339 unqualified')
 require(sha(SOURCE/'topaz_temp_core.h')==f339['source_pins'][str(ROOT/'work/kernel-port/versions/f339-topaz-hwmon/topaz_temp_core.h')],'F339 core changed')
 fm=json.loads((F362/'manifest.json').read_text());require(sha(F362/'manifest.json')=='8e576d3d5f4676dcf5287d8dc640784a7756daf9af2a9ce77c585c1eb3300957','F362 manifest drift')
 rootfs=F362/fm['artifacts']['rootfs_squashfs']['file'];require(sha(rootfs)==fm['artifacts']['rootfs_squashfs']['sha256'],'F362 rootfs drift')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=Path('/workspace/OpenMitraStar-build/f363')/('f363-components-'+stamp);out.mkdir(parents=True,exist_ok=False)
 nodes=copy.deepcopy(parse(old_dtb));recovery=next(n for n in nodes if n['path']=='/soc/recovery@e0000000');reg=dict(recovery['props'])['reg'];require(len(reg)>=8 and struct.unpack('>II',reg[:8])==(0xe0000000,0x200),'unexpected recovery resource')
 recovery['props']=[(name,struct.pack('>II',0xe0000000,8)+value[8:] if name=='reg' else value) for name,value in recovery['props']]
 sensor_path='/soc/temperature-sensor@e0000108';require(not any(n['path']==sensor_path for n in nodes),'temperature node already exists')
 nodes.append({'name':'temperature-sensor@e0000108','path':sensor_path,'props':[('compatible',b'quantenna,topaz-internal-tempsens\0'),('reg',struct.pack('>II',0xe0000108,12)),('status',b'okay\0'),('openmitrastar,experimental-temperature-control',b'')]})
 dt=out/'f363.dtb';dt.write_bytes(serialize(nodes,old_dtb.read_bytes()));old=node_map(old_dtb);new=node_map(dt)
 delta=[(p,n) for p in set(old)|set(new) for n in set(old.get(p,{}))|set(new.get(p,{})) if old.get(p,{}).get(n)!=new.get(p,{}).get(n)]
 require(set(delta)=={('/soc/recovery@e0000000','reg'),*( (sensor_path,n) for n in dict(nodes[-1]['props']) )},'unrelated DT change')
 require(new['/soc/recovery@e0000000']['reg'][8:]==reg[8:],'GPIO/watchdog tail changed')
 require(reservations(dt.read_bytes())==reservations(old_dtb.read_bytes()),'reserved memory changed')
 overlaps=[]
 for p,props in new.items():
  if p==sensor_path or not p.startswith('/soc/') or p.count('/')!=2:continue
  data=props.get('reg',b'')
  if len(data)%8:continue
  for i in range(0,len(data),8):
   start,size=struct.unpack('>II',data[i:i+8])
   if start<0xe0000114 and start+size>0xe0000108:overlaps.append((p,hex(start),hex(size)))
 # IRQ/PCIe intentionally map shared SYSCTL without request_mem_region.
 # Their broad DT windows overlap, but their actual accesses do not touch
 # the sensor. Do not change those proven drivers merely to reshape a map.
 shared_maps={'/soc/interrupt-controller@e0000000':('drivers/irqchip/irq-qtn-topaz.c',{'TOPAZ_RESET_CAUSE','TOPAZ_LHOST_INT_EN','TOPAZ_LHOST_ORINT_EN','TOPAZ_INTR_INV0'},'irqc'),'/soc/pcie@cf000000':('drivers/pci/controller/pcie-qtn-topaz.c',{'TOPAZ_SYSCTL_CSR','TOPAZ_SYSCTL_PCIE_STAT'},'pcie')}
 shared_proofs={}
 import re
 for p,start,size in overlaps:
  require(p in shared_maps and start=='0xe0000000' and size=='0x200','unexpected shared SYSCTL overlap')
  relative,names,owner=shared_maps[p]
  observed=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',k['source']+'/'+relative],capture_output=True,text=True,timeout=20)
  require(not observed.returncode,'shared SYSCTL source missing')
  text=observed.stdout
  accessed=set(re.findall(owner+r'->sysctl\s*\+\s*(\w+)',text));require(accessed==names,'shared SYSCTL accesses changed')
  offsets={n:int(re.search(r'^#define\s+'+n+r'\s+(0x[0-9a-fA-F]+)',text,re.M)[1],16) for n in names}
  require(all(v+4<=0x108 or v>=0x114 for v in offsets.values()),'shared user accesses sensor registers')
  require('of_iomap(node, 0)' in text if owner=='irqc' else 'pcie->sysctl = devm_ioremap(dev, sysctl_res->start,' in text,'shared mapping ownership changed')
  (out/('ownership-'+owner+'.c')).write_bytes(text.encode())
  shared_proofs[p]={'source':k['source']+'/'+relative,'sha256':hashlib.sha256(text.encode()).hexdigest(),'offsets':offsets,'exclusive_resource_claim':False}
 (out/'base.config').write_bytes(old_cfg.read_bytes());(out/'base.dtb').write_bytes(old_dtb.read_bytes())
 shutil.copytree(SOURCE,out/'sensor-source');shutil.copytree(QBASE,out/'qdrv-baseline-source');shutil.copytree(QSRC,out/'qdrv-source')
 source_pins={str(p.relative_to(out)):sha(p) for directory in ('sensor-source','qdrv-baseline-source','qdrv-source') for p in (out/directory).rglob('*') if p.is_file()}
 dep_rows=[s for s in DEPS.read_text().splitlines() if s.split()[1]!='topaz_read_internal_temp_sens'];(out/'peer-dependencies.symvers').write_bytes(('\n'.join(dep_rows)+'\n').encode())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');qtn=linux(ROOT/'work/sources/Quantenna-GPL')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src={q(k['source'])}
kout="$out/kernel"
cp -a --reflink=auto {q(k['build_directory'])} "$kout"
"$src/scripts/config" --file "$kout/.config" --module HWMON
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" olddefconfig > "$out/config.log" 2>&1
cp "$out/f363.dtb" "$kout/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb"
SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f358-flash-arbitration KBUILD_BUILD_VERSION=358 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=/home/user/openmitrastar-build/f358-flash-arbitration-20260921T173956Z/a=/f358-output" -j4 vmlinux modules uImage.bin > "$out/kernel.log" 2>&1
cp "$kout/vmlinux" "$out/f363.vmlinux"
cp "$kout/.config" "$out/f363.config"
cp "$kout/Module.symvers" "$out/Module.symvers"
cp "$kout/arch/arc/boot/uImage.bin" "$out/f363.uncompressed.uImage"
cp "$kout/drivers/hwmon/hwmon.ko" "$out/hwmon.ko"
"${{tc}}objcopy" -O binary -R .note -R .note.gnu.build-id -R .comment -S "$out/f363.vmlinux" "$out/f363.raw.bin"
unsquashfs -cat {q(linux(rootfs))} lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko > "$out/installed-f362-qdrv.ko"
for lane in a b; do
 mkdir "$out/$lane"
 cp -a "$out/sensor-source" "$out/$lane/sensor"
 SOURCE_DATE_EPOCH=1790006400 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/sensor" KCFLAGS="-ffile-prefix-map=$out/$lane/sensor=/f363-sensor" -j4 modules > "$out/sensor-$lane.log" 2>&1
 cat "$out/peer-dependencies.symvers" "$out/$lane/sensor/Module.symvers" > "$out/$lane/dependencies.symvers"
 for kind in baseline temperature; do
  if test "$kind" = baseline; then donor="$out/qdrv-baseline-source"; else donor="$out/qdrv-source"; fi
  cp -a "$donor" "$out/$lane/$kind"
  SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/$kind" QTN_GPL={q(qtn)} KBUILD_EXTRA_SYMBOLS="$out/$lane/dependencies.symvers" KCFLAGS="-ffile-prefix-map=$out/$lane/$kind=/f363-qdrv" -j4 modules > "$out/qdrv-$kind-$lane.log" 2>&1
 done
done
cmp "$out/a/sensor/temp_sens.ko" "$out/b/sensor/temp_sens.ko"
cmp "$out/a/baseline/qdrv/qdrv.ko" "$out/b/baseline/qdrv/qdrv.ko"
cmp "$out/a/temperature/qdrv/qdrv.ko" "$out/b/temperature/qdrv/qdrv.ko"
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware':False}),flush=True)
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr);errors=[];comparisons={}
 if run.returncode:errors.append('component build failed')
 else:
  cfg=config_values(out/'f363.config');base_cfg=config_values(old_cfg);cfg_diff={n:(base_cfg.get(n),cfg.get(n)) for n in set(base_cfg)|set(cfg) if base_cfg.get(n)!=cfg.get(n)}
  require(cfg_diff=={'CONFIG_HWMON':(None,'m')},'configuration drift '+str(cfg_diff))
  embedded,address=extract_embedded(out/'f363.vmlinux');require(node_map(out/'kernel/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb')==new,'compiled DT drift');require(embedded==(out/'kernel/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb').read_bytes(),'embedded DT mismatch')
  funcs=[qc.normalized_functions(p) for p in (out/'installed-f362-qdrv.ko',out/'a/baseline/qdrv/qdrv.ko',out/'a/temperature/qdrv/qdrv.ko')]
  for label,left,right,allowed in [('baseline_abi',funcs[0],funcs[1],{'qdrv_wps_button_read'}),('temperature_only',funcs[1],funcs[2],{'qdrv_get_internal_temp'})]:
   changed=sorted(n for n in set(left)|set(right) if left.get(n)!=right.get(n));comparisons[label]={'functions':len(right),'changed':changed}
   unexpected=set(changed)-allowed
   if label=='temperature_only' and unexpected=={'qdrv_wlan_exit'}:
    comparisons[label]['warning_line_metadata']=warn_line_metadata(out/'a/baseline/qdrv/qdrv.ko',out/'a/temperature/qdrv/qdrv.ko',out/'a/baseline/qdrv/qdrv_wlan.c',out/'a/temperature/qdrv/qdrv_wlan.c');unexpected.clear()
   require(not unexpected,'unrelated qdrv differences '+label+str(changed))
  profiles=[qc.inspect(p) for p in (out/'installed-f362-qdrv.ko',out/'a/temperature/qdrv/qdrv.ko')];require(profiles[0]['parameters']==profiles[1]['parameters'] and profiles[0]['functions']==profiles[1]['functions'],'qdrv profile regression')
  exports={line.split()[1] for line in (out/'Module.symvers').read_text().splitlines()};old_exports={line.split()[1] for line in Path(k['artifacts']['Module.symvers']['path']).read_text().splitlines()};require(old_exports<=exports,'old kernel exports removed')
  for n,digest in source_pins.items():require(sha(out/n)==digest,'source changed during build')
 result={'schema':'openmitrastar.f363-temperature-components/v1','status':'PASS_OFFLINE_TEMPERATURE_INTEGRATION' if not errors else 'FAIL','errors':errors,'f362_kernel_proof':item(KPROOF),'f362_manifest':item(F362/'manifest.json'),'f339_qualification':item(F339),'f339_core_byte_identical':True,'hardware_actions':False,'default_sensor_mmio':False,'clock_or_measurement_qualified':False,'dt_delta':delta,'recovery_reg_tail_preserved':True,'shared_sysctl_maps_reviewed':shared_proofs,'exclusive_resource_conflicts':[],'qdrv_comparisons':comparisons,'kernel_build_identity':'#358 @1790006400','kernel_build_directory':str(out/'kernel'),'kernel_build_directory_linux':linux(out/'kernel'),'kernel_source':k['source'],'kernel_source_linux':k['source'],'source_pins':source_pins,'artifacts':{n:item(out/n) for n in ('f363.vmlinux','f363.raw.bin','f363.uncompressed.uImage','f363.config','f363.dtb','Module.symvers','hwmon.ko','a/sensor/temp_sens.ko','a/temperature/qdrv/qdrv.ko') if (out/n).exists()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':result['status'],'errors':errors,'comparisons':comparisons},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
