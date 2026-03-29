import json
from pathlib import Path
from finance_autoresearch.runtime import build_runtime

runtime = build_runtime()
try:
    path = Path(r'runtime/openclaw/mutation-75c02771-34ea-4f06-8d71-719aba4c9429-1-mutate_strategy/response.json')
    artifact = json.loads(path.read_text(encoding='utf-8'))['artifact']
    runtime.autoresearch_runner._patch_applier(artifact, repository_root=Path('.').resolve())
    smoke = runtime.autoresearch_runner._run_smoke_harness(Path('src/finance_autoresearch/strategy/mutable/strategy_candidate.py').resolve())
    serial = {}
    for key, val in smoke.get('combinations', {}).items():
        serial[str(key)] = {
            'symbol': val.get('symbol'),
            'timeframe': val.get('timeframe'),
            'validation': val.get('splits', {}).get('validation', {}),
            'out_of_sample': val.get('splits', {}).get('out_of_sample', {}),
        }
    print(json.dumps(serial, ensure_ascii=False, indent=2))
finally:
    runtime.close()
