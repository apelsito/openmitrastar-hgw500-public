from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "om_bridge_fdb_nolibc.c"


def test_nolibc_reader_contract():
    text = SOURCE.read_text(encoding="utf-8")
    for marker in (
        '"/sys/class/net/br0/brforward"',
        '"/sys/class/net/br0/brif/eth0/port_no"',
        '"/sys/class/net/br0/brif/wlan0/port_no"',
        '"lookup"',
        '"dump"',
        "OM_FDB_RECORD_SIZE 16U",
        "runtime=arc700-nolibc-readonly",
        "void om_fdb_main(om_word *stack)",
        '"trap0"',
        '".global _start\\n"',
    ):
        assert marker in text
    for forbidden in (
        "RTM_NEWNEIGH",
        "RTM_DELNEIGH",
        "OM_NR_OPEN ",
        "OM_O_WRONLY",
        "OM_O_CREAT",
        "OM_O_TRUNC",
    ):
        assert forbidden not in text
