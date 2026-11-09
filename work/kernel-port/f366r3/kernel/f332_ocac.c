// SPDX-License-Identifier: GPL-2.0-only
#include "f332_ocac.h"
int f332_ocac_prepare(struct f332_ocac_state*s,const struct f332_ocac_point*p,unsigned count,
 bool home_is_dfs,bool scan_is_weather,bool current_valid,uint32_t last_current)
{
 unsigned i,j;uint8_t last_status;
 if(!s||count>10||(count&&!p)||s->previous_pointer>255)return -1;
 for(i=0;i<count;i++)if(p[i].fifo_pointer>255)return -1;
 last_status=count?p[count-1].status:s->previous_status;
 if(!home_is_dfs&&last_status==2&&(!current_valid||last_current>255))return -2;
 if(home_is_dfs){s->filter=false;s->oem_iteration_marker=0;}
 else{
  for(i=0;i<count;i++){
   if(s->previous_status==2&&p[i].status==1)
    for(j=s->previous_pointer;j<p[i].fifo_pointer;j++)s->mask[j]=1;
   s->previous_status=p[i].status;s->previous_pointer=p[i].fifo_pointer;
  }
  if(s->previous_status==2)
   for(j=s->previous_pointer;j<last_current;j++)s->mask[j]=1;
  s->previous_pointer=0;s->oem_iteration_marker=(uint8_t)(count+1);s->filter=true;
 }
 /* Original only sets this flag here. Reset ownership is explicit. */
 if(scan_is_weather)s->weather=true;
 return 0;
}
void f332_ocac_consume(struct f332_ocac_state*s)
{
 unsigned i;if(!s)return;for(i=0;i<256;i++)s->mask[i]=0;
 /* clear_pt does not erase the previous interval state or weather flag. */
}
