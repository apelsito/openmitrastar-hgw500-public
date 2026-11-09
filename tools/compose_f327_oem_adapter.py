"""Compose only the F327 source from the pinned F316 source; no hardware."""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f316_radar_native/qtn_radar_native_f316_main.c"
DEST = ROOT / "work/kernel-port/modules/f327_radar_event_lifecycle/qtn_radar_native_f327_main.c"

def compose() -> str:
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == "c8425105133b0d2e365d7aad6dca6aad2e8be7c2dd3ecb34b1ba3961e0a0e535"
    source = SOURCE.read_text()
    def replace(old: str, new: str) -> None:
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    def function(name: str, body: str) -> None:
        nonlocal source
        match = re.search(r"(?m)^(?:static )?(?:void|int|bool|uint8_t) " + name + r"\([^;]*?\)\n\{", source)
        assert match, name
        opening = match.end() - 1
        level = 1; end = opening + 1
        while level:
            level += (source[end] == "{") - (source[end] == "}")
            end += 1
        source = source[:opening + 1] + "\n" + body.strip() + "\n" + source[end - 1:]
    replace('#include "classifier/f316_classifier.h"', '#include "classifier/f316_classifier.h"\n#include "f327_event_lifecycle.h"\n#include "f327_oem_requests.h"')
    replace('#define F315_SCHEMA "openmitrastar.radar-native-f316/v1"', '#define F315_SCHEMA "openmitrastar.radar-native-f327/v2"\n#define F327_RELEASE_QUALIFIED 0')
    replace('#define F315_PROC_DIR "openmitrastar_radar_f316"', '#define F315_PROC_DIR "openmitrastar_radar_f327"')
    replace('static struct f316_classifier_state f316_classifier;', 'static struct f327_session f327_session;\nstatic struct f327_oem_requests f327_requests;\nstatic DEFINE_SPINLOCK(f327_request_lock);')
    replace('static bool f316_callback_inflight;\nstatic u32 f316_epoch;\nstatic u32 f316_delivered_epoch;', '#define f316_callback_inflight (f327_session.callback_inflight)\n#define f316_epoch ((u32)f327_requests.epoch)')
    function('f316_update_ready_locked', 'ready = false; /* Qualification is compile-time closed for this artifact. */')
    # Preserve the original function identifier for the existing INIT_DELAYED_WORK.
    match = re.search(r'static void f315_poll_worker\(struct work_struct \*work\)\n\{', source)
    assert match
    opening = match.end()-1; level=1; end=opening+1
    while level:
        level += (source[end] == '{') - (source[end] == '}'); end += 1
    source = source[:match.start()] + '#include "f327_oem_kernel_adapter.inc"\n#include "f327_oem_worker.inc"' + source[end:]
    function('radar_disable', 'f327_request_disable(false);')
    function('radar_enable', 'f327_request_enable();')
    function('radar_stop', 'f327_request_disable(true);')
    function('radar_start', 'return false; /* OEM classifier/acquisition not yet physically qualified. */')
    function('radar_set_chan', 'return f327_request_channel(channel);')
    function('radar_set_bw', 'f327_request_bandwidth(bandwidth);')
    function('radar_get_chan', 'return READ_ONCE(f327_requests.channel);')
    function('radar_get_status', 'return READ_ONCE(f316_enabled);')
    for name, parameter, assignment, bit in (
        ('radar_register', 'callback', 'f316_dfs_callback', 1),
        ('radar_register_is_dfs_chan', 'callback', 'f316_is_dfs_channel', 2),
        ('radar_register_is_dfs_weather_chan', 'unused', 'f316_is_weather_channel', 4),
    ):
        function(name, f'''unsigned long flags;
\tif (!{parameter}) return -EINVAL;
\tspin_lock_irqsave(&f327_request_lock, flags);
\tif (!f327_oem_invalidate(&f327_requests)) {{
\t\tspin_unlock_irqrestore(&f327_request_lock, flags);
\t\treturn -EOVERFLOW;
\t}}
\t{assignment} = {parameter};
\tf327_requests.registrations |= {bit};
\tready = false; f316_enabled = false;
\tspin_unlock_irqrestore(&f327_request_lock, flags);
\treturn 0;''')
    replace('\tf316_classifier_init(&f316_classifier);', '\tf327_init(&f327_session);\n\tf327_oem_init(&f327_requests, shadow_channel, shadow_bandwidth);')
    replace('static int __init qtn_radar_native_f316_init(void)\n{\n\tint ret = 0;', 'static int __init qtn_radar_native_f316_init(void)\n{\n\tint ret = 0;\n\tif (authoritative_enable || weather_enable)\n\t\treturn -EPERM;')
    replace('\tradar_stop();\n\tWRITE_ONCE(ready, false);', '\tradar_stop();\n\t/* Final module teardown runs in process context after qdrv dependency release. */\n\tcancel_delayed_work_sync(&f315_poll_work);\n\tWRITE_ONCE(ready, false);')
    replace('static int f315_status_show(struct seq_file *s, void *unused)\n{', 'static int f315_status_show(struct seq_file *s, void *unused)\n{\n\tseq_puts(s, "disable_contract=oem-nonblocking\\ncallback_inflight_may_finish=1\\nhardware_quiesce_claim=0\\n");')
    replace('/* F316 native Linux 5.10 QT4 radar provider with gated callback authority. */', '/* F327 OEM-style atomic ABI requests and worker-owned classifier history. */')
    return source

if __name__ == '__main__':
    DEST.write_text(compose(), encoding='ascii', newline='\n')
    print(DEST)
