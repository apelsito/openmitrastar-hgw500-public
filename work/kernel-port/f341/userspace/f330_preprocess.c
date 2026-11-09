#include "f330_preprocess.h"
#include "eu-profile.h"
_Static_assert(sizeof(struct f330_raw)==16,"OEM raw ABI");
extern struct f330_raw *f330_oem_preprocess(unsigned *,struct f330_raw *,unsigned,unsigned *);
volatile uint32_t f330_recorded_counter_writes[2];
static unsigned char before[0x9458],after[0x9458];
static struct f330_raw incoming[128];
static struct f330_result pending_result;
static struct f330_raw *history_before,*history_after;
static uint32_t current_generation,request_sequence,pending_request,phase,enters,leaves,fault;
static int32_t clock_seconds,clock_microseconds;
static int blocked;
static uint32_t *word(unsigned off) { return (void *)(f330_oem_bss+off); }
static void copy(void *d,const void *s,size_t n)
{ unsigned char *to=d;const unsigned char *from=s;size_t i;for(i=0;i<n;i++)to[i]=from[i]; }
static void clear(void *d,size_t n)
{ unsigned char *to=d;size_t i;for(i=0;i<n;i++)to[i]=0; }
void *f330_abi_memcpy(void *d,const void *s,size_t n) {copy(d,s,n);return d;}
int f330_abi_printk(const char *s,...) {(void)s;return 0;}
void f330_abi_bb_enter(unsigned id,const char *file,unsigned line)
{
    (void)file;
    if(id!=1 || line!=0xee || phase!=0) {fault=1;return;}
    phase=1;enters++;
}
void f330_abi_bb_leave(unsigned id,const char *file,unsigned line)
{
    (void)file;
    if(id!=1 || line!=0xf1 || phase!=1 || f330_recorded_counter_writes[0]!=0 || f330_recorded_counter_writes[1]!=0) {fault=2;return;}
    phase=2;leaves++;
}
struct timeval32 {int32_t sec,usec;};
void f330_abi_do_gettimeofday(struct timeval32 *tv)
{
    if(phase!=2)fault=3;
    tv->sec=clock_seconds;tv->usec=clock_microseconds;
}
static uint32_t timestamp(int32_t sec,int32_t usec)
{return (uint32_t)sec*10000000u+(uint32_t)usec*10u;}
int f330_begin(uint32_t gen,uint32_t base,int tag_enabled)
{
    if(!gen || (tag_enabled!=0 && tag_enabled!=1))return F330_INVALID;
    clear(f330_oem_bss,0x9458);copy(f330_oem_bss+0x12a4,f328_eu_cfg,300);
    f330_oem_bss[0x137e]=(uint8_t)tag_enabled;
    f330_oem_history_pointer=(void *)(f330_oem_bss+0x1b40);
    *word(0x1294)=base;current_generation=gen;pending_request=0;blocked=0;
    return F330_OK;
}
int f330_prepare(uint32_t gen,const struct f330_raw *raw,unsigned count,
                 int32_t sec,int32_t usec,struct f330_result *result)
{
    unsigned total=0,current=0,i;
    struct f330_raw *output;
    if(gen!=current_generation)return F330_STALE;
    if(blocked || pending_request)return F330_BUSY;
    if(!result || count>128 || (count && !raw) || sec<0 || usec<0 || usec>=1000000)return F330_INVALID;
    for(i=0;i<count;i++)if(raw[i].tagged>1)return F330_INVALID;
    if(*word(0x1020)>128)return F330_ABI_FAULT;
    clear(result,sizeof(*result));clear(incoming,sizeof(incoming));if(count)copy(incoming,raw,count*sizeof(*raw));
    copy(before,f330_oem_bss,sizeof(before));history_before=f330_oem_history_pointer;
    result->history_count_before=*word(0x1020);result->poll_before=*word(0x1290);
    result->reset_before=*word(0x1298);result->timestamp_before=*word(0x1294);
    phase=enters=leaves=fault=0;clock_seconds=sec;clock_microseconds=usec;
    f330_recorded_counter_writes[0]=0xa55aa55a;f330_recorded_counter_writes[1]=0x5aa55aa5;
    output=f330_oem_preprocess(&total,incoming,count,&current);
    if(total>256 || current>128 || (total && output!=(void *)(f330_oem_bss+0x1b40)) || (!total && output))fault=4;
    result->total_count=total;result->current_window_count=current;
    result->history_count_after=*word(0x1020);result->poll_after=*word(0x1290);
    result->reset_after=*word(0x1298);result->timestamp_after=*word(0x1294);
    result->read=*word(0x1400);result->left=*word(0x1404);result->tag=*word(0x1408);
    result->merge=*word(0x140c);result->width=*word(0x1410);result->power=*word(0x1414);
    result->bb_enters=enters;result->bb_leaves=leaves;
    result->counter_writes=(f330_recorded_counter_writes[0]==0)+(f330_recorded_counter_writes[1]==0);
    result->abi_fault=fault;
    if(!fault && total)copy(result->pulses,output,total*sizeof(*output));
    copy(result->zc_source_index,f330_oem_bss+0x1448,sizeof(result->zc_source_index));
    if(fault) {copy(f330_oem_bss,before,sizeof(before));f330_oem_history_pointer=history_before;blocked=1;return F330_ABI_FAULT;}
    if(phase==2) {
        copy(after,f330_oem_bss,sizeof(after));history_after=f330_oem_history_pointer;
        copy(f330_oem_bss,before,sizeof(before));f330_oem_history_pointer=history_before;
        pending_request=++request_sequence;if(!pending_request)pending_request=++request_sequence;
        result->request_id=pending_request;result->reset_requested=1;result->committed=0;
        copy(&pending_result,result,sizeof(pending_result));
        return F330_RESET_REQUIRED;
    }
    if(phase || enters || leaves || result->counter_writes) {blocked=1;return F330_ABI_FAULT;}
    result->committed=1;return F330_OK;
}
int f330_confirm_reset(uint32_t gen,uint32_t request,int confirmed,int32_t sec,int32_t usec,struct f330_result *committed_result)
{
    if(gen!=current_generation || !request || request!=pending_request)return F330_STALE;
    if(!confirmed) {pending_request=0;blocked=1;return F330_ABI_FAULT;}
    if(!committed_result || sec<0 || usec<0 || usec>=1000000)return F330_INVALID;
    copy(f330_oem_bss,after,sizeof(after));f330_oem_history_pointer=history_after;
    *word(0x1294)=timestamp(sec,usec);pending_result.timestamp_after=*word(0x1294);
    pending_result.committed=1;copy(committed_result,&pending_result,sizeof(pending_result));
    pending_request=0;return F330_OK;
}
#ifdef F330_TEST
void f330_test_poll_count(uint32_t count) {*word(0x1290)=count;}
#endif
