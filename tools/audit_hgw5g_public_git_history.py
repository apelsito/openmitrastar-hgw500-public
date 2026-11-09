"""Readonly allrefs/worktree publication audit; emit paths/counts never secrets."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 head=git(a.repo,'rev-parse','HEAD').decode().strip();refs=git(a.repo,'show-ref').decode().splitlines();lines=git(a.repo,'rev-list','--objects','--all').decode().splitlines();objects={}
 for line in lines:
  fields=line.split(' ',1)
  if len(fields)==2:objects.setdefault(fields[0],[]).append(fields[1])
 metadata=git(a.repo,'cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)',input='')if False else None
 proc=subprocess.Popen(['git','-C',str(a.repo),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
 patterns={
 'private_key_pem':re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
 'github_token':re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
 'aws_access_id':re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'literal_bearer':re.compile(rb'(?i)authorization[\"\x27\s:=]{0,15}bearer\s+[A-Za-z0-9._-]{25,}'),
 'credential_literal':re.compile(rb'(?im)(?:password|passwd|passphrase|psk|api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*(?:=|:)\s*[\"\x27]([^\"\x27\r\n]{8,})[\"\x27]'),
 'hostapd_passphrase':re.compile(rb'(?im)^\s*wpa_passphrase\s*=\s*([^\r\n]{8,})'),
 'ssh_public_identity':re.compile(rb'ssh-(?:ed25519|rsa)\s+[A-Za-z0-9+/]{40,}'),
 'device_snapshot_identity':re.compile(rb'(?i)(?:client_mac|station_mac|bssid|local-mac-address)\s*[\"\x27\s:=]{1,10}[\"\x27]?(?:[0-9a-f]{2}:){5}[0-9a-f]{2}')}
 placeholders=re.compile(rb'(?i)(?:example|placeholder|changeme|password|your[_ -]|test[_ -]|dummy|redact|@|\$|<|%|secret|token|key|not.?a.?real|abcdefghijklmnopqrstuvwxyz|12345678)')
 findings=[];binary=[];suspect_paths=[];count=0;total=0;seenblobs=set();license_unknown=[]
 for oid,paths in objects.items():
  proc.stdin.write((oid+'\n').encode());proc.stdin.flush();meta=proc.stdout.readline().decode().strip().split()
  if len(meta)!=3 or meta[1]!='blob':
   if len(meta)==3:proc.stdout.read(int(meta[2]));proc.stdout.read(1)
   continue
  n=int(meta[2]);raw=proc.stdout.read(n);assert len(raw)==n;proc.stdout.read(1);count+=1;total+=n;seenblobs.add(oid)
  for path in paths:
   comments=path.endswith('comments.raw.bin')
   if re.search(r'(?i)\.(ko|elf|bin|ras|img|dtb|pfx|p12|key|pem|der|crt|cer)$',path)and not comments:suspect_paths.append(dict(path=path,blob=oid,bytes=n))
   if re.search(r'(?i)(?:^|/)(?:local-only|device-captures|runtime-captures|secrets|calibration|mtd[0-9]|uart-captures)(?:/|$)',path):suspect_paths.append(dict(path=path,blob=oid,bytes=n,reason='sensitive_directory_name'))
  if raw.startswith((b'\x7fELF',b'MZ',b'\x27\x05\x19\x56',b'hsqs')):binary.append(dict(paths=paths,blob=oid,bytes=n,signature=raw[:4].hex()))
  for kind,pattern in patterns.items():
   matches=[]
   for m in pattern.finditer(raw):
    value=m.group(1)if m.lastindex else m.group(0)
    if kind in('credential_literal','hostapd_passphrase')and(placeholders.search(value)or b'\n'in value or b' 'in value or b'/'in value):continue
    matches.append(dict(offset=m.start(),line=raw.count(b'\n',0,m.start())+1))
    if len(matches)>=15:break
   if matches:findings.append(dict(kind=kind,paths=paths,blob=oid,matches=matches,comments_archive_only=all('/comments' in x for x in paths)))
  for path in paths:
   if path.startswith('vendor/legacy-gpl/')and re.search(r'\.(?:c|h|S|cpp)$',path):
    prefix=raw[:12000].lower()
    if not any(x in prefix for x in(b'general public license',b'spdx-license-identifier',b'redistribution and use',b'license')):license_unknown.append(dict(path=path,blob=oid))
 proc.stdin.close();proc.wait();tracked=git(a.repo,'ls-files','-z').decode().split('\0');worktree_paths=[x for x in tracked if x];current_suspect=[x for x in worktree_paths if re.search(r'(?i)\.(ko|elf|bin|key|pem|pfx|p12|der|crt|cer)$',x)and not x.endswith('comments.raw.bin')]
 report=dict(status='READ_ONLY_PUBLICATION_AUDIT_REQUIRES_TRIAGE'if findings or binary or suspect_paths else'PASS_READ_ONLY_ALLREFS_ARTIFACT_SECRET_PATTERN_AUDIT',repository=str(a.repo),head=head,refs=refs,commits=int(git(a.repo,'rev-list','--all','--count')),history_blobs_scanned=count,history_blob_bytes=total,worktree_tracked_paths=len(worktree_paths),allref_path_artifact_candidates=suspect_paths,binary_signatures=binary,secret_pattern_candidates=findings,current_forbidden_extension_paths=current_suspect,vendor_source_missing_explicit_header_candidates=license_unknown,submodule_config=git(a.repo,'show','HEAD:.gitmodules').decode(),git_mutations=False,secret_values_printed=False,limits=['Regexcandidates requiremanualcontexttriage;absenceisnotuniversalsecretproof','Submodulecontents areexternalupstream;separatereadonlylicense/publicvisibilityverification','Untracked/ignoredlocal-onlybytesneverincludedoruploadedbythisaudit'])
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in('secret_pattern_candidates','vendor_source_missing_explicit_header_candidates','allref_path_artifact_candidates','refs')}));print(json.dumps(dict(secret_candidates=len(findings),artifact_paths=len(suspect_paths),unknown_vendor_headers=len(license_unknown))))
if __name__=='__main__':main()
