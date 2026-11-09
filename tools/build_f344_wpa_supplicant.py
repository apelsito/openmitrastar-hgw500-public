"""Offline OEM MADWIFI supplicant/CLI build with original OpenSSL configuration."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shlex,shutil,subprocess,tarfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/userspace/f344-wpa-madwifi/source'
VENDOR=ROOT/'work/sources/Quantenna-GPL/buildroot/package/wpa_supplicant'
ARCHIVE=ROOT/'work/sources/Quantenna-GPL/buildroot/download_backup/openssl-1.0.2d.tar.gz'
SSL_PATCH=ROOT/'work/sources/Quantenna-GPL/buildroot/package/openssl/openssl-1.0.2d.patch'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--reuse-crypto-a-result',type=Path);ap.add_argument('--reuse-crypto-a-proof',type=Path);a=ap.parse_args()
 reuse=None;reuse_proof=None
 if a.reuse_crypto_a_result:
  old=json.loads(a.reuse_crypto_a_result.read_text());reuse_proof=json.loads(a.reuse_crypto_a_proof.read_text())
  if old['archive']['sha256']!='671c36487785628a703374c652ad2cebea45fa920ae5681515df25d9f2c9a8c8' or not (a.reuse_crypto_a_result.parent/'a/openssl-build.log').is_file():raise ValueError('invalid crypto reuse')
  reuse=old['isolated_build']+'/a/openssl-1.0.2d'
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/userspace'/('f344-wpa-madwifi-'+stamp);out.mkdir(parents=True,exist_ok=False)
 if sha(ARCHIVE)!='671c36487785628a703374c652ad2cebea45fa920ae5681515df25d9f2c9a8c8':raise ValueError('OpenSSL archive drift')
 with tarfile.open(ARCHIVE,'r:gz') as archive:
  for member in archive.getmembers():
   parts=Path(member.name).parts
   if not parts or parts[0]!='openssl-1.0.2d' or '..' in parts or Path(member.name).is_absolute() or member.isdev():raise ValueError('unsafe archive member')
 config=(VENDOR/'wpa_supplicant-1.1.config').read_text()
 if any(x not in config.splitlines() for x in ['CONFIG_DRIVER_MADWIFI=y','CONFIG_DRIVER_WEXT=y','CONFIG_TLS=openssl','CONFIG_CTRL_IFACE=y']):raise ValueError('vendor profile drift')
 active=[line for line in config.splitlines() if re.match(r'^CONFIG_[A-Z0-9_]+=\S+',line)]
 shutil.copytree(SOURCE,out/'source');(out/'vendor.config').write_text(config);(out/'effective-feature-profile.json').write_text(json.dumps(active,indent=2)+'\n')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
 build='/home/user/openmitrastar-build/f344-wpa-madwifi-'+stamp
 script=f'''set -eu
out={q(linux(out))}
build={q(build)}
tc={q(tc)}
sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot
qtn_headers={q(linux(ROOT/'work/sources/Quantenna-GPL/drivers/include/shared'))}
madwifi_headers={q(linux(VENDOR/'madwifi'))}
test ! -e "$build"
mkdir -p "$build"
build_lane() {{
 lane="$1"
 mkdir -p "$build/$lane" "$out/$lane"
 if [ "$lane" = a ] && [ {q('yes' if reuse else 'no')} = yes ]; then
  cp -a --reflink=auto {q(reuse or '/unused')} "$build/$lane/openssl-1.0.2d"
  cp {q(linux(a.reuse_crypto_a_result.parent/'a/openssl-build.log') if reuse else '/unused')} "$out/$lane/openssl-build.log"
  cp {q(linux(a.reuse_crypto_a_proof) if reuse else '/unused')} "$out/$lane/reused-object-proof.json"
  python3 - "$build/$lane/openssl-1.0.2d" "$out/$lane/reused-object-proof.json" <<'PY'
from pathlib import Path
import sys,json,hashlib
root=Path(sys.argv[1]);proof=json.loads(Path(sys.argv[2]).read_text())
for library in proof.values():
 for name,digest in library['object_sha256'].items():
  found=list(root.rglob(name));assert len(found)==1 and hashlib.sha256(found[0].read_bytes()).hexdigest()==digest,name
PY
 else
 tar -xzf {q(linux(ARCHIVE))} -C "$build/$lane"
 ssl="$build/$lane/openssl-1.0.2d"
 patch -d "$ssl" -p1 < {q(linux(SSL_PATCH))} > "$out/$lane/openssl-patch.log"
 python3 - "$ssl/util/mkbuildinf.pl" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text();assert s.count('$date = localtime();')==1
p.write_text(s.replace('$date = localtime();', '$date = gmtime($ENV{{"SOURCE_DATE_EPOCH"}});'))
PY
 (cd "$ssl" && perl ./Configure linux-arc no-asm no-shared threads no-idea no-mdc2 no-rc5 no-camellia no-hw no-sse2 --cross-compile-prefix="$tc" --prefix=/usr --openssldir=/etc/ssl) > "$out/$lane/openssl-configure.log" 2>&1
 SOURCE_DATE_EPOCH=1788566400 make -C "$ssl" -j4 build_libs CC="${{tc}}gcc" AR="${{tc}}ar rcsD" RANLIB="${{tc}}ranlib -D" CFLAG="--sysroot=$sysroot -std=gnu99 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -DL_ENDIAN -DTERMIO -D_REENTRANT -DOPENSSL_THREADS -D_GNU_SOURCE -Wno-error=implicit-function-declaration" > "$out/$lane/openssl-build.log" 2>&1
 fi
 ssl="$build/$lane/openssl-1.0.2d"
 python3 {q(linux(ROOT/'tools/f344_rebuild_static_archives.py'))} --openssl-dir "$ssl" --output "$out/$lane/verified-crypto" --build-log "$out/$lane/openssl-build.log" --ar "${{tc}}ar" > "$out/$lane/archive-integrity.stdout"
 cp -a "$out/source" "$build/$lane/wpa"
 wpa="$build/$lane/wpa/wpa_supplicant"
 python3 - "$out/vendor.config" "$wpa/.config" "$sysroot" "$qtn_headers" "$madwifi_headers" "$ssl" "$out/$lane/verified-crypto" <<'PY'
from pathlib import Path
import sys,re
source,target,sysroot,qtn,madwifi,ssl,libs=sys.argv[1:]
lines=Path(source).read_text().splitlines()
lines=[line for line in lines if not re.match(r'^(CFLAGS|LIBS(?:_[a-z])?)\\s*\\+?=',line)]
lines += [f'CFLAGS += --sysroot={{sysroot}} -std=gnu99 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -D_GNU_SOURCE',
 f'CFLAGS += -I{{qtn}} -I{{madwifi}} -I{{ssl}}/include',
 f'LDFLAGS += --sysroot={{sysroot}} -static -Wl,--gc-sections',
 f'LIBS += -L{{libs}} -ldl', f'LIBS_c += -L{{libs}} -ldl',
 'CFLAGS += -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=discarded-qualifiers']
Path(target).write_text('\\n'.join(lines)+'\\n')
PY
 make -C "$wpa" clean > "$out/$lane/wpa-clean.log" 2>&1
 SOURCE_DATE_EPOCH=1788566400 make -C "$wpa" -j4 wpa_supplicant wpa_cli CC="${{tc}}gcc" AR="${{tc}}ar" PKG_CONFIG=/bin/false V=1 > "$out/$lane/wpa-build.log" 2>&1
 for binary in wpa_supplicant wpa_cli; do
  cp "$wpa/$binary" "$out/$lane/$binary.unstripped"
  "${{tc}}strip" --strip-unneeded "$wpa/$binary"
  cp "$wpa/$binary" "$out/$lane/$binary"
  "${{tc}}readelf" -h -l -d "$out/$lane/$binary" > "$out/$lane/$binary.elf.txt"
  "${{tc}}objdump" -d "$out/$lane/$binary" > "$out/$lane/$binary.disasm.txt"
  if grep -Eq '\\b(llock|scond)\\b' "$out/$lane/$binary.disasm.txt"; then exit 1; fi
  if grep -q 'Requesting program interpreter' "$out/$lane/$binary.elf.txt"; then exit 1; fi
  grep -q 'Flags:.*0x403' "$out/$lane/$binary.elf.txt"
 done
 cp "$wpa/.config" "$out/$lane/effective.config"
 cp "$out/$lane/verified-crypto/libssl.a" "$out/$lane/verified-crypto/libcrypto.a" "$out/$lane/"
 cp "$ssl/Makefile" "$out/$lane/openssl-Makefile"
}}
build_lane a & lane_a=$!
build_lane b & lane_b=$!
status=0
wait "$lane_a" || status=1
wait "$lane_b" || status=1
[ "$status" = 0 ] || exit 1
cmp "$out/a/wpa_supplicant" "$out/b/wpa_supplicant"
cmp "$out/a/wpa_cli" "$out/b/wpa_cli"
cmp "$out/a/libssl.a" "$out/b/libssl.a"
cmp "$out/a/libcrypto.a" "$out/b/libcrypto.a"
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=1200)
 (out/'launcher.stdout').write_bytes(p.stdout);(out/'launcher.stderr').write_bytes(p.stderr)
 report={'schema':'openmitrastar.f344-oem-supplicant-build/v1','status':'FAIL_BUILD' if p.returncode else 'PASS_OFFLINE_REPRODUCIBLE_OEM_SUPPLICANT',
  'returncode':p.returncode,'isolated_build':build,'vendor_features':active,'hardware_actions':False,'wifi_or_rf_tests':False,
  'archive':{'path':str(ARCHIVE),'sha256':sha(ARCHIVE)},'vendor_openssl_patch_sha256':sha(SSL_PATCH),
  'source_hashes':{str(x.relative_to(ROOT)):sha(x) for x in sorted(SOURCE.rglob('*')) if x.is_file()},
  'artifacts':{name:{'path':str(out/'a'/name),'bytes':(out/'a'/name).stat().st_size,'sha256':sha(out/'a'/name)} for name in ['wpa_supplicant','wpa_cli','libssl.a','libcrypto.a'] if (out/'a'/name).exists()},
  'reproducible':not p.returncode,'symvers':'not applicable: userspace ELF executables/static libraries',
  'crypto_a_reuse':str(a.reuse_crypto_a_result) if reuse else None,'crypto_a_reuse_proof_sha256':sha(a.reuse_crypto_a_proof) if reuse else None,
  'archive_formation':'one deterministic archive pass with exact member-byte checks and membership from actual archive commands',
  'compatibility_change':'os_sleep uses the existing nanosleep/EINTR recipe for the noatomic sysroot; build paths and reproducible OpenSSL metadata only',
  'limitations':['MADWIFI scan implementation ignores params.freqs; caller needs real driver channel mask','STATUS does not include frequency; use driver readback','-r is parsed and stored exactly as OEM; actual repeater mode is a separate driver operation']}
 report['arc_execution']='UNRUN; available Linux-user emulator has no ARC700 decoder; no router test authorized'
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'returncode':p.returncode},indent=2));return p.returncode
if __name__=='__main__':raise SystemExit(main())
