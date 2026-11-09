"""Qualify581recordWLAN against qualified580recordparent; nohardware."""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf,normalized_path
from recover_hgw5g_driver_ops import Elf as OpsElf


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def audit(oldpath,newpath):
    a,b=Elf(oldpath),Elf(newpath)
    assert set(a.byname)==set(b.byname),'section membership'
    for name,s in a.byname.items():
        assert all(s[k]==b.byname[name][k] for k in ('type','flags','align','entsize')),'sectionattrs'+name
    assert len(a.syms)==len(b.syms),'symbol count'
    setter='ieee80211_ioctl_setparam';changed=None;diagnostics=[]
    for i,(x,y) in enumerate(zip(a.syms,b.syms)):
        assert (x['name'],x['type'],x['bind'],x['other'],a.symsection(x))==(y['name'],y['type'],y['bind'],y['other'],b.symsection(y)),'symbol identity'
        if x['type']!=2 or not x['size']:continue
        sec=a.symsection(x);u=a.byname[sec]['data'][x['value']:x['value']+x['size']];v=b.byname[sec]['data'][y['value']:y['value']+y['size']]
        if x['name']==setter:
            assert x['value']==y['value'] and x['size']==16294 and y['size']==16232
            assert a.byname[sec]['data'][x['value']+x['size']:x['value']+x['size']+2]==bytes.fromhex('e078')
            changed={'symbol_index':i,'name':setter,'old_value':x['value'],'new_value':y['value'],'old_size':x['size'],'new_size':y['size'],'old_following_nop_bytes':2,'layout_growth':-64,
                     'old_sha256':hashlib.sha256(u).hexdigest(),'new_sha256':hashlib.sha256(v).hexdigest()}
        elif u!=v:
            assert x['name'] in ('ieee80211_delete_wlanunit','ieee80211_param_from_qdrv','ieee80211_ioctl_giwfreq'),'otherfunction'+x['name']
            w=bytearray(v);rows=[]
            if x['name']=='ieee80211_ioctl_giwfreq':
                assert u[74:78]==bytes.fromhex('8a22180b') and v[74:78]==bytes.fromhex('8a22580b')
                w[74:78]=u[74:78];rows.append({'offset':74,'kind':'exactcompactline+1'})
            else:
                delta=7 if x['name']=='ieee80211_delete_wlanunit' else 1
                for p in range(4,len(u)-3,2):
                    if u[p-4:p]==v[p-4:p]==bytes.fromhex('0a22800f'):
                        h,l=struct.unpack_from('<HH',u,p);nh,nl=struct.unpack_from('<HH',v,p)
                        old=(h<<16)|l;new=(nh<<16)|nl
                        if old!=new:
                            assert new-old==delta;w[p:p+4]=u[p:p+4];rows.append({'offset':p-4,'old_line':old,'new_line':new})
            assert bytes(w)==u,'unexpecteddiagnosticdelta'
            diagnostics.append({'symbol_index':i,'name':x['name'],'changes':rows})
    assert changed
    for sec,s in a.byname.items():
        if not s['flags']&4:continue
        v=bytearray(b.byname[sec]['data']);replacements=[]
        for row in [changed]+diagnostics:
            x,y=a.syms[row['symbol_index']],b.syms[row['symbol_index']]
            if a.symsection(x)==sec:
                payload=s['data'][x['value']:x['value']+x['size']+(2 if row is changed else 0)]
                replacements.append((y['value'],y['size'],payload))
        for start,size,payload in sorted(replacements,reverse=True):v[start:start+size]=payload
        assert bytes(v)==s['data'],'residual executable bytes'+sec
    @lru_cache(maxsize=None)
    def point(e,sec,value):
        if sec=='.rodata.str1.4':return ('string',normalized_path(e.cstring(sec,value)))
        if e is b and sec=='.text' and value>=changed['new_value']+changed['new_size']:value+=64
        if e is b and sec=='.rodata':
            table=next(s for s in e.syms if s['name']=='ieee80211_priv_args')
            if value>=table['value']+table['size']:value-=24
        return ('section',sec,value)
    def rel(e,r):
        s=e.syms[changed['symbol_index']]
        if r['section']==e.symsection(s) and s['value']<=r['offset']<s['value']+s['size']:return None
        t=e.syms[r['symbol']];sec=e.symsection(t)
        target=point(e,sec,t['value']+r['addend']) if t['type']==3 or sec=='.rodata.str1.4' else (t['name'],sec,t['type'],t['bind'],r['addend'])
        return (point(e,r['section'],r['offset']),r['type'],target)
    ar=Counter(v for r in a.relas if (v:=rel(a,r)) is not None);br=Counter(v for r in b.relas if (v:=rel(b,r)) is not None)
    assert ar==br,'unrelatedrelocations'+str(list((ar-br).elements())[:5])
    for i,(x,y) in enumerate(zip(a.syms,b.syms)):
        if i==changed['symbol_index'] or x['type']==3:continue
        assert x['size']==y['size'] or x['name']=='ieee80211_priv_args','symbolsize'
        assert point(a,a.symsection(x),x['value'])==point(b,b.symsection(y),y['value']),'symboladdress'+x['name']
    for sec,s in a.byname.items():
        t=b.byname[sec]
        if s['flags']&4 or s['type']==4 or sec in ('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
        u,v=s['data'],t['data']
        if sec=='.rodata':
            table=next(x for x in a.syms if x['name']=='ieee80211_priv_args');cut=table['value']+table['size']
            assert v[cut:cut+24]==struct.pack('<IHH',464,18433,0)+b'check_cur_chan'.ljust(16,b'\0')
            assert u==v[:cut]+v[cut+24:]
        elif sec=='.data':
            h=next(x for x in a.syms if x['name']=='ieee80211_iw_handler_def');p=h['value']+8;v=bytearray(v)
            assert struct.unpack_from('<H',u,p)[0]==580 and struct.unpack_from('<H',v,p)[0]==581
            struct.pack_into('<H',v,p,580);assert u==bytes(v)
        elif s['type']==8:assert (s['size'],s['align'])==(t['size'],t['align'])
        else:assert u==v,'data'+sec
    before=OpsElf(oldpath).ioctl_records();after=OpsElf(newpath).ioctl_records()
    assert len(before)==580 and len(after)==581 and after[:580]==before
    last=after[-1];assert (last['cmd'],last['set_args'],last['get_args'],last['name'])==(464,18433,0,'check_cur_chan')
    return {'status':'PASS_WLAN_EXACT15THSETTER_DELTA','symbols':len(a.syms),'baseline_relocations':len(a.relas),'candidate_relocations':len(b.relas),'relocations_outside_setter':sum(ar.values()),
            'changed_setter':changed,'diagnostic_only_changes':diagnostics,'table580to581':True,'all_original_bytes_outside_declared_delta':True}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--old-wlan',type=Path,required=True);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True);report=audit(a.old_wlan,a.build/'a/wlan/wlan.ko')
    assert sha(a.build/'a/wlan/wlan.ko')==sha(a.build/'b/wlan/wlan.ko');(a.output/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
