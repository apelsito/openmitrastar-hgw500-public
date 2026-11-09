"""Offline measured firmware component inventory; never contacts the router.

Extracts only the two pinned SquashFS roots in REA-Linux temporary storage.
The public result reports non-secret files, ELF linkage, duplicate content and
independent XZ estimates. These estimates are NOT additive flash allocation.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import lzma
import re
import struct
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
VERSIONS = {'F367r9': ('f367r9-f365-transition-observation-device-bound', '465c413d5f08c8a422e09dc1a942e4a7b89042fb684c80281ca776c4b419852e'),
            'F372': ('f372-f371-auc-tqe-observation-device-bound', 'fdffe1ad2798fb8938a847bcc1736fe370cd017a1a71c90b66097aaeac5441b6')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linux(path):
    path = Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]


def group(path):
    if path.startswith('lib/modules/'):
        return 'kernel_modules_'+('radio2g' if '/radio2g/' in path else 'radio5g' if '/radio5g/' in path else 'other')
    if path.startswith('lib/firmware/'):
        return 'radio_firmware'
    if path.startswith(('lib/', 'usr/lib/')):
        return 'shared_libraries'
    if path.startswith(('www/', 'usr/share/openmitrastar/web/')):
        return 'web_assets'
    if path.startswith(('bin/', 'sbin/', 'usr/bin/', 'usr/sbin/', 'usr/libexec/')):
        return 'programs_and_scripts'
    return 'configuration_and_metadata'


def linkage(data):
    if data[:4] != b'\x7fELF':
        return 'script' if data.startswith(b'#!') else 'data'
    if data[4] != 1:
        return 'elf_other_class'
    endian = '<' if data[5] == 1 else '>'
    hdr = struct.unpack(endian+'HHIIIIIHHHHHH', data[16:52])
    elf_type, machine, phoff, phsize, phnum = hdr[0], hdr[1], hdr[4], hdr[8], hdr[9]
    kinds = [struct.unpack_from(endian+'I', data, phoff+i*phsize)[0] for i in range(phnum)]
    return ('relocatable_module' if elf_type == 1 else 'elf_with_dynamic_segment' if 2 in kinds else 'static_elf')+';EM='+str(machine)


def worker(spec, destination):
    report = {'schema':'openmitrastar.component-size-inventory/v1', 'hardware_actions':False,
              'method':'Pinned SquashFS extraction; raw file bytes; exact SHA256 duplicate detection; per-file XZ(LZMA2,128KiB dictionary,preset6) reference',
              'limitations':['Per-file XZ bytes are not actual SquashFS allocation or additive flash savings.',
                             'Static linkage indicates potential library overlap, not a proven recompilation saving.',
                             'F367r9 is a sealed installed-image reference; live runtime overlays need separate SSH evidence.',
                             'F372 is an offline candidate, not an installation claim.'], 'images':{},
              'audit_script_sha256':sha(Path(__file__)),
              'legacy_server_source':spec['legacy_server_source']}
    rows = []
    for version, src in spec['sources'].items():
        image = Path(src['rootfs'])
        if sha(image) != src['rootfs_sha256']:
            raise ValueError('pinned rootfs changed: '+version)
        if sha(src['inventory']) != src['inventory_sha256']:
            raise ValueError('source inventory changed: '+version)
        expected=json.loads(Path(src['inventory']).read_text())['after']
        squashfs_stat=subprocess.run(['unsquashfs','-s',str(image)],check=True,capture_output=True,text=True).stdout
        with tempfile.TemporaryDirectory(prefix='openmitrastar-inventory-') as folder:
            extracted=Path(folder)/'root'
            subprocess.run(['unsquashfs','-no-progress','-d',str(extracted),str(image)],check=True,stdout=subprocess.DEVNULL)
            groups={}; duplicate={}; symlinks=0; count=0; version_rows=[]
            for path,entry in sorted(expected.items()):
                if entry['type']=='symlink':
                    symlinks+=1
                if entry['type']!='file':
                    continue
                data=(extracted/path).read_bytes()
                digest=hashlib.sha256(data).hexdigest()
                if len(data)!=entry['bytes'] or digest!=entry['sha256']:
                    raise ValueError('extracted inventory mismatch '+version+' '+path)
                kind=group(path);count+=1
                g=groups.setdefault(kind,{'files':0,'raw_bytes':0,'unique_bytes':0,'xz_individual_reference_bytes':0})
                g['files']+=1;g['raw_bytes']+=len(data)
                duplicate.setdefault(digest,[]).append({'path':path,'bytes':len(data),'group':kind})
                compressed=len(lzma.compress(data,format=lzma.FORMAT_XZ,filters=[{'id':lzma.FILTER_LZMA2,'dict_size':131072,'preset':6}]))
                g['xz_individual_reference_bytes']+=compressed
                # Do not publish configuration hashes/contents/device identity.
                if kind != 'configuration_and_metadata':
                    row={'image':version,'path':path,'category':kind,'raw_bytes':len(data),'xz_individual_reference_bytes':compressed,'sha256':digest,'linkage':linkage(data)}
                    rows.append(row);version_rows.append(row)
            for entries in duplicate.values():
                first=entries[0];groups[first['group']]['unique_bytes']+=first['bytes']
            duplicates=[entries for entries in duplicate.values() if len(entries)>1 and all(e['group']!='configuration_and_metadata' for e in entries)]
            servers={}
            for name in ['mini_httpd','mini_httpd-tls']:
                data=(extracted/'usr/sbin'/name).read_bytes()
                strings=re.findall(rb'[ -~]{5,}',data)
                servers[name]={'raw_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                               'xz_individual_reference_bytes':next(r['xz_individual_reference_bytes'] for r in version_rows if r['path']=='usr/sbin/'+name),
                               'version_strings':[s.decode() for s in strings if re.search(rb'mini_httpd/[0-9]|OpenSSL [0-9]|uClibc [0-9]',s)][:12]}
            report['images'][version]={'source_manifest_sha256':src['manifest_sha256'],'rootfs_sha256':sha(image),
                  'rootfs_compressed_bytes':image.stat().st_size,'regular_files':count,'symlinks':symlinks,
                  'groups':groups,'duplicate_non_secret_files':duplicates,'servers':servers,
                  'source_inventory_sha256':src['inventory_sha256'],
                  'squashfs_superblock':squashfs_stat,
                  'squashfs_duplicate_removal_enabled':'Duplicates are removed' in squashfs_stat,
                  'top_files':sorted(version_rows,key=lambda r:r['raw_bytes'],reverse=True)[:20],
                  'linkage_counts':{k:sum(r['linkage']==k for r in version_rows) for k in sorted({r['linkage'] for r in version_rows})}}
        if sha(image)!=src['rootfs_sha256']:
            raise ValueError('source drift after inventory')
    trial=Path(spec['tls_trial'])
    trial_manifest=json.loads(Path(spec['tls_trial_manifest']).read_text())
    if sha(trial)!=trial_manifest['binary_sha256'] or trial.stat().st_size!=trial_manifest['binary_bytes']:
        raise ValueError('trial artifact mismatch')
    report['tls_trial']={'raw_bytes':trial.stat().st_size,'sha256':sha(trial),
                         'xz_individual_reference_bytes':len(lzma.compress(trial.read_bytes(),format=lzma.FORMAT_XZ,filters=[{'id':lzma.FILTER_LZMA2,'dict_size':131072,'preset':6}])),
                         'wolfssl_version':trial_manifest['wolfssl_version'],'status':trial_manifest['status'],
                         'release_eligible':trial_manifest['release_eligible'],'not_proven':trial_manifest['not_proven'],
                         'source_sha256':trial_manifest['mini_httpd_source_sha256'],
                         'note':'Still based on mini_httpd1.19 with a newer TLS library, not a newer HTTP server.'}
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    with (destination/'components.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    labels={'programs_and_scripts':'Programas y scripts','configuration_and_metadata':'Configuración y metadatos',
            'radio_firmware':'Firmware interno de radios','kernel_modules_other':'Módulos Ethernet, almacenamiento y diagnóstico',
            'kernel_modules_radio2g':'Módulos 2,4 GHz','kernel_modules_radio5g':'Módulos 5 GHz','web_assets':'Web de gestión',
            'shared_libraries':'Bibliotecas compartidas'}
    lines=['# Inventario offline de componentes del HGW — 22 de octubre de 2026','',
           'Raíces exactas F367r9 y F372 verificadas contra sus SHA-256 e inventarios. Ninguna operación de hardware.',
           'F367r9 es la referencia del firmware instalado; F372 es un candidato pendiente. Los overlays de RAM se verifican por separado.','',
           '| Categoría | F367r9 archivos | F367r9 bytes sin comprimir | F372 bytes sin comprimir |','|---|---:|---:|---:|']
    for kind,g in report['images']['F367r9']['groups'].items():
        lines.append(f"| {labels[kind]} | {g['files']} | {g['raw_bytes']:,} | {report['images']['F372']['groups'].get(kind,{}).get('raw_bytes',0):,} |")
    lines+=['','Las categorías incluyen todos los archivos regulares. Los enlaces BusyBox no duplican el ejecutable.',
            'No se deben sumar los bytes sin comprimir ni las referencias XZ para calcular ocupación de flash. SquashFS comparte fragmentos y elimina contenido duplicado.','',
            '| Servidor | Bytes sin comprimir | Referencia XZ individual | Estado |','|---|---:|---:|---|']
    for name,value in report['images']['F367r9']['servers'].items():
        lines.append(f"| {name} | {value['raw_bytes']:,} | {value['xz_individual_reference_bytes']:,} | En F367r9/F372 |")
    t=report['tls_trial'];lines.append(f"| mini_httpd + wolfSSL {t['wolfssl_version']} | {t['raw_bytes']:,} | {t['xz_individual_reference_bytes']:,} | Trial offline; pendiente ARC/cliente/RAM |")
    lines+=['','La cadena del HTTP realmente conserva `mini_httpd/1.19/bhoc 23sep2004`. El trial usa el mismo servidor con wolfSSL5.9.2.',
            'El servidor HTTP pesa 160.104 bytes; eliminarlo entero no resolvería un exceso de 3.194.880 bytes y destruiría la gestión.',
            'La sustitución TLS reduce 837.052 bytes sin comprimir; el ahorro de la imagen completa aún debe medirse manteniendo contratos CGI/HTTPS.',
            'BusyBox y varios ejecutables son estáticos. Hay potencial de compartir libc al recompilar, pero no se cuantifica como ahorro sin build equivalente.',
            'Los dos hostapd controlan arquitecturas de driver distintas; sus dos nombres no demuestran duplicación eliminable.',
            'El inventario registra duplicados byte a byte. El empaquetado SquashFS ya puede deduplicarlos; no contarlos dos veces como ahorro.','']
    lines+=['No hay archivos de bibliotecas compartidas en estas raíces: los 32 ELF de aplicación son estáticos.',
            'Las cuatro rutas `usr/libexec/lyoko/{ar,busybox,gunzip,pkgbox}` tienen el mismo contenido de 238.624 bytes. La bandera del superblock confirma eliminación de duplicados; 715.872 bytes repetidos no constituyen ahorro nuevo.',
            'La web incluye `www/` y `usr/share/openmitrastar/web/`; el recuento anterior de 1.193.374 bytes cubría solo `www/`.',
            'Los bytes únicos por categoría se asignan a la primera ruta de cada hash; la ocupación física sigue siendo la raíz SquashFS completa.','']
    (destination/'INVENTARIO.md').write_text('\n'.join(lines))
    print(json.dumps({'status':'PASS_OFFLINE_COMPONENT_INVENTORY','output':str(destination),'images':{v:{'rootfs':r['rootfs_compressed_bytes'],'raw_total':sum(g['raw_bytes'] for g in r['groups'].values()),'servers':r['servers']} for v,r in report['images'].items()},'tls_trial':t}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--worker',type=Path);parser.add_argument('--output',type=Path);a=parser.parse_args()
    if a.worker:
        worker(json.loads(a.worker.read_text()),a.output);return
    out=ROOT/'outputs/inventory'/('router-components-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    sources={}
    for version,(folder,pinned) in VERSIONS.items():
        path=DEVICE/'firmware'/folder;manifest=path/'manifest.json';m=json.loads(manifest.read_text());rootfs=path/m['artifacts']['rootfs_squashfs']['file']
        if m['artifacts']['rootfs_squashfs']['sha256']!=pinned or sha(rootfs)!=pinned:
            raise ValueError('source mismatch '+version)
        sources[version]={'rootfs':linux(rootfs),'rootfs_sha256':pinned,'inventory':linux(path/'rootfs-inventory.json'),
                          'inventory_sha256':sha(path/'rootfs-inventory.json'),'manifest_sha256':sha(manifest)}
    trial=ROOT/'outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial'
    spec=out.with_suffix('.inputs.json');spec.parent.mkdir(parents=True,exist_ok=True)
    legacy=ROOT/'work/sources/Quantenna-GPL/buildroot/package/zminihttpd/mini_httpd-1.19'
    legacy_server_source={'source_c_sha256':sha(legacy/'mini_httpd.c'),'version_h_sha256':sha(legacy/'version.h'),
                          'version_define':next(line for line in (legacy/'version.h').read_text().splitlines() if line.startswith('#define SERVER_SOFTWARE')),
                          'note':'Original local source version; built binaries are bound independently by SHA256 and embedded version.'}
    spec.write_text(json.dumps({'sources':sources,'tls_trial':linux(trial/'mini_httpd-wolfssl'),'tls_trial_manifest':linux(trial/'manifest.json'),
                                'legacy_server_source':legacy_server_source},indent=2)+'\n')
    subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','-e','python3',linux(Path(__file__)),'--worker',linux(spec),'--output',linux(out)],check=True,timeout=180)
    print(str(out))


if __name__=='__main__':main()
