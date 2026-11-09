"""Audit strong imports against actual 7.3 object exports and kernel symvers."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--kernel-symvers', type=Path, required=True)
    parser.add_argument('--nm', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    module_names = args.build_root.joinpath('modules.order').read_text().splitlines()
    symbols = {}
    definitions = set()
    for name in module_names:
        obj = args.build_root / Path(name).with_suffix('.o')
        lines = subprocess.check_output([args.nm, str(obj)], text=True).splitlines()
        imports = set()
        exports = set()
        for line in lines:
            match = re.match(r'\s*(?:[0-9a-fA-F]+\s+)?([A-Za-z?])\s+(\S+)$', line)
            if not match:
                continue
            kind, symbol = match.groups()
            if kind == 'U':
                imports.add(symbol)
            if symbol.startswith('__export_symbol_'):
                exports.add(symbol[len('__export_symbol_'):])
            if kind in 'TDBRSGCA':
                definitions.add(symbol)
        symbols[name] = {'imports': sorted(imports), 'exports': sorted(exports)}
    kernel = {line.split()[1] for line in args.kernel_symvers.read_text().splitlines() if len(line.split()) >= 2}
    providers = set().union(*(set(data['exports']) for data in symbols.values()))
    missing = {}
    for name, data in symbols.items():
        missing[name] = sorted(set(data['imports']) - kernel - providers)
    result = {'kernel_symvers': str(args.kernel_symvers), 'module_count': len(symbols),
              'modules': symbols, 'unresolved_by_module': missing,
              'unresolved': sorted(set().union(*(set(items) for items in missing.values()))),
              'internal_export_provider_count': len(providers), 'hardware_accessed': False}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'module_count': result['module_count'], 'unresolved': result['unresolved']}, indent=2))


if __name__ == '__main__':
    main()
