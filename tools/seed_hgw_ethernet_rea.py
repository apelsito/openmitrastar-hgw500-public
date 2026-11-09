"""Classify ARC ELF function seeds and retain interior targets as labels.

Relocations identify references, not functions. Optional pinned objdump evidence
separates function candidates from hardware-loop and exception labels. All
executable-section relocations remain in metadata, including exclusions.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
from recover_hgw5g_driver_ops import Elf


def linked_bases(raw):
    off = struct.unpack_from('<I', raw, 32)[0]
    width, count, names_index = struct.unpack_from('<HHH', raw, 46)
    headers = [struct.unpack_from('<10I', raw, off + i * width) for i in range(count)]
    strings = raw[headers[names_index][4]:headers[names_index][4] + headers[names_index][5]]
    return {strings[h[0]:strings.index(0, h[0])].decode(): h[3] for h in headers}


def decode_listing(path):
    instructions = []
    if path is None:
        return instructions
    for line in path.read_text(errors='replace').splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f ]+)\s+\t([^\s]+)\s*(.*)', line)
        if match:
            instructions.append(dict(address=int(match[1], 16),
                size=len(match[2].replace(' ', '')) // 2,
                encoded_hex=b''.join(bytes.fromhex(word)[::-1] for word in match[2].split()).hex(),
                mnemonic=match[3], operands=match[4].split(';')[0].strip()))
    return instructions


def containing_instruction(instructions, address):
    return next((i for i in instructions if i['address'] <= address < i['address'] + i['size']), None)


def validate_listing(raw, instructions):
    """Check every supplied decoded instruction against the exact linked bytes."""
    off = struct.unpack_from('<I', raw, 32)[0]
    width, count = struct.unpack_from('<HH', raw, 46)
    headers = [struct.unpack_from('<10I', raw, off + i * width) for i in range(count)]
    for instruction in instructions:
        address, size = instruction['address'], instruction['size']
        section = next((h for h in headers if h[1] != 8 and h[3] <= address and address + size <= h[3] + h[5]), None)
        if section is None:
            raise ValueError('disassembly instruction outside initialized linked section')
        start = section[4] + address - section[3]
        if raw[start:start + size] != bytes.fromhex(instruction['encoded_hex']):
            raise ValueError('disassembly bytes do not match exact linked ELF at ' + hex(address))


def observed_entry_boundary(instructions, address):
    """Heuristic evidence: prologue or a leaf following decoded return."""
    index = next((n for n, i in enumerate(instructions) if i['address'] == address), None)
    if index is None:
        return None
    ins = instructions[index]
    if ins['mnemonic'] == 'push_s' and ins['operands'] == 'blink':
        return 'decoded_blink_save_prologue'
    if ins['mnemonic'].startswith('st.') and ins['operands'].startswith('blink,'):
        return 'decoded_blink_save_prologue'
    previous = instructions[max(0, index - 3):index]
    for n, candidate in enumerate(previous):
        if candidate['mnemonic'].startswith('j') and candidate['operands'] == '[blink]':
            tail = previous[n + 1:]
            delay = 1 if '.d' in candidate['mnemonic'] else 0
            if len(tail) >= delay and all(i['mnemonic'] in ('nop', 'nop_s') for i in tail[delay:]):
                return 'decoded_previous_return_leaf_boundary'
    return None


def observed_call_register(instructions, source):
    """Bounded lexical register-to-call observation, never a CFG proof."""
    if source is None or not source['mnemonic'].startswith('mov'):
        return None
    register = source['operands'].split(',', 1)[0].strip()
    if not re.fullmatch(r'(?:r\d+|gp)', register):
        return None
    index = instructions.index(source)
    for ins in instructions[index + 1:index + 33]:
        mnemonic, operands = ins['mnemonic'], ins['operands']
        if mnemonic in ('jl', 'jl.d', 'jl_s', 'jl_s.d'):
            if operands in (register, '[' + register + ']'):
                return dict(address=hex(ins['address']), register=register,
                    basis='bounded_literal_register_to_decoded_indirect_call')
            return None
        if mnemonic.startswith(('b', 'j', 'lp')):
            return None
        if not mnemonic.startswith(('st', 'cmp', 'tst', 'sr')) and operands.split(',', 1)[0].strip() == register:
            return None
    return None


def apply_additional_seeds(path, elf, linked, bases, instructions, entries):
    """Apply immutable, hash-pinned gap evidence without inventing OEM names."""
    if path is None:
        return None
    document = json.loads(path.read_text())
    if document.get('original_sha256') != hashlib.sha256(elf.raw).hexdigest():
        raise ValueError('additional-seed original SHA-256 mismatch')
    if document.get('linked_sha256') != hashlib.sha256(linked).hexdigest():
        raise ValueError('additional-seed linked SHA-256 mismatch')
    if not instructions:
        raise ValueError('additional seeds require byte-verified pinned disassembly')
    applied = []
    for seed in document['entries']:
        section = elf.byname.get(seed['section'])
        offset = int(seed['offset'], 0) if isinstance(seed['offset'], str) else seed['offset']
        if section is None or not section['flags'] & 4 or not 0 <= offset < section['size']:
            raise ValueError('additional seed outside original executable section')
        address = bases[section['name']] + offset
        instruction = containing_instruction(instructions, address)
        if instruction is None or instruction['address'] != address:
            raise ValueError('additional seed is not an exact decoded instruction start')
        kind = seed['seed_kind']
        if kind not in ('function', 'code', 'label') or not seed.get('basis') or not seed.get('correlation'):
            raise ValueError('additional seed requires kind, basis and correlation evidence')
        if kind == 'function':
            if not observed_entry_boundary(instructions, address):
                raise ValueError('additional function has no decoded entry boundary')
            if any(s['type'] == 2 and s['section'] == section['index'] and s['size']
                   and s['value'] < offset < s['value'] + s['size'] for s in elf.syms):
                raise ValueError('additional function would split an original symbol body')
        evidence = dict(seed_kind=kind, basis=seed['basis'], correlation=seed['correlation'],
            instruction=instruction, boundary=observed_entry_boundary(instructions, address))
        if address not in entries:
            entries[address] = dict(name='candidate_' + section['name'].strip('.').replace('.', '_') + '_' + hex(offset)[2:],
                seed_kind=kind, basis=seed['basis'], section=section['name'], offset=offset,
                size=None, **{'from': []})
        else:
            row = entries[address]
            if row['seed_kind'] != 'function' and (kind == 'function' or kind == 'code'):
                row['seed_kind'] = kind
        entries[address].setdefault('additional_evidence', []).append(evidence)
        applied.append(dict(address=hex(address), **evidence))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        applied=applied, limits=['Additional function seeds are caller-reviewed boundary candidates, not original names or CFG proof.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', required=True, type=Path)
    parser.add_argument('--linked', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--disassembly', type=Path,
        help='objdump -d of this exact linked ELF using the pinned ARC toolchain')
    parser.add_argument('--additional-seeds', type=Path,
        help='hash-pinned JSON of decoded gap candidates/code; names remain generated')
    args = parser.parse_args()
    elf = Elf(args.original)
    linked = args.linked.read_bytes()
    bases = linked_bases(linked)
    instructions = decode_listing(args.disassembly)
    validate_listing(linked, instructions)
    entries, references = {}, []
    for symbol in elf.syms:
        if symbol['type'] != 2 or symbol['section'] >= len(elf.sections):
            continue
        section = elf.sections[symbol['section']]
        if not section['flags'] & 4:
            continue
        address = bases[section['name']] + symbol['value']
        if address in entries:
            entries[address].setdefault('aliases', []).append(symbol['name'])
            continue
        entries[address] = dict(name=symbol['name'], seed_kind='function', basis='STT_FUNC',
            section=section['name'], offset=symbol['value'], size=symbol['size'], **{'from': []})
    for relocation in elf.relocs:
        symbol = elf.syms[relocation['symbol']]
        if symbol['section'] >= len(elf.sections):
            continue
        section = elf.sections[symbol['section']]
        if not section['flags'] & 4:
            continue
        ref = {k: relocation[k] for k in ('section', 'offset', 'type', 'addend')}
        ref.update(target_symbol=symbol['name'], target_section=section['name'])
        if relocation['addend'] is None:
            ref['classification'] = 'unresolved_implicit_addend'
            references.append(ref)
            continue
        offset = symbol['value'] + relocation['addend']
        address = bases[section['name']] + offset
        ref.update(target_offset=offset, target_address=hex(address))
        if not 0 <= offset < section['size']:
            ref['classification'] = 'excluded_outside_executable_section'
            references.append(ref)
            continue
        source = containing_instruction(instructions, bases.get(relocation['section'], 0) + relocation['offset'])
        ref['source_instruction'] = source
        ref['target_boundary_evidence'] = observed_entry_boundary(instructions, address)
        ref['call_evidence'] = observed_call_register(instructions, source)
        original_entry = entries.get(address)
        containing = [s for s in elf.syms if s['type'] == 2 and s['section'] == symbol['section']
            and s['size'] and s['value'] < offset < s['value'] + s['size']]
        data_source = elf.sections[relocation['section_index']]
        if original_entry and original_entry['basis'] == 'STT_FUNC':
            kind, basis = 'function', 'exact_original_function_entry'
        elif relocation['section'] == '__ex_table':
            kind, basis = 'label', 'exception_fault_or_fixup_label'
        elif section['name'] == '.fixup' or relocation['section'] == '.fixup':
            kind, basis = 'label', 'exception_fixup_or_resume_label'
        elif containing:
            kind, basis = 'label', 'interior_original_function_label'
            ref['containing_symbols'] = [s['name'] for s in containing]
        elif source and source['mnemonic'].startswith('sr') and '[lp_' in source['operands']:
            kind, basis = 'label', 'decoded_hardware_loop_target'
        elif source and source['mnemonic'].startswith(('b', 'j', 'lp')) and not source['mnemonic'].startswith(('bl', 'jl')):
            kind, basis = 'label', 'decoded_branch_target_not_function'
        elif data_source['flags'] & 2 and not data_source['flags'] & 4:
            kind, basis = 'function', 'allocated_data_function_pointer_candidate'
        elif ref['call_evidence']:
            kind, basis = 'function', 'decoded_indirect_call_target_candidate'
        elif source and source['mnemonic'].startswith(('mov', 'st')) and ref['target_boundary_evidence']:
            kind, basis = 'function', 'decoded_callback_literal_at_entry_boundary_candidate'
        else:
            kind, basis = 'label', 'unresolved_executable_reference_not_asserted_function'
        ref['classification'] = basis
        references.append(ref)
        if address not in entries:
            entries[address] = dict(name='candidate_' + section['name'].strip('.').replace('.', '_') + '_' + hex(offset)[2:],
                seed_kind=kind, basis=basis, section=section['name'], offset=offset, size=None, **{'from': []})
        elif kind == 'function' and entries[address]['seed_kind'] != 'function':
            entries[address].update(seed_kind=kind, basis=basis)
        entries[address]['from'].append(ref)
    additional = apply_additional_seeds(args.additional_seeds, elf, linked, bases, instructions, entries)
    args.output.mkdir(exist_ok=False)
    (args.output / 'seeds.tsv').write_text(''.join(
        f'0x{address:x}\tcode\n' if row['seed_kind'] == 'code' else
        f'0x{address:x}\t{row["seed_kind"]}\t{row["name"]}\n' for address, row in sorted(entries.items())))
    counts = Counter(row['seed_kind'] for row in entries.values())
    result = dict(original=str(args.original), original_sha256=hashlib.sha256(elf.raw).hexdigest(),
        linked_sha256=hashlib.sha256(linked).hexdigest(),
        disassembly=str(args.disassembly) if args.disassembly else None,
        disassembly_sha256=hashlib.sha256(args.disassembly.read_bytes()).hexdigest() if args.disassembly else None,
        entries=[dict(address=hex(address), **row) for address, row in sorted(entries.items())],
        count=len(entries), counts=dict(counts), executable_references=references, additional_seeds=additional,
        limits=['Function candidates are caller assertions; original local names and complete boundaries are not proved.',
            'Decoded register-call tracking and leaf boundaries are bounded lexical evidence, not CFG equivalence.',
            'Without exact linked-ELF disassembly, code targets are labels unless original symbols or allocated data pointers establish candidates.',
            'Exception sites, hardware-loop targets and internal branches are labels, not additional functions.',
            'No target execution or global function completeness proved.'])
    (args.output / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(count=len(entries), counts=dict(counts), executable_reference_count=len(references), output=str(args.output))))


if __name__ == '__main__':
    main()
