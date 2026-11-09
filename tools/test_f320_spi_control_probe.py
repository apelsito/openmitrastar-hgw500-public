"""Offline F320 source/ELF-contract regressions. Does not invoke a builder."""
from pathlib import Path
import pytest
import build_f320_spi_control_probe as build

SOURCE = build.SOURCE / f"{build.NAME}.c"


def test_current_source_contract():
    build.check_source(SOURCE.read_text(encoding="ascii"))


@pytest.mark.parametrize("old,new", [
    ("0xe2000000u", "0xe4030000u"),
    ("#define TOPAZ_SPI_CONTROL 0x0004u", "#define TOPAZ_SPI_CONTROL 0x9f00u"),
    ("#define TOPAZ_MAP_BITS 0x60000000u", "#define TOPAZ_MAP_BITS 0x0u"),
    ("if (!execute_read)", "if (false)"),
    ("return readl(address);", "return 0;"),
    ("return readl(address);", "writel(0, address); return readl(address);"),
])
def test_contract_rejects_wrong_address_or_expanded_access(old, new):
    with pytest.raises(ValueError):
        build.check_source(SOURCE.read_text(encoding="ascii").replace(old, new))


def helpers(extra=""):
    return ("00000000 <read_map_once>:\n   0: 1000 0000    ld r0,[r0]\n"
            "   4: 7ee0    j_s [blink]\n\n"
            "00000008 <read_control_once>:\n   8: 1000 0000    ld r0,[r0]\n" +
            extra + "   c: 7ee0    j_s [blink]\n")


def test_one_actual_load_per_helper():
    build.check_read_helpers(helpers())


@pytest.mark.parametrize("extra", ["   a: 0000    st r1,[r0]\n",
    "   a: 0000    ld r2,[r0]\n", "   a: 0000    bl 0\n", "   a: 0000    b 8\n"])
def test_binary_gate_rejects_extra_access_or_control_flow(extra):
    with pytest.raises(ValueError):
        build.check_read_helpers(helpers(extra))


def test_binary_gate_rejects_merged_helpers():
    with pytest.raises(ValueError):
        build.check_read_helpers(helpers().replace("<read_map_once>", "<merged>"))
