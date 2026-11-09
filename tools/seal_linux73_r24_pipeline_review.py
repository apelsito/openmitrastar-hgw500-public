"""Seal actual R24 pipeline+task writer fixtures with precise offline limits."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 pipeline=ROOT/'outputs/rea/linux73-r24-full-loader-pipeline-fixture-20261023T054000Z-r1';task=ROOT/'outputs/rea/linux73-r24-provider-writer-task-fixture-20261023T054300Z-r1';pr=json.loads((pipeline/'result.json').read_text());tr=json.loads((task/'result.json').read_text());assert pr['status']=='PASS_R24_ACTUAL_REQUEST_SHA256_WRITER_PREFLIGHT_INSTALL_END_RELEASE_PIPELINE_HOST_FIXTURE'and pr['full_load_pipeline_cases']==273;assert tr['status']=='PASS_ACTUAL_SRAM_CORE_BACKEND_TASK_WRITER_LEASE_OWNERSHIP_CONCURRENT_WAITS'and'cases=410'in tr['output']
 fw=a.candidate/'source/qdrv/qdrv_fw.c';backend=a.candidate/'providers/sram73/om73_sram_backend.c';header=a.candidate/'providers/sram73/om73_sram_backend.h';profiles=a.candidate/'source/qdrv/om73_fw_profiles.h';t=fw.read_text();start=t.index('int qdrv_fw_load(');load=t[start:t.index('\nint qdrv_fw_load_muc(',start)];assert load.index('om73_sram_writer_begin(')<load.index('qdrv_fw_writer_preflight(')<load.index('qdrv_fw_install(')<load.index('om73_sram_writer_end(')<load.index('*start_addr = loaded_entry;');assert tr['source_sha256']==sha(backend)and tr['header_sha256']==sha(header)
 paths=[Path(__file__),fw,backend,header,profiles,a.candidate/'result.json',pipeline/'result.json',task/'result.json'];pins={str(p):sha(p)for p in paths}
 for path,h in pr['pins'].items():p=Path(path);assert sha(p)==h;pins[str(p)]=h
 for folder in[pipeline,task]:
  for p in folder.iterdir():
   if p.is_file():pins[str(p)]=sha(p)
 r={'status':'PASS_R24_ACTUAL_LOAD_PIPELINE_HASH_AND_TASK_WRITER_LEASE_FIXTURES_OFFLINE_ONLY','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'candidate_result_sha256':sha(a.candidate/'result.json'),'loader_source_sha256':sha(fw),'provider_source_sha256':sha(backend),'profiles_sha256':sha(profiles),'pipeline_cases':273,'provider_cases_including_core':410,'provider_core_baseline_cases':362,'concurrent_writer_acquire_close_waiters':3,'hash_backend':'OpenSSL3.0.13SHA256hostrealcrypto','sanitizers':['address','undefined'],'checks':['Selectedthreefullcarriers pass request/hash/profile/preflight/writercheck/install/end/releasepipeline.','Onebitheader/metadata/payloadmutations,wrongCPU/size/profileandDSP28Btailchanges rejectbeforefirstmap andentry staysunchanged.','AllmemszdestinationsincludinglastMuCBSS arecheckedagainstactivepoolbeforeinstallmaps; overlaprefuseswithoutpayloadwrites.','Request/beginfailurecleanupandreleases,bothstartentryunchanged; endfailuredoesnotpublishentry.','Actualproviderusesstacktokenidentity/taskTLS/generation; copied/stale/foreign/nestedtokensrefuse andwriter/acquire/closewaituntilsame-taskend.','Loaderhashandmapsinsidelease; no poolregistration/init orphysicalmemorywritesbyfixtures.'],'limitations':['Pipelinepool/request/address/CCM/maps arefakes; providerfixtureusesactualcodebutpthreadlocks/TLSandfakehardware. NoLinuxscheduler/MMIO/core/RFproof.','ActualOpenSSLhashverifiesbytes, notOEMsignatureauthenticity. Kernelsha256APIwasvalidatedseparately butnotexecutedondevice.','Mapfailurecanleaveprevioussegmentwrites;F355mustretainpartialownership. Failedwriter_endmayretainlease;noautomaticunlock/rollbackclaimed.','Writerleasecoversqdrv_fw_loadpipeline only. R24doesnotwraphal_reset,clearsram,AuCclear_memoutsideFWloadorallMCu/DSPindirectwriters.','Boardreservationstillabsent/defaultclosed. ExacthashprofilesdonotcloseQmatrixnomuoverlap orcompletewritersmap.','Nofunctionaloperationcountincrease,driverloadacceptance,SRAMreservation,physicaltraffic/persistence/release claim.'],'pins':pins};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 doc='''# R24: prueba del pipeline de firmware y lease de escritor

Estado offline. No se cargó firmware ni se registró/reservó SRAM en hardware.

El pipeline real `qdrv_fw_load` pasa273casos con los3carriers seleccionados.
SHA256 se calcula con OpenSSL3.0.13(realcryptohost); request/release, pool,
direcciones, mapas yCCM son fakes explícitos. ASAN/UBSAN pasan. Las mutaciones
de1bit enheader/metadata/payload y encolaDSP, CPU/tamaño/perfil incorrectos y
solape delúltimoBSSMuC se rechazan antes delprimer mapa; entrypermaneceintacto.
Los fallos debegin/end y mapas tampoco publican elentry.

La fixture independiente delprovider ejecuta core/backend reales con locks
pthread ytaskTLS:410casos(incluidos362delcore), tokenscopiados/stale/foreign
rechazados y3waiterswriter/acquire/close. Losrecursos físicos son simulados.
Esto demuestra elcontrol de loscaminos de código, no concurrencia delkernel
o aceptación delbus enla placa.

El lease se mantiene durante hash/preflight/checks/maps/install y elentry se
publica después deend. Siunmapa posteriorfalla puedenquedar escriturasprevias;
no existe rollback atómico. Unend rechazadoretienelease según elcontrato;
no se inventa ununlock automático desdeuna tarea/token inválidos.

Ellease R24cubre elloader, NOhal_reset, clearsram, AuCclear_mem previo al
loader ni todoslosescritores indirectosMuC/DSP/AuC. Lareserva siguecerrada y
elmapacompleto/Qmatrixnomu permanecependiente. Identidad SHA256noequivale a
firmaOEM o autorización deescritores. No aumentanopsfuncionales aceptadas.
''';(a.output/'R24_PIPELINE_REVIEW.md').write_text(doc);print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json'),'doc_sha256':sha(a.output/'R24_PIPELINE_REVIEW.md')},indent=2))
if __name__=='__main__':main()
