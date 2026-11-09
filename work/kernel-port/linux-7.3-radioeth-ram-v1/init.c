// SPDX-License-Identifier: GPL-2.0-only
/* UART-only supervisor plus finite Ethernet diagnosis. No shell or flash tools. */
typedef unsigned long word;
typedef unsigned int u32;
typedef unsigned short u16;
#define AT_FDCWD (-100)
static long syscall6(long nr,long a,long b,long c,long d,long e,long f){
 register long r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c;
 register long r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r8 __asm__("r8")=nr;
 __asm__ volatile("trap0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r8):"memory");return r0;
}
#define call5(n,a,b,c,d,e) syscall6(n,a,b,c,d,e,0)
static word len(const char*s){word n=0;while(s[n])n++;return n;}
static int eq(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static void zero(void*p,word n){char*b=p;while(n--)*b++=0;}
static void say(const char*s){word n=len(s);while(n){long r=call5(64,1,(long)s,n,0,0);if(r<=0)return;s+=r;n-=r;}}
static void number(long n){char b[24];word p=sizeof(b);b[--p]=0;unsigned long v=n<0?-n:n;do{unsigned long q=0,r=0;for(int bit=31;bit>=0;bit--){r=(r<<1)|((v>>bit)&1);if(r>=10){r-=10;q|=1UL<<bit;}}b[--p]='0'+r;v=q;}while(v);if(n<0)b[--p]='-';say(b+p);}
static void report(const char*name,long r){say(name);say("=");number(r);say("\n");}
static void cat(const char*p){char b[256];long fd=call5(56,AT_FDCWD,(long)p,0,0,0),r;if(fd<0){report("READ_ERROR",fd);return;}while((r=call5(63,fd,(long)b,sizeof(b),0,0))>0){word off=0;while(off<(word)r){long v=call5(64,1,(long)(b+off),r-off,0,0);if(v<=0)break;off+=v;}}call5(57,fd,0,0,0,0);}
static void pause_ms(long ms){struct{long long seconds,nanos;}t={ms/1000,(ms%1000)*1000000LL};call5(407,1,0,(long)&t,0,0);}
struct sockaddr_in{u16 family,port;unsigned char ip[4],pad[8];};
struct ifreq{char name[16];union{struct sockaddr_in addr;short flags;char bytes[16];}u;};
_Static_assert(sizeof(struct ifreq)==32,"ARC32 ifreq ABI");
_Static_assert(sizeof(struct sockaddr_in)==16,"IPv4 ABI");
static int loaded;
static void load_driver(void){if(loaded){say("ETHLOAD_ALREADY\n");return;}long fd=call5(56,AT_FDCWD,(long)"/qtn-topaz-emac-eth73.ko",0,0,0);if(fd<0){report("ETHLOAD_OPEN",fd);return;}long r=call5(273,fd,(long)"",0,0,0);call5(57,fd,0,0,0,0);report("ETHLOAD",r);if(!r)loaded=1;}
static void iface(unsigned which,int up){
 struct ifreq q;zero(&q,sizeof(q));q.name[0]='e';q.name[1]='t';q.name[2]='h';q.name[3]='0'+which;
 long fd=call5(198,2,2,0,0,0),r;if(fd<0){report("NET_SOCKET",fd);return;}
 if(up){q.u.addr.family=2;q.u.addr.ip[0]=192;q.u.addr.ip[1]=168;q.u.addr.ip[2]=1;q.u.addr.ip[3]=90+which;
  r=call5(29,fd,0x8916,(long)&q,0,0);if(r){report("NET_ADDR",r);goto done;}
  q.u.addr.ip[0]=255;q.u.addr.ip[1]=255;q.u.addr.ip[2]=255;q.u.addr.ip[3]=0;
  r=call5(29,fd,0x891c,(long)&q,0,0);if(r){report("NET_MASK",r);goto done;}}
 zero(&q.u,sizeof(q.u));r=call5(29,fd,0x8913,(long)&q,0,0);if(r){report("NET_GETFLAGS",r);goto done;}
 q.u.flags=up?(q.u.flags|1):(q.u.flags&~1);r=call5(29,fd,0x8914,(long)&q,0,0);
 say(which?"ETH1_":"ETH0_");report(up?"UP":"DOWN",r);
done:call5(57,fd,0,0,0,0);
}
static void udp_echo(void){
 struct sockaddr_in local,peer;char b[512];u32 size;zero(&local,sizeof(local));local.family=2;local.port=(u16)0x3123; /* htons(9009) */
 long fd=call5(198,2,2|0x800,0,0,0);if(fd<0){report("UDP_SOCKET",fd);return;}
 long r=call5(200,fd,(long)&local,sizeof(local),0,0);if(r){report("UDP_BIND",r);goto done;}
 say("UDP_READY_PORT9009\n");unsigned receives=0,sends=0;
 for(unsigned i=0;i<200;i++){size=sizeof(peer);r=syscall6(207,fd,(long)b,sizeof(b),0,(long)&peer,(long)&size);
  if(r>0&&size==sizeof(peer)){receives++;long s=syscall6(206,fd,(long)b,r,0,(long)&peer,size);if(s==r)sends++;}
  else if(r<0&&r!=-11&&r!=-4){report("UDP_RECV",r);break;}
  pause_ms(50);}
 report("UDP_RECEIVED",receives);report("UDP_ECHOED",sends);
done:call5(57,fd,0,0,0,0);
}

static void address_status(unsigned which){
 struct ifreq q;zero(&q,sizeof(q));q.name[0]='e';q.name[1]='t';q.name[2]='h';q.name[3]='0'+which;
 long fd=call5(198,2,2,0,0,0);if(fd<0){report("NET_SOCKET",fd);return;}
 long r=call5(29,fd,0x8915,(long)&q,0,0);
 say(which?"ETH1_ADDR":"ETH0_ADDR");
 if(r){say("_ERROR=");number(r);say("\n");}
 else{say("=");for(unsigned i=0;i<4;i++){if(i)say(".");number(q.u.addr.ip[i]);}say("\n");}
 zero(&q.u,sizeof(q.u));r=call5(29,fd,0x8913,(long)&q,0,0);
 say(which?"ETH1_FLAGS":"ETH0_FLAGS");say("=");number(r?r:q.u.flags);say("\n");
 call5(57,fd,0,0,0,0);
}


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

static volatile u32 ram[262144];
static void memtest(void){for(word i=0;i<262144;i++)ram[i]=(u32)i^0x5a3c96e1U;for(word i=0;i<262144;i++)if(ram[i]!=((u32)i^0x5a3c96e1U)){say("memtest FAIL\n");return;}for(word i=0;i<262144;i++)ram[i]=~((u32)i^0x5a3c96e1U);for(word i=0;i<262144;i++)if(ram[i]!=~((u32)i^0x5a3c96e1U)){say("memtest FAIL\n");return;}say("memtest PASS 1MiB two patterns\n");}
__attribute__((noreturn))void _start(void){
 char line[48],c;word n=0;call5(40,(long)"proc",(long)"/proc",(long)"proc",0,0);call5(40,(long)"sysfs",(long)"/sys",(long)"sysfs",0,0);
 call5(40,(long)"devpts",(long)"/dev/pts",(long)"devpts",0,0);
 say("\nOPENMITRASTAR_ETH73_PID1_REACHED\n");say("OPENMITRASTAR_RADIOETH73_RAM_V1\n");cat("/proc/sys/kernel/osrelease");say("eth73> ");
 for(;;){reap();long r=call5(63,0,(long)&c,1,0,0);if(r<=0){pause_ms(100);continue;}if(c!='\n'&&c!='\r'){if(n<sizeof(line)-1)line[n++]=c;continue;}line[n]=0;n=0;
  if(eq(line,"status")){cat("/proc/sys/kernel/osrelease");cat("/proc/uptime");}
  else if(eq(line,"interrupts"))cat("/proc/interrupts");else if(eq(line,"meminfo"))cat("/proc/meminfo");else if(eq(line,"memtest"))memtest();
  else if(eq(line,"ethload"))load_driver();else if(eq(line,"modules"))cat("/proc/modules");
  else if(eq(line,"eth0up"))iface(0,1);else if(eq(line,"eth0down"))iface(0,0);else if(eq(line,"eth1up"))iface(1,1);else if(eq(line,"eth1down"))iface(1,0);
  else if(eq(line,"netstats"))cat("/proc/net/dev");else if(eq(line,"ethstats"))cat("/sys/class/net/eth0/lyoko_emac_port_stats");
  else if(eq(line,"eth1stats"))cat("/sys/class/net/eth1/lyoko_emac_port_stats");
  else if(eq(line,"netdiag")){address_status(0);address_status(1);cat("/proc/net/route");cat("/proc/net/fib_trie");}
  else if(eq(line,"eth0state")){cat("/sys/class/net/eth0/carrier");cat("/sys/class/net/eth0/operstate");}
  else if(eq(line,"eth1state")){cat("/sys/class/net/eth1/carrier");cat("/sys/class/net/eth1/operstate");}

  else if(eq(line,"eth0txdiag"))cat("/sys/class/net/eth0/lyoko_emac_txdiag");
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
  else if(eq(line,"udpecho"))udp_echo();else if(eq(line,"cpuinfo"))cat("/proc/cpuinfo");
  else if(eq(line,"reboot")){say("ETH73_REBOOT_REQUESTED\n");call5(142,0xfee1dead,0x28121969,0x1234567,0,0);}
  else if(len(line)>5&&line[0]=='e'&&line[1]=='c'&&line[2]=='h'&&line[3]=='o'&&line[4]==' '){word j=5;int valid=1;while(line[j]){char v=line[j++];if(!((v>='A'&&v<='Z')||(v>='a'&&v<='z')||(v>='0'&&v<='9')||v=='-'))valid=0;}if(valid){say("ETH73_NONCE=");say(line+5);say("\n");}}
  else say("status interrupts meminfo memtest cpuinfo ethload modules eth0up eth0down eth1up eth1down netstats ethstats eth1stats eth0txdiag eth1txdiag radioload pcistatus radiostatus radioes radioap apstatus wlanup sshstart shell udpecho reboot echo TOKEN\n");
  say("eth73> ");}
}
