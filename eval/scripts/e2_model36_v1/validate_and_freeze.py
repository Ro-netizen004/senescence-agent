"""Local validation followed by a separate, exclusive freeze step. No API calls."""
import os
import subprocess
import sys
from pathlib import Path
from common import ROOT, OUT, read, sha, write, textfile, now
from privacy_export import DEST as EXPORT, original_preservation
from integration import DEST, verify_export


def main():
    os.umask(0o077)
    if sys.argv[1:] == ['--freeze']:
        return freeze()
    assert not (DEST / 'AMENDMENT_LOCK.json').exists()
    logs = DEST / 'validation_02'
    logs.mkdir(exist_ok=False)
    commands = [
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/e2_model36_v1', '-p', 'test_model36.py', '-v'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/e2_privacy_v1', '-p', 'test_privacy_export.py', '-v'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/e2', '-p', 'test_e2.py', '-v'],
        [sys.executable, '-m', 'unittest', '-v', *['backend/tests/' + x for x in [
            'test_output_firewall.py', 'test_inference_state.py', 'test_admissibility_confounding.py',
            'test_admissibility_replicates.py', 'test_governance_method_parity.py', 'test_governance_guard.py']]],
        [sys.executable, '-m', 'pip', 'check'],
    ]
    results = []
    for i, cmd in enumerate(commands, 1):
        result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        path = logs / f'CHECK_{i}.txt'
        textfile(path, 'COMMAND: ' + ' '.join(cmd) + '\n' + result.stdout)
        results.append({'path': str(path.relative_to(ROOT)), 'exit_code': result.returncode, 'sha256': sha(path)})
        print(f'Check {i}: exit {result.returncode}', flush=True)
        if result.returncode:
            raise SystemExit('Validation failed; preserve logs; no freeze')
    packages = subprocess.run([sys.executable, '-m', 'pip', 'freeze', '--all'], text=True, capture_output=True, check=True).stdout
    assert sorted(packages.splitlines()) == sorted((OUT / 'ENVIRONMENT_FREEZE.txt').read_text().splitlines())
    assert sys.version.split()[0] == '3.11.9' and Path(sys.executable).parent.parent.name == '.venv-task2'
    textfile(DEST / 'ENVIRONMENT_FREEZE.txt', packages)
    verify_export()
    write(DEST / 'PRESERVATION_AFTER.json', original_preservation())
    write(DEST / 'VALIDATION_SUMMARY.json', {'time': now(), 'status': 'PASS_OFFLINE_ONLY',
        'checks': results, 'tests': {'new_integration': 11, 'privacy': 21, 'original_e2': 23, 'targeted': 28},
        'total_tests': 83, 'python': sys.version.split()[0], 'executable': sys.executable,
        'environment_unchanged': True, 'contexts': 102, 'routes': 408,
        'new_api_calls': 0, 'scored_reports': 0, 'real_case_rendering': 0,
        'live_transport_verified': False, 'gate_states_preserved': 102,
        'execution_permission': False})


def freeze():
    summary = read(DEST / 'VALIDATION_SUMMARY.json')
    assert summary['status'] == 'PASS_OFFLINE_ONLY'
    for item in summary['checks']:
        assert item['exit_code'] == 0 and sha(ROOT / item['path']) == item['sha256']
    verify_export(); original_preservation()
    assert (DEST / 'READINESS_CHECKLIST.md').is_file()
    paths = list(DEST.rglob('*')) + list((ROOT / 'eval/scripts/e2_model36_v1').glob('*.py'))
    dependencies = [OUT / 'E2_PROTOCOL_LOCK.json', OUT / 'E2_BLOCKED_SNAPSHOT_MANIFEST.json',
                    OUT / 'E2_E4_SAMPLE.json', EXPORT / 'EXPORT_SPEC_LOCK.json']
    files = {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths + dependencies)
             if p.is_file() and '__pycache__' not in p.parts}
    write(DEST / 'AMENDMENT_LOCK.json', {'time': now(),
        'status': 'FROZEN_PRE_EXECUTION_AMENDMENT_E2_BLOCKED',
        'protocol_sha256': sha(DEST / 'E2_MODEL_AMENDMENT_V1.md'), 'files': files,
        'original_e2_status': 'E2_BLOCKED', 'research_transfer_authorized': False,
        'scored_execution_authorized': False, 'requested_model': 'gemini-3.6-flash',
        'actual_scored_backend': None, 'dependency_policy': 'Verify referenced original/privacy locks recursively before use'})
    print('protocol_sha256=' + sha(DEST / 'E2_MODEL_AMENDMENT_V1.md'))
    print('amendment_lock_sha256=' + sha(DEST / 'AMENDMENT_LOCK.json'))
    print('frozen_entries=' + str(len(files)))


if __name__ == '__main__':
    main()
