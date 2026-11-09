"""Run one static REA function analysis in the isolated ARC700 lane (WSL)."""
import argparse
from pathlib import Path
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lab', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--procedure', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.lab / 'manifest.json').read_text())
    before = hashlib.sha256(args.target.read_bytes()).hexdigest()
    env = os.environ.copy()
    env.update(GHIDRA_INSTALL_DIR=manifest['ghidra'],
               JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64',
               REA_GHIDRA_LANGUAGE_ID=manifest['language_id'],
               REA_GHIDRA_COMPILER_SPEC_ID=manifest['compiler_spec_id'])
    command = ['node', str(Path(manifest['runtime']) / 'scripts/rea.mjs'),
               'function', str(args.target), '--procedure', args.procedure,
               '--provider', 'ghidra', '--format', 'json', '--full-output']
    started = datetime.now(timezone.utc).isoformat()
    print(json.dumps({'started': started, 'procedure': args.procedure,
                      'output': str(args.output), 'target_sha256': before}), flush=True)
    with (args.output / 'rea.json').open('wb') as stdout, (args.output / 'rea.stderr').open('wb') as stderr:
        proc = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=900)
    after = hashlib.sha256(args.target.read_bytes()).hexdigest()
    result = {'command': command, 'started_utc': started,
              'finished_utc': datetime.now(timezone.utc).isoformat(),
              'exit_code': proc.returncode, 'target_sha256': before,
              'target_unchanged': before == after, 'hardware_accessed': False,
              'rea_output_sha256': hashlib.sha256((args.output / 'rea.json').read_bytes()).hexdigest(),
              'lab_manifest_sha256': hashlib.sha256((args.lab / 'manifest.json').read_bytes()).hexdigest()}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return proc.returncode

if __name__ == '__main__':
    raise SystemExit(main())
