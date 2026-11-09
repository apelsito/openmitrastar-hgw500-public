"""Exact F366r2 image and r2 capture binding over unchanged F366 return core."""
from pathlib import Path
import argparse
import json
import os

import f366_acquisition_executor as core
import f366_acquisition_executor_r2 as capture
import f366r2_native_evidence as native

EVIDENCE_ROOT = core.EVIDENCE_ROOT
SUPERVISOR_SHA = core.SUPERVISOR_SHA
desktop_ps = core.desktop_ps
CANDIDATE_SHA = 'c260249e2633e6e90b775ea51c25b68b1771ff3f340f54f652ef967e83fcbb07'


class Host(capture.Host):
    def diagnostic(self, token, uart, output):
        result = super().diagnostic(token, uart, output)
        result.update(native.review_transcript(output.read_text(encoding='ascii')))
        return result


def load_plan(path, digest):
    plan = core.load_plan(path, digest)
    core.require(plan.get('candidate_revision') == 'f366r2' and plan.get('capture_revision') == 2, 'r2_plan_revision')
    image = plan['images']['f366']
    core.require(image['sha256'] == CANDIDATE_SHA and image['bytes'] == 5451776 and image['full_slot_crc32'] == '64db5015', 'r2_exact_candidate')
    for module in (capture, capture.evidence, native):
        file = str(Path(module.__file__).resolve())
        core.require(plan['sources'].get(file) == core.baseline.sha(file), 'r2_module_not_bound')
    core.require(plan['sources'].get(str(Path(__file__).resolve())) == core.baseline.sha(__file__), 'r2_worker_not_bound')
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
        print(json.dumps(dict(status='OFFLINE_VALID_F366R2', capture_revision=2, hardware_actions=False)))
        return 0
    core.require(os.environ.get('OM_F366_CONTEXT') and args.output_dir and args.output_dir.is_dir() and args.output_dir.resolve().parent == EVIDENCE_ROOT.resolve(), 'owning_launcher_required')
    return core.run(plan, args.output_dir, host_factory=Host)


if __name__ == '__main__':
    raise SystemExit(main())
