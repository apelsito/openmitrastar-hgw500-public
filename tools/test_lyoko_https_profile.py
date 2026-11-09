import pytest

from lyoko_https_profile import CIPHERS, LEGACY_CONFIG, OLD_ROUTE, NEW_ROUTE, modernize_config, loopback_config, routing_before_config


def test_only_three_deliberate_lines_change():
    before = LEGACY_CONFIG.splitlines()
    after = modernize_config(LEGACY_CONFIG).splitlines()
    assert len(before) == len(after)
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [0, 4, 9]
    assert NEW_ROUTE in modernize_config(LEGACY_CONFIG)
    assert all("GCM" in name or "CHACHA20" in name for name in CIPHERS.split(":"))


@pytest.mark.parametrize("data", [LEGACY_CONFIG + b"host=0.0.0.0\n", LEGACY_CONFIG.replace(b"port=443", b"port=444"), b""])
def test_unknown_source_is_rejected(data):
    with pytest.raises(ValueError):
        modernize_config(data)


def test_host_binding_cannot_reach_the_router():
    for production in (modernize_config(LEGACY_CONFIG), routing_before_config()):
        test = loopback_config(production, 4199)
        assert b"host=127.0.0.1\n" in test and b"192.168.1.90" not in test
        assert b"port=4199\n" in test and b"certfile=/run/https.pem\n" in test
        assert test.count(b"cgipat=") == 1
        assert (NEW_ROUTE if NEW_ROUTE in production else OLD_ROUTE) in test


@pytest.mark.parametrize("port", [True, 80, -1, 65536, "4199"])
def test_bad_test_ports_fail_closed(port):
    with pytest.raises(ValueError):
        loopback_config(modernize_config(LEGACY_CONFIG), port)


def test_test_profile_cannot_silently_widen_cgi_scope():
    with pytest.raises(ValueError):
        loopback_config(modernize_config(LEGACY_CONFIG).replace(NEW_ROUTE, b"cgipat=**\n"), 4199)
