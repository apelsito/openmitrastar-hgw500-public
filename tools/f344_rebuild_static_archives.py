"""Rebuild OpenSSL archives once from exact compiled ELF members and verify bytes."""
from pathlib import Path
import argparse,hashlib,json,re,shlex,struct,subprocess
def members(path):
 b=path.read_bytes();assert b.startswith(b'!<arch>\n');position=8;longnames=b'';result={}
 while position<len(b):
  h=b[position:position+60];assert len(h)==60 and h[58:60]==b'`\n';position+=60
  size=int(h[48:58].strip());data=b[position:position+size];assert len(data)==size;position+=(size+1)&~1
  name=h[:16].decode().strip()
  if name=='//':longnames=data;continue
  if name=='/' or name=='/SYM64/':continue
  if name.startswith('/'):
   offset=int(name[1:]);name=longnames[offset:].split(b'/\n',1)[0].decode()
  else:name=name.rstrip('/')
  assert name not in result;result[name]=data
 return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--openssl-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ar',required=True);ap.add_argument('--build-log',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False);report={}
 for library,folder in [('libcrypto.a','crypto'),('libssl.a','ssl')]:
  existing=subprocess.check_output([a.ar,'t',str(a.openssl_dir/library)],text=True).splitlines()
  declared=set()
  for line in a.build_log.read_text().splitlines():
   if not line.startswith(a.ar+' '):continue
   command=shlex.split(line)
   index=next((i for i,v in enumerate(command) if v.endswith('/'+library) or v==library),None)
   if index is not None:declared.update(Path(v).name for v in command[index+1:])
  if library=='libcrypto.a':
   # OpenSSL's @-prefixed engine recipe does not echo its AR invocation.
   engine_make=(a.openssl_dir/'engines/Makefile').read_text().replace('\\\n',' ')
   line=re.search(r'^LIBOBJ\s*=\s*(.+)$',engine_make,re.M)
   if not line:raise ValueError('engine member declaration missing')
   declared.update(line.group(1).split())
  if len(existing)!=len(set(existing)) or not declared or set(existing)-declared:raise ValueError('unexpected archive member set')
  names=sorted(declared)
  paths=[];objects={}
  for name in names:
   if not re.fullmatch(r'[A-Za-z0-9_.-]+\.o',name):raise ValueError('unsafe member')
   found=list(a.openssl_dir.rglob(name))
   if len(found)!=1:raise ValueError('ambiguous object '+name)
   data=found[0].read_bytes()
   if data[:6]!=b'\x7fELF\x01\x01' or struct.unpack_from('<H',data,18)[0]!=93 or struct.unpack_from('<I',data,36)[0]!=0x403:raise ValueError('wrong ARC object '+name)
   paths.append(found[0]);objects[name]=data
  target=a.output/library
  subprocess.run([a.ar,'rcsD',str(target),*map(str,paths)],check=True)
  actual=members(target)
  if actual!=objects:raise ValueError('archive member changed')
  prior=members(a.openssl_dir/library)
  report[library]={'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'members':len(objects),
   'original_archive_member_mismatches':sum(prior.get(n)!=b for n,b in objects.items()),'original_missing_members':len(declared-set(existing)),
   'member_set_matches_archive_commands_and_engine_makefile':True,'every_member_matches_compiled_elf':True,
   'object_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in objects.items()}}
 (a.output/'archive-integrity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:{n:v for n,v in x.items() if n!='object_sha256'} for k,x in report.items()},indent=2))
if __name__=='__main__':main()
