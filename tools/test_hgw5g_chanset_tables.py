"""Compile recovered tables/lookup and verify exact OEM rows and bounds.

Cross product checks first-match lookup against independently decoded OEM rows.
Malformed bounds must refuse without touching an invalid payload pointer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists()
    rows = json.loads((args.candidate/"tables.json").read_text())
    inputs = {str(p):sha(p) for p in args.candidate.iterdir() if p.is_file()}
    inputs[str(Path(__file__).resolve())] = sha(Path(__file__))
    inputs[str(args.compiler)] = sha(args.compiler)
    args.output.mkdir(parents=True)
    (args.output/"input-pins.json").write_text(json.dumps(inputs, indent=2)+"\n")
    fixture = ["#include <assert.h>", "#include <stdint.h>", "#include <stdio.h>",
               '#include "openmitrastar_chanset_recovered.h"',
               "static const uint32_t expected[130][20] = {"]
    for table in rows:
        for row in table["entries"]:
            fixture.append("{"+",".join(str(x)+"U" for x in row)+"},")
    fixture += ["};", r'''
int main(void) {
    struct om_chanset_view view, sentinel;
    const struct om_chanset_entry *found, *expected_found;
    const unsigned bands[6] = {0,0,1,1,1,1};
    const unsigned widths[6] = {20,40,20,40,80,160};
    const unsigned counts[6] = {14,18,30,28,24,16};
    const unsigned queries[6] = {0,20,40,80,160,161};
    unsigned table, index, word, channel, width, secondary, all=0, exact=0, base=0;
    for(table=0;table<6;table++) {
        assert(om_chanset_template(bands[table],widths[table],&view)==0);
        assert(view.count==counts[table] && view.capacity==counts[table]);
        for(index=0;index<view.count;index++) {
            const uint32_t *compiled=(const uint32_t*)&view.entries[index];
            for(word=0;word<20;word++) {assert(compiled[word]==expected[base+index][word]);exact++;}
        }
        for(channel=0;channel<256;channel++)for(width=0;width<6;width++)for(secondary=0;secondary<5;secondary++) {
            int result;
            expected_found=0;
            for(index=0;index<view.count;index++) {
                const uint32_t *row=expected[base+index];
                if(row[0]==channel && row[2]==queries[width] && row[1]==secondary) {
                    expected_found=&view.entries[index];break;
                }
            }
            found=(const struct om_chanset_entry*)(uintptr_t)1;
            result=om_chanset_find(&view,channel,queries[width],secondary,&found);
            assert(result==!!expected_found && found==expected_found);all++;
        }
        base+=view.count;
    }
    sentinel.entries=(const struct om_chanset_entry*)(uintptr_t)1; sentinel.count=7;sentinel.capacity=8;
    view=sentinel;
    assert(om_chanset_template(9,20,&view)==-22 && view.entries==sentinel.entries && view.count==7);
    assert(om_chanset_template(0,80,&view)==-22 && view.entries==sentinel.entries && view.count==7);
    assert(om_chanset_template(1,21,&view)==-22 && view.entries==sentinel.entries && view.count==7);
    assert(om_chanset_template(0,20,0)==-22);
    found=(const struct om_chanset_entry*)(uintptr_t)3;
    assert(om_chanset_find(0,1,20,0,&found)==-22 && (uintptr_t)found==3);
    view=sentinel;view.count=9;
    assert(om_chanset_find(&view,1,20,0,&found)==-22 && (uintptr_t)found==3);
    view=sentinel;view.capacity=99;
    assert(om_chanset_find(&view,1,20,0,&found)==-22 && (uintptr_t)found==3);
    view.entries=0;view.count=0;view.capacity=0;
    assert(om_chanset_find(&view,1,20,0,&found)==-22 && (uintptr_t)found==3);
    assert(om_chanset_find(&sentinel,1,20,0,0)==-22);
    { /* duplicate keys must select the first original record */
        struct om_chanset_entry duplicate[2]={{0}};
        duplicate[0].primary=duplicate[1].primary=1;
        duplicate[0].bandwidth=duplicate[1].bandwidth=20;
        view.entries=duplicate;view.count=2;view.capacity=2;
        assert(om_chanset_find(&view,1,20,0,&found)==1 && found==duplicate);
    }
    printf("{\"lookup_cases\":%u,\"exact_compiled_words\":%u,\"negative_cases\":9,\"duplicate_first_match\":true}\n",all,exact);
    return 0;
}
''']
    source = args.output/"fixture.c"
    source.write_text("\n".join(fixture)+"\n", encoding="utf-8")
    command = [str(args.compiler), "-std=c11", "-O1", "-fno-strict-aliasing",
               "-I"+str(args.candidate.resolve()), str(source),
               str(args.candidate/"openmitrastar_chanset_recovered.c"), "-o", str(args.output/"fixture.exe")]
    (args.output/"compile.command.json").write_text(json.dumps(command, indent=2)+"\n")
    compile = subprocess.run(command, capture_output=True, timeout=60)
    (args.output/"compile.stderr").write_bytes(compile.stderr)
    assert compile.returncode == 0, compile.stderr.decode(errors="replace")
    run = subprocess.run([str(args.output/"fixture.exe")], capture_output=True, timeout=30)
    (args.output/"fixture.stdout").write_bytes(run.stdout)
    (args.output/"fixture.stderr").write_bytes(run.stderr)
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    observed = json.loads(run.stdout)
    assert observed["lookup_cases"] == 46080 and observed["exact_compiled_words"] == 2600
    for path, digest in inputs.items():
        assert sha(Path(path)) == digest, "input drift " + path
    result = dict(status="PASS_HOST_COMPILED_EXACT130_ROWS_AND_BOUNDED_FIRST_LOOKUP",
                  hardware_accessed=False, firmware_eligible=False,
                  inputs_unchanged=True, source_pins=len(inputs), **observed,
                  limits="Table/lookup source fixture only;461 scan/rank/lifetime/integration/physical unrun")
    (args.output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
