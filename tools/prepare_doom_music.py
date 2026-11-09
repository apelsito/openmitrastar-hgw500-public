"""Create a new minimal music-enabled candidate. No router or firmware I/O."""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import json
import struct
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'outputs/doom/english-episode1-20261021T222750344251Z/index.html'
ASSETS = ROOT / 'outputs/doom/browser-20261022-r2-touch/www/Doom'
INDEX_SHA = 'f05c849f945e56f4250a7800e627a732e9711746465c8359d5cfeb270d5baa33'
SOURCE_SHA = '9be6e02bb1f4f4b00f73d21b0c1ba4f2b8087e3c6cb1f477435baa390b3aa482'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def prepare(out):
    original = INDEX.read_bytes()
    source = (ASSETS / 'doom-wasm-source.tar.gz').read_bytes()
    assert sha(original) == INDEX_SHA
    assert sha(source) == SOURCE_SHA
    text = original.decode('utf-8')
    changes = [('music_volume 0\\n', 'music_volume 8\\n'),
               ('snd_musicdevice 0\\n', 'snd_musicdevice 3\\n'),
               ("'-nogui','-nomusic','-config'", "'-nogui','-config'")]
    for before, after in changes:
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    candidate = text.encode('utf-8')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'index.html').write_bytes(candidate)
    evidence = []
    prefix = 'doom-wasm-65e0d3ae2ffa604155eebd96ed40da6567bd08f4/'
    selections = {
        'src/i_sound.c': [(102, 115), (162, 187), (229, 263)],
        'src/i_sound.h': [(89, 103)],
        'src/i_oplmusic.c': [(361, 382), (1615, 1660), (1714, 1795)],
        'opl/opl_sdl.c': [(170, 223), (283, 356)],
        'opl/opl.c': [(64, 104), (474, 507)],
    }
    with tarfile.open(fileobj=io.BytesIO(source)) as archive:
        for name, ranges in selections.items():
            b = archive.extractfile(prefix + name).read()
            lines = b.decode().splitlines()
            evidence.append({'path':name,'sha256':sha(b),'line_count':len(lines),
                'excerpts':[{'first_line':a,'last_line':min(z,len(lines)),
                'lines':[f'{i+1}: {lines[i]}' for i in range(a-1,min(z,len(lines)))]} for a,z in ranges]})
    outer = zipfile.ZipFile(ASSETS / 'doom19s.zip')
    inner = zipfile.ZipFile(io.BytesIO(outer.read('DOOMS_19.1')+outer.read('DOOMS_19.2')))
    wad = inner.read('DOOM1.WAD')
    count, directory = struct.unpack_from('<II', wad, 4)
    music = {}
    for i in range(count):
        offset, size, raw = struct.unpack_from('<II8s', wad, directory+i*16)
        name=raw.rstrip(b'\0').decode()
        if name in ('D_E1M1','D_E1M2','D_INTRO','GENMIDI'):
            b=wad[offset:offset+size]
            music[name]={'bytes':size,'sha256':sha(b),'signature':b[:8].hex()}
    assert set(music)=={'D_E1M1','D_E1M2','D_INTRO','GENMIDI'}
    manifest={'status':'MUSIC_CANDIDATE_PHYSICAL_UNRUN','created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'index':{'path':str(out/'index.html'),'sha256':sha(candidate),'bytes':len(candidate)},
        'baseline':{'path':str(INDEX),'sha256':INDEX_SHA,'bytes':len(original)},
        'changes':changes,'assets_unchanged':{p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in sorted(ASSETS.iterdir()) if p.name!='index.html'},
        'source_archive_sha256':SOURCE_SHA,'source_evidence':evidence,'original_wad_sha256':sha(wad),'music_lumps':music,
        'provenance_limit':'Upstream source attribution retained; exact source-to-binary rebuild correspondence is not independently proved.',
        'mechanism':'Original IWAD MUS scores and GENMIDI instruments through existing OPL emulator. No new music assets.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest

if __name__=='__main__':
    out=ROOT/'outputs/doom'/('music-episode1-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    manifest=prepare(out)
    print(json.dumps({'output':str(out),'index':manifest['index']},indent=2))
