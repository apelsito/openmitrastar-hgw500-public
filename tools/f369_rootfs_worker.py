"""Offline F369 packaging delta over the immutable F367r9 rootfs."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog, ARTIFACTS_PATH

VERSION = 'lyoko-foundation-6.12.0-f369-store38-quarantine-device'
QDRV = 'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
NATIVE = 'usr/libexec/openmitrastar/om-radio5-start-f367-native'
CONTRACT = 'usr/share/openmitrastar/radio5g/driver-contract.env'
PROFILE = 'usr/share/openmitrastar/dfs-f367/profile.json'
RELEASE = 'etc/openmitrastar/release'
STORAGE = 'usr/share/openmitrastar/storage/artifacts.sha256'
ALLOWED = {QDRV, NATIVE, CONTRACT, PROFILE, RELEASE, STORAGE, ARTIFACTS_PATH}

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser()
    for name in ('source', 'qdrv', 'image', 'result'): p.add_argument('--'+name, type=Path, required=True)
    for name in ('source-sha', 'qdrv-sha', 'build-id'): p.add_argument('--'+name, required=True)
    p.add_argument('--epoch', type=int, required=True)
    a = p.parse_args()
    assert os.name == 'posix' and os.geteuid() == 0 and not a.image.exists() and not a.result.exists()
    for name in ('source', 'qdrv'): assert sha(getattr(a,name).read_bytes()) == getattr(a,name+'_sha')
    with tempfile.TemporaryDirectory(prefix='f369-rootfs-', dir='/tmp') as temporary:
        root = Path(temporary)/'root'; verified = Path(temporary)/'verified'; packed = Path(temporary)/'image.squashfs'
        subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
        before = web.inventory(root); verify_artifact_catalog(root)
        assert before[QDRV]['sha256'] == 'f5fc5d07d996c3d30ef5401d5306de6e783dd2845c170953f84217abfd277499'
        old_hash = before[QDRV]['sha256'].encode(); new_hash = a.qdrv_sha.encode()
        native_original = (root/NATIVE).read_bytes(); contract_original = (root/CONTRACT).read_bytes()
        assert native_original.startswith(b'#!') and native_original.count(old_hash) == contract_original.count(old_hash) == 1
        native = native_original.replace(old_hash,new_hash); contract = contract_original.replace(old_hash,new_hash)
        assert native.replace(new_hash,old_hash) == native_original and contract.replace(new_hash,old_hash) == contract_original
        release = (root/RELEASE).read_text().splitlines()
        assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.11.8-f367r9-transition-observation-device' in release
        release = '\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=') else line for line in release)+'\n'
        original_profile = json.loads((root/PROFILE).read_text()); assert original_profile['runtime_revision'] == 'F367r9'
        profile = dict(original_profile)
        profile.update(runtime_revision='F369',qdrv_source_revision='F368r2',diagnostic_only=True,product_automatic_5g_start=False,store38_ack_normalized=True,store38_published_timeout_descriptor_quarantined=True,store38_descriptor_reclaim='reboot-only',functional_deadlines_unchanged=True)
        assert all(profile[key] == value for key,value in original_profile.items() if key != 'runtime_revision')
        replacements = {QDRV:a.qdrv.read_bytes(),NATIVE:native,CONTRACT:contract,RELEASE:release.encode(),PROFILE:(json.dumps(profile,sort_keys=True,indent=2)+'\n').encode()}
        changes = {name:(data,before[name]['mode']) for name,data in replacements.items()}
        for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256',STORAGE,ARTIFACTS_PATH):
            original = (root/catalog).read_bytes(); rows=[]
            for line in original.decode().splitlines():
                digest,path=line.split('  ',1); name=path.lstrip('/')
                rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
            data=('\n'.join(rows)+'\n').encode()
            if data != original: changes[catalog]=(data,before[catalog]['mode'])
        assert set(changes) == ALLOWED
        expected = {name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
        web.validate_delta(before,web.inventory(root),expected); verify_artifact_catalog(root)
        subprocess.run(['sh','-n',str(root/NATIVE)],check=True)
        subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
        after=web.inventory(verified); checks=web.validate_delta(before,after,expected); verify_artifact_catalog(verified)
        assert all(before[name] == after[name] for name in before if name not in changes)
        for catalog in (STORAGE,'usr/share/openmitrastar/temperature/artifacts.sha256'):
            for line in (verified/catalog).read_text().splitlines():
                digest,path=line.split('  ',1); assert sha((verified/path.lstrip('/')).read_bytes()) == digest
        shutil.copyfile(packed,a.image)
        a.result.write_text(json.dumps(dict(status='PASS_F369_STORE38_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),native_profile=profile,native_hash_pins_only=True,all_other_entries_unchanged=True,hardware_actions=False),sort_keys=True)+'\n')

if __name__ == '__main__': main()
