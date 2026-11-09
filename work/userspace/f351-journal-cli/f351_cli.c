/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/vfs.h>
#include <unistd.h>
#include "vendor/f350_uapi.h"
#include "vendor/f342_journal.h"

#define NODE "/dev/om-f350-journal"
#define CLASS_DEVICE "/sys/class/misc/om-f350-journal/dev"
#define SYSFS_MAGIC 0x62656572u
_Static_assert(sizeof(struct f350_request)==4180,"F350 ABI size");
_Static_assert(offsetof(struct f350_request,payload)==84,"F350 ABI payload");

static void wipe(void *data,size_t n)
{volatile unsigned char *p=data;while(n--)*p++=0;}
static int write_all(int fd,const void *data,size_t n)
{
 const unsigned char *p=data;
 while(n){ssize_t r=write(fd,p,n);if(r<0&&errno==EINTR)continue;if(r<=0)return -1;p+=(size_t)r;n-=(size_t)r;}
 return 0;
}
static int zeroes(const void *data,size_t n)
{const unsigned char *p=data;while(n--)if(*p++)return 0;return 1;}
static int input_payload(unsigned char *data,size_t *length)
{
 size_t used=0;
 for(;;){
  unsigned char extra;void *target=used==4096?&extra:data+used;size_t capacity=used==4096?1:4096-used;
  ssize_t n=read(STDIN_FILENO,target,capacity);
  if(n<0&&errno==EINTR)continue;
  if(n<0)return -1;
  if(!n){if(!used)return -1;*length=used;return 0;}
  if(used==4096)return -1;
  used+=(size_t)n;
 }
}
static int device_identity(int fd)
{
 struct stat st;struct statfs fs;char text[32],*end;size_t used=0;unsigned long maj,min;int sysfd,ok=0;
 if(fstat(fd,&st)||!S_ISCHR(st.st_mode)||st.st_uid!=0||st.st_gid!=0||(st.st_mode&07777)!=0600)return -1;
 sysfd=open(CLASS_DEVICE,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 if(sysfd<0)return -1;
 if(fstatfs(sysfd,&fs)||(unsigned long)fs.f_type!=SYSFS_MAGIC)goto done;
 for(;;){
  ssize_t n;
  if(used==sizeof(text)-1)goto done;
  n=read(sysfd,text+used,sizeof(text)-1-used);
  if(n<0&&errno==EINTR)continue;
  if(n<0)goto done;
  if(!n)break;
  if(memchr(text+used,0,(size_t)n))goto done;
  used+=(size_t)n;
 }
 text[used]=0;
 if(!used||text[0]<'0'||text[0]>'9')goto done;
 errno=0;maj=strtoul(text,&end,10);if(errno||*end!=':'||maj!=10)goto done;
 if(end[1]<'0'||end[1]>'9')goto done;
 errno=0;min=strtoul(end+1,&end,10);
 if(errno||min>0xfffffUL||strcmp(end,"\n")||major(st.st_rdev)!=maj||minor(st.st_rdev)!=min)goto done;
 ok=1;
done:
 if(close(sysfd))ok=0;
 return ok?0:-1;
}
static uint64_t sequence(const struct f350_request *r)
{return((uint64_t)r->sequence_hi<<32)|r->sequence_lo;}
static int validate(const struct f350_request *r,unsigned operation,size_t input_length)
{
 unsigned common;
 if(r->abi!=F350_ABI||r->operation!=operation||r->flags||r->backend_status||r->quarantined||r->claimed||
    r->exact_part_verified||r->common_bp0>1||r->commit_visible>1||r->protection_restored>1||r->witnesses_unchanged>1||
    r->id==0||r->id>=0xffffffu||(r->status_register&1u)||r->failure_phase)return -1;
 common=r->id==0xc22018u&&!(r->status_register&0x3fu)&&!(r->security_register&0x9cu);
 if(r->common_bp0!=common)return -1;
 if(operation==F350_OBSERVE){
  return !r->status&&!r->journal_status&&!r->length&&!r->record_length&&!sequence(r)&&!r->slot&&!r->phase&&
   !r->commit_visible&&!r->protection_restored&&!r->witnesses_unchanged&&zeroes(r->payload,sizeof(r->payload))?0:-1;
 }
 if(r->id!=0xc22018u||r->phase!=F342_PHASE_DONE||r->status!=r->journal_status)return -1;
 if(r->status==F342_EMPTY){
  if(operation==F350_SAVE||sequence(r)||r->record_length||r->length||r->slot!=F342_SLOT_NONE||r->commit_visible||
     r->protection_restored||r->witnesses_unchanged||!zeroes(r->payload,sizeof(r->payload)))return -1;
  return 1;
 }
 if(r->status||!sequence(r)||!r->record_length||r->record_length>4096||r->slot>1)return -1;
 if(operation==F350_SAVE)return common&&r->length==input_length&&r->record_length==input_length&&
   r->commit_visible==1&&r->protection_restored==1&&r->witnesses_unchanged==1?0:-1;
 if(r->commit_visible||r->protection_restored||r->witnesses_unchanged)return -1;
 if(operation==F350_INSPECT)return !r->length&&zeroes(r->payload,sizeof(r->payload))?0:-1;
 if(r->length!=r->record_length)return -1;
 return zeroes(r->payload+r->length,sizeof(r->payload)-r->length)?0:-1;
}
static int metadata(unsigned operation,const struct f350_request *r)
{
 char text[384];int n;
 if(operation==F350_OBSERVE)n=snprintf(text,sizeof(text),"{\"status\":\"observed\",\"id\":\"%06x\",\"control\":\"%08x\",\"status_register\":%u,\"security_register\":%u,\"common_bp0\":%u,\"exact_part_verified\":false}\n",
  r->id,r->control,(unsigned)r->status_register,(unsigned)r->security_register,(unsigned)r->common_bp0);
 else n=snprintf(text,sizeof(text),"{\"status\":\"%s\",\"sequence\":%" PRIu64 ",\"slot\":%u,\"bytes\":%u}\n",
  operation==F350_SAVE?"saved":"record",sequence(r),r->slot,r->record_length);
 return n<0||(size_t)n>=sizeof(text)?-1:write_all(STDOUT_FILENO,text,(size_t)n);
}
int main(int argc,char **argv)
{
 struct f350_request request;unsigned operation;size_t length=0;int fd=-1,result=1,valid;
 if(argc==1||(argc==2&&!strcmp(argv[1],"--help"))){
  const char help[]="om-journal-cli: observe | inspect | load | save\nsave reads 1..4096 bytes from stdin; load emits only a validated record.\nNo arguments or --help performs no device access.\n";
  return write_all(STDOUT_FILENO,help,sizeof(help)-1)?1:0;
 }
 if(argc!=2){fputs("invalid arguments\n",stderr);return 2;}
 if(!strcmp(argv[1],"observe"))operation=F350_OBSERVE;
 else if(!strcmp(argv[1],"load"))operation=F350_LOAD;
 else if(!strcmp(argv[1],"save"))operation=F350_SAVE;
 else if(!strcmp(argv[1],"inspect"))operation=F350_INSPECT;
 else {fputs("unknown command\n",stderr);return 2;}
 /* Poison output fields to reject a no-op or incomplete ioctl response. */
 memset(&request,0xa5,sizeof(request));request.abi=F350_ABI;request.operation=operation;request.flags=0;request.length=0;
 if(operation==F350_SAVE){
  memset(request.payload,0,sizeof(request.payload));
  if(input_payload(request.payload,&length)){fputs("save requires 1..4096 complete input bytes\n",stderr);result=2;goto done;}
  request.length=(__u32)length;
 }
 fd=open(NODE,O_RDWR|O_CLOEXEC|O_NOFOLLOW);
 if(fd<0||device_identity(fd)){fputs("journal device identity rejected\n",stderr);goto done;}
 if(ioctl(fd,F350_IOCTL,&request)!=0){fputs("journal ioctl failed\n",stderr);goto done;}
 valid=validate(&request,operation,length);
 if(valid<0){fputs("journal response rejected\n",stderr);goto done;}
 if(close(fd)){fd=-1;fputs("journal close failed\n",stderr);goto done;}fd=-1;
 if(valid==1){
  if(operation==F350_INSPECT){const char empty[]="{\"status\":\"empty\"}\n";if(write_all(STDOUT_FILENO,empty,sizeof(empty)-1))goto done;}
  else fputs("journal empty\n",stderr);
  result=3;goto done;
 }
 if(operation==F350_LOAD){if(write_all(STDOUT_FILENO,request.payload,request.length)){fputs("output write failed\n",stderr);goto done;}}
 else if(metadata(operation,&request)){fputs("output write failed\n",stderr);goto done;}
 result=0;
done:
 if(fd>=0)(void)close(fd);
 wipe(&request,sizeof(request));return result;
}
