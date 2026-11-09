"""New immutable F372 packaging/metadata addendum; read-only firmware inputs."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
from elftools.elf.elffile import ELFFile
from io import BytesIO
from build_f367r8_mode_image import linux
from f372_rootfs_worker import QDRV,START,CONTRACT
from build_f372_observation_image import PARAMETERS

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
FIRMWARE=DEVICE/'firmware/f372-f371-auc-tqe-observation-device-bound'
QUAL=ROOT/'outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/qualification-20261021T222300Z'

def sha(data): return hashlib.sha256(data).hexdigest()
def extract(image,name):
    return subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','-e','unsquashfs','-cat',linux(image),name],check=True,capture_output=True).stdout

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    assert not a.output.exists()
    manifest_path=FIRMWARE/'manifest.json'; original_manifest=manifest_path.read_bytes()
    assert sha(original_manifest)=='e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5'
    m=json.loads(original_manifest); image=FIRMWARE/m['artifacts']['webformat']['file']; rootfs=FIRMWARE/m['artifacts']['rootfs_squashfs']['file']
    assert sha(image.read_bytes())=='e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9' and image.stat().st_size==5382144
    assert sha(rootfs.read_bytes())==m['artifacts']['rootfs_squashfs']['sha256']
    params_path=QUAL/'module-parameters.json'; params=json.loads(params_path.read_text()); proof_path=QUAL/'result.json'; proof=json.loads(proof_path.read_text())
    assert proof['status']=='PASS_OFFLINE_COMPLETE_MODULE' and proof['new_parameters_0444']==sorted(PARAMETERS)
    for name in PARAMETERS: assert params['permissions'][name]==0o444 and name+':uint' in params['metadata']['parmtype']
    qdrv=extract(rootfs,QDRV); assert sha(qdrv)==proof['module']['sha256']=='d5e1f58303eaaa02123e0cf6352bd40c40df3027be300d2a1143b07f54a05dae' and len(qdrv)==686144
    elf=ELFFile(BytesIO(qdrv)); actual={}
    for value in elf.get_section_by_name('.modinfo').data().split(b'\0'):
        if b'=' in value:
            k,v=value.decode().split('=',1); actual.setdefault(k,[]).append(v)
    assert {k:sorted(v) for k,v in actual.items()}=={k:sorted(v) for k,v in params['metadata'].items()}
    starter=extract(rootfs,START); contract=extract(rootfs,CONTRACT); catalog=extract(rootfs,'usr/share/openmitrastar/radio5g/artifacts.sha256')
    digest=sha(qdrv).encode(); assert starter.count(digest)==contract.count(digest)==1
    assert b'PATH=/usr/libexec/openmitrastar/f371-compat:/sbin:/bin:/usr/sbin:/usr/bin\n' in starter
    for name,data in ((QDRV,qdrv),(START,starter),(CONTRACT,contract)):
        assert sha(data)==m['runtime_bindings']['/'+name]
        assert (sha(data)+'  /'+name+'\n').encode() in catalog
    a.output.mkdir(parents=True,exist_ok=False)
    rows={str(path.resolve()):sha(path.read_bytes()) for path in (Path(__file__),manifest_path,image,rootfs,params_path,proof_path)}
    result=dict(schema='openmitrastar.f372-packaging-addendum/v1',status='PASS_EXACT_PACKAGED_MODULE_AND_METADATA',generated_at_utc=datetime.now(timezone.utc).isoformat(),source_pins=rows,parameters=sorted(PARAMETERS),permissions='0444',packaged_module_sha256=sha(qdrv),packaged_module_bytes=len(qdrv),module_metadata_matches_qualification=True,starter_and_driver_contract_exact_hash=True,catalog_runtime_bindings_exact=True,firmware_inputs_unchanged=True,hardware_accessed=False,physical_gates='UNRUN')
    assert manifest_path.read_bytes()==original_manifest
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))

if __name__=='__main__': main()
