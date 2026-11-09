"""ELF-only qdrv profile comparison, without loading modules or firmware."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct

def inspect(path: Path) -> dict:
    data=Path(path).read_bytes()
    if data[:6] != b'\x7fELF\x01\x01': raise ValueError('ELF32 little endian required')
    header=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    if header[1] != 1: raise ValueError('relocatable module required')
    sections=[struct.unpack_from('<IIIIIIIIII',data,header[6]+i*header[11]) for i in range(header[12])]
    ss=sections[header[13]]; names=data[ss[4]:ss[4]+ss[5]]
    def string(raw,offset): return raw[offset:].split(b'\0',1)[0].decode('ascii')
    named={string(names,s[0]):(i,s) for i,s in enumerate(sections)}
    sy=named['.symtab'][1]; st=sections[sy[6]]; strings=data[st[4]:st[4]+st[5]]
    symbols=[]
    for i in range(0,sy[5],sy[9]):
        item=struct.unpack_from('<IIIBBH',data,sy[4]+i)
        symbols.append({'name':string(strings,item[0]),'value':item[1],'size':item[2],'section':item[5]})
    pi,ps=named['__param']; params={}
    for symbol in symbols:
        if symbol['section']==pi and symbol['name'].startswith('__param_'):
            if symbol['size'] != 20: raise ValueError('kernel_param ARC32 stride mismatch')
            params[symbol['name'][8:]]=struct.unpack_from('<H',data,ps[4]+symbol['value']+12)[0]
    mi=named['.modinfo'][1]
    info=[x.decode('ascii') for x in data[mi[4]:mi[4]+mi[5]].split(b'\0') if x]
    section_hashes={name:hashlib.sha256(data[s[4]:s[4]+s[5]]).hexdigest() for name,(_,s) in named.items() if name and s[1]!=8}
    functions={s['name']:s['size'] for s in symbols if s['name']=='qdrv_openmitrastar_beacon_preflight_enabled'}
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'machine':header[2],
            'parameters':params,'param_section_bytes':ps[5],'functions':functions,
            'modinfo':info,'section_hashes':section_hashes}

def assert_profile(candidate: dict, baseline: dict) -> None:
    if candidate['parameters'] != baseline['parameters']: raise ValueError('F321 parameter set/perms not preserved')
    if candidate['functions'].get('qdrv_openmitrastar_beacon_preflight_enabled') != baseline['functions']['qdrv_openmitrastar_beacon_preflight_enabled']:
        raise ValueError('beacon preflight implementation profile differs')
    if candidate['parameters'].get('openmitrastar_beacon_preflight_enable') != 0o400:
        raise ValueError('beacon preflight parameter missing')
    if candidate['parameters'].get('openmitrastar_beacon_v89_wire_enable') != 0o400:
        raise ValueError('V89 wire parameter missing')

def normalized_functions(path: Path) -> dict:
    data=Path(path).read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    sections=[struct.unpack_from('<IIIIIIIIII',data,h[6]+i*h[11]) for i in range(h[12])]
    strings_sec=sections[h[13]];strings=data[strings_sec[4]:strings_sec[4]+strings_sec[5]]
    def string(raw,offset):return raw[offset:].split(b'\0',1)[0].decode('ascii')
    sy=next(s for s in sections if string(strings,s[0])=='.symtab');st=sections[sy[6]];names=data[st[4]:st[4]+st[5]]
    result={}
    for off in range(0,sy[5],16):
        a=struct.unpack_from('<IIIBBH',data,sy[4]+off)
        if a[3]&15!=2 or not a[2] or not a[5] or a[5]>=len(sections):continue
        sec=sections[a[5]];raw=bytearray(data[sec[4]+a[1]:sec[4]+a[1]+a[2]])
        for rel in sections:
            if rel[1]!=4 or rel[7]!=a[5]:continue
            for r in range(0,rel[5],rel[9]):
                ro,ri,ad=struct.unpack_from('<IIi',data,rel[4]+r)
                if a[1]<=ro<a[1]+a[2]:
                    delta=ro-a[1];raw[delta:delta+4]=b'\0'*min(4,len(raw)-delta)
        result[string(names,a[0])]={'bytes':a[2],'relocation_masked_sha256':hashlib.sha256(raw).hexdigest()}
    return result
