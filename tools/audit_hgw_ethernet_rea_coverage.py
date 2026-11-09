"""Audit exact ARC ELF code bytes, decoder evidence and REA body coverage.

Offline only. Creates a new immutable output and preserves original executable
sections. Measures byte-level coverage separately from semantic reconstruction.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from recover_hgw5g_driver_ops import Elf
from seed_hgw_ethernet_rea import linked_bases, decode_listing, validate_listing


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contiguous_ranges(addresses):
    rows=[]
    for address in sorted(addresses):
        if rows and rows[-1]['end']+1==address:
            rows[-1]['end']=address
        else:
            rows.append(dict(start=address,end=address))
    return [dict(start=hex(r['start']),end=hex(r['end']),bytes=r['end']-r['start']+1) for r in rows]


def audit_module(spec, output):
    tag=spec['module']
    if not tag or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in tag):
        raise ValueError('invalid module identifier')
    original=Path(spec['original']);linked=Path(spec['linked']);listing=Path(spec['disassembly']);export=Path(spec['export'])
    sources=[original,linked,listing,export/'result.json']
    before={str(p):digest(p) for p in sources}
    elf=Elf(original);raw=linked.read_bytes();bases=linked_bases(raw);instructions=decode_listing(listing);validate_listing(raw,instructions)
    result=json.loads((export/'result.json').read_text())
    if result['target_sha256']!=digest(linked):
        raise ValueError('REA export target does not match selected linked ELF')
    bodies=set();body_owner={};functions=[];missing_info=[]
    for fn in result['functions']:
        details=json.loads((export/f'function-{fn["index"]:04}.json').read_text())
        info=fn.get('info') or (details.get('info') or {}).get('value',{}).get('result') or {}
        body=info.get('body') or {};addresses=set()
        if not body.get('available'):
            missing_info.append(fn['address'])
        for span in body.get('ranges',[]):
            addresses.update(range(int(span['start'],16),int(span['end'],16)+1))
        bodies.update(addresses)
        for address in addresses:body_owner.setdefault(address,[]).append(fn['address'])
        functions.append(dict(address=fn['address'],name=fn['name'],body=body,
            info_available=bool(body.get('available')),pseudocode=fn['pseudocode'],warnings=fn['warnings'],errors=fn['errors']))
    sections=[];total=set();decoded=set();padding=set();body_code=set();gap_code=set();gap_padding=set()
    for sec in elf.sections:
        if not sec['flags']&4:continue
        start=bases[sec['name']];end=start+sec['size'];span=set(range(start,end));total.update(span)
        sec_instructions=[i for i in instructions if start<=i['address']<end];classified=[];section_decoded=set()
        for instruction in sec_instructions:
            instruction_bytes=set(range(instruction['address'],instruction['address']+instruction['size']))
            if section_decoded&instruction_bytes:raise ValueError('linear instruction spans overlap')
            section_decoded.update(instruction_bytes)
            nop=instruction['mnemonic'] in ('nop','nop_s')
            covered=instruction_bytes&bodies;missing=instruction_bytes-bodies
            if nop:padding.update(instruction_bytes);gap_padding.update(missing)
            else:body_code.update(covered);gap_code.update(missing)
            classified.append(dict(**instruction,encoding_class='NOP_ENCODING_PADDING_CANDIDATE' if nop else 'DECODED_CODE',
                ghidra_body_covered_bytes=len(covered),ghidra_body_uncovered_bytes=len(missing),
                body_owners=sorted({owner for byte in instruction_bytes for owner in body_owner.get(byte,[])})))
        decoded.update(section_decoded)
        raw_name=tag+'-'+sec['name'].strip('.').replace('.','_')+'-original.raw'
        (output/raw_name).write_bytes(sec['data'])
        sections.append(dict(name=sec['name'],original_bytes=sec['size'],original_sha256=hashlib.sha256(sec['data']).hexdigest(),
            original_raw_export=raw_name,linked_start=hex(start),linked_end=hex(end-1),decoded_bytes=len(section_decoded),
            body_covered_bytes=len(span&bodies),body_uncovered_ranges=contiguous_ranges(span-bodies),
            undecoded_ranges=contiguous_ranges(span-section_decoded),instructions=classified))
    original_functions=[s for s in elf.syms if s['type']==2 and s['section']<len(elf.sections) and elf.sections[s['section']]['flags']&4]
    unique_starts={bases[elf.sections[s['section']]['name']]+s['value'] for s in original_functions};export_starts={int(f['address'],16) for f in functions}
    after={str(p):digest(p) for p in sources}
    if before!=after:raise ValueError('selected input changed during audit')
    return dict(schema='openmitrastar.ethernet-rea-final-coverage/v1',module=tag,inputs=before,hardware_accessed=False,
        source_unchanged=True,export_status=result['status'],export_session_closed=result['session_closed'],
        original_function_symbols=len(original_functions),unique_original_function_starts=len(unique_starts),
        missing_original_function_starts=[hex(a) for a in sorted(unique_starts-export_starts)],
        original_executable_bytes=len(total),linear_byte_verified_decoded_bytes=len(total&decoded),
        all_linear_executable_bytes_decoded=total<=decoded,ghidra_body_union_bytes=len(total&bodies),
        body_uncovered_bytes=len(total-bodies),decoded_non_nop_body_uncovered_bytes=len(gap_code),
        nop_body_uncovered_bytes=len(gap_padding),nop_encoding_bytes=len(padding),
        overlapping_body_bytes=sum(len(owners)>1 for byte,owners in body_owner.items() if byte in total),
        function_count=len(functions),pseudocode_returned=sum(f['pseudocode'] for f in functions),
        warning_functions=sum(bool(f['warnings']) for f in functions),missing_body_info=missing_info,
        functions=functions,sections=sections,
        limits=['Whole-byte preservation and pinned linear decoding are separately measured from Ghidra function bodies.',
            'NOP encoding does not prove unreachable alignment padding.',
            'Provider body membership, successful pseudocode and seed candidates do not certify semantic CFG or source equivalence.',
            'Original raw sections retain unapplied ET_REL relocations; derived linked addresses remain analysis-only synthetic.',
            'No firmware, hardware, traffic or release acceptance is established.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    spec=json.loads(a.spec.read_text());a.output.mkdir(exist_ok=False);summary=[]
    for module in spec['modules']:
        result=audit_module(module,a.output);(a.output/(module['module']+'-coverage.json')).write_text(json.dumps(result,indent=2)+'\n')
        summary.append({k:v for k,v in result.items() if k not in ('functions','sections','limits')})
        print(json.dumps({k:result[k] for k in ['module','original_executable_bytes','linear_byte_verified_decoded_bytes','ghidra_body_union_bytes','body_uncovered_bytes','decoded_non_nop_body_uncovered_bytes','warning_functions']}),flush=True)
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(a.output/'input-spec.json').write_text(json.dumps(spec,indent=2)+'\n')
    lines=['# Final Ethernet executable coverage ledger','', 'Offline audit preserves every original executable section and compares exact linked-byte disassembly with final REA function bodies. No hardware accessed.','', '| Module | Original executable bytes / verified linear decode | Ghidra body bytes | Non-NOP bytes outside bodies | NOP bytes outside bodies | Procedures / warning procedures |','|---|---:|---:|---:|---:|---:|']
    for r in summary:lines.append(f'| {r["module"]} | {r["original_executable_bytes"]} / {r["linear_byte_verified_decoded_bytes"]} | {r["ghidra_body_union_bytes"]} | {r["decoded_non_nop_body_uncovered_bytes"]} | {r["nop_body_uncovered_bytes"]} | {r["function_count"]} / {r["warning_functions"]} |')
    lines.extend(['', 'Whole executable-byte preservation and linear decoding are confirmed only where numerator equals denominator. Ghidra bodies remain partial wherever non-NOP bytes are outside bodies. All exact gap ranges and decoded instructions are retained per module.', '', 'Function seeds and source correlations are candidates; OEM stripped names are not recovered by naming them. Pseudocode warnings and unknown flow remain explicit. NOP encodings are facts; treating them as unreachable padding is an inference. No Linux5.10 hardware acceptance is established.', ''])
    (a.output/'REPORT.md').write_text('\n'.join(lines))


if __name__=='__main__':main()
