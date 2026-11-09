"""File-only R9 overflow audit and focused replay of the real recovery guard."""
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
import argparse,hashlib,json,threading
import f336_wdt_ram_executor as original
import f362_recovery_delta as recovery
from f367_uart_epoch_metadata import EpochMetadata

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class FakeUart(original.Capture):
    def __init__(self):
        self.lock=threading.Lock();self.total=0;self.buffer=bytearray();self.failed=None
        self.write_in_flight=False;self.serial_recovery_record={};self.kernel_handoff_start=0
        self.prompt_ready=False;self.autoboot=False;self.serial=SimpleNamespace(is_open=True,out_waiting=0)
        self.epoch=EpochMetadata()
    def append(self,data):
        self.epoch.feed(data)
        with self.lock:
            self.total+=len(data);self.buffer.extend(data)
            if len(self.buffer)>262144:del self.buffer[:-262144]

def replay():
    checks={};uart=FakeUart();uart.append(b'Linux version 5.10.260-openmitrastar-radiohw test\n')
    uart.append(b'OM harmless numeric status=1\n'*12000)
    actions=[]
    try:recovery.serial_reboot_to_prompt(SimpleNamespace(guard=lambda:True),uart,drive=lambda *a:actions.append('BREAK'),sleep=lambda *a:actions.append('sleep'))
    except original.Failure as error:checks['actual_old_guard_overflows_before_any_action']=str(error)=='uart_window_overflow' and not actions and not uart.serial_recovery_record
    else:checks['actual_old_guard_overflows_before_any_action']=False
    checks['bounded_metadata_survives_ring_rotation']=uart.epoch.proof(0)['eligible'] and len(uart.buffer)==262144 and len(uart.epoch.pending)<=8192
    checks['active_interceptor_still_rejected']=not uart.epoch.proof(0,autoboot=True)['eligible']
    checks['reader_failure_still_rejected']=not uart.epoch.proof(0,reader_failed=True)['eligible']
    checks['missing_epoch_rejected']=not EpochMetadata().proof(0)['eligible']
    uart.append(b'Info: Quantenna U-Boot version:v36.7.0.30\n')
    checks['newer_reset_invalidates_old_linux']=not uart.epoch.proof(0)['eligible']
    uart.append(b'Linux version 5.10.260-openmitrastar-radiohw next\ntopaz>')
    checks['newer_prompt_invalidates_linux']=not uart.epoch.proof(0)['eligible']
    fresh=FakeUart();fresh.append(b'Linux version 5.10.260-openmitrastar-radiohw test\n');fresh.autoboot=True
    try:recovery.serial_reboot_to_prompt(SimpleNamespace(guard=lambda:True),fresh,drive=lambda *a:actions.append('BREAK'),sleep=lambda *a:actions.append('sleep'))
    except original.Failure as error:checks['actual_autoboot_guard_also_prevents_break']=str(error)=='fresh_linux_epoch_required' and not actions
    else:checks['actual_autoboot_guard_also_prevents_break']=False
    cursor=fresh.checkpoint();fresh.append(b'fresh response\ntopaz>');checks['fresh_command_window_unchanged']=fresh.since(cursor)==b'fresh response\ntopaz>'
    fresh.append(b'noise\n'*50000)
    try:fresh.since(cursor)
    except original.Failure as error:checks['command_overflow_remains_strict']=str(error)=='uart_window_overflow'
    else:checks['command_overflow_remains_strict']=False
    return checks

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--output-dir',type=Path);args=parser.parse_args()
    run=args.run_dir;result=json.loads((run/'result.json').read_text())
    assert result['status']=='FAILED_RECOVERY_UNPROVEN_NO_RETRY' and result['recovery_error']=='uart_window_overflow'
    base=[json.loads(line) for line in (run/'uart-redacted.jsonl').read_text().splitlines()]
    semantic=[json.loads(line) for line in (run/'uart-semantic-r2.jsonl').read_text().splitlines()];byseq={row['sequence']:row for row in semantic}
    boot=[row for row in base if 'topaz>bootm 0x83000000' in row['text']]
    linux=[row for row in base if row['text'].startswith('Linux version 5.10.260-openmitrastar-radiohw')]
    assert len(boot)==len(linux)==1
    boot_offset=byseq[boot[0]['seq']]['stream_offset'];linux_offset=byseq[linux[0]['seq']]['stream_offset'];total=result['uart']['bytes'];floor=total-262144
    assert boot_offset<linux_offset<floor and result['serial_recovery']=={} and result['rollback_attempted'] is False
    checks=replay();assert all(checks.values()),checks
    out=args.output_dir or ROOT/'outputs/preflight'/('f367r9-uart-window-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    inputs=[run/'result.json',run/'uart-redacted.jsonl',run/'uart-semantic-r2.jsonl',Path(__file__).resolve(),ROOT/'tools/f367_uart_epoch_metadata.py',ROOT/'tools/f336_wdt_ram_executor.py',ROOT/'tools/f362_recovery_delta.py',ROOT/'tools/f365_install_executor.py',ROOT/'tools/f367_campaign_executor.py']
    report=dict(schema='openmitrastar.f367r9-uart-window-audit/v1',status='PASS_OFFLINE_OVERFLOW_REPRODUCED',checks=checks,source_bindings={str(p):sha(p) for p in inputs},observed=dict(received_bytes=total,ring_capacity=262144,ring_retained_floor=floor,bootm_echo_offset=boot_offset,linux_banner_offset=linux_offset,software_recovery_flag_only=True,serial_break_attempted=False,serial_b_written=False,rollback_attempted=False,post_failure_reset_observed=False,uart_capture_complete=result['uart']['semantic_capture']['complete'],uart_dropped_bytes=result['uart']['semantic_capture']['dropped_bytes']),cause='Serial recovery reads since the original bootm cursor after that history has aged out of the bounded command-response ring. The exception precedes the BREAK record and all recovery writes.',latent_guard='Autoboot is rearmed during the return wait; it must be explicitly quiesced through an owned reader/writer handshake, not ignored or forced false.',metadata_proposal_only=True,hardware_actions=False,firmware_changed=False,existing_sources_changed=False)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='ascii')
    plan='''# R9: recuperacion host tras overflow

El resultado original permanece inmutable. No se ha restaurado F365 y no se puede liberar la lease solo porque COM3 y los hijos hayan cerrado: el watchdog sigue sin demostrar inactivo.

## Ruta demostrada

`f367_campaign_executor.restore` agota la espera de reset, fija software_recovery=true y llama `f365_install_executor.Host.reboot_to_prompt(..., True)`. Esta rama llama `f362_recovery_delta.serial_reboot_to_prompt`, que valida dominio y despues hace `since(kernel_handoff_start)`. El ring solo conserva262144bytes. La excepcion ocurre antes de registrar/intentar BREAK o escribir b. El flagsoftware_recovery no prueba ninguna accion ejecutada. No hubo una segunda escritura flash.

## Recuperacion actual: operador root

1. Mantener exclusividad y reconciliar la lease retenida con el proceso propietario ya terminado; guardar un recibo nuevo, sin cambiar el resultado fallido. Root verifica identidad/boot/control del watchdog por SSH readonly, si sigue accesible.
2. Si SSH esta sano y la identidad coincide, la via normal de reboot usa un checkpoint UART nuevo y evita este cursor historico. El retorno requiere la misma autoridad/nonce, F365 exacta, Bootbase fresco y dos controles watchdog0; despues los mismos checks de particiones protegidas/store y el escritor F365. No reiniciar la campaña R9 ni desarmar guardas para obtenerlo.
3. Si SSH no permite demostrar el estado actual, no convertir los logs antiguos en autorizacion de BREAK. Aplicar el procedimiento de recuperacion ya autorizado con observacion/identidad frescas y un unico operador. No ejecutar un nuevo flash sin Bootbase/control0/dominio comprobados.

## Delta host propuesto para siguientes sesiones

Conservar `since` estricto para todas las respuestas de comandos. Registrar desde el primer byte metadata acotada de Linux/reset/prompt con offsets absolutos, independiente del ring; el modulo nuevo y las10comprobaciones locales muestran que esa prueba sobrevive a la rotacion, e invalida resets/prompts posteriores o fallo dellector.

Antes de la ruta serial, transferir explicitamente la propiedad de escrituras: cancelar el interceptor automatico y esperar confirmacion del lector/escritor de que no hay escritura pendiente. Si eso no se demuestra, abortar. Mantener los gates de lease, lector, noflashinflight, serialidle, epochLinux fresca y nosegundoBREAK. Solo entonces sustituir el fetch historico por la pruebaepoch; conservar sin cambio BREAK600ms, clear150ms, b unico y prueba de reset/prompt frescos. Guardar recibo antes de cualquier accion.

Este artefacto es un plan y un prototipo de metadata de solo lectura; no instala un bypass ni contiene un lanzador fisico. El handshake y su integracion deben verificarse en un delta host nuevo antes de otro ensayo. Ninguna imagen de firmware cambia.
'''
    (out/'RECOVERY_PLAN.md').write_text(plan,encoding='utf-8')
    print(json.dumps(dict(result=str(out/'result.json'),sha256=sha(out/'result.json'),status=report['status'],checks=len(checks),observed=report['observed'],hardware_actions=False),indent=2))
if __name__=='__main__':main()
