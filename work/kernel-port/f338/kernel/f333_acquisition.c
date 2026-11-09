/* SPDX-License-Identifier: GPL-2.0-only */
#include "f333_acquisition.h"
_Static_assert(sizeof(struct f333_raw)==16,"OEM raw layout");
static const struct f333_consume_action consume_plan[]={
    {F333_CONSUME_WRITE,0xe6000320u,2},
    {F333_CONSUME_WRITE,0xe6091530u,0},
    {F333_CONSUME_WRITE,0xe6091520u,0},
    {F333_CONSUME_WRITE,0xe609151cu,0},
    {F333_CONSUME_WRITE,0xe609156cu,0},
    {F333_OCAC_COUNT_ZERO,0,0},
    {F333_ZC_ACCURATE_ONE,0,1},
    {F333_CONSUME_WRITE,0xe6091570u,0},
    {F333_ZC_CURSOR_ZERO,0,0},
    {F333_OCAC_MASK_CLEAR,0,256},
};
unsigned f333_get_consume_plan(const struct f333_consume_action **out)
{if(!out)return 0;*out=consume_plan;return sizeof(consume_plan)/sizeof(consume_plan[0]);}
static void zero(void *v,unsigned n) {f333_u8 *p=v;while(n--)*p++=0;}
static int valid(const struct f333_snapshot *s)
{
    return s && s->start<256 && s->current_ptr<256 &&
           (s->tag_enabled==0 || s->tag_enabled==1) &&
           (s->ocac_filter==0 || s->ocac_filter==1) &&
           (!s->ocac_filter || s->ocac_mask);
}
static unsigned available(const struct f333_snapshot *s)
{return s->current_ptr>=s->start?s->current_ptr-s->start:s->current_ptr-s->start+256u;}
void f333_decode_pair(f333_u32 high,f333_u32 low,int tag_enabled,struct f333_raw *p)
{
    p->start=high&0x07ffffffu;p->stop=low&0x07ffffffu;
    p->max_power=((high&0xf8000000u)>>22)|(low>>27);
    p->tagged=(f333_u8)(tag_enabled && ((low>>27)&1u));
    p->pad[0]=p->pad[1]=p->pad[2]=0;
}
int f333_capture_raw(const struct f333_snapshot *s,f333_read_word read,void *ctx,
                    struct f333_raw *out,unsigned capacity,struct f333_raw_meta *meta)
{
    unsigned count,i,selected=0,position;f333_u32 high,low;
    if(!meta)return F333_INVALID;
    zero(meta,sizeof(*meta));
    if(!valid(s) || !read)return F333_INVALID;
    count=available(s);meta->available=count;
    for(i=0;i<count;i++)if(!s->ocac_filter || s->ocac_mask[i])selected++;
    if(selected>capacity || (selected && !out))return F333_CAPACITY;
    position=s->start;
    for(i=0;i<count;i++) {
        /* Original loop advances the physical bank pointer only on selection. */
        if(s->ocac_filter && !s->ocac_mask[i])continue;
        if(!read(ctx,F333_BANK_HIGH,position,&high))return F333_READ_FAILED;
        meta->words_read++;
        if(!read(ctx,F333_BANK_LOW,position,&low))return F333_READ_FAILED;
        meta->words_read++;
        f333_decode_pair(high,low,s->tag_enabled,&out[meta->captured_count++]);
        position=(position+1u)&255u;
    }
    meta->preprocess_count=(!s->tag_enabled && meta->captured_count>128)?128:meta->captured_count;
    meta->complete=1;return F333_OK;
}
int f333_capture_zc(const struct f333_snapshot *s,f333_read_word read,void *ctx,
                   f333_s32 out[][112],unsigned capacity,struct f333_zc_meta *meta)
{
    unsigned count,i,j,k,selected=0,cursor;f333_u32 value;
    if(!meta)return F333_INVALID;
    zero(meta,sizeof(*meta));
    if(!valid(s) || !read || s->win_per_pulse!=28 || s->zc_start_bytes>=4096 ||
       (s->zc_start_bytes&3) || (s->software_zc_accurate!=0 && s->software_zc_accurate!=1))return F333_INVALID;
    meta->source_accurate=s->software_zc_accurate;meta->next_cursor=s->zc_start_bytes;
    if(!s->software_zc_accurate)return F333_ZC_NOT_ACCURATE;
    count=available(s);if(count>18)count=18;meta->considered_rows=count;
    for(i=0;i<count;i++)if(!s->ocac_filter || s->ocac_mask[i])selected++;
    if(selected>capacity || (selected && !out))return F333_CAPACITY;
    cursor=s->zc_start_bytes;
    for(i=0;i<count;i++) {
        if(s->ocac_filter && !s->ocac_mask[i])continue;
        for(j=0;j<28;j++) {
            if(cursor>=0xe00u) {
                for(k=0;k<4;k++)out[meta->captured_rows][j*4+k]=-1;
                meta->invalid_samples+=4;
            } else {
                if(!read(ctx,F333_ZC_RAM,cursor>>2,&value))return F333_READ_FAILED;
                meta->words_read++;
                for(k=0;k<4;k++)out[meta->captured_rows][j*4+k]=(f333_s32)((value>>(8*k))&255u);
                meta->valid_samples+=4;
            }
            cursor=(cursor+4u)&0xfffu;
        }
        meta->captured_rows++;meta->next_cursor=cursor;
    }
    meta->complete=1;return F333_OK;
}
