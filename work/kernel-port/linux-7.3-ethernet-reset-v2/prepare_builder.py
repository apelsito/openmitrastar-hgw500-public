"""Version the existing RAM integration recipe for the reset-v2 diagnostic."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
base=HERE.parent/'linux-7.3-ethernet-ram/build_diag.py'
text=base.read_text()
text=text.replace("ELF_SHA='3c173455469c84ed46664a9f3b36b80dfd112ab77b77cc1f755413cbb2a6e19a'", "ELF_SHA='b6d391e8799201139e21ee514b34f0905ca4e7611621cd6c41bb93420bd55c1a'")
text=text.replace("MOD_SHA='067f040165348edcdc3d125cf284f6921802cc3590909df9fe3772c0b9adf798'", "MOD_SHA='b003924f48d8a4f55efb4adf3f40137fdcb92ed373358e3288f0b7d966c93439'")
text=text.replace("p.add_argument('--base',type=Path,required=True);", "p.add_argument('--base',type=Path,required=True);p.add_argument('--module-build',type=Path,required=True);")
text=text.replace("sha(a.base/('module-'+lane)/'qtn-topaz-emac-eth73.ko')", "sha(a.module_build/lane/'qtn-topaz-emac-eth73.ko')")
text=text.replace("s=dt.read_text();assert s.count('status = \"disabled\";')==1", "s=dt.read_text();assert s.count('local-mac-address = ['+mac[1]+'];')==1 and s.count('status = \"okay\";')>=2")
text=text.replace(" s=s.replace('status = \"disabled\";', 'local-mac-address = ['+mac[1]+'];\\n\\t\\t\\tstatus = \"okay\";');dt.write_text(s)", " # Preserve the exact active per-unit DT; no new board identity write.\n dt.write_text(s)")
text=text.replace("a.base/'module-a/qtn-topaz-emac-eth73.ko'", "a.module_build/'a/qtn-topaz-emac-eth73.ko'")
text=text.replace("'schema':'openmitrastar.eth73-ram-integration/v1'", "'schema':'openmitrastar.eth73-reset-ram-integration/v2'")
text=text.replace("'driver_loading':'EXPLICIT_UART_ETHLOAD_ONLY'", "'driver_loading':'EXPLICIT_UART_ETHLOAD_ONLY','change':'Local DMA stop reset fallback and expanded PID1 diagnostics only'")
target=HERE/'build_diag.py';assert not target.exists();target.write_text(text,newline='\n')
assert 'disabled' not in text and '--module-build' in text
print(target)
