"""Reproducible exact WASM startup OPL delay repair; local files only."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import io
import json
import subprocess
import tarfile
import difflib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOLS=Path('D:/Tools/REA/wabt-1.0.42/bin')
WASM=ROOT/'outputs/doom/browser-20261022-r2-touch/www/Doom/chocolate-doom.wasm'
WASM_SHA='6366f83a58fe8596ce742a66dbf86871d315862c89c11e65b54935be03c7e6c4'
MUSIC=ROOT/'outputs/doom/music-episode1-20261022T091921038291Z'
DELAY='''  (func $OPL_Delay (type 48) (param $us i64)
    (local $buffer i32) (local $bytes i32)
    local.get $us
    i64.const 1159368
    i32.wrap_i64
    i32.load
    i64.extend_i32_u
    i64.mul
    i64.const 999999
    i64.add
    i64.const 1000000
    i64.div_u
    i32.wrap_i64
    i32.const 4
    i32.mul
    local.tee $bytes
    call $dlmalloc
    local.set $buffer
    local.get $buffer
    i32.eqz
    if
      unreachable
    end
    local.get $buffer
    i32.const 0
    local.get $bytes
    call $memset
    drop
    i32.const 0
    local.get $buffer
    local.get $bytes
    call $OPL_Mix_Callback
    local.get $buffer
    call $dlfree)
'''
SOURCE_PATCH='''--- a/opl/opl.c
+++ b/opl/opl.c
@@
 void OPL_Delay(uint64_t us)
 {
+#ifdef __EMSCRIPTEN__
+    /* Single-thread browser: OPL_Detect cannot wait for an audio callback
+       while synchronously initialising main. Advance the existing emulator
+       into a private silent buffer; this delay is used only by detection. */
+    OPL_SDL_StartupDelay(us);
+    return;
+#else
     delay_data_t delay_data;
@@
     SDL_DestroyCond(delay_data.cond);
+#endif
 }
--- a/opl/opl_sdl.c
+++ b/opl/opl_sdl.c
@@
+void OPL_SDL_StartupDelay(uint64_t us)
+{
+    size_t samples = (us * mixing_freq + OPL_SECOND - 1) / OPL_SECOND;
+    size_t bytes = samples * 4;
+    void *buffer = calloc(1, bytes);
+    if (buffer == NULL) { abort(); }
+    OPL_Mix_Callback(NULL, buffer, bytes);
+    free(buffer);
+}
--- a/opl/opl_internal.h
+++ b/opl/opl_internal.h
@@
+void OPL_SDL_StartupDelay(uint64_t us);
'''

def sha(b):return hashlib.sha256(b).hexdigest()
def leb(b,p):
    n=s=0
    while True:
        x=b[p];p+=1;n|=(x&127)<<s
        if not x&128:return n,p
        s+=7
def sections(b):
    p=8;r={}
    while p<len(b):
        k=b[p];z,p=leb(b,p+1);d=b[p:p+z];p+=z
        if k:r[k]=d
    return r
def funcs(b):
    n,p=leb(b,0);r=[]
    for _ in range(n):z,p=leb(b,p);r.append(b[p:p+z]);p+=z
    return r

def build(out):
    before=WASM.read_bytes();assert sha(before)==WASM_SHA
    out.mkdir(parents=True,exist_ok=False)
    subprocess.run([str(TOOLS/'wasm2wat.exe'),str(WASM),'-o',str(out/'baseline.wat')],check=True)
    wat=(out/'baseline.wat').read_text();start=wat.index('  (func $OPL_Delay ');end=wat.index('\n  (func ',start+1)
    assert wat.count('call $OPL_Delay')==1
    detect_start=wat.index('  (func $OPL_Detect ');detect_end=wat.index('\n  (func ',detect_start+1)
    assert 'call $OPL_Delay' in wat[detect_start:detect_end]
    old=wat[start:end]
    # Binding is proved from pinned OPL_SDL_Init storing Mix_QuerySpec's frequency.
    init=wat[wat.index('  (func $OPL_SDL_Init '):];init=init[:init.index('\n  (func ',1)]
    assert 'i32.const 1159368\n' in init and 'call $Mix_QuerySpec' in init
    after=wat[:start]+DELAY+wat[end:];(out/'candidate.wat').write_text(after)
    subprocess.run([str(TOOLS/'wat2wasm.exe'),str(out/'candidate.wat'),'--debug-names','-o',str(out/'chocolate-doom.wasm')],check=True)
    subprocess.run([str(TOOLS/'wasm-validate.exe'),str(out/'chocolate-doom.wasm')],check=True)
    rebuilt=(out/'chocolate-doom.wasm').read_bytes();a,b=sections(before),sections(rebuilt)
    assert set(a)==set(b)
    for k in a:
        if k!=10:assert a[k]==b[k],f'Unrelated section {k} changed'
    f,g=funcs(a[10]),funcs(b[10]);assert len(f)==len(g)
    changed=[i for i,(x,y) in enumerate(zip(f,g)) if x!=y];assert changed==[1096],changed
    (out/'index.html').write_bytes((MUSIC/'index.html').read_bytes())
    # Make a real patch against the exact pinned source, retaining its licence.
    source_archive=ROOT/'outputs/doom/browser-20261022-r2-touch/www/Doom/doom-wasm-source.tar.gz'
    originals={}
    with tarfile.open(source_archive) as archive:
        for name in ['opl/opl.c','opl/opl_sdl.c','opl/opl_internal.h']:
            member=next(m for m in archive.getmembers() if m.name.endswith('/'+name))
            originals[name]=archive.extractfile(member).read().decode('utf-8')
    modified=dict(originals)
    function='void OPL_Delay(uint64_t us)\n{\n'
    assert modified['opl/opl.c'].count(function)==1
    modified['opl/opl.c']=modified['opl/opl.c'].replace(function,function+'''#ifdef __EMSCRIPTEN__
    /* Browser startup cannot wait for its own audio callback synchronously.
       This function is called only by OPL_Detect in the pinned artifact. */
    OPL_SDL_StartupDelay(us);
    return;
#else
''')
    closing='    SDL_DestroyCond(delay_data.cond);\n}'
    assert modified['opl/opl.c'].count(closing)==1
    modified['opl/opl.c']=modified['opl/opl.c'].replace(closing,'    SDL_DestroyCond(delay_data.cond);\n#endif\n}')
    anchor='static void OPL_SDL_Shutdown(void)'
    assert modified['opl/opl_sdl.c'].count(anchor)==1
    modified['opl/opl_sdl.c']=modified['opl/opl_sdl.c'].replace(anchor,'''// Advance the existing emulator and callback queue during browser detection.
void OPL_SDL_StartupDelay(uint64_t us)
{
    size_t samples = (us * mixing_freq + OPL_SECOND - 1) / OPL_SECOND;
    size_t bytes = samples * 4;
    void *buffer = calloc(1, bytes);
    if (buffer == NULL) { abort(); }
    OPL_Mix_Callback(NULL, buffer, bytes);
    free(buffer);
}

'''+anchor)
    header=modified['opl/opl_internal.h'];position=header.rfind('#endif');assert position>=0
    modified['opl/opl_internal.h']=header[:position]+'void OPL_SDL_StartupDelay(uint64_t us);\n\n'+header[position:]
    patch=''.join(''.join(difflib.unified_diff(originals[name].splitlines(True),modified[name].splitlines(True),fromfile='a/'+name,tofile='b/'+name)) for name in originals)
    (out/'source-equivalent.patch').write_text(patch,encoding='utf-8',newline='\n')
    (out/'source-equivalent').mkdir()
    for name,content in modified.items():
        target=out/'source-equivalent'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8',newline='\n')
    (out/'original-delay.wat').write_text(old)
    (out/'source-evidence.json').write_bytes((MUSIC/'manifest.json').read_bytes())
    manifest={'status':'OFFLINE_SINGLE_FUNCTION_DELTA_PASS_MUSIC_PHYSICAL_UNRUN','created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
      'baseline_wasm_sha256':WASM_SHA,'wasm_sha256':sha(rebuilt),'wasm_bytes':len(rebuilt),
      'index_sha256':sha((out/'index.html').read_bytes()),'index_bytes':(out/'index.html').stat().st_size,
      'allocated_function_bodies':len(f),'changed_function_bodies':changed,'changed_function_name':'OPL_Delay','imported_function_count':259,
      'unchanged_sections':[k for k in a if k!=10],'callsite_count':1,'only_callsite_function':'OPL_Detect',
      'mixing_freq_address':1159368,'new_delay_body':DELAY,'tools':{p.name:sha(p.read_bytes()) for p in (TOOLS/'wasm2wat.exe',TOOLS/'wat2wasm.exe',TOOLS/'wasm-validate.exe')},
      'source_patch_sha256':sha((out/'source-equivalent.patch').read_bytes()),
      'source_patch_limit':'Source-equivalent repair supplied for reproducibility; current binary is an exact pinned artifact transformation, not an upstream source rebuild.',
      'asset_rule':'Original shareware MUS/GENMIDI, no music downloads or new runtime assets.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    out=a.output or ROOT/'outputs/doom'/('music-opl-qualified-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    print(json.dumps({'output':str(out),'manifest':build(out)},indent=2))
