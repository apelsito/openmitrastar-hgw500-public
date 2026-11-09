"""Close isolated TQE readback ledger and actual R26 AuC pipeline evidence."""
import argparse,hashlib,json,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cross-prefix',required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);adapter=ROOT/'outputs/rea/linux73-tqe-reset-adapter-20261023T061700Z-r2';fixture=ROOT/'outputs/rea/linux73-tqe-reset-fixture-20261023T062300Z-r2';arc=ROOT/'outputs/rea/linux73-tqe-reset-arc-20261023T062600Z-r1';auc=ROOT/'outputs/rea/linux73-r26-auc-prepared-fixture-20261023T065000Z-r1';r24=ROOT/'outputs/rea/linux73-carrier-writer-candidate-20261023T053000Z-r24';r26=ROOT/'outputs/rea/linux73-clear-reset-candidate-20261023T064300Z-r26';tf=json.loads((fixture/'result.json').read_text());af=json.loads((auc/'result.json').read_text());assert tf['actual_controller_cases']==24 and tf['checks']==83 and af['actual_AuC_prepared_pipeline_cases']==46 and af['positive_callback_rejected']
 obj=arc/'om73_tqe_reset_adapter.o';asm=subprocess.check_output([a.cross_prefix+'objdump','-d',str(obj)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm);imports=subprocess.check_output([a.cross_prefix+'nm','-u',str(obj)],text=True)
 paths=[Path(__file__),adapter/'result.json',adapter/'om73_tqe_reset_adapter.c',adapter/'om73_tqe_reset_adapter.h',fixture/'result.json',obj,arc/'Kbuild',auc/'result.json',r24/'source/platform/topaz/switch_tqe.c',r24/'source/platform/topaz/topaz_congest_queue.c',r24/'source/qdrv/qdrv_hal.c',r26/'source/qdrv/qdrv_fw.c',r26/'source/qdrv/qdrv_auc.c',r26/'source/qdrv/qdrv_soc.c',ROOT/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h',ROOT/'work/sources/Quantenna-GPL/common/topaz_platform.h'];pins={str(p):sha(p)for p in paths}
 r={'status':'PASS_OFFLINE_TQE_LOCAL_CONTROLLER_LEDGER_AND_R26_ACTUAL_AUC_PREPARED_PIPELINE','hardware_accessed':False,'firmware_eligible':False,'driver_sources_modified':False,'TQE_controller':{'source':str(adapter),'ARC_object_bytes':obj.stat().st_size,'ARC_object_sha256':sha(obj),'ARC_imports':[l.split()[-1]for l in imports.splitlines()],'fixture_cases':24,'fixture_checks':83,'real_MMIO_provider_connected':False,'real_global_producer_fence_connected':False},'R26_AUC':{'cases':46,'loader_destinations_checked_before_prepare':8,'all_clear_spans_checked_before_first_map':4,'positive_callback_normalized_to_EPROTO':True,'actual_init_enable_called_on_rejection':False,'hash_backend':'OpenSSL3.0.13realhostSHA256','sanitizers':['address','undefined'],'source_fw_sha256':sha(r26/'source/qdrv/qdrv_fw.c'),'source_auc_sha256':sha(r26/'source/qdrv/qdrv_auc.c')},'exact_known_contract':['CompiledARC hal_reset mask0x4180NETSS/MAC/BB doesnotincludeSRAMbit3; NETSSimpactonTQEregisters remainsunknown.','TQEringmoduledependencyallocates/publishesbeforeqdrv_soc_init/hal_reset; keepownedringheapgeneration, do notheapinitafterreset.','CPUIFreadbacks:CSRIRQbit0/resetbit31,STATUSemptybit30,QPTRhalvesincludingwrapbit,TXSTARTnreadybit0,RX_RINGbaseandcount.','ExistingR24NAPIcompletionreenablesIRQ; localpause mustremaskafterdrain. Existingteardown ring0/count0→CPUIFreset→freeownership isnotnewremoteproducerstopproof.','Sourcecontrollerrequiresmissingexclusiveproducerfencebeforeanymutations; bounded24cases verifydefaultrefusal/readbacktimeouts andpreservedsameringreprogram.'],'remaining_real_gates':['GlobalproducerfenceforEMAC/WMAC/MCu/AuC/DSP andLHOSTbank/batch/taskletwithpendingretainedreferenceproof notpresent.','IRQmask/synchronizeIRQ/NAPI/taskletdrainalone do notstop remoteingress or proveNETSSresetmayproceed.','Coreprovideremptyarena-onlyresetlease willrejectownedring; preservinglivepoolringneedsaseparateactualresourceownercontract withglobalfence, notflagoverride.','TQEcontrollerlocal_stop/local_resume callbacks abstractactualLinuxsequence; nofullkernelhelperhookimplementation orhardwarequiescence acceptance.','Failureonresume mayleavepartiallyrestoredCSR/ring whileproducerfencestillheld; no rollback/recoveryoperator admitted, prototypequarantine only.','R26AuCclear+loadlease nowcoversclearspans, buthardwaremapfailuremayleavepreviousclears; entryunchanged/noAuCenable iscontrolproofonly.','R26resetsoftwareadmissionisnotNETSS/TQE/firmwarequiescence; noSRAMregistration/loadnormal/RF/client/releaseclaim.'],'pins':pins};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');doc='''# TQE y R26: contrato offline de pausa/reset y prepare AuC

El reset ARC observado escribe0x4180(NETSS|MAC|BB), sin resetSRAM. TQE
publica elringantesdelstartQDRV; reinicializarelheapdespuésdelreset perdería
suownership. El controladoraislado mantiene allocation_owner, bus ycount;
despublica/reprograma el mismo ring y no libera ni reconstruye SRAM.

Los readbacks están ligados a los registros existentes: IRQ/reset enCSR,
STATUSempty, QPTRread/write conwrap yTXSTARTnready. Dos snapshots consecutivos
deidle preceden ring0/count0+CPUIFreset. El poll esacotado; discrepanciasretienen
laidentidad en cuarentena.24casos/83checks y objetoARCcompilado sirven sólo
para elcontrolador. Callbacks MMIO/Linux/productores son simulados.

Falta elcontrato real de productores remotos y delbank/batch/tasklet LHOST.
IRQ/NAPIdrain no demuestra esa pausa; NAPIpuede reactivarIRQalcompletar. El
provideractual no ofrece esa barreraexclusiva. Sinella elcontrolador devuelve
EOPNOTSUPP antesdecambiarregistros. Noestá conectadoaldriver ni habilitareset.
El softwarelease de resetconarenaempty tampoco acepta unringvivo mediante
una bandera: necesitacontrato real de ownership/quiesce distinto.

La pruebaR26 incluye qdrv_auc_init, auc_clear_mem y qdrv_fw_load_prepared
reales.46casos: hash y8destinosde loader precedenprepare; los4clearspans se
validan antesdelprimerclearmap. Hash/tamaño/metadata y cadaerror de mapase
rechazan sin publicarentry ni habilitarAuC. Callback positivoinesperado se
normalizaaEPROTO. SHA256hostOpenSSLreal; recursos/lease/MMIO son fakes,
ASAN/UBSAN pasan. Noejecución físicade firmwareo reset.

ElpipelineR26 cierra elclearAuCpreviamentefuera dellease, pero no convierte
unmaprefusado en rollbackatomico:clearsanteriorespuedenquedar. Tampocoprueba
queNETSSpuedaresetearTQE condescriptores/firmwares activos. LareservaSRAM,
productorfence y pruebasfísicas siguenpendientes. R24/R26fuentesintactas.
''';(a.output/'TQE_R26_OFFLINE_REVIEW.md').write_text(doc);print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json'),'document_sha256':sha(a.output/'TQE_R26_OFFLINE_REVIEW.md')},indent=2))
if __name__=='__main__':main()
