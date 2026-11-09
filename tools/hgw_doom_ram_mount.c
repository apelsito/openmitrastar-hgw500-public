/* HGW fixed RAM mounts. ARC700 syscalls only: no libc, TLS or atomics. */
typedef unsigned long word;
#define BASE "/run/openmitrastar/doom-20261022-r1"
#define FILES BASE "/files"
#define WEB FILES "/www"
#define LED FILES "/om-ledctl"
#define BOOT "5f513265-a294-4366-9567-e1d8af704b6b\n"
#define AT_FDCWD (-100)
#define NR_MKDIRAT 34
#define NR_UMOUNT2 39
#define NR_MOUNT 40
#define NR_OPENAT 56
#define NR_CLOSE 57
#define NR_READ 63
#define NR_WRITE 64
#define NR_EXIT 93
#define NR_GETEUID 175
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
static int eq(const char *a,const char *b) {while(*a&&*a==*b){a++;b++;}return *a==*b;}
static word len(const char *s) {word n=0;while(s[n])n++;return n;}
static void say(const char *s) {word n=len(s);while(n){long r=call5(NR_WRITE,1,(long)s,n,0,0);if(r<=0)return;s+=r;n-=r;}}
__attribute__((noreturn)) static void finish(long rc) {call5(NR_EXIT,rc,0,0,0,0);for(;;)__asm__ volatile("nop");}
__attribute__((noreturn)) static void fail(const char *what,long rc) {
 char digits[12];word n=0;unsigned long v=(unsigned long)(rc<0?-rc:rc);
 say("DOOM_MOUNT_REFUSED ");say(what);say(" errno_hex=");
 do {digits[n++]=(char)('0'+((v&15)<10?(v&15):(v&15)+39));v>>=4;}while(v);
 while(n){char c[2];c[0]=digits[--n];c[1]=0;say(c);}say("\n");finish(1);
}
static long readfile(const char *p,char *buf,word cap) {
 long fd=call5(NR_OPENAT,AT_FDCWD,(long)p,0,0,0);word done=0;
 if(fd<0)return fd;
 while(done<cap-1){long r=call5(NR_READ,fd,(long)(buf+done),cap-1-done,0,0);
  if(r<0){call5(NR_CLOSE,fd,0,0,0,0);return r;}if(!r)break;done+=r;}
 call5(NR_CLOSE,fd,0,0,0,0);buf[done]=0;
 if(done==cap-1)return -75;return (long)done;
}
static char mounts[16384];
/* Fixed paths have no whitespace; refuse duplicates or a foreign backing store. */
static int mounted(const char *p) {
 long rc=readfile("/proc/mounts",mounts,sizeof mounts);int count=0;char *s=mounts;
 if(rc<0)fail("mount-table",rc);
 while(*s){char *src=s,*target,*type,*next;while(*s&&*s!=' ')s++;if(!*s)fail("mount-format",-22);*s++=0;target=s;
  while(*s&&*s!=' ')s++;if(!*s)fail("mount-format",-22);*s++=0;type=s;
  while(*s&&*s!=' ')s++;if(!*s)fail("mount-format",-22);*s++=0;next=s;
  while(*next&&*next!='\n')next++;if(*next)next++;
  if(eq(target,p)){if(!eq(src,"tmpfs")||!eq(type,"tmpfs"))fail("foreign-mount",-22);count++;}s=next;
 }
 if(count>1)fail("duplicate-mount",-22);return count;
}
static void guard(void) {char boot[80];long r=readfile("/proc/sys/kernel/random/boot_id",boot,sizeof boot);
 if(r<0)fail("boot-read",r);if(!eq(boot,BOOT))fail("wrong-boot",-22);
 r=call5(NR_GETEUID,0,0,0,0,0);if(r!=0)fail("root-required",r<0?r:-1);
}
static void present(const char *p) {long fd=call5(NR_OPENAT,AT_FDCWD,(long)p,0400000,0,0);if(fd<0)fail("missing-file",fd);call5(NR_CLOSE,fd,0,0,0,0);}
static void bind(const char *src,const char *dst) {long r;if(mounted(dst))fail("already-mounted",-16);present(src);r=call5(NR_MOUNT,(long)src,(long)dst,0,4096,0);if(r<0)fail("bind",r);if(!mounted(dst))fail("bind-readback",-22);}
static void unmount(const char *p) {long r;if(!mounted(p))fail("mount-required",-22);r=call5(NR_UMOUNT2,(long)p,0,0,0,0);if(r<0)fail("unmount",r);if(mounted(p))fail("unmount-readback",-22);}
__attribute__((used,noreturn)) void doom_main(word *stack) {
 word argc=stack[0];char **argv=(char **)(stack+1);const char *mode;
 if(argc!=2){say("DOOM_MOUNT_USAGE\n");finish(2);}mode=argv[1];
 if(!eq(mode,"inspect")&&!eq(mode,"stage")&&!eq(mode,"expose")&&!eq(mode,"led")&&!eq(mode,"unweb")&&!eq(mode,"unled")&&!eq(mode,"unstage")){say("DOOM_MOUNT_USAGE\n");finish(2);}
 guard();
 if(eq(mode,"inspect")){mounted(FILES);mounted("/www");mounted("/usr/sbin/om-ledctl");say("DOOM_MOUNT_INSPECT_PASS\n");finish(0);}
 if(eq(mode,"stage")){long r;if(mounted(FILES))fail("already-staged",-16);
  r=call5(NR_MKDIRAT,AT_FDCWD,(long)FILES,0700,0,0);if(r<0)fail("mkdir-files",r);
  r=call5(NR_MOUNT,(long)"tmpfs",(long)FILES,(long)"tmpfs",6,(long)"size=8388608,mode=0755");if(r<0)fail("tmpfs",r);
  if(!mounted(FILES))fail("tmpfs-readback",-22);say("STAGE_RAM_WEB_PASS_EMPTY\n");finish(0);}
 if(eq(mode,"expose")){if(!mounted(FILES))fail("stage-required",-22);present(WEB "/Doom/index.html");bind(WEB,"/www");say("WEB_BIND_PASS\n");finish(0);}
 if(eq(mode,"led")){if(!mounted(FILES))fail("stage-required",-22);bind(LED,"/usr/sbin/om-ledctl");say("LED_BIND_PASS\n");finish(0);}
 if(eq(mode,"unweb")){unmount("/www");finish(0);}
 if(eq(mode,"unled")){unmount("/usr/sbin/om-ledctl");finish(0);}
 if(eq(mode,"unstage")){if(mounted("/www")||mounted("/usr/sbin/om-ledctl"))fail("binds-active",-16);unmount(FILES);finish(0);}
 finish(2);
}
__asm__(".global _start\n.type _start,@function\n_start:\nmov r0, sp\nbl doom_main\nnop\n");
