from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "tools/run_aelita_2g_wpa2_runtime_psk_once_ssh_v2.py"
SPEED = ROOT / "tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py"
RADIO5 = ROOT / "tools/run_f293_5g_aelita_traffic_ssh_v2.py"


def load_speed_wrapper():
    spec = importlib.util.spec_from_file_location("aelita_speed_ssh_v2_test", SPEED)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_and_5g_wrappers_are_network_free_in_dry_run(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    for script, extra in (
        (RUNTIME, []),
        (RADIO5, ["--profile", "f301"]),
    ):
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--aelita-host-key-mode", "pinned",
                "--aelita-known-hosts", str(known_hosts),
                *extra,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert '"mode": "dry-run"' in proc.stdout
        assert not known_hosts.exists()


def test_speed_wrapper_rewrites_only_runtime_child(monkeypatch, tmp_path: Path) -> None:
    wrapper = load_speed_wrapper()
    captured = []

    def fake_run(command, *args, **kwargs):
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(wrapper.real_subprocess, "run", fake_run)
    options = type(
        "Options",
        (),
        {
            "aelita_known_hosts": tmp_path / "known_hosts",
            "aelita_host_key_mode": "pinned",
            "aelita_host_key_sha256": "",
            "aelita_ssh_connect_timeout": 7,
        },
    )()
    proxy = wrapper._SubprocessProxy(options)
    original = [sys.executable, str(ROOT / "tools/run_aelita_2g_wpa2_runtime_psk_once.py"), "--execute"]
    proxy.run(original)
    rewritten = captured[-1]
    assert rewritten[1] == str(wrapper.RUNTIME_V2)
    assert rewritten[rewritten.index("--aelita-host-key-mode") + 1] == "pinned"
    assert rewritten[rewritten.index("--aelita-ssh-connect-timeout") + 1] == "7"
    assert "--aelita-host-key-sha256" not in rewritten


def test_wrappers_and_soak_do_not_embed_credentials_or_public_keys() -> None:
    paths = (
        ROOT / "tools/aelita_ssh_policy.py",
        RUNTIME,
        SPEED,
        RADIO5,
        ROOT / "tools/run_f301_sequential_dual_radio_soak_ssh_v2.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in (
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
        "wpa_passphrase=",
        "psk=",
    ):
        assert forbidden not in combined
    assert "ssh-keyscan" in (ROOT / "tools/aelita_ssh_policy.py").read_text(encoding="utf-8")
    assert "ssh-keyscan" not in RUNTIME.read_text(encoding="utf-8")
    assert "ssh-keyscan" not in SPEED.read_text(encoding="utf-8")
    assert "ssh-keyscan" not in RADIO5.read_text(encoding="utf-8")
