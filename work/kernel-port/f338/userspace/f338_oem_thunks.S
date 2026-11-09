/* Userspace ABI adapters. Original algorithm bytes remain untouched. */
.text
.macro OEM_CALL public,target
.global \public
.type \public,@function
\public:
 sub sp,sp,16
 st gp,[sp,0]
 st blink,[sp,4]
 bl \target
 ld gp,[sp,0]
 ld blink,[sp,4]
 add sp,sp,16
 j [blink]
.size \public,.-\public
.endm
OEM_CALL f338_oem_detect_init,f328_oem_detect_init
OEM_CALL f338_oem_detect_reset,f328_oem_detect_reset
OEM_CALL f338_oem_detect_radar,f328_oem_detect_radar
OEM_CALL f338_oem_detect_radar_poll,f328_oem_detect_radar_poll
OEM_CALL f338_oem_preprocess,f330_oem_preprocess
.global f338_oem_timer_call
.type f338_oem_timer_call,@function
f338_oem_timer_call:
 sub sp,sp,16
 st gp,[sp,0]
 st blink,[sp,4]
 mov r12,r0
 mov r0,r1
 jl [r12]
 ld gp,[sp,0]
 ld blink,[sp,4]
 add sp,sp,16
 j [blink]
.size f338_oem_timer_call,.-f338_oem_timer_call
