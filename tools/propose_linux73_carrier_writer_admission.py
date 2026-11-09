"""Bound proposal for SHA256 profiles+SRAM writer admission; no driver changes."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--kernel-source',type=Path,required=True);p.add_argument('--kernel-context',type=Path,required=True);p.add_argument('--comments',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 profile=ROOT/'outputs/rea/linux73-r23-independent-loader-contract-20261023T045000Z-r1/selected-carrier-loader-contract.json';profiles=json.loads(profile.read_text())['carrierprofiles'];assert len(profiles)==3;proof=json.loads((a.candidate/'result.json').read_text());assert not proof['board_reservation_registered'];backend=a.candidate/'providers/sram73/om73_sram_backend.c';bt=backend.read_text();assert'kernel_occupancy_sha256'in bt and'complete_writers_map_sha256'in bt
 header=a.kernel_source/'include/crypto/sha2.h';implementation=a.kernel_source/'lib/crypto/sha256.c';config=a.kernel_context/'.config';symvers=a.kernel_context/'Module.symvers';ht=header.read_text();ct=config.read_text();symbols=symvers.read_text();assert'void sha256(const u8 *data, size_t len,'in ht and'CONFIG_CRYPTO_LIB_SHA256=y'in ct;assert any(l.split()[1:4]==['sha256','vmlinux','EXPORT_SYMBOL']for l in symbols.splitlines());assert'EXPORT_SYMBOL(sha256);'in implementation.read_text()
 ledger=ROOT/'outputs/rea/linux73-selected5g-sram-occupancy-20261022T223000Z-r1/reservation-proposal.json';l=json.loads(ledger.read_text());assert not l['enabled'];comment=json.loads((a.comments/'manifest.json').read_text());assert comment['status']=='PASS_EXACT_COMMENT_CATALOG'and not comment['source_files_modified'];assert comment['file_count']==178
 pins={str(p):sha(p)for p in[Path(__file__),a.candidate/'result.json',a.candidate/'source/qdrv/qdrv_fw.c',backend,profile,ledger,header,implementation,config,symvers,a.kernel_context/'vmlinux',a.comments/'manifest.json',a.comments/'artifact-hashes.json']}
 contract={'schema':'openmitrastar.carrier-writer-admission-proposal/v1','enabled':False,'implemented_in_driver':False,'kernel_sha256':sha(a.kernel_context/'vmlinux'),'kernel_config_sha256':sha(config),'kernel_Module_symvers_sha256':sha(symvers),'candidate_result_sha256':sha(a.candidate/'result.json'),'hash_backend':{'include':'crypto/sha2.h','function':'sha256(const u8 *data,size_t len,u8 out[SHA256_DIGEST_SIZE])','provider':'vmlinux EXPORT_SYMBOL sha256','config':'CONFIG_CRYPTO_LIB_SHA256=y','source_sha256':sha(implementation),'scope':'RealcurrentLinux73builtinAPI; nofakereplacement orcrypto_shashallocationrequired'},'profiles':profiles,'identity_rules':['ExactCPUenum+carrierlength+SHA256overentireimmutablefw->data includingDSP28Btrailer','FWINFOexactone/version0x25040059/type1 verifiedasstructuralcorroboration,notauthorizationalone','Selectedbytesrequest_firmware immutableuntilrelease; donottrustnamesorcaller yesflags','One exact3profile bootstraptuple boundtokernel+candidate+fw_no_mu1 beforepooladmission; nomu hash isnotproofallMuC/DSPwritersqmatrixdisabled'], 'write_lease_rules':['Processcontext shared lifecyclemutex encompasses digest/preflight/destinationplan andallmapping/copy/BSSzero; notjusthash-before-lock','Acquire writerlease rejects pool OPENING/CLOSING; rejects activepool ifanyplannedSRAMsegmentintersectsownedarena usingphysicalnormalizedintervals andmemszincludingBSS','Whilewriterleaseactive, pool acquire/close/reset/clear mustrejectorwait beforeanymemorytouch; hashbindingssnapshotbeforestatechange','Poolacquire requires verifiedall3profiletuple already bound andcompletefixed/indirectwritermap/kerneloccupancycontract; currentmissingmapmeansstillclosed','Disjointwrite lease maycoexistwithactiveheap onlyif completeconsumer/lifetimeproof shows noindirect writesintoheap; sourcePT_LOADdisjointnessalone doesnotgrantthis','Endleaseafterallsegments success/failure retains partialF355ownershipanddoesnotpermitclosing/reinitializingpool orstartingunknownfirmware','Use actualleaseobject/generation storedbyresourceowner; do notexpose blanketboolallowed oruserspace registration'], 'exact_heap_interval':{'start_offset':'0x12000','end_offset':'0x20000','physical_start':'0x88012000','physical_end':'0x88020000','bus_start':'0x80012000','bus_end':'0x80020000'},'existing_pool_API_gap':'No writerbegin/end or synchronizedarenaquery isexportedbyR23pool. Astaticpre-maprangecheckcannotclose racewithom73_sram_acquire; newinternalresourceownerleaseAPIrequiredbeforeimplementation.', 'blocking_unknowns':['CompleteMCu/AuC/DSPindirectwriterbounds+Qmatrixnomu semantics notclosed','ActualhardwareSRAMreservation/mapproperties andNETSSresetconsumerlifetime remainunverified','Selectedkernelhashnow111a...2709 differshistoricalv6; reservationmustbindonecurrentexactkernel notreuseoldmapclaims'],'promotion':'NO_GO_PROPOSAL_UNIMPLEMENTED_DEFAULT_CLOSED'}
 (a.output/'carrier-writer-contract.json').write_text(json.dumps(contract,indent=2)+'\n')
 doc='''# R23: perfiles de firmware y admisión de escritores SRAM

Propuesta sin implementar. El pool permanece cerrado por defecto; no hay
registro, reserva, mapa ni escritura física nuevos.

El kernel actual tiene CONFIG_CRYPTO_LIB_SHA256=y y exporta sha256 desde
vmlinux. API real: `<crypto/sha2.h>`, `sha256(data, len, digest)`. Fijar CPU,
longitud y digest del carrier completo, incluida la colaDSP de28bytes; no basta
el nombre o FWINFO. Los perfiles exactos de MuC/AuCnomu/DSP y cada segmento
traducido están en carrier-writer-contract.json. Son hashes de identidad,
no firmas OEM ni demostración de autorización de todos los escritores.

Orden obligatorio propuesto: request_firmware → snapshotbytesinmutables →
lease de vida compartido con elpool → SHA256/rol/tamaño → preflight completo →
plan de destinos con memsz/BSS → exclusión del intervaloreservado → maps/writes.
Ese mismo lease debe impedir acquire/close/reset/clear concurrentes. Hash y
rangos antesdellease dejarían una carrera con acquire. Elpool actual carece de
API writerbegin/end; un getter dearena o boolallowed no sustituye ese contrato.

La admisión bootstrap debe fijar los3carriers y fw_no_mu=1 antesde adquirirelpool.
Incluso con segmentosdisjuntos, sólo un mapacompleto de escritoresindirectos
puede permitir firmwareactivo juntoalheap. ElAuCnomu ocupa70000–79c00, que se
solapa con qmatrixGPL70000–80000; no demuestra queMuC/DSP dejen de usarla.

La exclusión usa direcciones físicasnormalizadas y longitudesmemsz, noaliases
virtuales ni sólofilesz. [12000,20000) corresponde a physical88012000–88020000.
FWINFOffff0000 se excluye como metadata; DSPXY permanece skip acotado. Elentry
sólo se publica despuésde todaslasinstalaciones; fallo conservaF355 parcial.

El catálogo R23 conserva178ficheros,7167comentarios/724512bytes. Doscomentarios
de funcionesreemplazadas noestánliteralmenteenR23: permanecen en los históricos
R20/R22 inalterados. La nuevaextracción eslexicalexacta, no reintroduce texto ni
modifica ninguna fuente. No declarar que todosloscomentariosoriginales siguen
presentes en elarchivoR23.

Gate pendiente: identidad de unkernelactual exacto, mapacompleto deocupación,
reservaexclusiva real y leasekernel que coordinepool/reset/firmware. No se
implementó eladmission ni se tocóhardware, calib, claves, flash, TX o Ioctl26.
''';(a.output/'CARRIER_WRITER_ADMISSION.md').write_text(doc)
 r={'status':'PASS_CURRENT_KERNEL_SHA256_PROFILE_WRITER_ADMISSION_PROPOSAL_NOT_IMPLEMENTED','hardware_accessed':False,'firmware_eligible':False,'contract_sha256':sha(a.output/'carrier-writer-contract.json'),'doc_sha256':sha(a.output/'CARRIER_WRITER_ADMISSION.md'),'kernel_sha256':contract['kernel_sha256'],'profiles':len(profiles),'comments':{k:comment[k]for k in['file_count','comment_count','raw_comment_bytes','raw_comment_sha256']},'pins':pins};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json'),'kernel_sha256':r['kernel_sha256']},indent=2))
if __name__=='__main__':main()
