import json
from pathlib import Path
from finance_autoresearch.runtime import build_runtime
from finance_autoresearch.backtest.prescreener import prescreen_candidate

runtime = build_runtime()
try:
    path = Path(r'runtime/openclaw/mutation-75c02771-34ea-4f06-8d71-719aba4c9429-1-mutate_strategy/response.json')
    artifact = json.loads(path.read_text(encoding='utf-8'))['artifact']
    runtime.autoresearch_runner._patch_applier(artifact, repository_root=Path('.').resolve())
    smoke = runtime.autoresearch_runner._run_smoke_harness(Path('src/finance_autoresearch/strategy/mutable/strategy_candidate.py').resolve())
    report = prescreen_candidate(candidate_id='debug', backtest_results=smoke)
    print('REPORT', report)
    for key, val in smoke.get('combinations', {}).items():
        oos = val['splits']['out_of_sample']
        v = val['splits']['validation']
        print(str(key), 'trade_count=', oos['trade_count'], 'turnover=', oos['turnover'], 'exposure=', oos['exposure'], 'val_sharpe=', v['sharpe'], 'oos_sharpe=', oos['sharpe'])
finally:
    runtime.close()
