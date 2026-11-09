#ifndef OPENMITRASTAR_COMPAT_TRACE_SKB_H
#define OPENMITRASTAR_COMPAT_TRACE_SKB_H

/* OEM-only packet timing tracepoints; they do not affect datapath state. */
#define trace_skb_perf_start(skb, path) do { } while (0)
#define trace_skb_perf_stamp_call(skb) do { } while (0)
#define trace_skb_perf_finish(skb) do { } while (0)

#endif
