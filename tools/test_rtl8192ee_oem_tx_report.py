from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = (
    ROOT
    / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
)
OEM = (
    ROOT
    / "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/files"
    / "drivers/net/wireless/rtl8192cd"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


source = TRX.read_text(encoding="utf-8")
oem_sme = (OEM / "8192cd_sme.c").read_text(encoding="utf-8", errors="replace")
oem_gen = (
    OEM / "WlanHAL/RTL88XX/RTL8192E/RTL8192EE/Hal8192EEGen.c"
).read_text(encoding="utf-8", errors="replace")

require("static bool hgw500_oem_tx_report;" in source, "opt-in parameter missing")
require(
    'module_param_named(hgw500_oem_tx_report,' in source,
    "module parameter registration missing",
)
require("#define H2C_92E_AP_REQ_TX_REPORT\t0x43" in source, "H2C id mismatch")
require("#define C2H_92E_AP_TX_REPORT\t\t0x04" in source, "C2H id mismatch")
require("get_unaligned_le16(report + 1)" in source, "txok parser missing")
require("get_unaligned_le16(report + 3)" in source, "txfail parser missing")
require("cmd_id = frame[0];" in source and "seq = frame[1];" in source, "C2H header parser missing")
require("time_before(jiffies," in source and "+ HZ" in source, "request pacing missing")
require("request[1] = 2;" in source, "known live MACID fallback missing")

c2h_guard = source.index("if (status->packet_report_type == C2H_PACKET")
hdr_parse = source.index("hdr = (struct ieee80211_hdr *)frame;", c2h_guard)
require(c2h_guard < hdr_parse, "C2H must exit before 802.11 header parsing")

request_fn = source[source.index("static void rtl92ee_hgw500_request_oem_tx_report") :]
request_fn = request_fn[: request_fn.index("static void rtl92ee_hgw500_trace_c2h")]
for forbidden in ("set_tx_desc_", "dma_", "HW_DESC_OWN", "tx_polling"):
    require(forbidden not in request_fn, f"observation helper changes {forbidden}")

require("H2C_88XX_AP_REQ_TXREP\t\t= 0x43" in (OEM / "WlanHAL/RTL88XX/Hal88XXFirmware.h").read_text(encoding="utf-8", errors="replace"), "OEM H2C contract mismatch")
require("H2CCommand[0] = REMAP_AID(sta);" in oem_sme, "OEM MACID request evidence missing")
require("C2H_8192E_TX_RATE =4" in oem_gen, "OEM C2H report id mismatch")
require("rpt1.txok = CmdBuf[k+1]" in oem_gen, "OEM txok layout evidence missing")
require("rpt1.txfail = CmdBuf[k+3]" in oem_gen, "OEM txfail layout evidence missing")
require("rpt1.initil_tx_rate = CmdBuf[k+5]" in oem_gen, "OEM rate layout evidence missing")

print("RTL8192EE_OEM_TX_REPORT_SOURCE_PASS")
