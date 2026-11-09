from pathlib import Path
import importlib.util
import socket
import subprocess
import sys
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/ensure_lyoko_speed_server.ps1"
SERVER = ROOT / "tools/openmitrastar_l2_speed_server.py"

SPEC = importlib.util.spec_from_file_location("lyoko_speed_server", SERVER)
assert SPEC and SPEC.loader
SERVER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER_MODULE)


def test_speed_server_is_scoped_and_managed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'AllowedClient = "192.168.1.63"' in text
    assert 'LocalPort $Port -RemoteAddress $AllowedClient' in text
    assert "-WindowStyle Hidden" in text
    assert "server.pid" in text
    assert "openmitrastar_l2_speed_server.py" in text
    assert 'ValidateSet("Ensure", "Status", "Stop")' in text
    assert '"--allowed-client", $AllowedClient' in text
    assert 'firewall = "app-acl-only"' in text


def test_stop_only_targets_owned_process() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'CommandLine -like "*openmitrastar_l2_speed_server.py*"' in text
    assert "Stop-Process -Id $owned.ProcessId" in text


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int, allowed_client: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVER),
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--mib",
            "1",
            "--allowed-client",
            allowed_client,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert "OML2_HTTP_READY" in process.stdout.readline()
    return process


def test_server_allows_configured_client() -> None:
    port = _free_port()
    process = _start_server(port, "127.0.0.1")
    try:
        with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
            assert response.status == 200
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_server_rejects_other_clients() -> None:
    allowed = {"192.168.1.63"}
    assert SERVER_MODULE.client_allowed("192.168.1.63", allowed)
    assert SERVER_MODULE.client_allowed("127.0.0.1", allowed)
    assert not SERVER_MODULE.client_allowed("192.168.1.64", allowed)
