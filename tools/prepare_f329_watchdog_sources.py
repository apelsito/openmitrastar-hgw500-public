"""Create isolated F329 source overlay from the pinned local Linux 5.10 tree.

File-only: no device, firmware, network, privilege or startup operations.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/kernel-port/versions/f329-watchdog"
KERNEL = "/home/user/mitrastar-linux-5.10.260"
DISTRO = "podman-mem9-tidb"


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"source contract changed: {old[:100]!r}")
    return text.replace(old, new, 1)


def main():
    if OUT.exists():
        raise SystemExit("F329 source overlay already exists; preserve it")
    OUT.mkdir(parents=True)
    originals = {}

    def read(path):
        p = subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "--", "cat", KERNEL + "/" + path], capture_output=True, check=True)
        originals[path] = hashlib.sha256(p.stdout).hexdigest()
        target = OUT / "upstream" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.stdout)
        return p.stdout.decode()

    def put(path, text):
        target = OUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    path = "drivers/watchdog/dw_wdt.c"
    s = read(path)
    s = once(s, "struct dw_wdt {\n", "struct dw_wdt {\n\t/* F329: legacy Topaz register window and explicit experiment opt-in. */\n\tbool\t\t\ttopaz;\n")
    s = once(s, "\tu32 top_val;\n\n\t/*\n\t * Note IRQ", "\tu32 top_val;\n\n\tif (dw_wdt->topaz && (top_s < wdd->min_timeout ||\n\t\t\t       top_s > wdd->max_timeout))\n\t\treturn -EINVAL;\n\n\t/*\n\t * Note IRQ")
    s = once(s, "writel(top_val | top_val << WDOG_TIMEOUT_RANGE_TOPINIT_SHIFT,", "/* Topaz BSP documents only the low TORR nibble, not TOPINIT. */\n\twritel(dw_wdt->topaz ? top_val :\n\t       top_val | top_val << WDOG_TIMEOUT_RANGE_TOPINIT_SHIFT,")
    s = once(s, "\t/*\n\t * We ignore actual value", "\t/* IRQ delivery/polarity has not been physically qualified on Topaz. */\n\tif (dw_wdt->topaz)\n\t\treturn -EOPNOTSUPP;\n\n\t/*\n\t * We ignore actual value")
    s = once(s, "\tdw_wdt_set_timeout(wdd, wdd->timeout);\n\tdw_wdt_ping(&dw_wdt->wdd);", "\tint ret = dw_wdt_set_timeout(wdd, wdd->timeout);\n\n\tif (ret)\n\t\treturn ret;\n\tdw_wdt_ping(&dw_wdt->wdd);")
    s = once(s, "\tdw_wdt_arm_system_reset(dw_wdt);\n\n\treturn 0;", "\tdw_wdt_arm_system_reset(dw_wdt);\n\t/* Irreversible until reset: core must retain the owner after close. */\n\tif (dw_wdt->topaz)\n\t\tset_bit(WDOG_HW_RUNNING, &wdd->status);\n\n\treturn 0;")
    s = once(s, "\tif (!dw_wdt->rst) {", "\t/* No per-watchdog reset/disable primitive is established for Topaz. */\n\tif (dw_wdt->topaz)\n\t\treturn -EBUSY;\n\n\tif (!dw_wdt->rst) {")
    s = once(s, "static const struct watchdog_info dw_wdt_pt_ident", "static const struct watchdog_info topaz_wdt_ident = {\n\t.options = WDIOF_KEEPALIVEPING | WDIOF_SETTIMEOUT,\n\t.identity = \"Topaz DesignWare watchdog\",\n};\n\nstatic const struct watchdog_info dw_wdt_pt_ident")
    s = once(s, "\tdata = readl(dw_wdt->regs + WDOG_COMP_PARAMS_1_REG_OFFSET);", "\t/* Topaz has only 0x20 documented bytes. Never probe +0xf4. */\n\tif (dw_wdt->topaz) {\n\t\ttops = dw_wdt_fix_tops;\n\t\tgoto handle_tops;\n\t}\n\tdata = readl(dw_wdt->regs + WDOG_COMP_PARAMS_1_REG_OFFSET);")
    s = once(s, "\t/* Convert the specified TOPs", "handle_tops:\n\t/* Convert the specified TOPs")
    s = once(s, "\tregset = devm_kzalloc(dev, sizeof(*regset), GFP_KERNEL);", "\t/* Generic register dump reaches undocumented component registers. */\n\tif (dw_wdt->topaz)\n\t\treturn;\n\tregset = devm_kzalloc(dev, sizeof(*regset), GFP_KERNEL);")
    s = once(s, "\tint ret;\n\n\tdw_wdt = devm_kzalloc", "\tint ret;\n\tbool topaz = of_device_is_compatible(dev->of_node,\n\t\t\t\t\t     \"quantenna,topaz-wdt-f329\");\n\n\t/* Reject unreviewed DTs before mapping or touching any register. */\n\tif (topaz) {\n\t\tstruct resource *res = platform_get_resource(pdev, IORESOURCE_MEM, 0);\n\n\t\tif (!of_machine_is_compatible(\"mitrastar,hgw-500bna-qcv2\") ||\n\t\t    !of_property_read_bool(dev->of_node,\n\t\t\t\t\t   \"quantenna,watchdog-experiment\"))\n\t\t\treturn -EPERM;\n\t\tif (!res || res->start != 0xf4000000 || resource_size(res) != 0x20)\n\t\t\treturn -EINVAL;\n\t}\n\n\tdw_wdt = devm_kzalloc")
    s = once(s, "\tdw_wdt->regs = devm_platform_ioremap_resource(pdev, 0);", "\tdw_wdt->topaz = topaz;\n\tdw_wdt->regs = devm_platform_ioremap_resource(pdev, 0);")
    s = once(s, "\tif (dw_wdt->rate == 0) {", "\tif (dw_wdt->rate == 0 || (topaz && dw_wdt->rate != 125000000)) {")
    s = once(s, "\tdw_wdt->rst = devm_reset_control_get_optional_shared(&pdev->dev, NULL);", "\tdw_wdt->rst = topaz ? NULL :\n\t\tdevm_reset_control_get_optional_shared(&pdev->dev, NULL);")
    s = once(s, "\t/* Enable normal reset without pre-timeout by default. */\n\tdw_wdt_update_mode(dw_wdt, DW_WDT_RMOD_RESET);", "\t/* Topaz probe is read-only: defer control writes until start. */\n\tif (topaz)\n\t\tdw_wdt->rmod = DW_WDT_RMOD_RESET;\n\telse\n\t\tdw_wdt_update_mode(dw_wdt, DW_WDT_RMOD_RESET);")
    s = once(s, "\tret = platform_get_irq_optional(pdev, 0);", "\tret = topaz ? -ENXIO : platform_get_irq_optional(pdev, 0);")
    s = once(s, "\t\tdw_wdt->wdd.info = &dw_wdt_ident;", "\t\tdw_wdt->wdd.info = topaz ? &topaz_wdt_ident : &dw_wdt_ident;")
    s = once(s, "\twatchdog_set_nowayout(wdd, nowayout);", "\t/* No stop primitive, so never advertise safe close or unload. */\n\twatchdog_set_nowayout(wdd, topaz || nowayout);\n\tif (topaz)\n\t\twdd->max_timeout = wdd->max_hw_heartbeat_ms / 1000;")
    s = once(s, "\tif (dw_wdt_is_enabled(dw_wdt)) {\n\t\twdd->timeout", "\tif (dw_wdt_is_enabled(dw_wdt)) {\n\t\t/* Never adopt/retime an unknown pre-armed Topaz watchdog. */\n\t\tif (topaz) {\n\t\t\tret = -EBUSY;\n\t\t\tgoto out_assert_rst;\n\t\t}\n\t\twdd->timeout")
    s = once(s, "\t\twdd->timeout = DW_WDT_DEFAULT_SECONDS;\n\t\twatchdog_init_timeout(wdd, 0, dev);\n\t\t/* Limit timeout value to hardware constraints. */\n\t\tdw_wdt_set_timeout(wdd, wdd->timeout);", "\t\twdd->timeout = topaz ? 8 : DW_WDT_DEFAULT_SECONDS;\n\t\tret = watchdog_init_timeout(wdd, 0, dev);\n\t\tif (topaz && ret)\n\t\t\tgoto out_assert_rst;\n\t\t/* Topaz probe never writes TORR, CR or CRR. */\n\t\tif (topaz) {\n\t\t\tu32 top;\n\n\t\t\twdd->timeout = dw_wdt_find_best_top(dw_wdt, wdd->timeout, &top);\n\t\t} else {\n\t\t\tdw_wdt_set_timeout(wdd, wdd->timeout);\n\t\t}")
    s = once(s, "\tdw_wdt_dbgfs_clear(dw_wdt);", "\t/* Built-in plus suppressed bind attributes prevent active removal. */\n\tif (dw_wdt->topaz && (watchdog_active(&dw_wdt->wdd) ||\n\t\t\t     watchdog_hw_running(&dw_wdt->wdd)))\n\t\treturn -EBUSY;\n\tdw_wdt_dbgfs_clear(dw_wdt);")
    s = once(s, "\t{ .compatible = \"snps,dw-wdt\", },", "\t{ .compatible = \"quantenna,topaz-wdt-f329\", },\n\t{ .compatible = \"snps,dw-wdt\", },")
    s = once(s, "\t\t.name\t= \"dw_wdt\",", "\t\t.name\t= \"dw_wdt\",\n\t\t.suppress_bind_attrs = true,")
    put(path, s)

    path = "drivers/misc/qtn-topaz-recovery.c"
    s = read(path)
    s = once(s, "\twritel(WDT_ENABLE, rec->wdt + WDT_CONTROL);\n\twritel(WDT_RESET_TIMEOUT, rec->wdt + WDT_TIMEOUT_RANGE);\n\twritel(WDT_RESTART_MAGIC, rec->wdt + WDT_COUNTER_RESTART);", "\tif (rec->wdt) {\n\t\twritel(WDT_ENABLE, rec->wdt + WDT_CONTROL);\n\t\twritel(WDT_RESET_TIMEOUT, rec->wdt + WDT_TIMEOUT_RANGE);\n\t\twritel(WDT_RESTART_MAGIC, rec->wdt + WDT_COUNTER_RESTART);\n\t}")
    s = once(s, "\trec->wdt = devm_platform_ioremap_resource(pdev, 2);\n\tif (IS_ERR(rec->wdt))\n\t\treturn PTR_ERR(rec->wdt);", "\t/* F329 single-owner contract: dedicated watchdog owns this resource. */\n\tif (!of_property_read_bool(dev->of_node, \"quantenna,separate-watchdog\")) {\n\t\trec->wdt = devm_platform_ioremap_resource(pdev, 2);\n\t\tif (IS_ERR(rec->wdt))\n\t\t\treturn PTR_ERR(rec->wdt);\n\t}")
    put(path, s)
    path = "arch/arc/kernel/reset.c"
    s = read(path)
    s = once(s, "\t/* Exact watchdog + full-chip sysctl sequence from the Topaz GPL BSP. */", "\t/* Give the registered owners the first terminal restart attempt. */\n\tdo_kernel_restart(__unused);\n\n\t/* Preserve the exact OEM fallback when no handler exists or it returns.\n\t * This terminal, sequential path is not a second runtime MMIO owner.\n\t */")
    put(path, s)
    path = "arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
    s = read(path)
    s = once(s, "reg = <0xe0000000 0x200>, <0xf1000000 0x40>,\n\t\t\t      <0xf4000000 0x20>;\n\t\t\treg-names = \"sysctl\", \"gpio\", \"watchdog\";", "reg = <0xe0000000 0x200>, <0xf1000000 0x40>;\n\t\t\treg-names = \"sysctl\", \"gpio\";\n\t\t\tquantenna,separate-watchdog;")
    s = once(s, "\t\t\tmitrastar,product-watchdog-canary;\n\t\t\tqtn,product-watchdog-timeout-range = <15>;\n\t\t\tqtn,product-watchdog-pet-seconds = <1>;", "\t\t\t/* No autonomous early/head watchdog canary in F329. */")
    s = once(s, "\tuart_clk: uart-clock {", "\twdt_clk: watchdog-clock {\n\t\tcompatible = \"fixed-clock\";\n\t\t#clock-cells = <0>;\n\t\t/* ASIC APB specification, NOT a measured watchdog rate. */\n\t\tclock-frequency = <125000000>;\n\t};\n\n\tuart_clk: uart-clock {")
    s = once(s, "\t\ttopaz_irqc: interrupt-controller@e0000000 {", "\t\twatchdog@f4000000 {\n\t\t\tcompatible = \"quantenna,topaz-wdt-f329\";\n\t\t\treg = <0xf4000000 0x20>;\n\t\t\tclocks = <&wdt_clk>;\n\t\t\tclock-names = \"tclk\";\n\t\t\ttimeout-sec = <8>;\n\t\t\t/* Physical experiment must separately enable status and add\n\t\t\t * quantenna,watchdog-experiment; never auto-arm at probe. */\n\t\t\tstatus = \"disabled\";\n\t\t};\n\n\t\ttopaz_irqc: interrupt-controller@e0000000 {")
    put(path, s)
    put("watchdog.config", "CONFIG_WATCHDOG=y\nCONFIG_WATCHDOG_CORE=y\nCONFIG_DW_WATCHDOG=y\nCONFIG_WATCHDOG_NOWAYOUT=y\n# CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED is not set\n# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set\n# CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY is not set\n# CONFIG_PM is not set\n# CONFIG_DEBUG_FS is not set\n")
    put("source-origin.json", json.dumps({"kernel": KERNEL, "linux_version": "5.10.260", "original_sha256": originals, "hardware_touched": False}, indent=2)+"\n")
    print(OUT)


if __name__ == "__main__":
    main()
