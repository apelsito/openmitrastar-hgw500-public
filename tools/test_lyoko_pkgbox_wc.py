from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_lyoko_pkgbox.sh"


def test_pkgbox_contains_wc_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "head wc dd mkdir" in text
    assert "CONFIG_WC=y" in text
    assert "CONFIG_SHA512SUM=y" in text
    assert "CONFIG_DD=y" in text
    assert "CONFIG_BUSYBOX=y" in text
    assert "--enable STATIC --enable STATIC_LIBGCC --enable BUSYBOX" in text
    assert "--enable HEAD --enable WC" in text
    assert '"wc", "dd", "mkdir"' in text
    assert '"sha512sum"' in text
    assert '"dd"' in text
    assert '"multicall_invocation": true' in text
