from copy import deepcopy
import json
import sys
from types import SimpleNamespace
import pytest
import run_f325_capture as gate


REGION = "wifi0     get_region:21317\n"
MODE = "wifi0     get_mode:11ac80Edge+\n"
WIRELESS = ('wifi0     IEEE 802.11ac  ESSID:"private-network"\n'
            '          Mode:Master  Frequency:5.18 GHz  Access Point: 02:00:00:00:00:01\n'
            '          Bit Rate:0 kb/s   Tx-Power:0 dBm\n')


@pytest.mark.parametrize("prefix,newline", [("wifi0     ", "\n"), ("", "\r\n")])
def test_radio_profile_is_exact_and_drops_private_fields(prefix, newline):
    result = gate.parse_radio_profile(prefix + "get_region:21317" + newline,
                                     prefix + "get_mode:11ac80Edge+" + newline, WIRELESS)
    assert result == {"region": "ES", "current_channel": 36, "bandwidth_mhz": 80}
    assert "private-network" not in str(result) and "02:00:00:00:00:01" not in str(result)


@pytest.mark.parametrize("region,mode,wireless", [
    ("", MODE, WIRELESS),
    (REGION, "", WIRELESS),
    (REGION, MODE, ""),
    (REGION + REGION, MODE, WIRELESS),
    (REGION, MODE + MODE, WIRELESS),
    (REGION, MODE, WIRELESS + "          Frequency:5.18 GHz\n"),
    (REGION, MODE, WIRELESS + "          Frequency:\n"),
    (REGION.replace("21317", "21843"), MODE, WIRELESS),
    (REGION.replace("21317", "ES"), MODE, WIRELESS),
    (REGION.replace("21317", "+21317"), MODE, WIRELESS),
    (REGION.replace("wifi0", "wifi1"), MODE, WIRELESS),
    (REGION, MODE.replace("11ac80Edge+", "11ac20"), WIRELESS),
    (REGION, MODE.replace("11ac80Edge+", "11ac160"), WIRELESS),
    (REGION, MODE.replace("11ac80Edge+", "11ac80Edge+extra"), WIRELESS),
    (REGION, MODE, WIRELESS.replace("5.18", "5.2")),
    (REGION, MODE, WIRELESS.replace("GHz", "MHz")),
    (REGION, MODE, WIRELESS.replace("5.18", "5.18extra")),
    (REGION, MODE, 'wifi0  ESSID:"Frequency:5.18 GHz"\n'),
    (REGION, MODE, WIRELESS.replace("private-network", "Frequency:5.18 GHz")),
])
def test_unsafe_or_ambiguous_radio_profile_refused(region, mode, wireless):
    with pytest.raises(ValueError):
        gate.parse_radio_profile(region, mode, wireless)


def rows(empty=True):
    first = dict(boot_id="fixture", config_failures=0, mmio_write_refusals=0, map_failures=0,
                 once_phase=0, shadow_arm=0, polling=0, hardware_dirty=0, reboot_required=0,
                 config_attempts=0, stop_reason=0, poll_runs=0, poll_empty=0, mmio_writes=0)
    final = dict(first, once_phase=2, hardware_dirty=1, reboot_required=1, config_attempts=1,
                 stop_reason=2, poll_runs=400, poll_empty=400 if empty else 350, mmio_writes=1500)
    return [first, deepcopy(final), deepcopy(final)]


def test_empty_capture_never_claims_radar():
    result = gate.validate_stopped(rows())
    assert result["status"] == "INCONCLUSIVE_NO_PULSES"
    assert not result["physical_radar_detection_proven"] and not result["hardware_restore_proven"]


def test_nonempty_capture_is_only_activity():
    result = gate.validate_stopped(rows(False))
    assert result["status"] == "CAPTURE_ACTIVITY_OBSERVED"
    assert not result["physical_radar_detection_proven"]


@pytest.mark.parametrize("field,value", [("polling",1),("shadow_arm",1),("hardware_dirty",0),
    ("reboot_required",0),("config_attempts",2),("stop_reason",3),("poll_runs",401),
    ("mmio_writes",1501),("map_failures",1),("boot_id","another")])
def test_stop_or_continuity_failure_refused(field,value):
    data=rows();data[-1][field]=value
    with pytest.raises(ValueError):gate.validate_stopped(data)


@pytest.mark.parametrize("index", [-2, -1])
def test_manual_stop_is_never_accepted_as_automatic_deadline(index):
    data = rows()
    data[index]["stop_reason"] = 1
    with pytest.raises(ValueError):
        gate.validate_stopped(data)


