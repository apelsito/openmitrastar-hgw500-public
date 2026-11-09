"""Focused file-only package, shims and watchdog parser verification."""
from pathlib import Path
import hashlib,json,subprocess,tarfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run_sh(script,data=b''):
    return subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','-e','sh','-c',script],input=data,capture_output=True)
def main():
    manifest=json.loads((OUT/'manifest.json').read_text()); checks=[]
    with tarfile.open(OUT/'package.tar') as archive:
        members={p.name:p for p in archive.getmembers()}
        assert set(members)==set(manifest['files'])|set(manifest['symlinks'])
        for path,row in manifest['files'].items():
            data=archive.extractfile(path).read()
            assert hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']
        for path,target in manifest['symlinks'].items():assert members[path].issym() and members[path].linkname==target
        checks.append('archive-all-members-hashes-and-symlinks')
    linux='/mnt/c/'+(OUT/'payload/bin').as_posix()[3:]
    for name,count,expected in [('head',1,b'a\n'),('head',2,b'a\nb\n'),('tail',2,b'b\nc\n'),('tail',5,b'a\nb\nc\n')]:
        r=run_sh('sh '+linux+'/'+name+' -n '+str(count),b'a\nb\nc\n')
        assert r.returncode==0 and r.stdout==expected,(name,count,r.returncode,r.stdout,r.stderr)
        checks.append(name+'-'+str(count))
    guard=(OUT/'payload/bin/guard').read_text()
    parser=guard.split('/usr/sbin/om-watchdog-supervisor --inspect | awk ',1)[1].split('\n}',1)[0]
    for control,expected in [('00000000',0),('00000001',1),('ffffffff',1)]:
        data=json.dumps(dict(event='inspect',device_opened=0,control_valid=1,control=control)).encode()
        r=run_sh('awk '+parser,data)
        assert r.returncode==expected,(control,r.returncode,r.stderr)
        checks.append('watchdog-parser-'+control)
    source=(OUT/'payload/donor/om-radio5-start').read_bytes(); actual=(OUT/'payload/bin/om-radio5-start').read_bytes()
    old=b'PATH=/sbin:/bin:/usr/sbin:/usr/bin\n';new=('PATH='+manifest['remote']+'/bin:/sbin:/bin:/usr/sbin:/usr/bin\n').encode()
    assert actual.replace(new,old,1)==source;checks.append('starter-only-PATH-delta')
    for p in (OUT/'payload/bin').iterdir():
        r=run_sh('sh -n /mnt/c/'+p.as_posix()[3:]);assert r.returncode==0,p
    checks.append('all-six-runtime-shells-syntax')
    # mknod and held FIFO writer behavior in an isolated Linux temporary directory.
    fifo="set -eu; d=$(mktemp -d /tmp/f365-ram-verify-XXXXXX); trap 'rm -rf \"$d\"' EXIT; mknod \"$d/p\" p; awk '{print;fflush()}' < \"$d/p\" > \"$d/result\" & r=$!; exec 7>\"$d/p\"; printf 'one\\n' > \"$d/p\"; printf 'two\\n' > \"$d/p\"; exec 7>&-; wait \"$r\"; cat \"$d/result\""
    r=run_sh(fifo);assert r.returncode==0 and r.stdout==b'one\ntwo\n',(r.returncode,r.stdout,r.stderr)
    checks.append('mknod-FIFO-held-writer-two-events')
    result=dict(status='PASS_F365_RAM_OFFLINE_FOCUSED_VERIFICATION',hardware_actions=False,physical_activation='NOT_RUN',package_sha256=sha(OUT/'package.tar'),manifest_sha256=sha(OUT/'manifest.json'),plan_sha256=sha(OUT/'plan.json'),checks=checks,source_pins={str(Path(__file__).resolve()):sha(Path(__file__)),str(ROOT/'tools/f365_ram_build.py'):sha(ROOT/'tools/f365_ram_build.py'),str(ROOT/'tools/f365_ram_remote.sh'):sha(ROOT/'tools/f365_ram_remote.sh')})
    dest=OUT/'verification.json';assert not dest.exists();dest.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(status=result['status'],checks=len(checks),path=str(dest),sha256=sha(dest))))
if __name__=='__main__':main()
