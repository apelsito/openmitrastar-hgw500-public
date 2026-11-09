"""Fetch pinned 2026 userland inputs over HTTPS into new offline directories."""
import argparse
import hashlib
import json
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HEADERS={'User-Agent':'OpenMitraStar-owner-port','Accept':'application/vnd.github+json'}

def fetch(url):
    assert url.startswith('https://')
    request=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(request,timeout=45) as response:
        assert response.url.startswith('https://'), 'Transport downgrade'
        data=response.read(64*1024*1024+1)
    assert len(data)<=64*1024*1024
    return data

def release_commit(repo,tag):
    result=json.loads(fetch('https://api.github.com/repos/'+repo+'/git/ref/tags/'+tag))['object']
    if result['type']=='tag':
        result=json.loads(fetch(result['url']))['object']
    assert result['type']=='commit'
    return result['sha']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    libc=release_commit('wbx-github/uclibc-ng','v1.0.59')
    inputs=[
        ('uclibc-ng','1.0.59',libc,'https://codeload.github.com/wbx-github/uclibc-ng/tar.gz/'+libc),
        ('wolfssl','5.9.4','3c5eead44904df64e6a5a1f4ebdce377d35a849a','https://codeload.github.com/wolfSSL/wolfssl/tar.gz/3c5eead44904df64e6a5a1f4ebdce377d35a849a'),
        ('uhttpd','2026-10-19','ca796d7dec5697a2d1a7a42be79677f239b64282','https://codeload.github.com/openwrt/uhttpd/tar.gz/ca796d7dec5697a2d1a7a42be79677f239b64282'),
        ('libubox','2026-10-08','da2d205a5cf3e877c45a2eec488218cbaf452e7d','https://codeload.github.com/openwrt/libubox/tar.gz/da2d205a5cf3e877c45a2eec488218cbaf452e7d'),
        ('ustream-ssl','2026-07-08','cea28c5bc43ae80c3531c98f4e4dc67b7dcf0ebb','https://codeload.github.com/openwrt/ustream-ssl/tar.gz/cea28c5bc43ae80c3531c98f4e4dc67b7dcf0ebb'),
        ('libnl-tiny','2025-12-02','40493a655d8caa2ccf5206dde1e733abe2920432','https://codeload.github.com/openwrt/libnl-tiny/tar.gz/40493a655d8caa2ccf5206dde1e733abe2920432'),
        ('hostapd','2.12',None,'https://w1.fi/releases/hostapd-2.12.tar.gz'),
        ('busybox','1.38.0',None,'https://busybox.net/downloads/busybox-1.38.0.tar.bz2'),
    ]
    rows=[]
    for name,version,commit,url in inputs:
        print('FETCH '+name+' '+version,flush=True)
        data=fetch(url);archive=a.output/(name+'.tar');archive.write_bytes(data)
        extracted=a.output/name;extracted.mkdir()
        with tarfile.open(archive) as tar:tar.extractall(extracted,filter='data')
        children=list(extracted.iterdir());assert len(children)==1 and children[0].is_dir()
        rows.append({'name':name,'version':version,'commit':commit,'url':url,'bytes':len(data),
                     'sha256':hashlib.sha256(data).hexdigest(),'source':str(children[0]),
                     'provenance':'Maintainer or official upstream repository over HTTPS; commit or release archive pinned.',
                     'signature_verified':False,'status':'SOURCE_ONLY_UNBUILT'})
        (a.output/'manifest.json').write_text(json.dumps({'schema':'openmitrastar.userland2026-inputs/v1','hardware_accessed':False,'fetched_utc':datetime.now(timezone.utc).isoformat(),'inputs':rows},indent=2)+'\n')
    print(json.dumps({'status':'PASS_PINNED_HTTPS_SOURCE_ACQUISITION','components':len(rows),'build':'UNRUN','hardware':'UNRUN'}))

if __name__=='__main__':main()
