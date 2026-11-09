"""Verify the publication manifest only; no downloads or router access."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'handoff/SOURCE_MANIFEST.json').read_text())
failed=[]
for row in manifest['files']:
 p=root/row['path']
 if not p.is_file():failed.append({'path':row['path'],'reason':'missing'});continue
 with p.open('rb')as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 if p.stat().st_size!=row['bytes']or h!=row['sha256']:failed.append({'path':row['path'],'reason':'size/hash'})
print(json.dumps({'status':'PASS'if not failed else'FAIL','files':len(manifest['files']),'bytes':sum(r['bytes']for r in manifest['files']),'failed':failed,'hardware_accessed':False},indent=2))
raise SystemExit(1 if failed else 0)
