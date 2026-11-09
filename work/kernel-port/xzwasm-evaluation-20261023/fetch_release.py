"""Fetch public pinned release metadata and single self-contained browser decoder."""
from pathlib import Path
import hashlib,json,urllib.request
HERE=Path(__file__).resolve().parent
OUT=HERE/'release'
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'OpenMitraStar-local-xzwasm-evaluation','Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir()
 info=json.loads(get('https://api.github.com/repos/SteveSanderson/xzwasm/releases/latest'))
 rows=[]
 for asset in info['assets']:
  if asset['name'] not in ('xzwasm.min.js','xzwasm.js'):continue
  data=get(asset['browser_download_url'])
  (OUT/asset['name']).write_bytes(data)
  rows.append({'name':asset['name'],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'url':asset['browser_download_url'],'github_digest':asset.get('digest')})
 if not any(r['name']=='xzwasm.min.js' for r in rows):raise RuntimeError('Decoder asset absent')
 result={'tag':info['tag_name'],'published_at':info['published_at'],'release_url':info['html_url'],'assets':rows}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
