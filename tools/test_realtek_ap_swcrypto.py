#!/usr/bin/env python3
"""Static gate for the MitraStar AP software-crypto fallback."""

from pathlib import Path


CORE = Path(
    r"\\wsl.localhost\podman-mem9-tidb\home\user\mitrastar-linux-5.10.260"
    r"\drivers\net\wireless\realtek\rtlwifi\core.c"
)


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(f"STATIC_FAIL {message}")


text = CORE.read_text(encoding="utf-8")
start = text.index("static int rtl_op_set_key")
end = text.index("static void rtl_op_rfkill_poll", start)
body = text[start:end]

tokens = [
    'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
    "rtlhal->hw_type == HARDWARE_TYPE_RTL8192EE",
    "vif->type == NL80211_IFTYPE_AP",
    'pr_info_once("OMRTL stage=ap-swcrypto-fallback accepted',
    "return 1;",
    "return -ENOSPC;",
]
positions = [body.index(token) for token in tokens]
require(positions == sorted(positions), "scope/fallback order changed")
require("#include <linux/of.h>" in text, "machine compatibility header missing")

print("STATIC_PASS policy=mitrastar+rtl8192ee+ap+swenc")
print("STATIC_PASS fallback=mac80211-software-key-return-1")
