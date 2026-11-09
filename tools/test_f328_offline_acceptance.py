"""Actual output acceptance and optimization-resistant input integrity gates."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import build_f328_oem_classifier_offline as build

class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name)
        rows=[]
        for count,width,found in [(2,40,0),(8,40,1),(16,40,1),(32,40,1),(32,1,0),(32,500,0)]:
            values=(count,10000,width,found,0,found,0,0,0,1)
            keys=('count','pri','width','detected','poll','ssr','itlv','lsr','fault','guards')
            rows.append('F328_VECTOR '+' '.join(f'{key}={value:08x}' for key,value in zip(keys,values)))
        self.serial='F328_ORACLE_BEGIN exact_oem_classifier_only=1\n'+'\n'.join(rows)+'\nF328_ORACLE_DONE vectors=6 rf_proof=0 firmware=0\n'
        (self.out/'serial.log').write_text(self.serial)
        (self.out/'qemu-exit.txt').write_text('0\n')
        (self.out/'guest-errors.log').write_bytes(b'');(self.out/'qemu.stderr').write_bytes(b'')
    def tearDown(self):self.temp.cleanup()
    def test_exact_rows(self):self.assertTrue(build.validate_run(self.out)['passed'])
    def test_timeout_rejected(self):
        (self.out/'qemu-exit.txt').write_text('124');self.assertFalse(build.validate_run(self.out)['passed'])
    def test_crash_after_done_rejected(self):
        (self.out/'qemu-exit.txt').write_text('139');self.assertFalse(build.validate_run(self.out)['passed'])
    def test_missing_exit_rejected(self):
        (self.out/'qemu-exit.txt').unlink();self.assertFalse(build.validate_run(self.out)['passed'])
    def test_positive_false_result_rejected(self):
        (self.out/'serial.log').write_text(self.serial.replace('detected=00000001','detected=00000000',1));self.assertFalse(build.validate_run(self.out)['passed'])
    def test_guard_overwrite_rejected(self):
        (self.out/'serial.log').write_text(self.serial.replace('guards=00000001','guards=00000000',1));self.assertFalse(build.validate_run(self.out)['passed'])
    def test_abi_fault_rejected(self):
        (self.out/'serial.log').write_text(self.serial.replace('fault=00000000','fault=00000001',1));self.assertFalse(build.validate_run(self.out)['passed'])
    def test_duplicate_vector_rejected(self):
        (self.out/'serial.log').write_text(self.serial.replace('F328_ORACLE_DONE',self.serial.splitlines()[1]+'\nF328_ORACLE_DONE'));self.assertFalse(build.validate_run(self.out)['passed'])
    def test_guest_error_rejected(self):
        (self.out/'guest-errors.log').write_text('invalid read');self.assertFalse(build.validate_run(self.out)['passed'])
    def test_stderr_rejected(self):
        (self.out/'qemu.stderr').write_text('timeout');self.assertFalse(build.validate_run(self.out)['passed'])
    def test_missing_done_rejected(self):
        (self.out/'serial.log').write_text('\n'.join(self.serial.splitlines()[:-1]));self.assertFalse(build.validate_run(self.out)['passed'])
    def test_provenance_rejection_under_optimized_python(self):
        script='''import sys,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import f328_oem_classifier_projection as p
with tempfile.TemporaryDirectory() as d:
 p.OEM=Path(d)/'bad.ko';p.OEM.write_bytes(b'bad')
 try:p.emit(Path(d))
 except ValueError:print('REJECTED_BAD_OEM_UNDER_OPTIMIZATION')
 else:raise SystemExit(8)
'''
        proc=subprocess.run([sys.executable,'-O','-c',script,str(Path(__file__).resolve().parent)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('REJECTED_BAD_OEM_UNDER_OPTIMIZATION',proc.stdout)

if __name__=='__main__':unittest.main()
