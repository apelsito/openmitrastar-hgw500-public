// SPDX-License-Identifier: GPL-2.0-only
/* ARC700 UART PID1: raw syscalls, no libc/CRT/TLS/atomic dependency. */
typedef unsigned long word;
typedef unsigned int u32;
#define AT_FDCWD (-100)
#define NR_OPENAT 56
#define NR_CLOSE 57
#define NR_READ 63
#define NR_WRITE 64
#define NR_MOUNT 40
#define NR_CLOCK_NANOSLEEP_TIME64 407
static long call5(long nr,long a,long b,long c,long d,long e) {
 register long r0 __asm__("r0")=a;
 register long r1 __asm__("r1")=b;
 register long r2 __asm__("r2")=c;
 register long r3 __asm__("r3")=d;
 register long r4 __asm__("r4")=e;
 register long r8 __asm__("r8")=nr;
 __asm__ volatile("trap0" : "+r"(r0) : "r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r8) : "memory");
 return r0;
}
static word len(const char *s){word n=0;while(s[n])n++;return n;}
static int eq(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static void say(const char *s){word n=len(s);while(n){long v=call5(NR_WRITE,1,(long)s,n,0,0);if(v<=0)return;s+=v;n-=v;}}
static void cat(const char *p){
 char b[256];long fd=call5(NR_OPENAT,AT_FDCWD,(long)p,0,0,0),n;
 if(fd<0){say("read failed\n");return;}
 while((n=call5(NR_READ,fd,(long)b,sizeof(b),0,0))>0){
  word off=0;while(off<(word)n){long v=call5(NR_WRITE,1,(long)(b+off),n-off,0,0);if(v<=0)break;off+=v;}
 }
 call5(NR_CLOSE,fd,0,0,0,0);
}
static volatile u32 ram[262144];
static void memtest(void){
 word i;
 for(i=0;i<262144;i++)ram[i]=(u32)i^0x5a3c96e1U;
 for(i=0;i<262144;i++)if(ram[i]!=((u32)i^0x5a3c96e1U)){say("memtest FAIL\n");return;}
 for(i=0;i<262144;i++)ram[i]=~((u32)i^0x5a3c96e1U);
 for(i=0;i<262144;i++)if(ram[i]!=~((u32)i^0x5a3c96e1U)){say("memtest inverse FAIL\n");return;}
 say("memtest PASS 1MiB two patterns; no whole-RAM/cache proof\n");
}
__attribute__((noreturn)) void _start(void){
 char line[48],c;word n=0;
 call5(NR_MOUNT,(long)"proc",(long)"/proc",(long)"proc",0,0);
 say("\nOPENMITRASTAR_BASIC73_PID1_REACHED\n");
 cat("/proc/sys/kernel/osrelease");
 say("UART commands: help, status, cpuinfo, interrupts, meminfo, memtest, echo TOKEN\nbasic73> ");
 for(;;){
  long r=call5(NR_READ,0,(long)&c,1,0,0);
  if(r<=0){struct {long long seconds,nanos;} pause={1,0};
   call5(NR_CLOCK_NANOSLEEP_TIME64,1,0,(long)&pause,0,0);continue;}
  if(c!='\n'&&c!='\r'){if(n<sizeof(line)-1)line[n++]=c;continue;}
  line[n]=0;n=0;
  if(eq(line,"status")){cat("/proc/sys/kernel/osrelease");cat("/proc/uptime");}
  else if(eq(line,"cpuinfo"))cat("/proc/cpuinfo");
  else if(eq(line,"interrupts"))cat("/proc/interrupts");
  else if(eq(line,"meminfo"))cat("/proc/meminfo");
  else if(eq(line,"memtest"))memtest();
  else if(line[0]=='e'&&line[1]=='c'&&line[2]=='h'&&line[3]=='o'&&line[4]==' '){
   word j=5;int valid=line[j]!=0;
   while(line[j]){char v=line[j++];if(!((v>='A'&&v<='Z')||(v>='a'&&v<='z')||(v>='0'&&v<='9')||v=='-'))valid=0;}
   if(valid){say("BASIC73_NONCE=");say(line+5);say("\n");}else say("invalid nonce\n");
  }
  else say("help, status, cpuinfo, interrupts, meminfo, memtest\n");
  say("basic73> ");
 }
}
