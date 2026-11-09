"""Create the syscall-only diagnostic PID1 without changing accepted v1 inputs."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
source=HERE.parent/'linux-7.3-ethernet-ram/init.c'
text=source.read_text()
needle='static volatile u32 ram[262144];'
helper=r'''
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
'''
assert text.count(needle)==1
text=text.replace(needle,helper+'\n'+needle)
needle='else if(eq(line,"ethstats"))cat("/sys/class/net/eth0/lyoko_emac_port_stats");'
assert text.count(needle)==1
text=text.replace(needle,needle+'''
  else if(eq(line,"eth1stats"))cat("/sys/class/net/eth1/lyoko_emac_port_stats");
  else if(eq(line,"netdiag")){address_status(0);address_status(1);cat("/proc/net/route");cat("/proc/net/fib_trie");}
  else if(eq(line,"eth0state")){cat("/sys/class/net/eth0/carrier");cat("/sys/class/net/eth0/operstate");}
  else if(eq(line,"eth1state")){cat("/sys/class/net/eth1/carrier");cat("/sys/class/net/eth1/operstate");}
''')
target=HERE/'init.c'
assert not target.exists()
target.write_text(text,newline='\n')
print(target)
