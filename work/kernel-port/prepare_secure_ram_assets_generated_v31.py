"""Build exact authenticated RAM asset upload; no arbitrary command or path."""
from pathlib import Path
import hashlib,json,subprocess,base64
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/doom/linux73-https-assets-v31'
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-control-v23'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-v31'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists() or OUT.exists():raise RuntimeError('Immutable outputs exist')
 NEW.mkdir();OUT.mkdir()
 bundle=ROOT/'outputs/doom/browser-20261022-r2-touch/www/Doom'
 music=ROOT/'outputs/doom/music-opl-qualified-20261022-r3-sourcepatch'
 files={name:bundle/name for name in ['chocolate-doom.js','doom19s.zip','doom-wasm-source.tar.gz','fflate.js','fflate-LICENSE.txt','GPL-2.0.txt','PROVENANCE.json','upstream-engine.txt']}
 files.update({name:music/name for name in ['chocolate-doom.wasm','index.html','source-equivalent.patch']})
 binary=subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','--','python3','-c',"import pathlib,sys;sys.stdout.buffer.write(pathlib.Path('/home/rea/openmitrastar-linux73-20261022T135100Z/dropbear73-pie-qualified-v1/dropbearmulti-a').read_bytes())"],capture_output=True,check=True).stdout
 (OUT/'dropbearmulti').write_bytes(binary)
 assert sha(OUT/'dropbearmulti')=='23026d9cabd53cab1d9b7c5a78ef5c5be0e6842b7a81a1696af9949bf5974da0'
 records=[{'name':name,'local':str(p),'target':'/www/Doom/'+name,'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in files.items()]
 records.append({'name':'dropbearmulti','local':str(OUT/'dropbearmulti'),'target':'/run/dropbear73-pie','bytes':len(binary),'sha256':sha(OUT/'dropbearmulti')})
 # Per-request authentication and CSRF bind to the same session used by LYOKO.
 # Files write only to exact fixed RAM paths; each hash is known at generation.
 script=r'''#!/bin/sh
set -eu
fail() { printf 'Status: %s\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n{"ok":false}\n' "$1"; exit 0; }
[ "${HTTPS:-}" = on ] || fail '403 Forbidden'
[ "${REQUEST_METHOD:-}" = POST ] || fail '405 Method Not Allowed'
auth=$(/bin/sh /usr/libexec/openmitrastar/om-api-v1 session)
printf %s "$auth" | grep -q '"authenticated":true' || fail '403 Forbidden'
token=$(printf %s "${HTTP_COOKIE:-}" | sed -n 's/^OMSESSION=\\([0-9a-f]*\\)$/\\1/p')
[ "${#token}" -eq 64 ] || fail '403 Forbidden'
csrf=$(sed -n 's/^csrf=//p' /run/openmitrastar/web/sessions/$token | head -n 1)
[ -n "$csrf" ] && [ "${HTTP_X_OM_CSRF:-}" = "$csrf" ] || fail '403 Forbidden'
case "${QUERY_STRING:-}" in
'''
 for r in records:
  script+="'file="+r['name']+"') target='"+r['target']+"'; size="+str(r['bytes'])+"; expected='"+r['sha256']+"' ;;\n"
 script+=r'''*) fail '400 Bad Request' ;;
esac
[ "${CONTENT_LENGTH:-}" = "$size" ] || fail '413 Payload Too Large'
[ ! -e "$target" ] || fail '409 Conflict'
mkdir -p /www/Doom
umask 077
trap 'rm -f "$target.part"' EXIT
/bin/busybox head -c "$size" > "$target.part"
actual=$(sha256sum "$target.part" | cut -d ' ' -f 1)
[ "$actual" = "$expected" ] || fail '422 Unprocessable Content'
case "$target" in /run/dropbear73-pie) chmod 700 "$target.part" ;; *) chmod 644 "$target.part" ;; esac
mv "$target.part" "$target"
printf 'Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n{"ok":true,"bytes":%s,"sha256":"%s"}\n' "$size" "$expected"
'''
 (OUT/'upload.cgi').write_bytes(script.encode())
 (OUT/'manifest.json').write_text(json.dumps({'status':'EXACT_RAM_ASSETS_PREPARED','records':records,'cgi_sha256':sha(OUT/'upload.cgi'),'flash':False,'physical_upload':'UNRUN'},indent=2)+'\n')
 text=base64.b64encode(script.encode()).decode()
 scripts={'runtime':'uname -r','init':': > /run/om73-assets.b64'}
 for i in range(0,len(text),64):scripts['p'+str(i//64)]="printf %s '"+text[i:i+64]+"' >> /run/om73-assets.b64"
 scripts['decode']=' /bin/busybox base64 -d /run/om73-assets.b64 > /www/__assets.cgi; chmod 700 /www/__assets.cgi; sha256sum /www/__assets.cgi'
 scripts['after']='cat /proc/uptime; head -n 3 /proc/meminfo'
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R23-'+self.nonce[:8]+'-'+name","marker='R30-'+self.nonce[:8]+'-'+name")
 code=code.replace("   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')","   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')\n   if name=='decode':m.BASE.require('"+sha(OUT/'upload.cgi')+"' in gates[name],'Exact asset CGI drift')")

 start=code.index("  status=self.synchronize_nonce(m.KERNEL);")
 end=code.index("  for name in SCRIPTS:",start)
 recovery=r"""  prior=json.loads((ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-assets-stage-v30/result.json').read_text())
  m.BASE.require(prior['artifact']['sha256']==self.config['sha256'] and prior['error_reason']=='Exact asset CGI drift' and prior['flash_writes']==prior['bootenv_writes']==0,'Prior exact stopped shell absent')
  self.safe();self.fresh();self.s.write(b'\x03\x15\n',timeout=3);time.sleep(.2)
  gates={}
 """
 code=code[:start]+recovery+code[end:]
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py',OUT/'upload.cgi',OUT/'manifest.json']:
  pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print(json.dumps({'cgi_sha256':sha(OUT/'upload.cgi'),'bytes':len(script),'assets':len(records),'total_asset_bytes':sum(x['bytes'] for x in records)}))
if __name__=='__main__':main()
