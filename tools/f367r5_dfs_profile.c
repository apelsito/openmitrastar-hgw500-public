/* SPDX-License-Identifier: GPL-2.0-only
 * Fixed AP52 regulatory publication through the existing OEM subioctl.
 * Never sets an active-channel list, power, CAC status or a radar-test flag.
 */
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <linux/wireless.h>
#include "f367r5_oem_ioctl.h"

#define STATE "/sys/module/qdrv/parameters/openmitrastar_dfs_state"
#define CLAIM "/run/openmitrastar/f367/dfs-profile-publication"
static int reject(const char *why)
{
 int saved=errno;
 fprintf(stderr,"OMF367_PROFILE_REJECT reason=%s errno=%d\n",why,saved);
 return 1;
}
static int number(const char *json,const char *key,unsigned *out)
{
 char needle[80],*end;const char *p;unsigned long value;
 if(snprintf(needle,sizeof(needle),"\"%s\":",key)>=(int)sizeof(needle))return -1;
 p=strstr(json,needle);if(!p||strstr(p+1,needle))return -1;
 p+=strlen(needle);while(*p==' '||*p=='\t')p++;
 if(*p<'0'||*p>'9')return -1;
 errno=0;value=strtoul(p,&end,10);
 if(errno||value>0xffffffffUL||(*end!=','&&*end!='}'))return -1;
 *out=(unsigned)value;return 0;
}
static int state(char *buffer,size_t size)
{
 FILE *f=fopen(STATE,"r");size_t n;
 if(!f)return -1;
 n=fread(buffer,1,size-1,f);
 if(ferror(f)||!feof(f)||n==0){fclose(f);return -1;}
 buffer[n]=0;fclose(f);
 return strstr(buffer,"\"schema\":\"openmitrastar.f367-kernel-state/v1\"")?0:-1;
}
static int equal(const char *json,const char *key,unsigned expected)
{unsigned value;return !number(json,key,&value)&&value==expected;}
static void request(struct iwreq *wr)
{memset(wr,0,sizeof(*wr));memcpy(wr->ifr_name,"wifi0",6);}
static int region(int fd)
{
 struct iwreq wr;uint32_t value=IEEE80211_PARAM_REGULATORY_REGION;
 request(&wr);memcpy(wr.u.name,&value,sizeof(value));
 if(ioctl(fd,IEEE80211_IOCTL_GETPARAM,&wr))return -1;
 memcpy(&value,wr.u.name,sizeof(value));
 return (value&0xffffffU)==21317U?0:-1;
}
static int readback(int fd,struct ieee80211req_chanlist *list,struct ieee80211req_chaninfo *info)
{
 struct iwreq wr;
 request(&wr);memset(list,0,sizeof(*list));wr.u.data.pointer=list;wr.u.data.length=sizeof(*list);
 if(ioctl(fd,IEEE80211_IOCTL_GETCHANLIST,&wr)||wr.u.data.length!=sizeof(*list))return -1;
 request(&wr);memset(info,0,sizeof(*info));wr.u.data.pointer=info;wr.u.data.length=sizeof(*info);
 if(ioctl(fd,IEEE80211_IOCTL_GETCHANINFO,&wr)||info->ic_nchans>IEEE80211_CHAN_MAX||!info->ic_nchans)return -1;
 return 0;
}
static const struct ieee80211_chan *channel(const struct ieee80211req_chaninfo *info,unsigned wanted)
{
 unsigned i;const struct ieee80211_chan *found=NULL;
 for(i=0;i<info->ic_nchans;i++)if(info->ic_chans[i].ic_ieee==wanted){if(found)return NULL;found=&info->ic_chans[i];}
 return found;
}
static int active(const struct ieee80211req_chanlist *list,unsigned chan)
{return !!(list->ic_channels[chan/8]&(1U<<(chan%8)));}
int main(int argc,char **argv)
{
 struct ieee80211req_chanlist before,after;
 struct ieee80211req_chaninfo old,new;
 const struct ieee80211_chan *c36,*c52,*changed;
 struct iwreq wr;char json[4096];int fd,claim,publish;unsigned i;int target=52;
 if(argc!=2||(strcmp(argv[1],"publish")&&strcmp(argv[1],"check"))){errno=EINVAL;return reject("arguments");}
 publish=!strcmp(argv[1],"publish");
 if(geteuid()!=0){errno=EPERM;return reject("not-root");}
 if(state(json,sizeof(json))||!equal(json,"configured",1)||!equal(json,"region_es",1)||
    !equal(json,"control_fault",0)||!equal(json,"tx_fault_latched",0))return reject("kernel-context");
 if(publish&&!equal(json,"profile_publish_allowed",1)){errno=EPERM;return reject("publication-window-closed");}
 if(!publish&&!equal(json,"region_eu",1)){errno=EPERM;return reject("region-not-eu");}
 fd=socket(AF_INET,SOCK_DGRAM,0);if(fd<0)return reject("socket");
 if(region(fd)){close(fd);return reject("region-readback");}
 if(readback(fd,&before,&old)){close(fd);return reject("channel-readback");}
 c36=channel(&old,36);c52=channel(&old,52);
 if(!active(&before,36)||!active(&before,52)||!c36||!c52||c36->ic_freq!=5180||c52->ic_freq!=5260||
    (c36->ic_flags&IEEE80211_CHAN_DFS)){close(fd);errno=EPERM;return reject("target52-or-fallback36-unavailable");}
 if(!publish){
  close(fd);if(!(c52->ic_flags&IEEE80211_CHAN_DFS)){errno=EPERM;return reject("target52-not-dfs");}
  printf("OMF367_PROFILE_READBACK channel=52 active=1 dfs=1 fallback36_active=1 fallback36_dfs=0\n");return 0;
 }
 /* Claim is never removed: no second publication may clear a later NOP. */
 claim=open(CLAIM,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(claim<0){close(fd);return reject("publication-already-claimed");}
 {static const char label[]="OEM_SUBIO14_CHANNEL52\n";
 if(write(claim,label,sizeof(label)-1)!=(ssize_t)(sizeof(label)-1)){close(claim);close(fd);return reject("publication-claim-write");}}
 close(claim);
 /* Recheck after the one-shot claim and immediately before the sole mutation. */
 if(state(json,sizeof(json))||!equal(json,"profile_publish_allowed",1)||!equal(json,"region_es",1)){
  close(fd);errno=EPERM;return reject("publication-window-changed");
 }
 request(&wr);wr.u.data.flags=SIOCDEV_SUBIO_SET_MARK_DFS_CHAN;wr.u.data.length=1;wr.u.data.pointer=&target;
 if(ioctl(fd,IEEE80211_IOCTL_EXT,&wr)){close(fd);return reject("oem-regulatory-subio14");}
 if(readback(fd,&after,&new)||region(fd)){close(fd);return reject("publication-readback");}
 close(fd);
 if(memcmp(&before,&after,sizeof(before))||new.ic_nchans!=old.ic_nchans){errno=EPROTO;return reject("active-mask-or-table-changed");}
 for(i=0;i<old.ic_nchans;i++){
  const struct ieee80211_chan *prior=&old.ic_chans[i];
  changed=channel(&new,prior->ic_ieee);
  if(!changed||changed->ic_freq!=prior->ic_freq||
     changed->ic_flags!=(prior->ic_flags|(prior->ic_ieee==52?(IEEE80211_CHAN_DFS|IEEE80211_CHAN_PASSIVE):0))){
   errno=EPROTO;return reject("unexpected-channel-flags");
  }
 }
 if(state(json,sizeof(json))||!equal(json,"target52_active",1)||!equal(json,"target52_dfs",1)||
    !equal(json,"target52_radar",0)||!equal(json,"region_es",1)){errno=EPROTO;return reject("kernel-publication-readback");}
 printf("OMF367_PROFILE_PUBLISHED producer=OEM_SUBIO14 channel=52 active=1 dfs=1 passive=1 active_mask_unchanged=1\n");
 return 0;
}
