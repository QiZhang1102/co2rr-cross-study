#!/usr/bin/env python3
"""One-command CPU reproduction using pinned public input and frozen assignments."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    os.chdir(ROOT)
    logs=ROOT/'results';logs.mkdir(exist_ok=True)
    names=['outer_splits.csv','predictions.csv','metrics.csv','paired_comparisons.csv','calibration_matched_metrics.csv']
    expected={n:digest(logs/n) for n in names if (logs/n).exists()}
    commands=[('download',[sys.executable,'scripts/download_data.py']),
              ('prepare',[sys.executable,'scripts/prepare_data.py'])]
    if not (logs/'split_manifest.json').exists():commands.append(('freeze_splits',[sys.executable,'scripts/run_models.py','--prepare-splits']))
    commands += [('train',[sys.executable,'scripts/run_models.py','--run']),
                 ('analysis',[sys.executable,'scripts/analyze_results.py']),
                 ('tests',[sys.executable,'-m','unittest','discover','-s','tests','-v']),
                 ('report',[sys.executable,'scripts/generate_report.py'])]
    stages=[]
    for label,cmd in commands:
        began=time.perf_counter();print('Running '+label,flush=True)
        with (logs/('reproduce_'+label+'.log')).open('w') as out:
            completed=subprocess.run(cmd,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
        stages.append({'stage':label,'command':cmd,'exit_code':completed.returncode,'seconds':time.perf_counter()-began})
        if label=='tests':(logs/'tests.log').write_bytes((logs/'reproduce_tests.log').read_bytes())
        if completed.returncode:
            print((logs/('reproduce_'+label+'.log')).read_text());raise SystemExit(completed.returncode)
    comparisons={n:{'expected_sha256':v,'actual_sha256':digest(logs/n),'identical':v==digest(logs/n)} for n,v in expected.items()}
    passed=all(x['identical'] for x in comparisons.values())
    (logs/'one_command_reproduction.json').write_text(json.dumps({'passed':passed,'stages':stages,'saved_reference_comparisons':comparisons,'note':'Requires original frozen config/engine/assignments. Run logs may differ in elapsed time.'},indent=2))
    if not passed:raise SystemExit('Saved reference mismatch; see results/one_command_reproduction.json')
    print('Reproduction passed; report/report_en.pdf and saved results are ready.')
if __name__=='__main__':main()
