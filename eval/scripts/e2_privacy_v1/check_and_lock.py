"""Local tests and candidate hash lock. Never authorizes execution or connects."""
import os
import subprocess
import sys
from pathlib import Path
from common import ROOT, OUT, read, sha, now, write, textfile, encode
from privacy_export import DEST, original_preservation


def main():
    assert not (DEST / 'EXPORT_SPEC_LOCK.json').exists()
    os.umask(0o077)
    assert sys.version.split()[0] == '3.11.9'
    assert Path(sys.executable).parent.parent.name == '.venv-task2'
    if sys.argv[1:] == ['--lock-only']:
        return lock()
    commands = [
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/e2_privacy_v1', '-p', 'test_privacy_export.py', '-v'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/e2', '-p', 'test_e2.py', '-v'],
        [sys.executable, '-m', 'unittest', '-v', *['backend/tests/' + x for x in [
            'test_output_firewall.py', 'test_inference_state.py', 'test_admissibility_confounding.py',
            'test_admissibility_replicates.py', 'test_governance_method_parity.py', 'test_governance_guard.py']]],
        [sys.executable, '-m', 'pip', 'check'],
    ]
    results = []
    for index, command in enumerate(commands, 1):
        result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = DEST / f'VALIDATION_{index}.txt'
        textfile(log, 'COMMAND: ' + ' '.join(command) + '\n' + result.stdout)
        results.append({'command': command, 'exit_code': result.returncode, 'log': log.name, 'sha256': sha(log)})
        print(encode({'check': index, 'exit_code': result.returncode}), flush=True)
        if result.returncode:
            raise SystemExit('Validation failed; no lock written. Preserve log and investigate before a new validation version.')
    freeze = subprocess.run([sys.executable, '-m', 'pip', 'freeze', '--all'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    textfile(DEST / 'ENVIRONMENT_FREEZE.txt', freeze.stdout)
    original = (OUT / 'ENVIRONMENT_FREEZE.txt').read_text()
    # Original E2 environment file may include headings: compare package entries.
    entries = lambda s: sorted(l.strip() for l in s.splitlines() if '==' in l or ' @ ' in l)
    assert entries(original) == entries(freeze.stdout), 'Package freeze differs from original E2'
    write(DEST / 'VALIDATION_SUMMARY.json', {'time': now(), 'checks': results, 'environment_matches_original_e2': True,
          'python_version': sys.version.split()[0], 'python_executable': sys.executable,
          'preparation_only': True, 'actual_reporter_execution_verified': False,
          'scientific_results_generated': 0, 'requests_sent': 0, 'status': 'LOCAL_CHECKS_PASSED_PERMISSION_BLOCKED'})
    write(DEST / 'PRESERVATION_FINAL.json', original_preservation())
    print(encode({'status': 'LOCAL_CHECKS_PASSED_PERMISSION_BLOCKED', 'requests_sent': 0}))


def lock():
    summary = read(DEST / 'VALIDATION_SUMMARY.json')
    assert summary['status'] == 'LOCAL_CHECKS_PASSED_PERMISSION_BLOCKED'
    assert all(r['exit_code'] == 0 and sha(DEST / r['log']) == r['sha256'] for r in summary['checks'])
    original_preservation()
    assert (DEST / 'TRANSFER_AUDIT_REPORT.md').is_file()
    paths = list(DEST.rglob('*')) + list((ROOT / 'eval/scripts/e2_privacy_v1').glob('*.py'))
    files = {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths) if p.is_file() and '__pycache__' not in p.parts}
    write(DEST / 'EXPORT_SPEC_LOCK.json', {'time': now(), 'status': 'FROZEN_CANDIDATE_NOT_AUTHORIZED',
          'experiment_status': 'E2_BLOCKED', 'files': files, 'max_reporting_requests': 204,
          'billing_verified': False, 'institutional_dua_clearance_verified': False,
          'final_user_transfer_approval': False, 'execution_wrapper_validated': False,
          'request_body_allowlist': 'candidate_requests/*.json only after all permissions, review and explicit approval',
          'local_only_mapping_and_audit_must_never_be_transmitted': True})
    print(encode({'status': 'E2_BLOCKED', 'candidate_lock_sha256': sha(DEST / 'EXPORT_SPEC_LOCK.json'), 'files': len(files)}))


if __name__ == '__main__':
    main()
