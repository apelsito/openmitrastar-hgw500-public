/* SPDX-License-Identifier: BSD-2-Clause
 * Shared syscall interface. Only fixed-width values; no kernel addresses.
 */
#ifndef F338_UAPI_H
#define F338_UAPI_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/ioctl.h>
typedef __u32 f338_u32;typedef __s32 f338_s32;
#else
#include <stdint.h>
#include <sys/ioctl.h>
typedef uint32_t f338_u32;typedef int32_t f338_s32;
#endif
#define F338_MAGIC 0x46333338U
#define F338_ABI 1U
#define F338_RAW_MAX 128U
#define F338_PROCESSED_MAX 256U
#define F338_ZC_ROWS 49U
#define F338_ZC_COLUMNS 112U
#define F338_RESET_MAX 3U
#define F338_DEADLINE_MS 100U
enum f338_wire_status {F338_WIRE_OK=0,F338_WIRE_INPUT=1,F338_WIRE_ENGINE=2,F338_WIRE_CANCELED=3};
enum f338_job_flags {F338_JOB_OCAC=1U,F338_JOB_WEATHER=2U,F338_JOB_POLL_DETECTOR=4U,F338_JOB_TAG=8U};
struct f338_header {f338_u32 magic,abi,size,session,sequence,generation;};
struct f338_raw {f338_u32 start,stop,max_power,tagged;};
/* tagged is a full u32 on the wire. The service validates0/1 and constructs
 * the OEM u8+padding layout explicitly rather than aliasing arbitrary bytes. */
struct f338_job {
 struct f338_header h;
 f338_u32 channel,bandwidth,scan_channel,flags,raw_count,legacy_ticks,timestamp_base,poll_counter;
 f338_s32 real_seconds,real_microseconds,tx_bytes_per_second;
 f338_u32 zc_accurate;
 struct f338_raw raw[F338_RAW_MAX];
 f338_s32 zc[F338_ZC_ROWS][F338_ZC_COLUMNS];
};
struct f338_reply {
 struct f338_header h;
 f338_u32 status,total_count,current_window_count,candidate,flushes,reset_sequences;
 unsigned char configuration[300],statistics[700];
};
struct f338_reset {
 struct f338_header h;
 f338_u32 request_id,sequence_emitted;
 f338_s32 actual_seconds,actual_microseconds;
};
#define F338_IOC_RESET _IOWR('R',0x38,struct f338_reset)
#define F338_IOC_HELLO _IOR('R',0x39,struct f338_header)
#endif
