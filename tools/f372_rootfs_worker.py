"""Offline F372 observation QDRV packaging on immutable F371 compatibility."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog, ARTIFACTS_PATH
from f371_rootfs_worker import START,HEAD,TAIL,QDRV,WLAN,RELEASE,STORAGE

VERSION='lyoko-foundation-6.12.3-f372-auc-tqe-observation-device'
CONTRACT='usr/share/openmitrastar/radio5g/driver-contract.env'
ALLOWED={QDRV,START,CONTRACT,RELEASE,ARTIFACTS_PATH,STORAGE}
PARENT_QDRV='cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01'

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','qdrv','image','result'): p.add_argument('--'+name,type=Path,required=True)
    for name in ('source-sha','qdrv-sha','build-id'): p.add_argument('--'+name,required=True)
    p.add_argument('--epoch',type=int,required=True); a=p.parse_args()
    assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
    for name in ('source','qdrv'): assert sha(getattr(a,name).read_bytes())==getattr(a,name+'_sha')
    with tempfile.TemporaryDirectory(prefix='f372-rootfs-',dir='/tmp') as directory:
        root=Path(directory)/'root'; verified=Path(directory)/'verified'; packed=Path(directory)/'image.squashfs'
        subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
        before=web.inventory(root); verify_artifact_catalog(root)
        assert before[QDRV]['sha256']==PARENT_QDRV
        contract=(root/CONTRACT).read_bytes(); old=PARENT_QDRV.encode(); new=a.qdrv_sha.encode()
        assert contract.count(old)==1
        changed_contract=contract.replace(old,new,1); assert changed_contract.replace(new,old,1)==contract
        # F365's beacon-lifetime feature selects a literal QDRV hash after loading contract.
        starter=(root/START).read_bytes(); assert starter.count(old)==1
        changed_starter=starter.replace(old,new,1)
        assert changed_starter.replace(new,old,1)==starter
        release=(root/RELEASE).read_text().splitlines()
        assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.12.2-f371-normal-start-compat-device' in release
        release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=') else line for line in release)+'\n'
        changes={QDRV:(a.qdrv.read_bytes(),before[QDRV]['mode']),START:(changed_starter,before[START]['mode']),CONTRACT:(changed_contract,before[CONTRACT]['mode']),RELEASE:(release.encode(),before[RELEASE]['mode'])}
        for catalog in (ARTIFACTS_PATH,'usr/share/openmitrastar/temperature/artifacts.sha256',STORAGE):
            original=(root/catalog).read_bytes(); rows=[]
            for line in original.decode().splitlines():
                digest,path=line.split('  ',1); name=path.lstrip('/')
                rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
            changed=('\n'.join(rows)+'\n').encode()
            if changed!=original: changes[catalog]=(changed,before[catalog]['mode'])
        assert set(changes)==ALLOWED
        expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
        web.validate_delta(before,web.inventory(root),expected); verify_artifact_catalog(root)
        subprocess.run(['sh','-n',str(root/START)],check=True)
        subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
        after=web.inventory(verified); checks=web.validate_delta(before,after,expected); verify_artifact_catalog(verified)
        assert all(before[name]==after[name] for name in before if name not in changes)
        for catalog in (STORAGE,'usr/share/openmitrastar/temperature/artifacts.sha256'):
            for line in (verified/catalog).read_text().splitlines():
                digest,path=line.split('  ',1); assert sha((verified/path.lstrip('/')).read_bytes())==digest
        for name in (HEAD,TAIL,WLAN,'etc/init.d/S55-radio5-ap','etc/openmitrastar/features/q3-radio5-autostart','etc/init.d/S50-radio-ap','etc/init.d/S53-qtn-calibration','etc/init.d/S54-qtn-mac','etc/init.d/S56-f352-ethernet','etc/init.d/S90-ready'): assert before[name]==after[name]
        shutil.copyfile(packed,a.image)
        a.result.write_text(json.dumps(dict(status='PASS_F372_OBSERVATION_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),driver_contract_and_starter_hash_only=True,all_other_entries_unchanged=True,normal_starter_logic_and_compatibility_unchanged=True,hardware_actions=False),sort_keys=True)+'\n')

if __name__=='__main__': main()
