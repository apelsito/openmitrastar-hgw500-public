"""Build one exact-donor F365 RAM radio package for a freshly quiescent R9.

File-only builder: never accesses the router, UART or network.
"""
from pathlib import Path
import hashlib, json, subprocess, tarfile

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path(r'/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware')
OUT=ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3'
REMOTE='/run/openmitrastar/f365-ram-20261021-r3'
BOOT='5f513265-a294-4366-9567-e1d8af704b6b'
MODULE='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/'
DONOR=PRIVATE/'f365-f364r3-temperature-data-device-bound'
PEER=PRIVATE/'f367r9-f365-transition-observation-device-bound'
BASE='openmitrastar-linux510-f365-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
def sha(data): return hashlib.sha256(data).hexdigest()
def extract(name):
    image=DONOR/(BASE+'.rootfs.squashfs')
    linux='/mnt/c/'+image.as_posix()[3:]
    return subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','-e','unsquashfs','-cat',linux,name],check=True,capture_output=True).stdout
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists(), str(path)
    path.write_bytes(data)
def main():
    assert not OUT.exists(), 'immutable output already exists'
    a=json.loads((DONOR/'rootfs-inventory.json').read_text())['after']
    b=json.loads((PEER/'rootfs-inventory.json').read_text())['after']
    am=json.loads((DONOR/'manifest.json').read_text()); bm=json.loads((PEER/'manifest.json').read_text())
    for key in ('kernel_lzma','config','dtb'): assert am['artifacts'][key]['sha256']==bm['artifacts'][key]['sha256']
    image=DONOR/(BASE+'.rootfs.squashfs')
    assert sha(image.read_bytes())==am['artifacts']['rootfs_squashfs']['sha256']
    sources={'donor_rootfs':dict(path=str(image),sha256=sha(image.read_bytes()))}
    mapping={MODULE+'qdrv.ko':'modules/qdrv.ko',MODULE+'wlan.ko':'modules/wlan.ko','usr/sbin/om-radio5-start':'donor/om-radio5-start','usr/sbin/om-radio5-stop':'bin/om-radio5-stop','usr/share/openmitrastar/radio5g/driver-contract.env':'share/driver-contract.env'}
    payload=OUT/'payload'
    for original,dest in mapping.items():
        data=extract(original); assert sha(data)==a[original]['sha256'] and len(data)==a[original]['bytes']
        write(payload/dest,data); sources[original]=dict(sha256=sha(data),bytes=len(data),package=dest)
    donor=(payload/'donor/om-radio5-start').read_bytes()
    anchor=b'PATH=/sbin:/bin:/usr/sbin:/usr/bin\n'
    assert donor.count(anchor)==1
    starter=donor.replace(anchor,('PATH='+REMOTE+'/bin:/sbin:/bin:/usr/sbin:/usr/bin\n').encode(),1)
    assert starter.replace(('PATH='+REMOTE+'/bin:/sbin:/bin:/usr/sbin:/usr/bin\n').encode(),anchor,1)==donor
    write(payload/'bin/om-radio5-start',starter)
    head=b'''#!/bin/ash
set -eu
n=10
if [ "${1:-}" = -n ]; then n=$2; shift 2; fi
case "$n" in ''|*[!0-9]*) exit 2;; esac
exec awk -v n="$n" 'NR<=n {print} NR==n {exit}' "$@"
'''
    tail=b'''#!/bin/ash
set -eu
n=10
if [ "${1:-}" = -n ]; then n=$2; shift 2; fi
case "$n" in ''|*[!0-9]*) exit 2;; esac
exec awk -v n="$n" '{if(n>0) rows[NR%n]=$0} END {first=NR-n+1; if(first<1) first=1; for(i=first;i<=NR;i++) if(n>0) print rows[i%n]}' "$@"
'''
    write(payload/'bin/head',head); write(payload/'bin/tail',tail)
    catalog=extract('usr/share/openmitrastar/radio5g/artifacts.sha256').decode()
    assert sha(catalog.encode())==a['usr/share/openmitrastar/radio5g/artifacts.sha256']['sha256']
    replacements={MODULE+'qdrv.ko':REMOTE+'/modules/qdrv.ko',MODULE+'wlan.ko':REMOTE+'/modules/wlan.ko','usr/sbin/om-radio5-start':REMOTE+'/bin/om-radio5-start','usr/sbin/om-radio5-stop':REMOTE+'/bin/om-radio5-stop','usr/share/openmitrastar/radio5g/driver-contract.env':REMOTE+'/share/driver-contract.env'}
    rows=[]; links={}
    for line in catalog.splitlines():
        digest,path=line.split('  ',1); name=path.lstrip('/')
        assert digest==a[name]['sha256']
        if name in replacements:
            relocated=replacements[name]; relative=relocated[len(REMOTE)+1:]
            rows.append(sha((payload/relative).read_bytes())+'  '+relocated)
        else:
            assert a[name]==b[name], 'dependency drift '+name
            rows.append(line)
            if name.startswith(MODULE): links['modules/'+name[len(MODULE):]]=path
    for p in ('bin/head','bin/tail'):
        rows.append(sha((payload/p).read_bytes())+'  '+REMOTE+'/'+p)
    write(payload/'share/artifacts.sha256',('\n'.join(rows)+'\n').encode())
    guard=(ROOT/'tools/f365_ram_remote.sh').read_bytes()
    write(payload/'bin/guard',guard)
    checks=[]
    for p in [*list((payload/'bin').iterdir()),payload/'donor/om-radio5-start']:
        linux='/mnt/c/'+p.as_posix()[3:]
        subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','-e','sh','-n',linux],check=True)
        checks.append('shell_syntax:'+p.name)
    manifest=dict(schema='openmitrastar.f365-ram-package/v1',status='PASS_OFFLINE_RAM_PACKAGE',remote=REMOTE,boot_id=BOOT,target='mitrastar,hgw-500bna-qcv2',version='f365-ram-20261021-r3',source_pins=sources,files={},symlinks=links,starter_single_delta='PATH adds package-local head/tail compatibility shims only',radio=dict(channel=36,bandwidth=80,security='preserved secure WPA2 baseline',native_radar=False,watchdog_arm=False,dfs_campaign=False),hardware_actions=False,module_unload_supported=False,rollback='RF closed, wifi0 down/detached, hostapd down; qdrv and dependencies remain loaded',host_child_lease_required=True,parent_quarantine_retired=False,checks=checks)
    for p in payload.rglob('*'):
        if p.is_file(): manifest['files'][p.relative_to(payload).as_posix()]=dict(sha256=sha(p.read_bytes()),bytes=p.stat().st_size)
    write(OUT/'manifest.json',(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
    plan=dict(schema='openmitrastar.f365-ram-activation-plan/v1',status='OFFLINE_READY_HOST_CHILD_LEASE_REQUIRED',manifest_sha256=sha((OUT/'manifest.json').read_bytes()),remote=REMOTE,boot_id=BOOT,scope='single nonDFS startup in RAM; no flash/reboot/unload',upload='Use pinned SSH transport to copy package.tar to '+REMOTE+'-package.tar; root alone holds fresh F319 child hardware lease',unpack='umask 077; mkdir '+REMOTE+'; tar -xf '+REMOTE+'-package.tar -C '+REMOTE,preflight='/bin/ash '+REMOTE+'/bin/guard preflight',activate='OM_F365_RAM_AUTH_BOOT='+BOOT+' /bin/ash '+REMOTE+'/bin/guard activate',inspect='/bin/ash '+REMOTE+'/bin/guard inspect',stop='/bin/ash '+REMOTE+'/bin/guard stop',qualification=dict(max_starter_seconds=115,outer_deadline_seconds=240,keep_running='Only after root observes nonDFS36 RF and management PASS; create RAM keep-running before240seconds',repeat_activation=False),authority_gap='Root must create/bind child lease with original parent quarantine unchanged before upload/activation',physical_status='NOT_RUN')
    write(OUT/'plan.json',(json.dumps(plan,indent=2,sort_keys=True)+'\n').encode())
    with tarfile.open(OUT/'package.tar','w',format=tarfile.USTAR_FORMAT) as tf:
        for p in sorted(payload.rglob('*')):
            if p.is_file():
                ti=tf.gettarinfo(str(p),p.relative_to(payload).as_posix()); ti.uid=ti.gid=0; ti.uname=ti.gname=''; ti.mtime=0
                ti.mode=0o700 if p.parent.name=='bin' else 0o600
                with p.open('rb') as f: tf.addfile(ti,f)
        for rel,target in sorted(links.items()):
            ti=tarfile.TarInfo(rel);ti.type=tarfile.SYMTYPE;ti.linkname=target;ti.mode=0o777;ti.mtime=0;tf.addfile(ti)
    write(OUT/'SHA256SUMS',(''.join(sha((OUT/name).read_bytes())+'  '+name+'\n' for name in ('manifest.json','plan.json','package.tar'))).encode())
    print(json.dumps(dict(status=manifest['status'],package=str(OUT/'package.tar'),bytes=(OUT/'package.tar').stat().st_size,sha256=sha((OUT/'package.tar').read_bytes()),hardware_actions=False)))
if __name__=='__main__': main()
