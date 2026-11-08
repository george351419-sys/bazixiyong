"""python3 tools/audit_fusion_release.py --enforce：发布门槛失败时返回非零。"""
import argparse
import json
from pathlib import Path
import sys
import subprocess
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bazi_core.engine import analyze
from bazi_core.release_audit import digest,summarize
from bazi_core.domain_validation import validate_domain_dataset


def run():
    fixture=json.loads((ROOT/'tests/fixtures/calendar_360.json').read_text())
    manifest=json.loads((ROOT/'validation/fusion_release_manifest.json').read_text())
    results=[]
    for case in fixture['cases']:
        pillars=case['pillars']
        chart=dict(gans=[p[0] for p in pillars],zhis=[p[1] for p in pillars])
        config=dict(fixture['config'],enable_special_ge=case['external'])
        results.append(dict(config=config,result=analyze(chart,config=config),source='implementation_snapshot'))
    domain=validate_domain_dataset(manifest.get('independent_dataset'),ROOT,required_scope='integrated_action',require_birth=True)
    report=summarize(results,manifest,digest(fixture),domain)
    report['independent_validation']=domain
    cases_path=ROOT/'tests/test_fusion_completion.py'
    if digest(cases_path.read_text())!=manifest['policy_cases_sha256']:
        report['failures'].append('constructed_cases_hash_mismatch')
    checked=subprocess.run([sys.executable,'-m','unittest','tests.test_fusion_completion','-q'],
        cwd=ROOT,capture_output=True,text=True,timeout=60)
    report['constructed_contract_suite_passed']=checked.returncode==0
    if checked.returncode:
        report['failures'].append('constructed_contract_cases_failed')
        report['constructed_contract_errors']=checked.stderr
    for suite in manifest.get('additional_contract_suites',[]):
        path=ROOT/suite['path']
        if digest(path.read_text())!=suite['sha256']: report['failures'].append('additional_contract_hash_mismatch')
        checked=subprocess.run([sys.executable,'-m','unittest',suite['module'],'-q'],cwd=ROOT,capture_output=True,text=True,timeout=60)
        if checked.returncode:
            report['failures'].append('additional_contract_suite_failed')
            report.setdefault('additional_contract_errors',[]).append(checked.stderr)
    report['domain_gold_standard']=bool(domain['passed'] and manifest.get('provenance',{}).get('independent_gold_standard') is True
        and manifest.get('provenance',{}).get('review_status')=='independent_domain_validation_approved')
    report['passed']=not report['failures']
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--enforce',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=run()
    data=json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)
    if args.output: args.output.write_text(data+'\n')
    print(data)
    if args.enforce and not report['passed']: raise SystemExit(1)
