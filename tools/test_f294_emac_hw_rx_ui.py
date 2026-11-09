from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-6.5.2-f294-emac-hw-rx-ui"
OVERLAY = FOUNDATION / "overlay"


def test_hardware_rx_path_is_explainable() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    css = (OVERLAY / "www/app.css").read_text(encoding="utf-8")
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    emulator = (FOUNDATION / "emulator/server.py").read_text(encoding="utf-8")

    assert 'id="rx-path"' in html
    for marker in (".rx-path", ".rx-stage.ok", ".rx-stage.warning", ".rx-stage.bad"):
        assert marker in css
    for marker in (
        "renderRxPath",
        "Tramas físicas RX",
        "Pérdidas DMA",
        "Tráfico antes del reinicio",
        "Bloqueo RX con tráfico físico",
        "mac_rx_frames",
        "mac_rx_progress_observations",
        "rx_restart_last_mac_rx_progress_age_ms",
    ):
        assert marker in js
    for marker in (
        "mac_rx_frames_valid",
        "mac_rx_frames",
        "mac_rx_progress_observations",
        "dma_missed_frames_total",
        "rx_restart_last_mac_rx_progress_age_ms",
    ):
        assert marker in emulator


def test_frontend_identity_and_javascript_are_current() -> None:
    identity = (OVERLAY / "etc/lyoko/frontend.env").read_text(encoding="ascii")
    assert "LYOKO_UI_VERSION=6.5.2" in identity
    assert "LYOKO_UI_SOURCE=lyoko-foundation-6.5.2-f294-emac-hw-rx-ui" in identity
    check = subprocess.run(
        [
            "python",
            str(ROOT / "tools/update_lyoko_frontend_identity.py"),
            str(FOUNDATION),
            "--version",
            "6.5.2",
            "--source",
            "lyoko-foundation-6.5.2-f294-emac-hw-rx-ui",
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stderr
    syntax = subprocess.run(
        ["node", "--check", str(OVERLAY / "www/app.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
