from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f151_5g_bridge_trial.py"


def test_cleanup_timeouts_do_not_hide_radio_result() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'result["speed_server_cleanup"]' in text
    assert 'result["oracle_restore_task_cleanup"]' in text
    assert 'result["temporary_profile_cleanup"]' in text
    assert text.count('"status": "WARN"') >= 3
    assert '"--lightweight"' in text
    assert '"--buffered"' in text
    assert "def read_interface_packets" in text
    assert 'router["counter_source"] = "pre-post-proc-net-dev"' in text
    assert "def read_association_evidence" in text
    assert 'router["association_source"] = "post-run-hostapd-log-tail"' in text
