import pytest
import f325_ui_gate as gate


def baseline():
    return "OMF325_BASELINE_BEGIN\nlifecycle=f325-single-boot-reset-required\nonce_phase=0\nhardware_dirty=0\nreboot_required=0\nshadow_arm=0\nconfigured=0\npolling=0\npoll_runs=0\nmmio_writes=0\ncallback_invocations=0\nbackend_ready=0\nsample_window_ms=20000\nchannel=36\nbandwidth=80\nOMF325_BASELINE_END\n"


def test_unarmed_f325_baseline():
    assert gate.verify_baseline(baseline())["mmio_writes"] == 0


@pytest.mark.parametrize("field", ["once_phase", "hardware_dirty", "reboot_required", "shadow_arm", "configured", "polling", "poll_runs", "mmio_writes", "callback_invocations", "backend_ready"])
def test_dirty_or_active_f325_is_not_an_unarmed_baseline(field):
    with pytest.raises(ValueError):
        gate.verify_baseline(baseline().replace(field + "=0", field + "=1"))


def test_duplicate_and_missing_fields_refused():
    with pytest.raises(ValueError):
        gate.verify_baseline(baseline().replace("channel=36", "channel=36\nchannel=36"))
    with pytest.raises(ValueError):
        gate.verify_baseline(baseline().replace("channel=36\n", ""))
