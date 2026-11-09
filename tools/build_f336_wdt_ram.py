"""Build F336 RAM-only watchdog kernel against exact read-only F321 flash FS.

Never starts TFTP, opens UART/SSH, reads MMIO or changes persistent boot state.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,dataclasses,json,lzma,shlex,struct,subprocess,sys,zlib
from elftools.elf.elffile import ELFFile
import f336_wdt_ram_contract as c
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def extract_embedded(elf_path):
    with elf_path.open('rb') as f:
        elf=ELFFile(f);symbols=elf.get_section_by_name('.symtab')
        symbol=symbols.get_symbol_by_name('__dtb_topaz_mitrastar_squashfs_begin')[0];address=int(symbol['st_value'])
        for section in elf.iter_sections():
            if int(section['sh_addr'])<=address<int(section['sh_addr'])+int(section['sh_size']):
                offset=address-int(section['sh_addr']);data=section.data()[offset:];size=struct.unpack_from('>I',data,4)[0]
                c.require(data[:4]==b'\xd0\x0d\xfe\xed' and size<=len(data),'embedded DT bounds');return data[:size],address
    raise ValueError('embedded DT not found')
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--resume-built-a',type=Path);args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=c.DEVICE/'analysis'/('f336-wdt-ram-'+stamp);out.mkdir(parents=True,exist_ok=False)
    f321_image=c.F321/(c.F321_BASE+'.webformat.bin');f321_dtb=c.F321/(c.F321_BASE+'.dtb');f321_rootfs=c.F321/(c.F321_BASE+'.rootfs.squashfs')
    c.require(c.sha(f321_image)=='eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18','F321 image changed')
    c.require(c.sha(f321_rootfs)=='75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e','F321 rootfs changed')
    c.require(f321_image.read_bytes()[0x180000:]==f321_rootfs.read_bytes(),'F321 image/rootfs binding')
    embedded,_=extract_embedded(c.F321/(c.F321_BASE+'.vmlinux'));c.require(embedded==f321_dtb.read_bytes(),'F321 DT/ELF binding')
    original=json.loads((c.F329/'result.json').read_text());c.require(original['status']=='PASS_OFFLINE_BUILD_PHYSICAL_GATES_UNRUN','F329 not qualified')
    for name,meta in original['artifacts'].items():c.require(c.sha(c.F329/name)==meta['sha256'],'F329 artifact drift '+name)
    dt=out/'f336-input.dtb';dt_contract=c.make_dt(f321_dtb,dt)
    driver=out/'dw_wdt.c';driver.write_bytes(c.driver_observation_overlay(c.F329_SOURCE/'drivers/watchdog/dw_wdt.c'))
    config=(c.F329/'f329.config').read_text();c.require(config.count('# CONFIG_WATCHDOG_SYSFS is not set')==1,'F329 sysfs config drift')
    (out/'f336-input.config').write_bytes(config.replace('# CONFIG_WATCHDOG_SYSFS is not set','CONFIG_WATCHDOG_SYSFS=y').encode())
    rootbuild='/home/user/openmitrastar-build/f336-wdt-ram-'+stamp;parent=original['isolated_build_directory'];q=shlex.quote
    resume=None
    if args.resume_built_a:
        resume=args.resume_built_a.resolve();old=json.loads((resume/'result.json').read_text())
        c.require(resume.is_relative_to(c.DEVICE/'analysis') and old['status']=='BUILD_FAILED','unexpected resume input')
        for name in ['dw_wdt.c','f336-input.config','f336-input.dtb']:
            c.require((resume/name).read_bytes()==(out/name).read_bytes(),'resume source/input changed '+name)
        rootbuild=old['isolated_build']
    tc=linux(c.ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    script=f'''set -eu
out={q(linux(out))}
build={q(rootbuild)}
parent={q(parent)}
tc={q(tc)}
src="$build/linux"
dtc -I dtb -O dts "$out/f336-input.dtb" > "$out/f336-input.dts" 2> "$out/dtc-input.log"
'''
    if resume:
        script+=f'''test -d "$src"
cmp "$out/dw_wdt.c" "$src/drivers/watchdog/dw_wdt.c"
cmp "$out/f336-input.dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
mkdir "$out/a"
cp {q(linux(resume/'a'))}/f336.* "$out/a/"
'''
    else:
        script+='''test ! -e "$build"
mkdir -p "$build"
cp -a --reflink=auto "$parent/linux" "$src"
cp "$out/f336-input.dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp "$out/dw_wdt.c" "$src/drivers/watchdog/dw_wdt.c"
'''
    script+=f'''test "$(sha256sum {q(linux(c.ROOT/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'))} | cut -d' ' -f1)" = 04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18
for lane in a b; do
 if [ "$lane" != a ] || [ {q('yes' if resume else 'no')} != yes ]; then
 kout="$build/$lane-{stamp}"
 mkdir "$kout" "$out/$lane"
 cp "$out/f336-input.config" "$kout/.config"
 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" olddefconfig > "$out/config-$lane.log" 2>&1
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f336-ram-watchdog KBUILD_BUILD_VERSION=336 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$kout=/f336-output" -j4 vmlinux dtbs uImage.bin > "$out/build-$lane.log" 2>&1
 cp "$kout/vmlinux" "$out/$lane/f336.vmlinux"
 cp "$kout/.config" "$out/$lane/f336.config"
 cp "$kout/arch/arc/boot/uImage.bin" "$out/$lane/f336.uncompressed.uImage"
 cp "$kout/arch/arc/boot/vmlinux.bin" "$out/$lane/f336.raw.bin"
 cp "$kout/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$out/$lane/f336.dtb"
 fi
 "${{tc}}objcopy" -O binary -R .note -R .note.gnu.build-id -R .comment -S "$out/$lane/f336.vmlinux" "$out/$lane/f336.raw.bin"
 {q(linux(c.ROOT/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'))} --keep --best "$out/$lane/f336.raw.bin" -c > "$out/$lane/f336.lzma"
 python3 {q(linux(c.ROOT/'tools/make_q1_lzma_uimage.py'))} "$out/$lane/f336.uncompressed.uImage" "$out/$lane/f336.lzma" "$out/$lane/f336.lzma.uImage" > "$out/uimage-$lane.log"
 python3 {q(linux(c.ROOT/'tools/pack_topaz_webformat.py'))} "$out/$lane/f336.lzma.uImage" {q(linux(c.ROOT/'Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin'))} "$out/$lane/F336-WDT-RAM-ONLY-NOT-A-FLASH-IMAGE.ras.bin" > "$out/ras-$lane.log"
done
cmp "$out/a/f336.vmlinux" "$out/b/f336.vmlinux"
cmp "$out/a/F336-WDT-RAM-ONLY-NOT-A-FLASH-IMAGE.ras.bin" "$out/b/F336-WDT-RAM-ONLY-NOT-A-FLASH-IMAGE.ras.bin"
'''
    (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
    result=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True)
    (out/'launcher.stdout').write_bytes(result.stdout);(out/'launcher.stderr').write_bytes(result.stderr)
    report={'schema':'openmitrastar.f336-wdt-ram-build/v1','created_utc':stamp,'status':'BUILD_FAILED','exit_code':result.returncode,'dt_contract':dt_contract,'isolated_build':rootbuild,'reused_compiled_a':str(resume) if resume else None,'hardware_actions':False,'watchdog_armed':False,'flash_eligible':False,'rootfs_bundled':False,'firmware_flash_image':False}
    if not result.returncode:
        kernel=out/'a/f336.vmlinux';image=out/'a/F336-WDT-RAM-ONLY-NOT-A-FLASH-IMAGE.ras.bin';raw=out/'a/f336.raw.bin'
        body,address=extract_embedded(kernel);(out/'embedded.dtb').write_bytes(body)
        c.require(c.node_map(out/'embedded.dtb')==c.node_map(dt),'embedded DT differs from reviewed F336 tree')
        c.require(body== (out/'a/f336.dtb').read_bytes(),'built sidecar is not kernel DT')
        c.require(raw.read_bytes()[address-c.LOAD:address-c.LOAD+len(body)]==body,'raw payload does not contain the embedded DT at its linked address')
        c.require(c.MARKER in body,'RAM identity marker missing')
        cfg=(out/'a/f336.config').read_text().splitlines()
        for key in ['CONFIG_WATCHDOG_SYSFS=y','CONFIG_WATCHDOG_NOWAYOUT=y','# CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED is not set','# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set','# CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY is not set','CONFIG_INITRAMFS_SOURCE=""']:c.require(key in cfg,'unsafe F336 config '+key)
        with kernel.open('rb') as f:
            elf=ELFFile(f);entry=int(elf.header['e_entry']);end=int(elf.get_section_by_name('.symtab').get_symbol_by_name('_end')[0]['st_value'])
        c.require(entry==c.ENTRY and c.LOAD<entry<c.LOAD+raw.stat().st_size,'RAM kernel entry drift')
        c.require(c.STAGING+image.stat().st_size<c.CRC_SCRATCH<c.LOAD and end<c.DDR_END,'RAM overlap or overrun')
        c.require(lzma.decompress((out/'a/f336.lzma').read_bytes(),format=lzma.FORMAT_ALONE)==raw.read_bytes(),'RAM compressed payload changed')
        boot=image_to_dict(validate_bootbase_slot('F336-RAM-format-only',image.read_bytes(),c.CRC_SCRATCH-c.STAGING));c.require(boot['accepted_by_contract'],'Bootbase RAS contract failed')
        c.require(int(boot['header']['load'],16)==c.LOAD and int(boot['header']['entry'],16)==entry,'Bootbase does not enter this kernel')
        (out/'bootbase-format.json').write_text(json.dumps(boot,indent=2)+'\n')
        report.update(status='PASS_OFFLINE_RAM_ARTIFACT_PHYSICAL_GATES_UNRUN',reproducible=True,
            artifact={'path':str(image),'bytes':image.stat().st_size,'sha256':c.sha(image),'crc32':f'{zlib.crc32(image.read_bytes())&0xffffffff:08x}'},
            embedded_dtb={'address':hex(address),'sha256':c.sha(out/'embedded.dtb'),'matches_built_sidecar':True},
            memory={'staging':hex(c.STAGING),'crc_scratch':hex(c.CRC_SCRATCH),'load':hex(c.LOAD),'entry':hex(entry),'kernel_end':hex(end),'ddr_end':hex(c.DDR_END)},
            rootfs={'path':str(f321_rootfs),'sha256':c.sha(f321_rootfs),'physical_address':'0x90960000','window':'0x460000','access':'read-only on preserved F321 mtd4'},
            config_delta=['WATCHDOG_SYSFS enabled; all F329 no-autoarm controls preserved'],driver_observation_overlay_sha256=c.sha(driver))
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'result':str(out/'result.json')},indent=2));return 0 if report['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
