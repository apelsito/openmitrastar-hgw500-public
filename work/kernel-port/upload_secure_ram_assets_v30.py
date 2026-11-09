"""Upload allowlisted game/SSH assets over authenticated pinned router HTTPS."""
from pathlib import Path
import argparse,hashlib,json,re,ssl,time
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
from urllib.parse import urlencode
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('Immutable evidence exists')
 config=json.loads(a.config.read_text());manifest=json.loads(a.manifest.read_text())
 context=ssl.create_default_context(cafile=config['tls_cert']);context.minimum_version=ssl.TLSVersion.TLSv1_2
 password=(DEVICE/'web_password.txt').read_text().rstrip('\r\n');expected=(DEVICE/'web_password.sha256').read_text().strip()
 assert hashlib.sha256(password.encode()).hexdigest()==expected
 cookie=None;rows=[];error=None;step='login';a.output.mkdir(parents=True)
 def save():
  result={'status':'PASS_EXACT_RAM_ASSETS_TLS' if error is None and len(rows)==len(manifest['records']) and all(r['exact'] for r in rows) else 'RAM_ASSETS_UPLOAD_INCOMPLETE','artifact_sha256':config['sha256'],'rows':rows,'error':error,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'credentials_logged':False,'cookies_logged':False,'flash_writes':0,'bootenv_writes':0,'persistent':False}
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result
 def request(path,body=None,headers=None):
  c=HTTPSConnection('192.168.1.91',context=context,source_address=('192.168.1.49',0),timeout=35)
  h={'Connection':'close'}|dict(headers or {})
  if cookie:h['Cookie']=cookie
  try:
   c.request('POST' if body is not None else 'GET',path,body=body,headers=h);r=c.getresponse();data=r.read(4194305)
   if len(data)>4194304:raise ValueError('Finite response exceeded')
   return r.status,{k.lower():v for k,v in r.getheaders()},data
  finally:c.close()
 try:
  status,headers,body=request('/index.cgi',urlencode({'login_password':password}).encode(),{'Content-Type':'application/x-www-form-urlencoded'});password=''
  jar=SimpleCookie();jar.load(headers.get('set-cookie',''));session=jar.get('OMSESSION')
  assert status==302 and session and bool(session['secure']) and re.fullmatch('[0-9a-f]{64}',session.value)
  cookie='OMSESSION='+session.value
  status,headers,body=request('/api/v1/status');session_state=json.loads(body);csrf=session_state.get('csrf','');assert status==200 and re.fullmatch('[0-9a-f]{64}',csrf)
  for record in manifest['records']:
   step=record['name'];data=Path(record['local']).read_bytes();assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256']
   status,headers,body=request('/__assets.cgi?'+urlencode({'file':record['name']}),data,{'Content-Type':'application/octet-stream','X-OM-CSRF':csrf})
   result=json.loads(body);exact=status==200 and result.get('ok') is True and result.get('bytes')==record['bytes'] and result.get('sha256')==record['sha256']
   row={'name':record['name'],'bytes':record['bytes'],'sha256':record['sha256'],'status':status,'exact':exact};rows.append(row);save();print(json.dumps(row),flush=True)
   if not exact:raise ValueError('Exact asset rejected')
   if record['target'].startswith('/www/Doom/'):
    status,headers,body=request('/Doom/'+record['name']);assert status==200 and hashlib.sha256(body).hexdigest()==record['sha256']
 except BaseException as failure:error={'step':step,'type':type(failure).__name__};raise
 finally:
  if cookie:
   try:request('/logout.cgi')
   except BaseException:error=error or {'step':'logout','type':'Unavailable'}
  cookie=None;password='';print(json.dumps(save(),indent=2))
if __name__=='__main__':main()
