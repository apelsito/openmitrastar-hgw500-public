"""Seal a local Ethernet source/REA handoff, never a flashable image."""
from datetime import datetime, timezone
import hashlib, json, re, shutil, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CAMPAIGN=ROOT/'outputs/rea/ethernet-full-20261022T132851Z'
BUILD=ROOT/'outputs/rea/ethernet-f374-build-20261022T135845610793Z'
BASELINE=ROOT/'outputs/rea/ethernet-baseline-20261022T133249267080Z'
REVIEW=ROOT/'outputs/rea/ethernet-r3-final-review-20261022T1401144672462Z'
FIXTURE=ROOT/'outputs/rea/f374r3-rx-quiesce-fixture-20261022T141640Z'
OEM=ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra'
GPL=ROOT/'work/sources/Quantenna-GPL'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=ROOT/'outputs/handoffs'/('hgw500-ethernet-rea-'+stamp)
    out.mkdir(parents=True,exist_ok=False)
    stage=out/'package';stage.mkdir();pins={};files={}
    def add(src,dst):
        src=Path(src).resolve();dest=stage/dst
        assert src.is_file() and not src.is_symlink(),str(src)
        assert dest.is_relative_to(stage) and dst not in files,'invalid/duplicate output '+str(dst)
        digest=sha(src);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dest)
        assert sha(dest)==digest,'copy mismatch'
        pins[str(src)]=digest;files[dst]={'bytes':dest.stat().st_size,'sha256':digest,'source':str(src)}
    def tree(src,dst,allowed=None):
        for p in sorted(Path(src).rglob('*')):
            if p.is_file() and not p.is_symlink() and (allowed is None or p.suffix in allowed):
                add(p,(Path(dst)/p.relative_to(src)).as_posix())
    build=json.loads((BUILD/'result.json').read_text())
    assert build['status']=='PASS_OFFLINE_F374_COMPLETE_MODULE' and build['reproducible']
    assert build['modules'][0]['sha256']==build['modules'][1]['sha256']=='d1a0fbb05b876855454f65519a0ecc64c20106c1c437174e2519281f99f46eed'
    baseline=json.loads((BASELINE/'result.json').read_text())
    assert baseline['whole_file_exact'] and baseline['status']=='PASS_OFFLINE_COMPLETE_ETHERNET_BASELINE'
    add(ROOT/'docs/OPENMITRASTAR_ETHERNET_REA_F374R3_20261022.md','LEEME_ETHERNET.md')
    # Render links against the delivered ZIP layout, preserving the workspace
    # source and recording this explicitly as a derived entry.
    readme=stage/'LEEME_ETHERNET.md';content=readme.read_text()
    linkmap={
        '../outputs/rea/ethernet-full-20261022T132851Z/final-r3-coverage/REPORT.md':'evidence/coverage/REPORT.md',
        '../outputs/rea/ethernet-coverage-20261022T133734Z/REPORT.md':'docs/oem-callback-seed-audit.md',
        '../outputs/rea/ethernet-baseline-20261022T133249267080Z/result.json':'evidence/build-f352/result.json',
        '../work/kernel-port/f374r3-ethernet-rx-quiesce/qtn-topaz-emac-f352.c':'source/f374r3/qtn-topaz-emac-f352.c',
        '../outputs/rea/ethernet-f374-build-20261022T135845610793Z/result.json':'evidence/build-f374r3/result.json',
        '../outputs/rea/f374r3-rx-quiesce-fixture-20261022T141640Z/result.json':'evidence/fault-fixture/result.json',
        '../outputs/rea/ethernet-r3-final-review-20261022T1401144672462Z/REVIEW.md':'evidence/final-review/REVIEW.md',
        '../outputs/rea/ethernet-source-audit-20261022-133356Z/REPORT.md':'docs/source-audit.md'}
    for before,after in linkmap.items():
        assert content.count(']('+before+')')==1,'missing README link '+before
        content=content.replace(']('+before+')',']('+after+')')
    readme.write_text(content)
    files['LEEME_ETHERNET.md'].update(bytes=readme.stat().st_size,sha256=sha(readme),transformation='relative links resolved against package layout')
    for name in ('OPENMITRASTAR_F352_DUAL_ETHERNET.md','OPENMITRASTAR_F362_DUAL_ETHERNET_IMAGE.md'):
        add(ROOT/'docs'/name,'docs/'+name)
    add(ROOT/'outputs/rea/ethernet-source-audit-20261022-133356Z/REPORT.md','docs/source-audit.md')
    add(ROOT/'outputs/rea/ethernet-coverage-20261022T133734Z/REPORT.md','docs/oem-callback-seed-audit.md')
    for name in ('arasan_emac_ahb.c','arasan_emac_ahb.h','emac_lib.c','emac_lib.h','ar823x.c','ar823x.h','mv88e6071.c','mv88e6071.h','Makefile'):
        add(GPL/'drivers/ruby'/name,'source/oem-gpl/drivers/ruby/'+name)
    add(GPL/'drivers/topaz/switch_emac.c','source/oem-gpl/drivers/topaz/switch_emac.c')
    tree(GPL/'common','source/oem-gpl/common',{'.h','.c'})
    # Reference headers are generic GPL source, never device identity/calibration.
    # Capture the driver's named QTN includes alongside the register definitions.
    qtn_headers=set()
    for p in [GPL/'drivers/ruby/arasan_emac_ahb.c',GPL/'drivers/ruby/emac_lib.c',GPL/'drivers/topaz/switch_emac.c']:
        qtn_headers.update(re.findall(r'#include\s*[<"](qtn/[^>"]+)[>"]',p.read_text(errors='replace')))
    for name in sorted(qtn_headers):
        candidate=GPL/'include'/name
        if candidate.is_file():add(candidate,'source/oem-gpl/include/'+name)
    for name in ('COPYING','LICENSE'):
        if (GPL/name).is_file():add(GPL/name,'source/oem-gpl/'+name)
    for version,folder in [('f352',ROOT/'work/kernel-port/modules/f352_dual_emac'),('f374r3',ROOT/'work/kernel-port/f374r3-ethernet-rx-quiesce')]:
        tree(folder,'source/'+version)
    add(ROOT/'work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h','source/linux510/include/linux/soc/qtn/topaz-ethernet.h')
    for folder,name in [(OEM/'ruby','emac.ko'),(OEM/'ruby','emaclib.ko'),(OEM/'topaz','switch_emac.ko')]:
        add(folder/name,'original-oem-modules/'+name)
    for folder,version in [(BASELINE,'f352'),(BUILD,'f374r3')]:
        for lane in ('a','b'):
            add(folder/lane/'qtn-topaz-emac-f352.ko','modules/'+version+'/'+lane+'/qtn-topaz-emac-f352.ko')
        tree(folder,'evidence/build-'+version,{'.json','.stdout','.stderr','.txt','.log','.cmd','.symvers'})
        # Compiler command files and metadata have suffix .json/.cmd; complete
        # source/object identities are included in the retained build result.
    tree(REVIEW,'evidence/final-review',{'.json','.md','.py','.c','.stdout','.stderr'})
    tree(FIXTURE,'evidence/fault-fixture',{'.json','.c','.stdout','.stderr'})
    tree(CAMPAIGN/'final-r3-coverage','evidence/coverage')
    for tag in ('oem-emac','oem-emaclib','oem-switch-emac','f352','f374r3'):
        suffix='rea-expanded-r2' if tag.startswith('oem-') else 'rea-native-symbols'
        tree(CAMPAIGN/(tag+'-'+suffix),'evidence/rea/'+tag)
        tree(CAMPAIGN/(tag+'-evidence-seal-r2'),'evidence/rea-seals/'+tag)
        if tag.startswith('oem-'):
            tree(CAMPAIGN/(tag+'-seeds-expanded-r2'),'evidence/seeds/'+tag)
    for name in ('export_hgw_ethernet_rea.mjs','seal_hgw_ethernet_rea_evidence.mjs','seed_hgw_ethernet_rea.py',
                 'audit_hgw_ethernet_rea_coverage.py','link_arc700_analysis_image.py',
                 'build_hgw_ethernet_baseline_gate.py','build_f374_ethernet_rx_quiesce.py',
                 'prepare_f374_ethernet_rx_quiesce.py','prepare_f374r2_ethernet_rx_quiesce.py',
                 'prepare_f374r3_ethernet_rx_quiesce.py','test_f374_ethernet_rx_quiesce.py',
                 'recover_hgw5g_driver_ops.py','qualify_f370_qdrv_module.py','build_f370_qdrv_module.py',
                 'compile_f368_changed_objects.py','create_hgw_ethernet_rea_handoff.py'):
        add(ROOT/'tools'/name,'tools/'+name)
    manifest={'schema':'openmitrastar.ethernet-rea-handoff/v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'PASS_LOCAL_SOURCE_BINARY_EVIDENCE_HANDOFF','firmware_eligible':False,'install_status':'NO_GO_INSTALL',
        'hardware_accessed':False,'files':files,'source_pins':pins,
        'classification':{'original-oem-modules':'ORIGINAL_UNMODIFIED_REFERENCE',
            'modules/f352':'EXACT_REPRODUCED_CURRENT_LINEAGE_REFERENCE',
            'modules/f374r3':'BOUNDED_OFFLINE_CANDIDATE_NEVER_INSTALL_WITHOUT_FULL_GATES',
            'evidence':'OFFLINE_OBSERVATIONS_NO_RUNTIME_ACCEPTANCE'},
        'limits':['OEM pseudocode retains explicit ARC decoding/CFG gaps.',
            'F374r3 corrects RX restart only; inherited stop/remove DMA lifetime remains unresolved.',
            'No full firmware image, raw protected partitions, device keys/configuration/calibration included.',
            'Toolchain/full kernel context referenced from existing general handoff; not duplicated here.',
            'No message sent, router access, module loading, UART, reboot or flash.']}
    (stage/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (stage/'EXCLUSIONS.md').write_text('# Alcance\n\nEste handoff local contiene Ethernet OEM, port y evidencia offline. No incluye imagen flashable, particiones, configuración/identidad personal, secretos, calibración ni toolchain/kernel completo. Los ELF sintéticos de análisis no se distribuyen como módulos: sus hashes y mapas están en la evidencia. F374r3 sigue NO_GO_INSTALL.\n')
    for target in linkmap.values():assert (stage/target).is_file(),'missing packaged README target '+target
    archive=out/'OpenMitraStar-HGW500-Ethernet-REA-F374r3.zip'
    payload=sorted(p for p in stage.rglob('*') if p.is_file())
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in payload:z.write(p,p.relative_to(stage).as_posix())
    checked=0
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None,'ZIP CRC error'
        assert len(z.namelist())==len(payload)
        for p in payload:
            name=p.relative_to(stage).as_posix()
            assert hashlib.sha256(z.read(name)).hexdigest()==sha(p),'ZIP member mismatch '+name
            checked+=1
    for p,h in pins.items():assert sha(p)==h,'input changed '+p
    result={'schema':'openmitrastar.ethernet-handoff-verification/v1','status':'PASS_ZIP_CRC_AND_ALL_MEMBER_HASHES',
        'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),
        'payload_files':len(payload),'member_hashes_verified':checked,'source_inputs_unchanged':True,
        'hardware_accessed':False,'firmware_eligible':False,'install_status':'NO_GO_INSTALL'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
