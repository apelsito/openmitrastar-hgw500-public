"""Build and qualify F335 WPS helper/overlay; no router actions or firmware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,subprocess,shutil
import f335_wps_overlay as overlay
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    overlay.build_overlay()
    out=ROOT/'outputs/kernel-port'/('f335-wps-control-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    source=out/'source';source.mkdir();shutil.copy2(overlay.DEST/'src/om-wpsctl.c',source/'om-wpsctl.c')
    shutil.copy2(ROOT/'tools/test_f335_wps_control.py',source/'test_f335_wps_control.py')
    shutil.copy2(ROOT/'tools/f335_wps_overlay.py',source/'f335_wps_overlay.py')
    q=shlex.quote;tc=overlay.linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    api=overlay.DEST/'overlay/usr/libexec/openmitrastar/om-api-v1'
    script=f'''set -eu
out={q(overlay.linux(out))}
src={q(overlay.linux(source))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -DF335_TEST "$src/om-wpsctl.c" -o "$out/om-wpsctl-test"
python3 "$src/test_f335_wps_control.py" --helper "$out/om-wpsctl-test" --api {q(overlay.linux(api))} --workspace {q(overlay.linux(ROOT))} --result "$out/tests.json" > "$out/tests.stdout" 2> "$out/tests.stderr"
for lane in a b; do
 mkdir "$out/$lane"
 SOURCE_DATE_EPOCH=1790006400 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -Wall -Wextra -Werror -pedantic -static -Wl,--gc-sections "$src/om-wpsctl.c" -o "$out/$lane/om-wpsctl"
 "${{tc}}strip" --strip-unneeded "$out/$lane/om-wpsctl"
 "${{tc}}readelf" -h -l "$out/$lane/om-wpsctl" > "$out/$lane/elf.txt"
 "${{tc}}objdump" -d "$out/$lane/om-wpsctl" > "$out/$lane/disassembly.txt"
 ! grep -Eq '\\b(llock|scond)\\b' "$out/$lane/disassembly.txt"
done
cmp "$out/a/om-wpsctl" "$out/b/om-wpsctl"
'''
    (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',overlay.linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
    (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
    tests=json.loads((out/'tests.json').read_text()) if (out/'tests.json').exists() else {}
    report={'schema':'openmitrastar.f335-wps-control/v1','created_at':datetime.now(timezone.utc).isoformat(),'status':'PASS_OFFLINE_CONTROL_OVERLAY' if not p.returncode and tests.get('success') else 'INCOMPLETE_OR_FAILED','returncode':p.returncode,'tests':tests,'hardware_actions':False,'firmware_created':False,'sources':{x.name:sha(x) for x in source.iterdir()}}
    if not p.returncode:
        prod=overlay.DEST/'overlay/usr/sbin';prod.mkdir(parents=True,exist_ok=True)
        artifacts={
            'om-wpsctl':(out/'a/om-wpsctl',None),
            'hostapd':(ROOT/'outputs/kernel-port/f335-hostapd-wps-20260921T110353Z/a/hostapd','9d4339e59814163277bf08aa4894f7d0c3ea4a01c726973b6b11d0c8edbef564'),
            'hostapd_cli':(ROOT/'outputs/kernel-port/f335-hostapd-wps-20260921T110353Z/a/hostapd_cli','6c36e862764ae01b4f90e9525164c697139943ef54ab598ef4aacc244873db4d')}
        report['artifacts']={}
        for name,(path,expected) in artifacts.items():
            overlay.require(not expected or sha(path)==expected,'immutable root hostapd artifact drift')
            shutil.copy2(path,prod/name);report['artifacts'][name]={'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
        report['overlay']=overlay.build_overlay()
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'tests':tests,'stderr':p.stderr.decode(errors='replace')[-1500:]},indent=2))
    return 0 if report['status']=='PASS_OFFLINE_CONTROL_OVERLAY' else 1
if __name__=='__main__':raise SystemExit(main())
