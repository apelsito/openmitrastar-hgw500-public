"""Regression tests for CAC-time backend loss and tuned-block drift."""
from __future__ import annotations

import json
from pathlib import Path
import shlex

import pytest

from test_f316_qtn_dfs_controls import create_f316_fake


ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "versions/lyoko-dfs-contract-v1/overlay/usr/sbin/om-qtnctl"


@pytest.mark.parametrize("fault,expected", [
    ("backend", "dfs-backend-lost-during-cac"),
    ("channel", "dfs-cac-target-changed:100:40"),
    ("bandwidth", "dfs-cac-target-changed:52:20"),
])
def test_cac_fault_never_reports_success_and_restores_original_radio(tmp_path, fault, expected):
    helpers, env, _, wsl_root = create_f316_fake(tmp_path)
    try:
        iwpriv = tmp_path / "bin/iwpriv"
        source = iwpriv.read_text(encoding="ascii")
        injection = {
            "backend": "printf '0\\n' > \"$root/dfs-ready\"",
            "channel": "printf '100\\n' > \"$root/channel\"",
            "bandwidth": "printf '20\\n' > \"$root/bandwidth\"",
        }[fault]
        source = source.replace("get_cacstatus)\n", f"get_cacstatus)\n  if [ -f \"$root/inject-cac-fault\" ]; then\n    {injection}\n    rm -f \"$root/inject-cac-fault\"\n  fi\n", 1)
        helpers.write_ascii(iwpriv, source)
        helpers.write_ascii(tmp_path / "inject-cac-fault", "1\n")
        request = tmp_path / "request.conf"
        helpers.write_ascii(request, "band=5g\nchannel=52\nbandwidth=40\n")
        result = helpers.run_wsl(
            f"{env} sh {shlex.quote(helpers.wsl_path(CONTROL))} apply {shlex.quote(helpers.wsl_path(request))}"
        )
        assert result.returncode == 1, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert expected in payload["detail"]
        assert "self_rollback=restored" in payload["detail"], payload
        assert (tmp_path / "channel").read_text(encoding="ascii").strip() == "36"
        assert (tmp_path / "bandwidth").read_text(encoding="ascii").strip() == "80"
    finally:
        helpers.cleanup_fake_qtn(wsl_root)


def test_normal_cac_completion_still_applies(tmp_path):
    helpers, env, _, wsl_root = create_f316_fake(tmp_path)
    try:
        request = tmp_path / "request.conf"
        helpers.write_ascii(request, "band=5g\nchannel=52\nbandwidth=40\n")
        result = helpers.run_wsl(
            f"{env} sh {shlex.quote(helpers.wsl_path(CONTROL))} apply {shlex.quote(helpers.wsl_path(request))}"
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "channel").read_text(encoding="ascii").strip() == "52"
        assert (tmp_path / "bandwidth").read_text(encoding="ascii").strip() == "40"
    finally:
        helpers.cleanup_fake_qtn(wsl_root)
