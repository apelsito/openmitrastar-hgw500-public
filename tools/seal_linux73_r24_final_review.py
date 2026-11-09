"""Final R24 private source/pair/ABI/catalog qualification bindings; no replay."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();pins={}
 def read(path):pins[str(path)]=sha(path);return json.loads(path.read_text())
 candidate=ROOT/'outputs/rea/linux73-carrier-writer-candidate-20261023T053000Z-r24';source=read(candidate/'result.json');pairpath=ROOT/'outputs/rea/linux73-carrier-writer-r24-pair-receipt-20261023T055500Z-r1/result.json';pair=read(pairpath);r22path=ROOT/'outputs/rea/linux73-typed-sram-dma-r22-pair-receipt-20261023T042500Z-r1/result.json';parentpair=read(r22path)
 assert pair['status']=='PASS_PAIRED_REAL_LINUX73_74C_22MODULES_IDENTICAL_TYPED_SRAM'and not pair['module_mismatches']and not pair['C_mismatches']and pair['input_pins_after_pass'];assert sha(pairpath)=='c3172e07dc81692d99d241f42ab0a5c3e5519146547e74ca55860e49c7a738c9'
 for lane in pair['lanes']:assert lane['C_units']==74 and len(lane['modules'])==22 and lane['all_imports_resolved']and not lane['forbidden_ISA']
 assert pair['lanes'][0]['modules']==pair['lanes'][1]['modules'];delta=[name for name,row in pair['lanes'][0]['modules'].items()if row!=parentpair['lanes'][0]['modules'][name]];assert set(delta)=={'qdrv.ko','om73_sram.ko'}
 for rel,h in source['files'].items():path=candidate/Path(rel.replace('\\','/'));assert sha(path)==h,rel;pins[str(path)]=h
 assert len(source['files'])==179;assert sha(candidate/'Kbuild')==source['kbuild_sha256'];pins[str(candidate/'Kbuild')]=sha(candidate/'Kbuild')
 tablepath=ROOT/'outputs/rea/linux73-r22-independent-dma-table-review-20261023T044700Z-r3/result.json';table=read(tablepath);wlanhash=pair['lanes'][0]['modules']['wlan.ko']['sha256'];assert wlanhash==table['WLAN_pair'][0]['sha256']==table['WLAN_pair'][1]['sha256'];assert table['table']['records']==610 and table['table']['bytes']==14640 and table['table']['handler_args_RELA_exact']and table['exact_original_records']==44
 pipelinepath=ROOT/'outputs/rea/linux73-r24-pipeline-independent-review-20261023T054600Z-r1/result.json';pipeline=read(pipelinepath);assert pipeline['status']=='PASS_R24_ACTUAL_LOAD_PIPELINE_HASH_AND_TASK_WRITER_LEASE_FIXTURES_OFFLINE_ONLY'and pipeline['pipeline_cases']==273 and pipeline['provider_cases_including_core']==410;assert pipeline['loader_source_sha256']==sha(candidate/'source/qdrv/qdrv_fw.c')and pipeline['provider_source_sha256']==sha(candidate/'providers/sram73/om73_sram_backend.c')and pipeline['profiles_sha256']==sha(candidate/'source/qdrv/om73_fw_profiles.h')
 abipath=ROOT/'outputs/rea/linux73-r24-actual-abi-witness-20261023T060000Z-r1/result.json';abi=read(abipath);assert abi['status']=='PASS_REAL_ARC_R24_ABI_UNCHANGED_DMA20_SKB208_NETDEV1408'and abi['ABI']['om_abi_dma_desc_size']==20 and abi['ABI']['om_abi_skb_size']==208 and abi['ABI']['om_abi_ndev_size']==1408 and abi['r24_pair_sha256']==sha(pairpath)
 comments=ROOT/'outputs/rea/linux73-r24-comments-20261023T055800Z-r1';catalog=read(comments/'manifest.json');artifacts=read(comments/'artifact-hashes.json');assert catalog['status']=='PASS_EXACT_COMMENT_CATALOG'and catalog['file_count']==179 and catalog['comment_count']==7176 and catalog['raw_comment_bytes']==725675 and not catalog['source_files_modified']and catalog['unterminated_comments']==0
 for name,h in artifacts.items():assert sha(comments/name)==h;pins[str(comments/name)]=h
 for row in catalog['files']:assert sha(candidate/row['path'])==row['sha256']
 configsha='e709aba8ed2b55f3e6debe1480bbea2f1320c4bcd9dc3e9832c185b8e72e8efe';symverssha='b3bdc2fecfad7321cd5d03454ea47d2341ef43ffc5e3f091de4c78c0d2726950';assert abi['kernel_config_sha256']==configsha and abi['kernel_symvers_sha256']==symverssha;assert configsha in pair['input_pins'].values()and symverssha in pair['input_pins'].values()
 shaapipath=ROOT/'outputs/rea/linux73-r23-carrier-writer-admission-proposal-20261023T050300Z-r1/result.json';shaapi=read(shaapipath);assert shaapi['status']=='PASS_CURRENT_KERNEL_SHA256_PROFILE_WRITER_ADMISSION_PROPOSAL_NOT_IMPLEMENTED';configentries={k:v for k,v in shaapi['pins'].items()if k.endswith('/.config')};assert configsha in configentries.values()
 a.output.mkdir(parents=True);pins[str(Path(__file__))]=sha(__file__);r={'status':'PASS_FINAL_R24_PRIVATE_OFFLINE_SOURCE_PAIR_ABI_610_TABLE_CATALOG_AND_LOADER_REVIEW','hardware_accessed':False,'firmware_eligible':False,'source_manifest_files_verified':179,'candidate_result_sha256':sha(candidate/'result.json'),'pair_receipt_sha256':sha(pairpath),'C_units_per_lane':74,'modules_per_lane':22,'changed_modules_from_R22':delta,'paired_hash_mismatches':[],'private_table':dict(table['table'],exact_original_records=44,proof_scope='InheritedexactELFbytesfromR22currentparsedrecordswlanSHA4588;R24pairbothlanessamebytes. NonewR24executionorhardwareclaim.'),'WLAN_sha256':wlanhash,'ABI':abi['ABI'],'pipeline_cases':273,'provider_cases_including_core':410,'catalog':{k:catalog[k]for k in['file_count','comment_count','raw_comment_bytes','raw_comment_sha256','unterminated_comments']},'kernel_config_sha256':configsha,'kernel_symvers_sha256':symverssha,'required_external_config':['CONFIG_CRYPTO_LIB_SHA256=y','CONFIG_IPV6=y'],'SHA256_requirement_status':'Currentbuiltkernelbuiltinsha256API/source/exportsboundbypriorliveverificationandpairconfighash; R24source.new_kernel_config_required omitsSHA256. ReproductionqualificationMUSTrequireCRYPTO_LIB_SHA256=y externally beforelegacy/toolbuild; no source manifest edited.','source_edit_performed':False,'remaining_gate_limits':['Noautomaticboardregistration/reservation: pool CLOSED/default; fullnormaldriverloadnotaccepted.','610table/44exactrecordsarenot610functionaloperationsorfull5GHzproof;RBS466468realframeproviderabsent.','Hashidentity/structuralpreflight/poolwriterleasecoversloaderonly; AuCclear_mem/hal_reset/clearsram/indirectfirmwarewriters notfullyfenced.','ActualfixtureuseshostOpenSSL/pthreadtasklocks+fakephysicalresources; nochip/bus/firmware/RFexecution.','Partialmapfailuremayleavepriorpayloadwrites andF355retainslife; invalidwriterendretainslease, notauto-unlock.','Fullhardwareclient/traffic/soak/persistence/rollback/recovery/release stillunrun.','R24catalogcurrentexactbytes; twooriginalcommentsinreplacedloaderfunctionsarepreservedinhistoricalR20/R22, notliterallyinR24.','WSLreadattempt0x8007274cnotrepeated;tableproofcarriedonlybecausemoduleSHAbyteidenticalwithverifiedR22.'],'pins':pins};(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 doc='''# R24: cierre offline privado para AELITA

Fuentes179ficheros verificadas; pareja de74unidadesC y22módulos iguales,
sin imports externos pendientes ni SWAPE/LLOCK/SCOND según los recibos de build.
Sólo qdrv.ko y om73_sram.ko cambian respecto deR22.

WLANR24 es byteidénticoalELFR22 yaanalizado: tabla610entradas/14640bytes,
count/RELA correctos y44tuplasOEM únicasexactas. Es una herencia porSHA256,
no una ejecución físicanueva. ABIARC20B DMA/208B skb/1408B net_device verificado.

273casosdelpipeline loader y410provider/corecaseconlease pasan enhost con
OpenSSL/pthread y recursos simulados. Elhash fija identidad completa porCPU;
preflight/rangos ylease se ejecutan antes delprimer mapa. Entry sólotrasend.

La reproducción exige CONFIG_CRYPTO_LIB_SHA256=y(además deIPV6 y los demás
requisitos). Está activo y exportasha256builtin en elkernel fijado porconfig
e709...8efe/symversb3bd...6950. ElmanifestR24 noañadeSHA256 a suarrayrequired;
esta condición es obligatoria en la calificación/herramientaexterna antes de
construir. No se alteró elmanifest o lasfuentes selladas.

Catálogonuevo:179ficheros,7176comentarios/725675bytes exactos. Fuentes intactas.
Doscomentarios de funcionesde loader reemplazadas permanecen en R20/R22históricos.

Elpool permaneceCLOSED/default, sinregistration deboard/reserva real. Ellease
sólocubreloader, noAuCclear_mem/reset/clearsram/escritoresindirectos. La tabla
no incrementaopsfuncionales y466/468 siguen sinprovider de tramas. Viabilidad
de carga normal, bus/cache,5GHzclient/tráfico/persistencia/recovery/release no
aceptadas. Ningún dato privado niacción física deriva deeste cierre.
''';(a.output/'R24_FINAL_OFFLINE_QUALIFICATION.md').write_text(doc);print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json'),'document_sha256':sha(a.output/'R24_FINAL_OFFLINE_QUALIFICATION.md')},indent=2))
if __name__=='__main__':main()
