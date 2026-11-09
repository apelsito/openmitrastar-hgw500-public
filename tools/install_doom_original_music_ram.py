"""Pinned reversible music update in RAM, with exact HTTP verification."""
from datetime import datetime, timezone
import hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KNOWN=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
CANDIDATE=ROOT/'outputs/doom/music-opl-qualified-20261022-r3-sourcepatch'
HELPER=ROOT/'outputs/doom/music-mount-20261022T093142135742Z/hgw-doom-ram-mount-a'
H='bf3a34e045de005aca272a864a8f5accc68ee6234779ea6f067eeadeadb1d2ca'
W='eb47045e861708f4263f994610ed2e58ab63838aff738e3577cca9b68797c20e'
I='5c8c0c9949161f0d5af4d020c6a8f4b6add20f4548bfe4abf5dac18eaa0efacc'
OLD_W='6366f83a58fe8596ce742a66dbf86871d315862c89c11e65b54935be03c7e6c4'
OLD_I='f05c849f945e56f4250a7800e627a732e9711746465c8359d5cfeb270d5baa33'
REMOTE='/tmp/openmitrastar-doom-music-20261022-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert sha(HELPER)==H and sha(CANDIDATE/'chocolate-doom.wasm')==W and sha(CANDIDATE/'index.html')==I
    out=ROOT/'outputs/doom'/('music-install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(exist_ok=False)
    argv=[str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),'-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49',
      '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes',
      '-o','UserKnownHostsFile='+str(KNOWN),'-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-o','LogLevel=ERROR','root@192.168.1.90']
    guard="test \"$(cat /proc/sys/kernel/random/boot_id)\" = '5f513265-a294-4366-9567-e1d8af704b6b' && "
    events=[];bound=False
    def run(name,cmd,data=None):
        p=subprocess.run(argv+[guard+cmd],input=data,capture_output=True,timeout=30)
        events.append(dict(stage=name,exit_code=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode()))
        print(json.dumps(events[-1]),flush=True)
        if p.returncode:raise RuntimeError(name)
        return p.stdout.decode()
    try:
        run('admission',"test ! -e '"+REMOTE+"' && test \"$(sha256sum /www/Doom/index.html | awk '{print $1}')\" = '"+OLD_I+"' && test \"$(sha256sum /www/Doom/chocolate-doom.wasm | awk '{print $1}')\" = '"+OLD_W+"' && mkdir '"+REMOTE+"'")
        for name,pin,p in [('mount-helper',H,HELPER),('chocolate-doom.wasm',W,CANDIDATE/'chocolate-doom.wasm'),('index.html',I,CANDIDATE/'index.html'),('source-equivalent.patch',sha(CANDIDATE/'source-equivalent.patch'),CANDIDATE/'source-equivalent.patch')]:
            run('upload-'+name,"umask 022; test ! -e '"+REMOTE+'/'+name+"' && cat > '"+REMOTE+'/'+name+"'",p.read_bytes())
            assert run('hash-'+name,"sha256sum '"+REMOTE+'/'+name+"' | awk '{print $1}'").strip()==pin
        run('prepare',"chmod 700 '"+REMOTE+"/mount-helper'; chmod 644 '"+REMOTE+"/chocolate-doom.wasm' '"+REMOTE+"/index.html' '"+REMOTE+"/source-equivalent.patch'")
        run('helper-inspect',REMOTE+'/mount-helper inspect')
        run('bind-music',REMOTE+'/mount-helper music');bound=True
        # The tiny source delta is public alongside its preserved source archive.
        run('source-delta-publish',"test ! -e /www/Doom/source-equivalent.patch && cp '"+REMOTE+"/source-equivalent.patch' /www/Doom/source-equivalent.patch")
        for name,pin in [('chocolate-doom.wasm',W),('index.html',I)]:
            r=urllib.request.urlopen('http://192.168.1.90/Doom/'+name,timeout=15);data=r.read();assert hashlib.sha256(data).hexdigest()==pin
        state=run('control-preserved',"/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'; /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping; cat /sys/class/watchdog/watchdog0/f340_control")
        assert state.splitlines()==['ENABLED','PONG','00000000']
        status='PASS_MUSIC_ASSETS_RAM_INSTALLED_AUDIO_GATE_PENDING'
    except Exception:
        status='FAILED'
        if bound:run('rollback',REMOTE+'/mount-helper unmusic')
        raise
    finally:
        result=dict(status=locals().get('status','FAILED'),events=events,wasm_sha256=W,index_sha256=I,flash=False,reboot=False,persistent=False,music_audio_verified=False)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':result['status']}),flush=True)
if __name__=='__main__':main()
