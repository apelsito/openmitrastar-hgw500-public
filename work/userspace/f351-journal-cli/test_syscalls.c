/* Native linker wrappers: no real device or sysfs path is ever opened. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/vfs.h>
#include <unistd.h>
#include "vendor/f350_uapi.h"
#include "vendor/f342_journal.h"
static unsigned sys_read,stdin_eintr;
static const char *scenario(void){const char *s=getenv("F351_FAKE");return s?s:"valid";}
static int is(const char*s){return !strcmp(scenario(),s);}
ssize_t __real_read(int,void*,size_t);
int __real_close(int);
int __wrap_open(const char *path,int flags,...)
{
 if(is("noio"))_exit(99);
 if(!(flags&O_NOFOLLOW)||!(flags&O_CLOEXEC))_exit(98);
 if(!strcmp(path,"/dev/om-f350-journal")){
  if((flags&O_ACCMODE)!=O_RDWR)_exit(97);
  if(is("symlink")){errno=ELOOP;return -1;}
  return 40;
 }
 if(!strcmp(path,"/sys/class/misc/om-f350-journal/dev")){sys_read=0;return 41;}
 _exit(96);
}
int __wrap_fstat(int fd,struct stat *st)
{
 if(fd!=40)_exit(95);
 memset(st,0,sizeof(*st));st->st_mode=S_IFCHR|0600;st->st_rdev=makedev(10,99);
 if(is("regular"))st->st_mode=S_IFREG|0600;
 if(is("owner"))st->st_uid=1000;
 if(is("group"))st->st_gid=1000;
 if(is("mode"))st->st_mode=S_IFCHR|0660;
 if(is("setuid"))st->st_mode=S_IFCHR|04600;
 if(is("rdev"))st->st_rdev=makedev(10,98);
 return 0;
}
int __wrap_fstatfs(int fd,struct statfs *fs)
{if(fd!=41)_exit(94);memset(fs,0,sizeof(*fs));fs->f_type=is("not_sysfs")?0:0x62656572;return 0;}
ssize_t __wrap_read(int fd,void *buf,size_t n)
{
 if(fd==0){
  if(is("stdin_error")){errno=EIO;return -1;}
  if(is("stdin_eintr")&&!stdin_eintr++){errno=EINTR;return -1;}
  return __real_read(fd,buf,n);
 }
 if(fd==41){
  const char *text="10:99\n";size_t len;
  if(sys_read++)return 0;
  if(is("sysfs_trailing"))text="10:99\nBAD";
  if(is("sysfs_negative"))text="10:-1\n";
  if(is("sysfs_huge"))text="10:999999999999999999999\n";
  if(is("sysfs_major"))text="1:99\n";
  if(is("sysfs_nul")){const char bad[]="10:99\n\0";len=sizeof(bad)-1;if(n<len)_exit(93);memcpy(buf,bad,len);return(ssize_t)len;}
  len=strlen(text);if(n<len)_exit(92);memcpy(buf,text,len);return(ssize_t)len;
 }
 _exit(91);
}
int __wrap_close(int fd)
{if(fd==40||fd==41){if(fd==40&&is("close_error")){errno=EIO;return -1;}return 0;}return __real_close(fd);}
int __wrap_ioctl(int fd,unsigned long command,...)
{
 va_list ap;struct f350_request *r,out;size_t copy;unsigned op,len;
 if(fd!=40||command!=F350_IOCTL)_exit(90);
 va_start(ap,command);r=va_arg(ap,struct f350_request*);va_end(ap);op=r->operation;len=r->length;
 if(is("untouched"))return 0;
 if(is("ioctl_positive"))return 1;
 memset(&out,0,sizeof(out));out.abi=F350_ABI;out.operation=op;out.id=0xc22018;out.control=0x205;out.common_bp0=1;
 if(op!=F350_OBSERVE){out.phase=F342_PHASE_DONE;out.sequence_lo=7;out.record_length=7;out.slot=1;}
 if(op==F350_LOAD){out.length=7;memcpy(out.payload,"secret\0",7);}
 if(op==F350_SAVE){out.length=len;out.record_length=len;out.commit_visible=out.protection_restored=out.witnesses_unchanged=1;memcpy(out.payload,r->payload,len);}
 if(is("maxload")){unsigned i;out.length=out.record_length=4096;for(i=0;i<4096;i++)out.payload[i]=(unsigned char)i;}
 if(is("empty")){out.status=out.journal_status=F342_EMPTY;out.length=out.record_length=out.sequence_lo=0;out.slot=F342_SLOT_NONE;memset(out.payload,0,sizeof(out.payload));}
 if(is("status"))out.status=-5;
 if(is("backend"))out.backend_status=-5;
 if(is("journal"))out.journal_status=-5;
 if(is("abi"))out.abi=2;
 if(is("op"))out.operation=99;
 if(is("flags"))out.flags=1;
 if(is("quarantine"))out.quarantined=1;
 if(is("claimed"))out.claimed=1;
 if(is("exact_part"))out.exact_part_verified=1;
 if(is("common"))out.common_bp0=0;
 if(is("bool"))out.common_bp0=2;
 if(is("id0"))out.id=0;
 if(is("idff"))out.id=0xffffff;
 if(is("wip"))out.status_register=1;
 if(is("failure_phase"))out.failure_phase=3;
 if(is("phase"))out.phase=F342_PHASE_SCAN;
 if(is("sequence"))out.sequence_lo=out.sequence_hi=0;
 if(is("slot"))out.slot=2;
 if(is("record0"))out.record_length=0;
 if(is("record_over"))out.record_length=4097;
 if(is("length"))out.length=out.length?out.length-1:1;
 if(is("tail"))out.payload[4095]=1;
 if(is("commit"))out.commit_visible=0;
 if(is("protection"))out.protection_restored=0;
 if(is("witness"))out.witnesses_unchanged=0;
 if(is("save_bool"))out.commit_visible=2;
 copy=is("partial")?24:is("header_only")?84:is("truncated_payload")?87:sizeof(out);
 memcpy(r,&out,copy);
 if(is("ioctl_error")){errno=EFAULT;return -1;}
 return 0;
}
