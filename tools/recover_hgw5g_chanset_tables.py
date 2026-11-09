"""Recover constant OEM channel-set tables and bounded typed lookup source.

Reads constant, non-relocated module data only. Tables are not permission to
use their channels: regulatory and scan/metrics/selection consumers stay open.
Never exports a firmware image, calibration data or device/client identities.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from recover_hgw5g_driver_ops import Elf

ROOT = Path(__file__).resolve().parents[1]
TABLES = [("band24_bw20", 0x8f380, 14), ("band24_bw40", 0x8f7e0, 18),
          ("band5_bw20", 0x8fd80, 30), ("band5_bw40", 0x906e0, 28),
          ("band5_bw80", 0x90fa0, 24), ("band5_bw160", 0x91720, 16)]

HEADER = r'''/* Derived from exact OEM constant tables and REA 0x12f18/0x12f9c.
 * Source reconstruction only: no scan, ranking or regulatory acceptance.
 * Templates preserve OEM oddities byte for byte. No table grants channel use.
 */
#ifndef OPENMITRASTAR_CHANSET_RECOVERED_H
#define OPENMITRASTAR_CHANSET_RECOVERED_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u32 om_cs_u32;
#else
#include <stdint.h>
#include <stddef.h>
typedef uint32_t om_cs_u32;
#endif
struct om_chanset_entry {
    om_cs_u32 primary, secondary_offset, bandwidth, center;
    om_cs_u32 invalid, inactive, cca[4], primary_cca[2];
    om_cs_u32 scan_cca, cci_instant, aci_instant, cci_longterm;
    om_cs_u32 aci_longterm, range_cost, dfs, cost;
};
struct om_chanset_view {
    const struct om_chanset_entry *entries;
    unsigned int count, capacity;
};
enum om_chanset_band { OM_CHANSET_BAND24 = 0, OM_CHANSET_BAND5 = 1 };
int om_chanset_template(enum om_chanset_band band, unsigned int bandwidth,
                        struct om_chanset_view *output);
int om_chanset_find(const struct om_chanset_view *view, unsigned int channel,
                    unsigned int bandwidth, unsigned int secondary_offset,
                    const struct om_chanset_entry **output);
#endif
'''

SOURCE = r'''/* Exact first-match semantics from OEM FUN_ram_00012f9c, using typed
 * fields rather than OEM raw offsets. Invalid bounds refuse before dereference.
 * Template selection is OEM FUN_ram_00012f18 for bands 0 and 1; out-of-range
 * band values fail explicitly instead of treating any nonzero as band5.
 */
#include "openmitrastar_chanset_recovered.h"
#include "openmitrastar_chanset_tables.h"
typedef char om_cs_size_is_80[(sizeof(struct om_chanset_entry) == 80) ? 1 : -1];
int om_chanset_template(enum om_chanset_band band, unsigned int bandwidth,
                        struct om_chanset_view *output)
{
    struct om_chanset_view selected = {0,0,0};
    if (!output) return -22;
    if (band == OM_CHANSET_BAND24) {
        if (bandwidth == 20) {
            selected.entries = om_cs_band24_bw20; selected.count = 14;
        } else if (bandwidth == 40) {
            selected.entries = om_cs_band24_bw40; selected.count = 18;
        }
    } else if (band == OM_CHANSET_BAND5) {
        if (bandwidth == 20) {
            selected.entries = om_cs_band5_bw20; selected.count = 30;
        } else if (bandwidth == 40) {
            selected.entries = om_cs_band5_bw40; selected.count = 28;
        } else if (bandwidth == 80) {
            selected.entries = om_cs_band5_bw80; selected.count = 24;
        } else if (bandwidth == 160) {
            selected.entries = om_cs_band5_bw160; selected.count = 16;
        }
    }
    if (!selected.entries) return -22;
    selected.capacity = selected.count;
    *output = selected;
    return 0;
}
int om_chanset_find(const struct om_chanset_view *view, unsigned int channel,
                    unsigned int bandwidth, unsigned int secondary_offset,
                    const struct om_chanset_entry **output)
{
    unsigned int index;
    if (!view || !output || !view->entries || view->count > view->capacity ||
        view->capacity > 98U) return -22;
    for (index = 0; index < view->count; index++) {
        const struct om_chanset_entry *entry = &view->entries[index];
        if (entry->primary == channel && entry->bandwidth == bandwidth &&
            entry->secondary_offset == secondary_offset) {
            *output = entry;
            return 1;
        }
    }
    *output = 0;
    return 0;
}
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists()
    manifest_path = ROOT/"outputs/rea/oem-wlan-missingops-20261022T134300Z-linked/manifest.json"
    analysis_path = manifest_path.parent/"wlan-ANALYSIS_ONLY-NOT_FIRMWARE.elf"
    manifest = json.loads(manifest_path.read_text())
    original_path = ROOT/"work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/wlan/wlan.ko"
    assert sha(original_path) == manifest["source"]["sha256"]
    assert sha(analysis_path) == manifest["derived"]["sha256"]
    original = Elf(original_path)
    old_data = next(s for s in original.sections if s["name"] == ".data")
    raw = analysis_path.read_bytes()
    header = struct.unpack_from("<HHIIIIIHHHHHH", raw, 16)
    assert header[0:2] == (2, 93)
    sections = [struct.unpack_from("<IIIIIIIIII", raw, header[5]+i*header[-3])
                for i in range(header[-2])]
    data = next(s for s in sections if s[1] != 8 and s[3] <= TABLES[0][1] < s[3]+s[5])
    assert data[5] == old_data["size"]
    evidence_path = ROOT/"outputs/rea/windows-oem-chanset-table-20261022T163400Z-r1/rea.json"
    evidence = json.loads(evidence_path.read_text())["data"]
    assert evidence["subject"]["digest"]["sha256"] == sha(analysis_path)
    assert evidence["raw_result"]["value"]["procedure"]["address"] == "0x12f18"
    rows, text = [], ["/* Exact OEM constant 80-byte records; no runtime data. */",
                      "#ifndef OPENMITRASTAR_CHANSET_TABLES_H", "#define OPENMITRASTAR_CHANSET_TABLES_H"]
    for name, address, count in TABLES:
        offset = address-data[3]
        length = count*80
        assert offset >= 0 and offset+length <= old_data["size"]
        payload = raw[data[4]+offset:data[4]+offset+length]
        assert payload == old_data["data"][offset:offset+length], "linked/source table drift"
        assert not any(r["section_index"] == old_data["index"] and
                       offset <= r["offset"] < offset+length for r in original.relocs), "table relocations"
        entries = [list(struct.unpack_from("<20I", payload, i*80)) for i in range(count)]
        assert all(not any(row[4:]) for row in entries), "constant template includes live metrics"
        rows.append(dict(name=name, analysis_address=hex(address), original_data_offset=offset,
                         count=count, bytes=length, sha256=hashlib.sha256(payload).hexdigest(), entries=entries))
        text.append(f"static const struct om_chanset_entry om_cs_{name}[{count}] = {{")
        for row in entries:
            text.append("    {"+",".join(str(x)+"U" for x in row[:6])+",{"+
                        ",".join(str(x)+"U" for x in row[6:10])+"},{"+
                        ",".join(str(x)+"U" for x in row[10:12])+"},"+
                        ",".join(str(x)+"U" for x in row[12:])+"},")
        text.append("};")
    text.append("#endif")
    args.output.mkdir(parents=True)
    (args.output/"openmitrastar_chanset_recovered.h").write_text(HEADER, encoding="utf-8", newline="\n")
    (args.output/"openmitrastar_chanset_tables.h").write_text("\n".join(text)+"\n", encoding="utf-8", newline="\n")
    (args.output/"openmitrastar_chanset_recovered.c").write_text(SOURCE, encoding="utf-8", newline="\n")
    (args.output/"tables.json").write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
    result = dict(status="SOURCE_ONLY_EXACT130_OEM_CHANSET_ROWS_BOUNDED_LOOKUP",
                  hardware_accessed=False, firmware_eligible=False, recovered_table_rows=sum(x[2] for x in TABLES),
                  table_bytes=sum(x[2]*80 for x in TABLES), table_relocations=0,
                  evidence_id=evidence["evidence_id"], original_table_bytes_exact=True,
                  inputs={str(p):sha(p) for p in [manifest_path, original_path, analysis_path, evidence_path]},
                  source_hashes={p.name:sha(p) for p in args.output.iterdir() if p.is_file()},
                  deviations=["Invalid band outside0/1 refuses, OEM treats nonzero as band5.",
                              "Typed lookup refuses malformed count/capacity before reading."],
                  remaining=["No registration of461 or port integration yet.",
                             "Scan queue/history, metric ranking, callbacks and lifetime still need reconstruction.",
                             "Channel lists preserve OEM irregularities and are not regulatory allowlists.",
                             "No RF, scan, radar, client or traffic evidence."])
    (args.output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("status", "recovered_table_rows", "table_bytes")}))


if __name__ == "__main__":
    main()
