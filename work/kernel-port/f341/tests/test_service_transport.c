/* Actual service main with synthetic syscalls; math is independently tested
 * by the ARC oracle. No /dev, network, or physical hardware is accessed. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include "f338_service_core.h"
static int opened,closed,reads,writes,engines,cancels,alarms,mode;
static int test_open(const char*p,int flags,...){assert(!strcmp(p,"/dev/om-radar-f338")&&(flags&O_CLOEXEC));opened++;return 7;}
static int test_close(int fd){assert(fd==7);closed++;return 0;}
static unsigned test_alarm(unsigned n){assert(n==0||n==2);alarms++;return 0;}
static int test_sigaction(int signal,const struct sigaction*a,struct sigaction*b){(void)signal;(void)a;(void)b;return 0;}
static int test_ioctl(int fd,unsigned long request,...)
{
 va_list ap;void*p;assert(fd==7);va_start(ap,request);p=va_arg(ap,void*);va_end(ap);
 if(request==F338_IOC_HELLO){struct f338_header*h=p;h->magic=F338_MAGIC;h->abi=F338_ABI;h->size=sizeof(*h);h->session=1;return 0;}
 assert(request==F338_IOC_RESET);errno=ESTALE;return -1;
}
static ssize_t test_read(int,void*,size_t);
static ssize_t test_write(int,const void*,size_t);
#define main f338_service_main
#define open test_open
#define close test_close
#define alarm test_alarm
#define sigaction(...) test_sigaction(__VA_ARGS__)
#define ioctl test_ioctl
#define read test_read
#define write test_write
#include "service-under-test.c"
#undef main
#undef open
#undef close
#undef alarm
#undef sigaction
#undef ioctl
#undef read
#undef write
int f338_selftest_main(int n,char**a){(void)n;(void)a;return 0;}
void f338_engine_close(void){}
void f338_engine_cancel(void){cancels++;}
int f338_engine_job(const struct f338_job*j,struct f338_reply*r,f338_reset_rpc rpc,void*c)
{
 struct f338_reset reset={0};engines++;memset(r,0,sizeof(*r));r->h=j->h;r->h.size=sizeof(*r);
 if(mode==1)return F338_ENGINE_FAILED;
 if(engines==2){reset.h=j->h;reset.h.size=sizeof(reset);reset.request_id=1;assert(rpc(c,&reset)==F338_ENGINE_CANCELED);return F338_ENGINE_CANCELED;}
 return 0;
}
static ssize_t test_read(int fd,void*p,size_t n)
{
 struct f338_job*j=(void*)p;assert(fd==7&&n==sizeof(*j));reads++;
 if(reads==2){errno=ESTALE;return -1;}
 if(reads==5){stopping=1;errno=EINTR;return -1;}
 memset(j,0,sizeof(*j));j->h.magic=F338_MAGIC;j->h.abi=F338_ABI;j->h.size=sizeof(*j);j->h.session=1;j->h.sequence=reads;j->h.generation=reads;return n;
}
static ssize_t test_write(int fd,const void*p,size_t n)
{(void)p;assert(fd==7&&n==sizeof(struct f338_reply));writes++;if(writes==1&&!mode){errno=ESTALE;return -1;}return n;}
int main(void)
{
 char*args[]={"om-radar-engine-f338","--serve",0};
 assert(!f338_service_main(2,args));assert(opened==1&&closed==1&&reads==5&&engines==3&&writes==2&&cancels==1&&alarms==6);
 opened=closed=reads=writes=engines=cancels=alarms=0;stopping=0;mode=1;
 assert(f338_service_main(2,args)==74);assert(opened==1&&closed==1&&engines==1&&writes==1);
 puts("F338_SERVICE_TRANSPORT_PASS cases=4 stale_read_math_reset_recover=1 terminal_engine_exit=1 hardware=0");return 0;
}
