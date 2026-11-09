/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "f344_native.h"
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static unsigned checks;
static bool fail_clock;
extern int __real_clock_gettime(clockid_t, struct timespec *);
int __wrap_clock_gettime(clockid_t id, struct timespec *t) {
  if (fail_clock) {errno = EIO; return -1;}
  return __real_clock_gettime(id, t);
}
#define C(x) do {checks++; assert(x);} while (0)
static void put(const char *dir, const char *name, const void *data, size_t n) {
  char path[768];
  C(snprintf(path, sizeof(path), "%s/%s", dir, name) > 0);
  C(!f344_write_file(path, data, n, 0600));
}
static void text(const char *dir, const char *name, const char *data) {
  put(dir, name, data, strlen(data));
}
int main(void) {
  char temp[]="/tmp/f344-native-test-XXXXXX", out[512], ap[512], sta[512], path[768];
  char *dir=mkdtemp(temp); struct f344_profile p,q;
  uint64_t start,ticks;size_t length;pid_t grandchild;int status;
  char *success[]={"/bin/sh","-c","printf ready",NULL};
  char *failure[]={"/bin/sh","-c","printf FAIL; exit 1",NULL};
  char *orphan[]={"/bin/sh","-c","sleep 20 & printf '%s' $!; exit 0",NULL};
  C(dir!=NULL);C(!chmod(dir,0700));C(!prctl(PR_SET_CHILD_SUBREAPER,1));
  C(!f344_run(success,out,sizeof(out),f344_now_ms()+1000)&&!strcmp(out,"ready"));
  C(f344_run(failure,out,sizeof(out),f344_now_ms()+1000)!=0);
  start=f344_now_ms();C(f344_run(orphan,out,sizeof(out),start+120)!=0);
  grandchild=(pid_t)strtol(out,NULL,10);C(grandchild>1);
  C(waitpid(grandchild,&status,0)==grandchild&&WIFSIGNALED(status)&&WTERMSIG(status)==SIGKILL);
  C(f344_now_ms()-start<1500);
  fail_clock=true;C(f344_run(success,out,sizeof(out),UINT64_MAX)!=0);fail_clock=false;
  C(f344_run(success,out,3,f344_now_ms()+1000)!=0);
  C(!f344_pid_start(getpid(),&ticks)&&ticks>0);
  text(dir,"mode","repeater\n");text(dir,"bandwidth","80\n");
  text(dir,"ap_ssid","synthetic-ap");text(dir,"sta_ssid","synthetic-sta");
  text(dir,"ap.conf","interface=wrong\nctrl_interface=/wrong\nchannel=100\nwpa=2\n");
  text(dir,"wpa.conf","ctrl_interface=/wrong\nupdate_config=1\nnetwork={\nssid=\"synthetic-sta\"\nkey_mgmt=NONE\n}\n");
  C(!f344_read_profile(dir,&p));C(p.target.mode==F344_MODE_REPEATER&&p.target.bandwidth==80);
  C(!strstr(p.ap_config,"interface=")&&!strstr(p.ap_config,"channel="));
  C(!strstr(p.sta_config,"ctrl_interface=")&&!strstr(p.sta_config,"update_config="));
  C(!f344_render_profile(&p,dir,ap,sizeof(ap),sta,sizeof(sta)));
  C(!f344_read_file(ap,out,sizeof(out)-1,&length,true));out[length]=0;
  C(strstr(out,"interface=wifi1\n")&&strstr(out,"channel=0\n"));
  text(dir,"wpa.conf","preserve-running-station\n");
  p.target.ap_frequency_mhz=5200;C(!f344_render_ap_follow(&p,dir,ap,sizeof(ap)));
  C(!f344_read_file(sta,out,sizeof(out)-1,&length,true));out[length]=0;
  C(!strcmp(out,"preserve-running-station\n"));
  put(dir,"ap.conf","wpa=2\0ignored",13);C(f344_read_profile(dir,&q)!=0);
  text(dir,"ap.conf","bss=wifi2\n");C(f344_read_profile(dir,&q)!=0);
  text(dir,"ap.conf","wpa=2\n");
  put(dir,"ap_ssid","012345678901234567890123456789012",33);C(f344_read_profile(dir,&q)!=0);
  put(dir,"ap_ssid","01234567890123456789012345678901\0x",32);C(!f344_read_profile(dir,&q));
  text(dir,"mode","ap\n");text(dir,"frequency","5260\n");C(f344_read_profile(dir,&q)!=0);
  text(dir,"frequency","5180\n");C(!f344_read_profile(dir,&q));
  snprintf(path,sizeof(path),"%s/ap.conf",dir);C(!chmod(path,0644));C(f344_read_profile(dir,&q)!=0);C(!chmod(path,0600));
  snprintf(path,sizeof(path),"%s/link",dir);C(!symlink(ap,path));C(f344_read_file(path,out,sizeof(out),&length,true)!=0);C(f344_write_file(path,"x",1,0600)!=0);
  C(!unlink(path));
  text(dir,"exact","1234");snprintf(path,sizeof(path),"%s/exact",dir);C(!f344_read_file(path,out,4,&length,true)&&length==4);C(f344_read_file(path,out,3,&length,true)!=0);
  C(!chmod(dir,0755));C(f344_read_profile(dir,&q)!=0);C(!chmod(dir,0700));
  /* All files are synthetic, confined to this mkdtemp directory. */
  {const char *names[]={"mode","bandwidth","frequency","ap_ssid","sta_ssid","ap.conf","wpa.conf","hostapd.conf","exact"};unsigned i;for(i=0;i<sizeof(names)/sizeof(names[0]);i++){snprintf(path,sizeof(path),"%s/%s",dir,names[i]);C(!unlink(path));}}
  C(!rmdir(dir));
  printf("F344_NATIVE_PROCESS_PROFILE_PASS checks=%u hardware=0 synthetic_profiles=1\n",checks);
  return 0;
}
