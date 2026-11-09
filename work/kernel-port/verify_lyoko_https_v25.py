"""Credential-pinned HTTPS login/logout; never print secrets or cookies."""
from pathlib import Path
import argparse,hashlib,json,re,ssl,time
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
from urllib.parse import urlencode
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('Immutable evidence exists')
 config=json.loads(a.config.read_text());password=(DEVICE/'web_password.txt').read_text().rstrip('\r\n');expected=(DEVICE/'web_password.sha256').read_text().strip()
 assert hashlib.sha256(password.encode()).hexdigest()==expected and re.fullmatch('[0-9a-f]{64}',expected)
 context=ssl.create_default_context(cafile=config['tls_cert']);context.minimum_version=ssl.TLSVersion.TLSv1_2
 checks={};rows=[];cookie=None;error=None;step='login-page'
 def request(path,body=None,cookie=None):
  c=HTTPSConnection('192.168.1.91',context=context,source_address=('192.168.1.49',0),timeout=12)
  headers={'Content-Type':'application/x-www-form-urlencoded','Cache-Control':'no-cache'}
  if cookie:headers['Cookie']=cookie
  try:
   c.connect();tls=c.sock.version();c.request('POST' if body is not None else 'GET',path,body=body,headers=headers)
   r=c.getresponse();data=r.read(300001)
   if len(data)>300000:raise ValueError('Finite body exceeded')
   rows.append({'path':path,'status':r.status,'bytes':len(data),'tls':tls})
   return r.status,{k.lower():v for k,v in r.getheaders()},data
  finally:c.close()
 def check(name,value):
  checks[name]=bool(value)
  if not value:raise ValueError(name)
 try:
  status,headers,data=request('/index.cgi');check('login_form',status==200 and b'login_password' in data and b'login-warning' not in data)
  step='login';form=urlencode({'login_password':password}).encode();password=''
  status,headers,data=request('/index.cgi',form);form=b''
  jar=SimpleCookie();jar.load(headers.get('set-cookie',''));session=jar.get('OMSESSION')
  if session and re.fullmatch('[0-9a-f]{64}',session.value):cookie='OMSESSION='+session.value
  check('login_redirect',status==302 and headers.get('location')=='/dashboard.cgi')
  check('secure_session_cookie',cookie is not None and bool(session['httponly']) and bool(session['secure']) and session['samesite'].lower()=='strict')
  step='dashboard';status,headers,data=request('/dashboard.cgi',cookie=cookie)
  check('dashboard_html',status==200 and b'lyoko' in data.lower());check('dashboard_no_store',headers.get('cache-control')=='no-store')
  step='session';status,headers,data=request('/api/v1/session',cookie=cookie);r=json.loads(data)
  check('authenticated_session',status==200 and r.get('authenticated') is True)
  step='frontend';status,headers,data=request('/api/v1/frontend',cookie=cookie);r=json.loads(data)
  check('frontend_contract',status==200 and r.get('schema')=='lyoko.api.frontend/v1')
 except BaseException as e:error={'step':step,'type':type(e).__name__}
 finally:
  if cookie:
   try:
    status,headers,data=request('/logout.cgi',cookie=cookie);checks['logout']=status==302 and headers.get('location')=='/index.cgi'
    status,headers,data=request('/api/v1/session',cookie=cookie);checks['session_invalid_after_logout']=status==403
   except BaseException as e:error=error or {'step':'logout','type':type(e).__name__}
  password='';cookie=None
 result={'status':'PASS_LYOKO_HTTPS_AUTHENTICATED_SESSION' if error is None and checks and all(checks.values()) else 'LYOKO_HTTPS_AUTH_INCOMPLETE','utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'artifact_sha256':config['sha256'],'checks':checks,'rows':rows,'error':error,'credentials_logged':False,'cookie_logged':False,'flash_writes':0,'bootenv_writes':0,'configuration_write':False}
 a.output.mkdir(parents=True);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
