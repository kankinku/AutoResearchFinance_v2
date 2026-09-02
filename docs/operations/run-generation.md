# Run generation

1. Initialize state with `python cli.py init --state-dir state`.
2. Validate every source with `validate-strategy`; unsupported imports are an explicit
   non-zero result and are not silently converted to candidates.
3. Load development or authorized validation Parquet data. Never pass sealed OOS data to
   `GenerationPipeline`; its access is reserved for a promotion-gate process.
4. Load optional external series with `ParquetDataProvider.read_series`; select a
   `SeriesRef` timeframe (`1m`, `5m`, `15m`, `1h`, `1d`, `1w`, or `1mo`), emit only completed higher-timeframe
   bars, align with `align_as_of`, and retain only observations available at the signal
   timestamp. This supports `US2Y`, `US10Y`, `US20Y`, `JP2Y`, `JP10Y`, `JP20Y`, `KR2Y`,
   `KR10Y`, and `KR20Y` as optional inputs.
5. Call `GenerationPipeline.run` with a parent IR, mutation operations, parameter domains,
   deterministic seed, and a `FunnelConfig`. Supply `BenchmarkData` to add QQQ and Nasdaq
   comparisons without changing the existing Funnel gates.
6. Persist the returned candidate hashes, gate decisions, benchmark comparisons, risk
   evaluations, state snapshot, and knowledge
   payload using `StateFileStore` and `AuditLog`. Store only hashes and abstract profiles
   in knowledge; raw market rows and source prose do not belong there.
7. Review `NEAR_MISS` entries through the Rescue Pool. A `SURVIVOR` is a research result,
   not permission to submit an order.

## CLI parameter search

The CLI accepts one JSON `--domain` per parameter. Without a domain, the run is an
explicit one-candidate baseline; `--count` does not duplicate that baseline.

```powershell
python cli.py run-generation `
  --source strategies\normalized\golden_cross.json `
  --data data\daily.parquet --method grid --count 6 --seed 7 `
  --domain '{"name":"indicators.sma_fast.period","values":[5,10,20]}' `
  --domain '{"name":"risk.position_size_pct","values":[50,100]}'
```

The equivalent Codex Desktop MCP `run_evaluation` input uses
`parameter_domains: [{"name": "...", "values": [...]}]`. Optional
`series_data_path` supplies external macro/rate/benchmark series. Supplying QQQ and
NASDAQ in that file adds same-period benchmark comparisons; macro/rate-only files are
valid and simply omit the benchmark comparison.

The reproducibility tuple is the Strategy IR, parameters, symbol/date range, dataset,
evaluator, cost model, compiler, Docker image digest, and seed. Changing any member
creates a new experiment hash.

반복 세대가 parameter domain을 받으면 매 세대 같은 탐색 공간을 새 seed로 다시
샘플링합니다. Research Director가 제안한 변경은 검증된 Strategy IR과 별도 승인
절차를 거쳐야 하며, 반복기가 원본 전략 파일을 직접 덮어쓰지는 않습니다.

An expression such as `US10Y.close@1w:rsi(period=14):lag=1` means that the completed
weekly US 10-year series is transformed locally and lagged one weekly bar. Indicator
registration requires all verification gates to pass; aliases are deduplicated by
semantic signature rather than by function name.
## 연도별 안정성 및 반복 실행

`run-generation`은 주문을 만들지 않고 승인된 전략 소스와 Parquet 데이터만으로
백테스트를 수행합니다. 기본값으로 모든 완료된 달력 연도의 왕복 거래수가 31회
이상이어야 통과합니다. 즉, 연간 거래수가 정확히 30회인 후보도 탈락합니다.

각 실행 원장에는 다음 연도별 지표가 함께 저장됩니다.

- `trade_count`: 해당 연도에 청산된 왕복 거래수(매도 체결수)
- `total_return`: 해당 연도 첫 평가자산 대비 마지막 평가자산의 수익률
- `max_drawdown`: 해당 연도 구간 최대 낙폭
- `complete`: 데이터가 해당 연도의 전체 기간을 포함하는지 여부

마지막 연도가 연중에 끝나는 데이터셋이면 `complete=false`로 표시하고 연간 최소
거래수 게이트에서 제외합니다. 이는 연초부터 현재까지의 부분 연도를 완전한 1년과
같이 판정하지 않기 위한 규칙입니다.

## 반복 실행

자동 반복은 반드시 세대 수를 지정합니다. 아래 예시는 20세대를 순차적으로
백테스트하며, 각 세대는 다른 seed를 사용하고 주문은 계속 비활성화됩니다.

```powershell
python cli.py repeat-research `
  --source strategies/qqq.yaml `
  --data data/qqq.parquet `
  --series-data data/benchmarks.parquet `
  --method random `
  --count 64 `
  --seed 0 `
  --min-trades 10 `
  --min-annual-trades 30 `
  --min-qqq-cagr 0.10 `
  --generations 20 `
  --interval-seconds 5 `
  --state-dir state
```

진행 상태는 `state/system/research_loop.json`, 개별 후보 결과는
`state/test-records.jsonl`에서 확인합니다. `state/system/research_loop.json`의
`completed_generations`와 `status`가 반복 실행의 현재 상태입니다.

## 단일 실행

```powershell
python cli.py run-generation `
  --source <strategy.yaml> `
  --data <data.parquet> `
  --min-trades 10 `
  --min-annual-trades 30
```