def test_missing_automatic_deadline_is_refused():
    data = rows()
    for row in data[-2:]:
        row.update(once_phase=1, shadow_arm=1, polling=1, stop_reason=0)
    with pytest.raises(ValueError):
        gate.validate_stopped(data)


def simulated_capture(monkeypatch, tmp_path, behavior):
    """Exercise the real host sequence with every external boundary replaced."""
    state = {"time": 0.0, "armed": False, "cleanup_stopped": False, "events": []}
    pristine = dict(rows()[0], configured=0)

    def observe():
        state["events"].append(("observe", state["time"]))
        if not state["armed"]:
            return deepcopy(pristine)
        stopped = state["cleanup_stopped"] or (behavior != "missing" and state["time"] >= 20)
        reason = 1 if state["cleanup_stopped"] else {"automatic": 2, "manual": 1, "other": 3}.get(behavior, 0)
        count = int(min(state["time"], 20) * 20)
        return dict(pristine, configured=1, once_phase=2 if stopped else 1,
                    hardware_dirty=1, reboot_required=1, config_attempts=1,
                    shadow_arm=int(not stopped), polling=int(not stopped),
                    stop_reason=reason if stopped else 0,
                    poll_runs=count, poll_empty=count, mmio_writes=count * 3)

    def ssh(script):
        if script == "/usr/sbin/iwpriv-qtn wifi0 get_region\n":
            return REGION
        if script == "/usr/sbin/iwpriv-qtn wifi0 get_mode\n":
            return MODE
        if script == "/usr/sbin/iwconfig-qtn wifi0\n":
            return WIRELESS
        if script == "OM_F325_CAPTURE_ACK=OPENMITRASTAR_F325_CAPTURE_ONCE_20S /usr/sbin/om-radar-once arm >/dev/null\n":
            state["armed"] = True
            state["events"].append(("arm", state["time"]))
            return ""
        if script == "/usr/sbin/om-radar-once stop >/dev/null\n":
            state["cleanup_stopped"] = True
            state["events"].append(("stop", state["time"]))
            return ""
        raise AssertionError("unexpected external command")

    def sleep(seconds):
        state["time"] += seconds

    output = tmp_path / "capture"
    monkeypatch.setattr(gate.contract, "validate_sealed_inputs", lambda: {})
    monkeypatch.setattr(gate, "subprocess", SimpleNamespace(
        run=lambda *args, **kwargs: SimpleNamespace(returncode=0),
        SubprocessError=gate.subprocess.SubprocessError))
    monkeypatch.setattr(gate, "ssh", ssh)
    monkeypatch.setattr(gate, "observe", observe)
    monkeypatch.setattr(gate, "time", SimpleNamespace(monotonic=lambda: state["time"], sleep=sleep))
    monkeypatch.setenv("OM_F325_PHYSICAL_CONTEXT", "test-only-context")
    monkeypatch.setattr(sys, "argv", ["run_f325_capture.py", "--execute", "--output-dir", str(output)])
    code = gate.main()
    report = json.loads((output / "result.json").read_text(encoding="ascii"))
    observations = json.loads((output / "observations.json").read_text(encoding="ascii"))
    return code, report, observations, state["events"]


def test_runner_observes_automatic_stop_twice_without_manual_stop(monkeypatch, tmp_path):
    code, report, observations, events = simulated_capture(monkeypatch, tmp_path, "automatic")
    assert code == 0 and report["status"] == "INCONCLUSIVE_NO_PULSES"
    assert all(event != "stop" for event, timestamp in events)
    assert observations[-2]["stop_reason"] == observations[-1]["stop_reason"] == 2
    assert events[-1][0] == events[-2][0] == "observe"
    assert events[-1][1] - events[-2][1] >= 1
    assert not report["hardware_restore_proven"] and not report["physical_radar_detection_proven"]


@pytest.mark.parametrize("behavior", ["missing", "manual", "other"])
def test_runner_deadline_failure_stays_failed_after_cleanup(monkeypatch, tmp_path, behavior):
    code, report, observations, events = simulated_capture(monkeypatch, tmp_path, behavior)
    assert code == 2 and report["status"] == "FAIL_CAPTURE"
    assert report["stop_command_completed"] is True
    assert report["mandatory_next_phase"] == "EXACT_F321_RESTORE"
    assert events[-1][0] == "stop" and events[-1][1] >= 23
    assert [event for event, timestamp in events].count("stop") == 1
    assert observations[-1]["stop_reason"] != 2
    if behavior == "missing":
        assert observations[-1]["once_phase"] == observations[-1]["polling"] == 1
