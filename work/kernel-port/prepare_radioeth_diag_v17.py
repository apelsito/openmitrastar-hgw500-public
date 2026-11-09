"""Version diagnostics with EXITKILL probe and exact v15 event image receipt."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 target=ROOT/'prepare_radioeth_diag_generated_v17.py'
 if target.exists():raise RuntimeError('Version exists')
 code=(ROOT/'prepare_radioeth_diag_v14.py').read_text()
 code=code.replace('linux-7.3-radioeth-diagnostic-v14','linux-7.3-radioeth-diagnostic-v17')
 code=code.replace('dropbear73-signal-probe-qualified-v2/probe','dropbear73-signal-probe-qualified-v3-exitkill/probe')
 code=code.replace('5c98e16408c5fd2b97a45ebf568d1b284adb4746f081d52a45df4a22b348422e','b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8')
 code=code.replace('radioeth73-events-physical-powercycle-v12/result.json','radioeth73-events-physical-powercycle-v15/result.json')
 code=code.replace("'PASS_EVENTS_RAM_DIAGNOSTIC_WITH_PROBE_AND_UPLOAD_FIXTURE'","'PASS_EVENTS_RAM_DIAGNOSTIC_WITH_EXITKILL_PROBE_AND_UPLOAD_FIXTURE'")
 target.write_text(code)
 print(str(target))
if __name__=='__main__':main()
