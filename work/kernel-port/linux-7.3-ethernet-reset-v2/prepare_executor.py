"""Version the proven transfer executor for the reset-v2 image and eth1 trial."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'linux-7.3-ethernet-ram'
text=(BASE/'executor.py').read_text()
start=text.index('  if self.b.args.wait_power_cycle:')
end=text.index("  m.parse_environment(self.command('printenv bootcmd bootselect'",start)
text=text[:start]+'''  # Fresh input on the currently-running ETH73 unit before manual restart.
  nonce=self.command('echo '+self.nonce)
  m.require(re.findall(rb'(?m)^ETH73_NONCE=([^\\r\\n]+)\\r?$',nonce)==[self.nonce.encode()],'Current ETH73 UART identity mismatch')
  m.require(KERNEL in self.command('status'),'Current ETH73 kernel differs')
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'CAPTURE_READY_OWNER_POWER_CYCLE','pnp_verified':True,'fresh_eth73_uart_nonce':True,'flash_writes':0,'bootenv_writes':0})+'\\n')
  print('ETH73_RESET_CAPTURE_READY_POWER_CYCLE_NOW',flush=True)
  deadline=self.clock()+600
  while self.clock()<deadline:
   try:self.catch_topaz_fast();break
   except TimeoutError:continue
  else:raise TimeoutError('new owner power-cycle not received')
'''+text[end:]
text=text.replace("'ethstats','cpuinfo','memtest','udpecho'", "'ethstats','eth1stats','netdiag','eth0state','eth1state','cpuinfo','memtest','udpecho'")
start=text.index('  for port in [0,1]:')
end=text.index("  before=self.command('interrupts');",start)
text=text[:start]+'''  diag=self.command('netdiag');(self.output/'network-address-diag.txt').write_bytes(diag)
  # Owner moved the cable to the second connector; leave eth0 down throughout.
  for command in ['eth1up','eth1down','eth1up']:
   result=self.command(command,seconds=35)
   m.require((b'ETH1_UP=0' if command.endswith('up') else b'ETH1_DOWN=0') in result,'Second port lifecycle failed')
  diag=self.command('netdiag');(self.output/'network-address-diag-after.txt').write_bytes(diag)
  self.command('eth1state')
'''+text[end:]
text=text.replace("self.command('ethstats')", "self.command('eth1stats')")
text=text.replace('192.168.1.90','192.168.1.91')
text=text.replace("'runtime':'ETH73_RAM_LEFT_RUNNING'", "'runtime':'ETH73_RESET_RAM_ETH1_UP_ETH0_DOWN'")
# Keep driver warnings/errors and numeric protocol evidence, but reject sensitive rows.
text=text.replace("ETH73ATTACH-)", "ETH73ATTACH-|qtn-topaz-emac-eth73 |ETH[01]_ADDR|ETH[01]_FLAGS|stop_reset_|[01]$|up$|down$|READ_ERROR|NET_[A-Z]+|\\s*[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+|Iface)")
target=HERE/'executor.py';assert not target.exists();target.write_text(text,newline='\n')
for name in ['run.ps1','assert_lease.ps1','test_executor.py']:
 s=(BASE/name).read_text()
 if name=='test_executor.py':
  begin=s.index(' def test_powercycle_ready_requires_basic_nonce');end=s.index(' def test_fast_stop_key',begin)
  s=s[:begin]+''' def test_powercycle_requires_current_uart_nonce(self):
  source=(HERE/'executor.py').read_text()
  nonce=source.index('Current ETH73 UART identity mismatch')
  self.assertLess(nonce,source.index('READY_POWER_CYCLE.json',nonce))
  self.assertNotIn('/sbin/reboot',source)
  self.assertNotIn('saveenv',source)
'''+s[end:]
 (HERE/name).write_text(s,newline='\n')
print(target)
