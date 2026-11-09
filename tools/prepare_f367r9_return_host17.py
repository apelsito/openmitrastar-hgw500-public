"""Bind root's read-only host17 observation to a new exact recovery plan."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import json

import f367r9_return_f365_host17 as current
import prepare_f367r9_return_f365 as previous

core = current.core


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--observation', type=Path, required=True)
    parser.add_argument('--observation-sha256', required=True)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--delta-tests', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    original = core.load_plan(current.PREVIOUS_PLAN, current.PREVIOUS_SHA)
    observation_path = core.safe_path(args.observation.resolve())
    core.require(core.sha(observation_path) == args.observation_sha256, 'root_observation_hash')
    observed = current.validate_observation(core.read(observation_path), original)
    plan = copy.deepcopy(original)
    plan['network']['interface_index'] = 17
    plan['network']['host17_observation'] = dict(path=str(observation_path), sha256=core.sha(observation_path))
    plan['host_binding_revision'] = 'r9-recovery-host17-v2'
    tests = core.safe_path(args.tests.resolve())
    plan['host17_tests'] = dict(path=str(tests), sha256=core.sha(tests))
    delta_tests = core.safe_path(args.delta_tests.resolve())
    plan['host17_delta_tests'] = dict(path=str(delta_tests), sha256=core.sha(delta_tests))
    seeds = ['f367r9_return_f365_host17.py', 'prepare_f367r9_return_host17.py', 'run_f367r9_return_f365_host17.ps1',
             'f367r9_return_context_host17.ps1', 'assert_f367r9_return_context_host17.ps1', 'f367r9_host17_guard.ps1',
             'collect_f367r9_host17_binding.ps1', 'test_f367r9_host17_binding.ps1', 'test_f367r9_return_host17.py']
    files = previous.dependency_files(core.ROOT/'tools'/name for name in seeds)
    files.update({current.PREVIOUS_PLAN, observation_path, tests, delta_tests})
    for source, digest in observed['source_pins'].items():
        core.require(core.sha(source) == digest, 'observation_source_drift')
        files.add(Path(source))
    for file in files:
        plan['sources'][str(file.resolve())] = core.sha(file)
    out = (args.output_dir or core.ROOT/'outputs/preflight'/('r9-return-host17-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve()
    core.safe_path(out, exists=False)
    core.require(not out.exists() and out.parent == core.ROOT/'outputs/preflight', 'new_scoped_plan_directory')
    out.mkdir()
    path = out/'plan.json'
    core.save_new(path, plan)
    digest = core.sha(path)
    current.load_plan(path, digest)
    result = dict(status='PASS_OFFLINE_R9_RETURN_HOST17_PLAN', plan=str(path), plan_sha256=digest,
                  source_pins=len(plan['sources']), hardware_actions=False, host_mutation=False,
                  observation=dict(path=str(observation_path), sha256=core.sha(observation_path)),
                  permission_projection_changed_fields=['connection_interface_index'], source_interface_index=17,
                  f365_sha256=core.F365_SHA, writer_and_recovery_flow_changed=False,
                  r9_failure_cause='NOT_ATTESTED_BY_CURRENT_INDEX_CHANGE', physical_return='NOT_RUN')
    core.save_new(out/'result.json', result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
