"""Offline F371 normal-start compatibility delta on immutable F365."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog, ARTIFACTS_PATH

VERSION = 'lyoko-foundation-6.12.2-f371-normal-start-compat-device'
START = 'usr/sbin/om-radio5-start'
RELEASE = 'etc/openmitrastar/release'
STORAGE = 'usr/share/openmitrastar/storage/artifacts.sha256'
COMPAT = 'usr/libexec/openmitrastar/f371-compat'
HEAD = COMPAT+'/head'
TAIL = COMPAT+'/tail'
ALLOWED = {START, RELEASE, HEAD, TAIL, ARTIFACTS_PATH, STORAGE}
QDRV = 'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
WLAN = 'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/wlan.ko'
START_SHA = 'ff06739f9c05e33904a3248fe858d0e9ec236f2a49fe31b7816ca4afda5468f5'
ANCHOR = b'PATH=/sbin:/bin:/usr/sbin:/usr/bin\n'
NEW_PATH = ('PATH=/'+COMPAT+':/sbin:/bin:/usr/sbin:/usr/bin\n').encode()

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','head','tail','image','result'): p.add_argument('--'+name,type=Path,required=True)
    for name in ('source-sha','head-sha','tail-sha','build-id'): p.add_argument('--'+name,required=True)
    p.add_argument('--epoch',type=int,required=True); a=p.parse_args()
    assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
    for name in ('source','head','tail'): assert sha(getattr(a,name).read_bytes())==getattr(a,name+'_sha')
    with tempfile.TemporaryDirectory(prefix='f371-rootfs-',dir='/tmp') as directory:
        root=Path(directory)/'root'; verified=Path(directory)/'verified'; packed=Path(directory)/'image.squashfs'
        subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
        before=web.inventory(root); verify_artifact_catalog(root)
        starter=(root/START).read_bytes()
        assert sha(starter)==START_SHA and starter.count(ANCHOR)==1
        changed_starter=starter.replace(ANCHOR,NEW_PATH,1)
        assert changed_starter.replace(NEW_PATH,ANCHOR,1)==starter
        assert before[QDRV]['sha256']=='cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01'
        assert before[WLAN]['sha256']=='f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f'
        assert (root/'etc/openmitrastar/features/q3-radio5-autostart').read_bytes()==b'Q3_RADIO5_AUTOSTART=1\n'
        assert b'exec /usr/sbin/om-radio5-start' in (root/'etc/init.d/S55-radio5-ap').read_bytes()
        assert HEAD not in before and TAIL not in before and COMPAT not in before
        release=(root/RELEASE).read_text().splitlines()
        assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.9.13-f365-temperature-data-device' in release
        release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=') else line for line in release)+'\n'
        changes={START:(changed_starter,before[START]['mode']),RELEASE:(release.encode(),before[RELEASE]['mode']),HEAD:(a.head.read_bytes(),0o755),TAIL:(a.tail.read_bytes(),0o755)}
        for catalog in (ARTIFACTS_PATH,'usr/share/openmitrastar/temperature/artifacts.sha256',STORAGE):
            original=(root/catalog).read_bytes(); rows=[]
            for line in original.decode().splitlines():
                digest,path=line.split('  ',1); name=path.lstrip('/')
                rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
            if catalog==ARTIFACTS_PATH:
                rows.extend(sha(changes[name][0])+'  /'+name for name in (HEAD,TAIL))
            changed=('\n'.join(rows)+'\n').encode()
            if changed!=original: changes[catalog]=(changed,before[catalog]['mode'])
        assert set(changes)==ALLOWED
        expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
        web.validate_delta(before,web.inventory(root),expected); verify_artifact_catalog(root)
        for name in (START,HEAD,TAIL): subprocess.run(['sh','-n',str(root/name)],check=True)
        # Exercise the exact shipped awk helper bodies; ash shebang is preserved.
        sample=b'one\ntwo\nthree\nfour\nfive\n'
        cases=[]
        for name,n,wanted in ((HEAD,'1',b'one\n'),(HEAD,'2',b'one\ntwo\n'),(TAIL,'2',b'four\nfive\n'),(TAIL,'5',sample),(TAIL,'9',sample)):
            test=subprocess.run(['sh',str(root/name),'-n',n],input=sample,capture_output=True)
            assert test.returncode==0 and test.stdout==wanted and test.stderr==b''
            cases.append(name.rsplit('/',1)[1]+'-'+n)
        subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
        after=web.inventory(verified); checks=web.validate_delta(before,after,expected); verify_artifact_catalog(verified)
        assert all(before[name]==after[name] for name in before if name not in changes)
        for catalog in (STORAGE,'usr/share/openmitrastar/temperature/artifacts.sha256'):
            for line in (verified/catalog).read_text().splitlines():
                digest,path=line.split('  ',1); assert sha((verified/path.lstrip('/')).read_bytes())==digest
        preserved=('etc/init.d/S55-radio5-ap','etc/openmitrastar/features/q3-radio5-autostart',QDRV,WLAN,'etc/init.d/S50-radio-ap','etc/init.d/S53-qtn-calibration','etc/init.d/S54-qtn-mac','etc/init.d/S56-f352-ethernet','etc/init.d/S90-ready','usr/share/openmitrastar/radio5g/driver-contract.env')
        assert all(before[name]==after[name] for name in preserved)
        shutil.copyfile(packed,a.image)
        a.result.write_text(json.dumps(dict(status='PASS_F371_NORMAL_START_COMPAT_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),helper_cases=cases,starter_only_path_delta=True,all_other_entries_unchanged=True,init_autostart_gate_unchanged=True,original_qdrv_wlan_2g_unchanged=True,hardware_actions=False),sort_keys=True)+'\n')

if __name__=='__main__': main()
