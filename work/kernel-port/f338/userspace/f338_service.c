/* Explicit userspace service entry. It is never started by importing a module. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include "f338_service_core.h"
extern int f338_selftest_main(int,char**);
static struct f338_job job;
static struct f338_reply reply;
static volatile sig_atomic_t stopping;
static void stop(int signal_number){(void)signal_number;stopping=1;}
static int reset_rpc(void*context,struct f338_reset*r)
{
 int fd=*(int*)context,rc;
 do{rc=ioctl(fd,F338_IOC_RESET,r);}while(rc<0&&errno==EINTR&&!stopping);
 return rc<0&&errno==ESTALE?F338_ENGINE_CANCELED:rc;
}
int main(int argc,char**argv)
{
 struct f338_header hello;struct sigaction action;ssize_t size;int fd,rc=0;
 if(argc==2&&!strcmp(argv[1],"--selftest"))return f338_selftest_main(argc,argv);
 if(argc!=2||strcmp(argv[1],"--serve")){fputs("Usage: om-radar-engine-f338 --selftest | --serve\n",stderr);return 64;}
 memset(&action,0,sizeof(action));action.sa_handler=stop;sigemptyset(&action.sa_mask);
 if(sigaction(SIGTERM,&action,0)||sigaction(SIGINT,&action,0))return 70;
 fd=open("/dev/om-radar-f338",O_RDWR|O_CLOEXEC);if(fd<0)return 71;
 memset(&hello,0,sizeof(hello));
 if(ioctl(fd,F338_IOC_HELLO,&hello)||hello.magic!=F338_MAGIC||hello.abi!=F338_ABI||hello.size!=sizeof(hello)||!hello.session){rc=72;goto done;}
 while(!stopping){
  do{size=read(fd,&job,sizeof(job));}while(size<0&&errno==EINTR&&!stopping);
  if(stopping)break;
  if(size<0&&errno==ESTALE)continue;
  if(size!=(ssize_t)sizeof(job)||job.h.session!=hello.session){rc=73;break;}
  /* Kernel independently enforces100ms and releases PM. The process alarm
   * also bounds a defective OEM math call without relying on a supervisor. */
  alarm(2);
  rc=f338_engine_job(&job,&reply,reset_rpc,&fd);
  if(rc==F338_ENGINE_CANCELED){alarm(0);rc=0;continue;}
  do{size=write(fd,&reply,sizeof(reply));}while(size<0&&errno==EINTR&&!stopping);
  alarm(0);
  if(size<0&&errno==ESTALE){f338_engine_cancel();rc=0;continue;}
  if(size!=(ssize_t)sizeof(reply)||rc){rc=74;break;}
 }
done:
 close(fd);f338_engine_close();return rc;
}
