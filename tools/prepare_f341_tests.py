from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'work/kernel-port/f341/tests'
target.mkdir(exist_ok=True)
for source in (ROOT/'work/kernel-port/f338/tests').iterdir():
    if source.is_file() and not (target/source.name).exists():(target/source.name).write_bytes(source.read_bytes())
source=(ROOT/'tools/test_f338_ipc.py').read_text()
source=source.replace("SOURCE=ROOT/'work/kernel-port/f338'","SOURCE=ROOT/'work/kernel-port/f341'").replace('f338-ipc-','f341-ipc-').replace('openmitrastar.f338-ipc-tests','openmitrastar.f341-ipc-tests')
destination=ROOT/'tools/test_f341_ipc.py'
if destination.exists():raise SystemExit('F341 IPC test runner already exists')
destination.write_bytes(source.encode())
