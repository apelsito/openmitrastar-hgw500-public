"""Finite device HTTPS traffic with pinned trust and exact image provenance."""
from pathlib import Path
import argparse,hashlib,json,ssl,time
from http.client import HTTPSConnection

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--config',type=Path,required=True);p.add_argument('--boot-receipt',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--host',default='192.168.1.91')
 p.add_argument('--source',default='192.168.1.49');p.add_argument('--upload-fixture',action='store_true')
 a=p.parse_args()
 if a.host not in ['192.168.1.90','192.168.1.91','192.168.73.1']:raise ValueError('Unknown target')
 if a.output.exists():raise ValueError('Immutable evidence exists')
 config=json.loads(a.config.read_text());boot=json.loads(a.boot_receipt.read_text())
 assert boot['artifact']['sha256']==config['sha256'] and boot['bootm']==1
 assert boot['flash_writes']==boot['bootenv_writes']==0
 assert sha(Path(config['tls_cert']).read_bytes())==config['tls_cert_sha256']
 artifact=json.loads(Path(config['receipt']).read_text())
 expected={r['path']:r for r in artifact['userland_non_sensitive']}
 a.output.mkdir(parents=True)
 rows=[];checks={};payload=bytes(range(256))*256
 def request(path,version,method='GET',body=None):
  context=ssl.create_default_context(cafile=config['tls_cert'])
  context.minimum_version=context.maximum_version=version
  connection=HTTPSConnection(a.host,context=context,timeout=18,source_address=(a.source,0))
  row={'path':path,'method':method,'requested_tls':version.name,'source':a.source,'host':a.host,'certificate_verified':True}
  begin=time.monotonic()
  try:
   connection.connect();row.update(negotiated_tls=connection.sock.version(),cipher=connection.sock.cipher()[0])
   connection.request(method,path,body=body,headers={'Connection':'close','Content-Type':'application/octet-stream'} if body is not None else {'Connection':'close'})
   response=connection.getresponse();data=response.read(1048577)
   if len(data)>1048576:raise ValueError('Finite response limit')
   row.update(status=response.status,bytes=len(data),sha256=sha(data),request_bytes=len(body) if body is not None else 0)
   rows.append(row);return response.status,data
  except (OSError,ValueError) as error:
   row.update(error_type=type(error).__name__,error_reason=str(error));rows.append(row);return None,b''
  finally:row['seconds']=round(time.monotonic()-begin,3);connection.close()
 for v in [ssl.TLSVersion.TLSv1_2,ssl.TLSVersion.TLSv1_3]:
  code,body=request('/__traffic.bin',v);checks[v.name+'_exact_65536']=code==200 and body==payload
 for path in ['/login.html','/openmitrastar-oem.css','/openmitrastar-oem.js']:
  code,body=request(path,ssl.TLSVersion.TLSv1_3)
  checks[path+'_exact']=code==200 and sha(body)==expected['/www'+path]['sha256']
 # No credentials: verify that unauthenticated management stays closed.
 code,body=request('/index.cgi',ssl.TLSVersion.TLSv1_3)
 checks['management_unauthenticated_closed']=code in [301,302,303,307,308,401,403]
 if a.upload_fixture:
  for v in [ssl.TLSVersion.TLSv1_2,ssl.TLSVersion.TLSv1_3]:
   code,body=request('/__traffic.cgi',v,'POST',payload)
   checks[v.name+'_upload_digest_exact']=code==200 and body.strip().split()[0:1]==[sha(payload).encode()]
 result={'schema':'openmitrastar.device-https/v13','status':'PASS_DEVICE_TLS_AND_MANAGEMENT_FILES' if all(checks.values()) else 'DEVICE_HTTPS_GATES_INCOMPLETE','utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'artifact_sha256':config['sha256'],'boot_receipt_sha256':sha(a.boot_receipt.read_bytes()),'checks':checks,'rows':rows,'flash_writes':0,'bootenv_writes':0,'credentials_used':False,'upload_fixture':a.upload_fixture,'wifi_association':'SEPARATE_GATE','authenticated_management_transactions':'UNRUN'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
