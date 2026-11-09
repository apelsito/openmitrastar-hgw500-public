"""Exact R3 candidate, r2 event capture and corrected R3 UART observation."""
from pathlib import Path
import argparse
import json
import os

import f366_acquisition_executor as core
import f366_acquisition_executor_r2 as capture
import f366r3_native_evidence as native
import f366r3_reset_observation as reset

EVIDENCE_ROOT = core.EVIDENCE_ROOT
SUPERVISOR_SHA = core.SUPERVISOR_SHA
desktop_ps = core.desktop_ps
CANDIDATE_SHA = 'ca66ddf07a6a1ef4470a77ca85c4151354e9d7dd831abc7e5f02c1a53a8b5d2d'


class Host(capture.Host):
    def diagnostic(self, token, uart, output):
        result = super().diagnostic(token, uart, output)
        events = [json.loads(line) for line in output.with_name('diagnostic-events-r2.jsonl').read_text(encoding='ascii').splitlines()]
        result.update(native.review_transcript(output.read_text(encoding='ascii'), events))
        return result


def load_plan(path, digest):
    plan = core.load_plan(path, digest)
    core.require(plan.get('candidate_revision') == 'f366r3' and plan.get('capture_revision') == 2 and plan.get('reset_observation_revision') == 3, 'r3_plan_revision')
    image = plan['images']['f366']
    core.require(image['sha256'] == CANDIDATE_SHA and image['bytes'] == 5451776 and image['full_slot_crc32'] == '94ddd37e', 'r3_exact_candidate')
    core.require(plan.get('radar_filter_parameter') == 235 and plan.get('radar_filter_bandwidth') == 80 and plan.get('native_guard_revision') == 3, 'r3_native_context')
    for module in (capture, capture.evidence, native, native.previous, reset):
        file = str(Path(module.__file__).resolve())
        core.require(plan['sources'].get(file) == core.baseline.sha(file), 'r3_module_not_bound')
    core.require(plan['sources'].get(str(Path(__file__).resolve())) == core.baseline.sha(__file__), 'r3_worker_not_bound')
    return plan


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.plan, args.plan_sha256)
    if not args.execute:
        print(json.dumps(dict(status='OFFLINE_VALID_F366R3', capture_revision=2, reset_observation_revision=3, hardware_actions=False)))
        return 0
    core.require(os.environ.get('OM_F366_CONTEXT') and args.output_dir and args.output_dir.is_dir() and args.output_dir.resolve().parent == EVIDENCE_ROOT.resolve(), 'owning_launcher_required')
    return core.run(plan, args.output_dir, host_factory=Host, uart_factory=reset.Uart)


if __name__ == '__main__':
    raise SystemExit(main())
