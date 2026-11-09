"""Generate syscall-only PID1 with explicit radio loader and bounded tools."""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

RADIO_HELPERS = r'''
struct module_input { const char *path; const char *parameters; };
static const struct module_input radio_modules[] = {
 {"/modules/firmware_class.ko", ""},
 {"/modules/crypto_skcipher.ko", ""},
 {"/modules/aead.ko", ""},
 {"/modules/libgf128hash.ko", ""},
 {"/modules/libaes.ko", ""},
 {"/modules/aes.ko", ""},
 {"/modules/ctr.ko", ""},
 {"/modules/ccm.ko", ""},
 {"/modules/ecb.ko", ""},
 {"/modules/gcm.ko", ""},
 {"/modules/sha256.ko", ""},
 {"/modules/libarc4.ko", ""},
 {"/modules/cfg80211.ko", ""},
 {"/modules/mac80211.ko", ""},
 {"/modules/rtlwifi.ko", "hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0"},
 {"/modules/btcoexist.ko", ""},
 {"/modules/rtl_pci.ko", "hgw500_eapol_trace=0 hgw500_eapol_mgnt_queue=1 hgw500_tx_queue_guard=0 hgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8 hgw500_tx_reclaim_poll=1"},
 {"/modules/rtl8192ee.ko", "msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=0 disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1 hgw500_tx_dma_wmb=1 hgw500_tx_close_diag=0 hgw500_tx_page_units=2 hgw500_tx_pbp_256=0 hgw500_txbd_mgmt_split=0 hgw500_force_data_mcs7=1 hgw500_force_data_mcs15=0 hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=0"},
};
static unsigned radio_loaded;
static void load_radio(void) {
 for (;radio_loaded < sizeof(radio_modules)/sizeof(radio_modules[0]);radio_loaded++) {
  const struct module_input *m=&radio_modules[radio_loaded];
  long fd=call5(56,AT_FDCWD,(long)m->path,0,0,0);
  if(fd<0){report("RADIO_OPEN_INDEX",radio_loaded);report("RADIO_OPEN_ERROR",fd);return;}
  long r=call5(273,fd,(long)m->parameters,0,0,0);
  call5(57,fd,0,0,0,0);
  report("RADIO_MODULE_INDEX",radio_loaded);report("RADIO_MODULE_RESULT",r);
  if(r){say("RADIOLOAD_STOP\n");return;}
 }
 say("RADIOLOAD_MODULES_COMPLETE\n");
 cat("/sys/class/net/wlan0/operstate");
}
static const char *const environment[]={"PATH=/bin:/sbin:/usr/bin:/usr/sbin","HOME=/","TERM=vt100",0};
static long child(const char *const args[],int background) {
 long pid=call5(220,17,0,0,0,0); /* clone(SIGCHLD), separate address space */
 if(pid==0){call5(221,(long)args[0],(long)args,(long)environment,0,0);call5(93,127,0,0,0,0);for(;;){}}
 if(pid<0){report("CHILD_ERROR",pid);return pid;}
 if(background){report("CHILD_STARTED",pid);return pid;}
 int status=0;long result=call5(260,pid,(long)&status,0,0,0);
 if(result<0){report("CHILD_WAIT_ERROR",result);return result;}
 report("CHILD_STATUS",status);return status;
}
static void pci_status(void) {
 const char *const args[]={"/bin/busybox","sh","-c",
  "for d in /sys/bus/pci/devices/*; do [ -d \"$d\" ] || continue; echo PCI_DEVICE; cat \"$d/vendor\" \"$d/device\" \"$d/class\"; done; for d in /sys/class/ieee80211/*; do [ -d \"$d\" ] || continue; echo WIPHY_PRESENT; done",0};
 child(args,0);
}
static void radio_status(void) {
 const char *const args[]={"/usr/sbin/iw","dev",0};child(args,0);
 const char *const reg[]={"/usr/sbin/iw","reg","get",0};child(reg,0);
}
static void radio_country(void) {
 const char *const args[]={"/usr/sbin/iw","reg","set","ES",0};child(args,0);
}
static void radio_ap(void) {
 /* Test config is generated privately during packaging: WPA2, ES, ch1/20MHz.
  * Never print its credentials. hostapd writes its private log under /run.
  */
 const char *const args[]={"/usr/sbin/hostapd","-B","-P","/run/hostapd.pid",
  "-f","/run/hostapd-private.log","/run/hostapd-test.conf",0};child(args,0);
}
static void ap_status(void) {
 const char *const args[]={"/usr/sbin/hostapd_cli","-p","/run/hostapd","status",0};child(args,0);
}
static void reap(void) {
 int status;while(call5(260,-1,(long)&status,1,0,0)>0){}
}
static void ssh_start(void) {
 const char *const args[]={"/usr/sbin/dropbearmulti","dropbear","-E","-s","-g",
  "-r","/etc/dropbear/dropbear_ed25519_host_key","-p","22","-P","/run/dropbear.pid",0};
 child(args,0);
}
'''

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    source = ROOT / 'work/kernel-port/linux-7.3-ethernet-reset-v2/init.c'
    text = source.read_text()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == 'ec3a81c3cb0a6845521efe681ca5dce6e6f9f83825df4ece4642470a7918af59'
    anchor = 'static volatile u32 ram[262144];'
    assert text.count(anchor) == 1
    text = text.replace(anchor, RADIO_HELPERS + '\n' + anchor)
    anchor = '  else if(eq(line,"udpecho"))udp_echo();'
    assert text.count(anchor) == 1
    additions = '''  else if(eq(line,"eth0txdiag"))cat("/sys/class/net/eth0/lyoko_emac_txdiag");
  else if(eq(line,"eth1txdiag"))cat("/sys/class/net/eth1/lyoko_emac_txdiag");
  else if(eq(line,"radioload"))load_radio();
  else if(eq(line,"pcistatus"))pci_status();
  else if(eq(line,"radiostatus"))radio_status();
  else if(eq(line,"radioes"))radio_country();
  else if(eq(line,"radioap"))radio_ap();
  else if(eq(line,"apstatus"))ap_status();
  else if(eq(line,"sshstart"))ssh_start();
  else if(eq(line,"wlanup")){const char *const a[]={"/bin/busybox","ifconfig","wlan0","192.168.73.1","netmask","255.255.255.0","up",0};child(a,0);}
  else if(eq(line,"shell")){const char *const a[]={"/bin/busybox","sh",0};child(a,0);}
'''
    text = text.replace(anchor, additions + anchor)
    text = text.replace('for(;;){long r=call5(63,0,', 'for(;;){reap();long r=call5(63,0,')
    anchor = 'say("\\nOPENMITRASTAR_ETH73_PID1_REACHED\\n");'
    assert text.count(anchor) == 1
    text = text.replace(anchor, 'call5(40,(long)"devpts",(long)"/dev/pts",(long)"devpts",0,0);\n ' + anchor + 'say("OPENMITRASTAR_RADIOETH73_RAM_V1\\n");')
    text = text.replace('netstats ethstats udpecho reboot echo TOKEN', 'netstats ethstats eth1stats eth0txdiag eth1txdiag radioload pcistatus radiostatus radioes radioap apstatus wlanup sshstart shell udpecho reboot echo TOKEN')
    a.output.write_text(text, newline='\n')
    print(json.dumps({'status':'PID1_SOURCE_PREPARED','sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'radio_load':'EXPLICIT_ONLY','ap_load':'EXPLICIT_ONLY','hardware_accessed':False}))

if __name__ == '__main__':
    main()
