"""Narrow F362 recovery and read-only two-port acceptance delta."""
import re,time
from f336_wdt_ram_executor import require,PROMPT
from f362_uart_reboot_probe import native_break
def clear_pending_break(uart,drive=native_break):
 record=getattr(uart,'serial_recovery_record',{})
 if record.get('break_attempted') and not record.get('break_cleared') and uart.serial and uart.serial.is_open:
  try:drive(uart.serial,False);record['break_cleared']=True;record['cleanup_clear_verified']=True
  except Exception:record['break_cleanup_failed']=True
 return not record.get('break_attempted') or record.get('break_cleared') is True
def serial_reboot_to_prompt(host,uart,drive=native_break,sleep=time.sleep,clock=time.monotonic):
 require(host.guard() and not uart.failed and not uart.write_in_flight,'serial_recovery_domain')
 require(not uart.serial_recovery_record.get('break_attempted'),'serial_recovery_no_retry')
 require(uart.kernel_handoff_start is not None,'linux_handoff_unknown')
 raw=uart.since(uart.kernel_handoff_start)
 linux=raw.rfind(b'Linux version 5.10.260-openmitrastar-radiohw')
 reset=max(raw.rfind(b'Boot reached stage 13'),raw.rfind(b'U-Boot '),raw.rfind(b'Bootbase Version'))
 require(linux>=0 and linux>reset and not PROMPT.search(raw) and not uart.has_prompt() and not uart.autoboot,'fresh_linux_epoch_required')
 require(uart.serial.is_open and uart.serial.out_waiting==0,'serial_not_idle')
 record=uart.serial_recovery_record;record.update(break_attempted=True,break_asserted=False,break_cleared=False,b_attempted=False,b_written=False)
 start=uart.checkpoint();count=len(uart.reset_times);began=clock()
 try:
  drive(uart.serial,True);record['break_asserted']=True;sleep(.600)
 finally:
  drive(uart.serial,False);record['break_cleared']=True
 sleep(.150)
 require(clock()-began<4 and len(uart.reset_times)==count and not uart.failed and not uart.has_prompt(),'serial_epoch_changed')
 # Arm only after BREAK has cleared, but before b can reset the router.
 uart.stop_autoboot(120);uart.invalidate_prompt();record['b_attempted']=True
 require(uart.serial.write(b'b')==1,'sysrq_short_write');record['b_written']=True
 uart.wait_prompt(120,start)
 require(len(uart.reset_times)>count and re.search(rb'sysrq\s*:\s*Resetting',uart.since(start),re.I),'serial_reset_not_demonstrated')
 record['new_prompt_and_dispatch']=True;return record
def ethernet_command():
 return "for n in eth0 eth1; do printf '%s_driver=' \"$n\"; readlink /sys/class/net/$n/device/driver; printf '%s_bridge=' \"$n\"; if [ -e /sys/class/net/br0/brif/$n ]; then echo 1; else echo 0; fi; printf '%s_carrier=' \"$n\"; cat /sys/class/net/$n/carrier; printf '%s_irq=' \"$n\"; sed -n 's/^irq=//p' /sys/class/net/$n/lyoko_emac_port_stats; done; if dmesg | grep -Fq 'F352 two independent direct-DMA netdevs; MAC1/PHY3 and MAC0/PHY1; no TQE forwarding'; then echo mapping=MAC1/PHY3,MAC0/PHY1; fi"
def verify_ethernet_response(data):
 text=data.decode('ascii');pairs=[line.split('=',1) for line in text.splitlines()];require(all(len(p)==2 for p in pairs) and len({p[0] for p in pairs})==len(pairs),'ethernet_response');rows=dict(pairs)
 require(rows.get('mapping')=='MAC1/PHY3,MAC0/PHY1','ethernet_dt_probe_mapping')
 result={}
 for name,mac,phy in [('eth0',1,3),('eth1',0,1)]:
  require(rows.get(name+'_driver','').endswith('/qtn-topaz-emac-f352'),'ethernet_driver')
  require(rows.get(name+'_bridge')=='1' and rows.get(name+'_carrier') in ('0','1'),'ethernet_bridge_carrier')
  require(rows.get(name+'_irq')==str(20 if mac==1 else 19),'ethernet_port_irq')
  result[name]=dict(mac=mac,phy=phy,bridge='br0',carrier=rows[name+'_carrier']=='1',driver='qtn-topaz-emac-f352')
 require(any(x['carrier'] for x in result.values()),'no_ethernet_carrier');return result
