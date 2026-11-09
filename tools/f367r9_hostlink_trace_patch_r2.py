"""R2: observe only LHOST shared calstate; preserve the R1 peer patch exactly."""
import f367r9_hostlink_trace_patch as previous

INCLUDES=previous.INCLUDES
PEER_HELPERS=previous.PEER_HELPERS
HOST_HELPERS=previous.HOST_HELPERS.replace(
 'u32 command,start_jiffies,budget_ticks,progress;',
 'u32 command,start_jiffies,budget_ticks,progress;\n int cal_wait;').replace(
 'cal_global=%u cal_shared=%d cal_default=%u',
 'cal_wait_available=%u cal_wait=%d cal_shared_available=%u cal_shared_current=%d cal_default=%u').replace(
 '(unsigned long long)(now-trace->start_ns),(unsigned)READ_ONCE(g_qtn_params.g_calstate),\n  shared_cal,',
 '(unsigned long long)(now-trace->start_ns),(unsigned)(trace->cal_wait>=0),trace->cal_wait,\n  (unsigned)(soc_shared_params!=NULL),shared_cal,').replace(
 'u32 command,const char *message,u32 budget_ticks,u32 start_jiffies)',
 'u32 command,const char *message,u32 budget_ticks,u32 start_jiffies,int cal_wait)').replace(
 'trace.budget_ticks=budget_ticks;trace.start_ns=ktime_get_ns();',
 'trace.budget_ticks=budget_ticks;trace.cal_wait=cal_wait;trace.start_ns=ktime_get_ns();')

DECL='\tint omr9_cal_wait=-1; /* OMF367R9_R2_LOCAL */\n'
ORIGINAL_IF='\tif (soc_shared_params->calstate == QTN_CALSTATE_DEFAULT) {'
CAPTURED_IF='\tomr9_cal_wait = soc_shared_params->calstate; /* OMF367R9_R2_SELECT */\n\tif (omr9_cal_wait == QTN_CALSTATE_DEFAULT) {'

def patch_hostlink(text):
    result=previous.patch_hostlink(text)
    result=previous.once(result,previous.HOST_HELPERS,HOST_HELPERS)
    result=previous.once(result,'\tint wait_time;\n','\tint wait_time;\n'+DECL)
    result=previous.once(result,ORIGINAL_IF,CAPTURED_IF)
    result=previous.once(result,'qdrv_f367r9_wait_begin(ioctl->ioctl_command,msg,wait_time,(u32)start_time)',
                         'qdrv_f367r9_wait_begin(ioctl->ioctl_command,msg,wait_time,(u32)start_time,omr9_cal_wait)')
    assert 'g_qtn_params' not in result
    return result

def patch_peer_csa(text):return previous.patch_peer_csa(text)

def strip_observation(text):
    text=text.replace(HOST_HELPERS,previous.HOST_HELPERS).replace(DECL,'').replace(CAPTURED_IF,ORIGINAL_IF)
    return previous.strip_observation(text)
