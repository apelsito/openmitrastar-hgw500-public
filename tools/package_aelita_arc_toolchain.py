"""Read safelist/hash licenses andarchiveexactownedTC tree privateasset only."""
import argparse,hashlib,json,os,re,stat,tarfile,subprocess,lzma
from pathlib import Path
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--metadata-only',action='store_true');a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);t=a.toolchain.resolve();rows=[];blocked=[];licenses=[];total=0
 allowed={'bin','lib','libexec','include','share','arc-snps-linux-uclibc'}
 for f in sorted(t.rglob('*')):
  rel=f.relative_to(t);info=f.lstat();mode=stat.S_IMODE(info.st_mode)
  if rel.parts[0]not in allowed:blocked.append({'path':rel.as_posix(),'reason':'nottoolchainsafelist'});continue
  if stat.S_ISLNK(info.st_mode):
   target=os.readlink(f);assert (f.parent/target).resolve().is_relative_to(t),'externalsymlink '+str(rel);rows.append({'path':rel.as_posix(),'type':'symlink','mode':oct(mode),'target':target});continue
  if stat.S_ISDIR(info.st_mode):rows.append({'path':rel.as_posix(),'type':'directory','mode':oct(mode)});continue
  if not stat.S_ISREG(info.st_mode):blocked.append({'path':rel.as_posix(),'reason':'specialfile'});continue
  if re.search(r'(?i)(?:^|/)(?:\.ssh|\.aws|\.codex|secrets|calibration|firmware)(?:/|$)|\.(?:pem|key|p12|pfx|ko|ras|dtb)$',rel.as_posix()):blocked.append({'path':rel.as_posix(),'reason':'privatedeviceassetname'});continue
  raw=f.read_bytes()
  if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',raw):blocked.append({'path':rel.as_posix(),'reason':'privatekeyortokenmarker'});continue
  h=hashlib.sha256(raw).hexdigest();rows.append({'path':rel.as_posix(),'type':'file','mode':oct(mode),'bytes':len(raw),'sha256':h});total+=len(raw)
  if rel.as_posix().startswith('share/licenses/'):licenses.append({'path':rel.as_posix(),'bytes':len(raw),'sha256':h})
 assert not blocked,blocked;gcc=t/'bin/arc-snps-linux-uclibc-gcc';assert sha(gcc)=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263';version=subprocess.check_output([str(gcc),'--version'],text=True).splitlines()[0]
 manifest={'schema':'openmitrastar.aelita-exact-arc-toolchain/v1','status':'PASS_SAFE_TOOLCHAIN_TREE_PRIVATE_ARCHIVE_PENDING','private_delivery':True,'hardware_accessed':False,'Git_mutations':False,'source_carrier':str(t),'gcc_version':version,'gcc_sha256':sha(gcc),'total_regular_bytes':total,'files':rows,'licenses':licenses,'blocked_paths':blocked,'binary_runtime_distribution_scope':'PrivateownerAELITAtoolchainasset; originalpercomponentlicensefilesretained, nofirmware/calibration/credentials','upstream_sourcebuildconfig':'share/arc-snps-linux-uclibc-ct-ng.config.bz2','archive_top_directory':'arc-toolchain','metadata_only':a.metadata_only};(a.output/'TOOLCHAIN_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'status':manifest['status'],'entries':len(rows),'bytes':total,'license_files':len(licenses),'gcc_version':version}),flush=True)
 if a.metadata_only:return
 archive=a.output/'arc-snps-linux-uclibc-gcc15.2.0-10504-aelita.tar.xz'
 with tarfile.open(archive,'w:xz',preset=6)as tar:
  for row in rows:
   f=t/row['path'];tar.add(f,arcname='arc-toolchain/'+row['path'],recursive=False)
 for row in rows:
  f=t/row['path']
  if row['type']=='file':assert sha(f)==row['sha256']
  elif row['type']=='symlink':assert os.readlink(f)==row['target']
 # Decodearchiveheaders/content andverifyeveryfile/symlinkmode without extracting.
 archived={}
 with tarfile.open(archive)as tar:
  for member in tar:
   rel=member.name.removeprefix('arc-toolchain/');row=next(r for r in rows if r['path']==rel);assert member.mode==int(row['mode'],8)
   if row['type']=='file':raw=tar.extractfile(member).read();assert len(raw)==row['bytes']and hashlib.sha256(raw).hexdigest()==row['sha256']
   elif row['type']=='symlink':assert member.issym()and member.linkname==row['target']
   archived[rel]=True
 assert len(archived)==len(rows)
 result={'status':'PASS_EXACT_PRIVATE_TOOLCHAIN_TAR_XZ_CONTENTS_HASHES_MODES_SYMLINKS','private':True,'hardware_accessed':False,'uploaded':False,'archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'manifest_sha256':sha(a.output/'TOOLCHAIN_MANIFEST.json'),'entries_verified':len(rows),'regular_files':sum(r['type']=='file'for r in rows),'symlinks':sum(r['type']=='symlink'for r in rows),'total_regular_bytes':total,'license_files':len(licenses),'gcc_sha256':sha(gcc),'limits':['ExactownedTCruntime/header/library/licensecarrierpackaged; noGitHubuploadperformed','NoAELITAextraction/executionyet','OriginalbuildsourceforGCC/binutils/libcnotfullyembedded; ct-ngconfigandcomponentlicensespresent']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
