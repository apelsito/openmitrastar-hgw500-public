from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_probe_hashes_ed25519_challenge_input() -> None:
    source = (ROOT / "tools/lyoko_sha512_probe.c").read_text(encoding="utf-8")
    assert "sha512_process(&state, prefix, 32)" in source
    assert "hash_file_contents(&state, argv[3])" in source
    assert "sha512_done(&state, digest)" in source
    assert "aligned(8)" in source


def test_builder_is_offline_only() -> None:
    source = (ROOT / "tools/build_lyoko_sha512_probe.sh").read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
    assert "sha512-neutral.o" in source
    assert "ENDIAN_NEUTRAL" in source
