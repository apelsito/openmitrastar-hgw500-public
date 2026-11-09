from pathlib import Path
import subprocess,sys
p=Path(__file__).resolve().parent.parent/"linux-7.3-radioeth-ram-v1"
for name in ["test_executor.py","test_bounded_serial.py"]:
 subprocess.run([sys.executable,str(p/name)],check=True)
