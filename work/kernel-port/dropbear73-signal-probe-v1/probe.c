// SPDX-License-Identifier: GPL-2.0-only
/* No libc dependency. Observe exact Dropbear -V signal/PC; no key access. */
typedef unsigned long word;
typedef unsigned int u32;
static long sc(long nr,long a,long b,long c,long d,long e){
 register long r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c;
 register long r3 __asm__("r3")=d,r4 __asm__("r4")=e,r8 __asm__("r8")=nr;
 __asm__ volatile("trap0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r8):"memory","cc");return r0;
}
void *memcpy(void*d,const void*s,word n){volatile char*t=d;const volatile char*f=s;for(word i=0;i<n;i++)t[i]=f[i];return d;}
void *memset(void*d,int value,word n){volatile char*t=d;for(word i=0;i<n;i++)t[i]=(char)value;return d;}
static void say(const char*s){word n=0;while(s[n])n++;sc(64,1,(long)s,n,0,0);}
static void hex(const char*label,u32 v){char b[11]={'0','x',0,0,0,0,0,0,0,0,'\n'};const char*d="0123456789abcdef";for(word i=0;i<8;i++)b[2+i]=d[(v>>(28-4*i))&15];say(label);sc(64,1,(long)b,sizeof(b),0,0);}
static __attribute__((noreturn)) void finish(long pid,long status){if(pid>0){sc(129,pid,9,0,0,0);int s;sc(260,pid,(long)&s,0,0,0);}sc(93,status,0,0,0,0);for(;;){}}
struct regs {word pad;struct{word bta,lp_start,lp_end,lp_count,status32,ret,blink,fp,gp,r12,r11,r10,r9,r8,r7,r6,r5,r4,r3,r2,r1,r0,sp;}scratch;word pad2;word callee[13];word efa,stop_pc;};
struct iovec {void*base;word len;};
_Static_assert(sizeof(struct regs)==160,"ARC700 NT_PRSTATUS layout");
__attribute__((noreturn)) void _start(void){
 static const char*args[]={"/usr/sbin/dropbearmulti","dropbear","-V",0};
 static const char*env[]={"PATH=/bin:/usr/bin:/usr/sbin",0};
 long pid=sc(220,17,0,0,0,0);
 if(pid<0){hex("CLONE_ERROR=",pid);finish(0,2);}
 if(pid==0){long r=sc(117,0,0,0,0,0);if(r){hex("TRACEME_ERROR=",r);finish(0,3);}long me=sc(172,0,0,0,0,0);sc(129,me,19,0,0,0);sc(221,(long)args[0],(long)args,(long)env,0,0);finish(0,127);}
 for(unsigned i=0;i<8;i++){
  int status=0;long r=sc(260,pid,(long)&status,0,0,0);if(r<0){hex("WAIT_ERROR=",r);finish(pid,4);}
  hex("TRACE_WAIT_STATUS=",status);
  if((status&0xff)==0){say("TRACE_EXITED\n");finish(0,0);}
  if((status&0xff)!=0x7f){say("TRACE_SIGNAL_EXIT\n");finish(0,1);}
  unsigned signal=(status>>8)&0xff;
  if(i==0){long option=sc(117,0x4200,pid,0,0x100000,0);if(option){hex("EXITKILL_OPTION_ERROR=",option);finish(pid,7);}}
  if(signal==7||signal==4||signal==11){
   u32 info[32]={0};r=sc(117,0x4202,pid,0,(long)info,0);hex("GETSIGINFO_RC=",r);
   hex("SIGNAL=",info[0]);hex("SIGNAL_CODE=",info[2]);hex("FAULT_ADDRESS=",info[3]);
   struct regs registers={0};struct iovec vector={&registers,sizeof(registers)};
   r=sc(117,0x4204,pid,1,(long)&vector,0);hex("GETREGSET_RC=",r);hex("REGSET_BYTES=",vector.len);
   if(!r){hex("PC=",registers.stop_pc);hex("RETURN_PC=",registers.scratch.ret);hex("BRANCH_TARGET=",registers.scratch.bta);hex("STATUS32=",registers.scratch.status32);hex("EFA=",registers.efa);}
   say("TRACE_FAULT_CAPTURED\n");finish(pid,1);
  }
  r=sc(117,7,pid,0,0,0);if(r){hex("CONT_ERROR=",r);finish(pid,5);}
 }
 say("TRACE_STOP_LIMIT\n");finish(pid,6);
}
