# Quant Autoresearch Harness 통합 재설계서 v2

## 문서 상태

- 상태: 검토 대기
- 작성일: 2026-09-02
- 범위: Codex 전용 터미널, 반복 전략 연구, 인디케이터·외부 시계열 연결, 평가·기억·대시보드 연결
- 상위 기준: `docs/architecture/quant-autoresearch-architecture-v1.0.md`
- 관계: 기존 `2026-09-02-codex-terminal-autoresearch-design.md`를 터미널·Autoresearch 범위에서 대체한다.
- 보존 규칙: 승인된 v1.0 아키텍처는 수정하지 않는다. 이 문서는 v1.0을 운영 가능한 연결 설계로 구체화한다.

이 문서는 구현 완료 보고서가 아니다. 현재 구현된 부분과 앞으로 연결해야 할 부분을 분리해 기록하고, 승인 후 테스트 우선 순서로 구현한다.

## 1. 처음부터 확인한 설계의 출발점

### 1.1 원래 해결하려던 문제

기존 구조는 LLM이 전략을 생각하고 로컬 시스템이 전략을 실행·판정하는 연구 하니스를 목표로 했다. LLM이 후보마다 Python을 직접 고치면 다음 문제가 생긴다.

1. 전략의 원본과 실행 코드가 달라진다.
2. LLM이 평가기·비용·데이터 코드를 바꾸어 점수를 조작할 수 있다.
3. 같은 전략을 다시 실행하기 어렵고 후보 간 비교가 불공정해진다.
4. 미래 데이터 누수, 과최적화, 비현실적 거래비용을 발견하기 어렵다.

그래서 다음 역할 분리를 상위 원칙으로 확정했다.

```text
LLM = 연구 가설과 방향을 생각한다
LOCAL = 허용된 연산으로 Strategy IR을 변이한다
WORKER = 고정된 데이터·비용으로 실행한다
EVALUATOR = 독립적으로 판정한다
MEMORY = 후보·근거·실패를 기억한다
```

### 1.2 인터뷰로 추가된 요구와 그 원인

| 확정 내용 | 들어오게 된 원인 | 설계 반영 |
|---|---|---|
| 미국 주식·미국 ETF만 | 초기 범위가 넓으면 데이터·거래규칙·통화·캘린더가 섞임 | 연구 유니버스와 데이터 계약에서 미국 상장 종목만 허용 |
| 사용자가 지정한 종목 목록만 | 자동 종목 발굴은 연구 목적을 오염시키고 범위를 넓힘 | `universe`를 명시 목록으로 고정하고 자동 발굴은 별도 후속 기능으로 분리 |
| 일봉 중심, 다른 봉은 보조 사용 | 신호 기준은 명확히 하되 다중 시간봉 정보도 활용할 필요 | 기본 신호 봉 `1d`, 보조 `1m/5m/15m/1h/1w/1mo`를 as-of 정렬 |
| 일봉 종가 확정 후 다음 거래일 시가 주문 | 종가 시점에 알 수 없는 가격을 신호에 사용하면 룩어헤드 발생 | 신호 시각과 실행 시각을 별도 필드로 기록하고 다음 거래일 open 체결 모델 사용 |
| 사용자가 실전·모의 모드 선택 | 같은 전략 연구와 운용 모드를 분리해야 함 | 모드는 사용자 선택 가능하되 현재 연구 런타임은 Paper-only, 주문은 별도 게이트 |
| 위험 감수율·배분·필터도 전략이 관리 | 수익률만 바꾸는 전략 평가는 실제 전략을 반영하지 못함 | IR에 위험 행동을 포함하고 평가 입력·성과 근거로 함께 기록 |
| VIX·금·DXY·다른 종목·상관관계 선택 | 단일 종목 지표만으로 시장 국면을 설명하기 어려움 | 등록된 외부 시계열과 상관·스프레드·z-score를 선택 가능한 FeatureSpec으로 제공 |
| 미국·일본·한국의 2년·10년·20년물 | 금리 기간·국가별 국면을 전략이 선택적으로 활용할 필요 | `US2Y/10Y/20Y`, `JP2Y/10Y/20Y`, `KR2Y/10Y/20Y`를 optional 후보로 등록 |
| 금리·외부 데이터는 필수가 아님 | 모든 전략에 같은 지표를 강제하면 과적합과 불필요한 결측이 증가 | LLM은 후보 중 선택하며, IR에 실제 사용한 특성만 남김 |
| 기존 평가 항목 유지 | 새 지표나 수익성만으로 기존 위험·강건성 검사를 대체하면 품질이 후퇴 | 기존 Funnel과 모든 기존 지표를 보존하고 벤치마크·연도 지표를 추가 |
| 수익성 중요도 1순위 | 다른 지표가 좋아도 돈을 벌지 못하는 전략은 실용성이 낮음 | 점수 순서에서 절대 수익성을 최우선으로 두되 다른 gate는 유지 |
| 동일 기간 QQQ 대비 연환산 +10%p 목표 | 절대 수익만 보면 단순 보유보다 나은지 알 수 없음 | 같은 기간·같은 데이터로 QQQ CAGR과 전략 CAGR을 비교하고 delta를 기록 |
| 완료 연도별 거래수와 수익률, 연 30회 이하는 탈락 | 전체 기간 평균이 일부 연도의 거래 부재를 숨길 수 있음 | 완료된 각 연도에 `trade_count > 30`을 적용하고 연도 수익률을 기록 |
| 반복 연구 | 한 번의 백테스트는 우연일 수 있고 전략 개선 과정이 필요 | 세대·후보·부모·변이·평가·상태를 원장에 누적 |
| Codex Desktop의 LLM을 `codex exec`로 연결 | 별도 LLM HTTP 서버나 API 키를 만들지 않고 로컬 Codex 인증을 사용 | 구조화된 `ResearchIntent`만 반환하는 로컬 CLI provider |
| Karpathy autoresearch 기반 | 연구 방향과 실험 결과를 반복 비교하는 운영 모델이 필요 | generation 단위 제안, 로컬 대량 실험, 개선 시 보존, 실패 시 폐기 |
| 무한 반복 요구 | 반복 연구를 계속 돌리고 싶음 | 보안·자원·중지 가능성을 위해 실제 무한 옵션은 만들지 않고 큰 유한 세대 + resume으로 제공 |

### 1.3 외부 자료와 현재 코드에서 확인된 사실

- 승인 아키텍처의 핵심은 Strategy IR 단일 원천, 구조 탐색과 파라미터 탐색 분리, generation 단위 LLM 호출, Fast→Full→Robustness→Validation Funnel, Frontier/Rescue/Champion 상태, Development·Validation·Sealed OOS 분리다.
- `research/llm/director.py`의 `ResearchIntent`는 구조·파라미터·혼합 모드, 부모 후보, typed operations, rationale, 선택적 `FeatureProposal`을 표현한다. Python patch와 evaluator change는 검증 단계에서 거부된다.
- `research/llm/codex_exec.py`는 `codex exec --ephemeral --sandbox read-only --output-schema`로 구조화된 결과를 받고, 인증키·KIS 환경변수를 자식 프로세스에 전달하지 않도록 차단한다.
- `mutation/engine.py`는 `ADD_INDICATOR`, 규칙·위험·필터 변경 등 typed mutation을 Strategy IR에 적용하고 결과를 검증한다.
- `experiments/candidate_generator.py`는 로컬에서 파라미터 조합을 만들고 `SET_PARAMETER` 변이로 후보 hash를 만든다. LLM이 모든 후보를 직접 작성하지 않는다.
- `orchestration/pipeline.py`는 백테스트, 비용·위험, 벤치마크, 강건성, Walk-forward, 연도 요약, selector, knowledge 추출을 연결한다.
- `evaluation/yearly.py`는 달력 연도별 수익률·최대낙폭·완료 round-trip 거래수를 계산하고, 마지막 부분 연도는 `complete=false`로 표시한다.
- 현재 feature 계층에는 `FeatureSpec`, `FeatureProposal`, `FeatureVerification`, registry·lifecycle·provenance·catalog가 있다. catalog에는 가져온 기술지표와 VIX·금·DXY·QQQ·NASDAQ 및 미국·일본·한국 2/10/20년 금리 계열이 연결돼 있다.
- 네 개 외부 저장소(`marketcalls/pyindicators`, `srlcarlg/srl-python-indicators`, `chironmind/CentaurTechnicalIndicators-Python`, `kshlgrg/pythonpine`)는 provenance 대상으로 조사됐다. 의미적 중복을 제거하고, 라이선스가 맞지 않는 코드는 그대로 vendoring하지 않으며 독립 구현·검증 계약을 사용한다.
- 현재 `runtime/research_loop.py`는 로컬 평가를 세대별로 반복하지만, Director의 intent를 실제 mutation queue와 완전히 연결한 end-to-end 연구 루프는 아직 완성된 것으로 볼 수 없다. 이 문서의 핵심 구현 대상이다.

## 2. 설계 불변식

1. Strategy IR이 전략의 유일한 원본이다. 생성 Python/Lean은 실행 산출물이다.
2. LLM은 연구 의도·지표 선택·FeatureProposal만 제안한다. 계산기·평가기·비용·보호 모듈의 코드를 임의로 바꾸지 않는다.
3. 인디케이터 이름만 전달하지 않는다. 모든 사용 특성은 canonical ID, 입력 series, timeframe, lookback, parameter, lag, data contract, implementation hash를 가진다.
4. 모든 시계열은 기준 시각에서 이용 가능했던 값만 사용한다. 상위 시간봉은 완성된 bar와 명시적 lag를 적용한다.
5. 같은 데이터·기간·비용·거래규칙·벤치마크로 baseline과 candidate를 비교한다.
6. 기존 평가 항목은 삭제하지 않는다. 새 지표는 추가 근거와 필터로만 들어간다.
7. Sealed OOS, 평가기, 비용, KIS 주문 모듈은 연구 LLM과 연구 worker에서 격리한다.
8. 연구 런타임은 주문을 생성하지 않는다. 실전·모의 운용은 별도 명시적 gate다.
9. 모든 후보는 `REJECT`, `NEAR_MISS`, `SURVIVOR`, `FRONTIER` 등의 상태와 원인을 기록한다. 통과 구현 테스트만으로 전략 개선 성공이라고 판정하지 않는다.
10. 모든 반복은 유한 예산, timeout, queue 제한, 자원 제한, stop/resume 상태를 가진다.

## 3. 인디케이터와 외부 데이터의 표준 계약

### 3.1 선택 가능한 데이터 층

```text
종목 OHLCV       ─┐
벤치마크 QQQ/NASDAQ ├─> SeriesRef ─> FeatureSpec ─> Strategy IR
VIX·금·DXY        ┤
미·일·한 금리 2/10/20 ┘
```

각 입력은 종목명이나 문자열 설명이 아니라 `SeriesRef`로 식별한다.

```yaml
series_id: US10Y
field: close
source: versioned-market-data
timezone: America/New_York
frequency: 1d
```

허용된 timeframe은 현재 계약인 `1m`, `5m`, `15m`, `1h`, `1d`, `1w`, `1mo`를 사용한다. 기본 전략 기준봉은 `1d`이며, 예를 들어 `US10Y`의 주봉 RSI는 다음처럼 표현되는 특성이다.

```yaml
feature_id: rates.us10y.rsi
inputs: [US10Y.close]
timeframe: 1w
lookback: 14
lag_bars: 1
calculator: rsi
parameters: {period: 14}
```

따라서 `2년물 RSI`, `10년물 주봉 RSI`, `20년물 변화율`, 다른 종목의 상대강도·상관관계도 같은 계약으로 표현한다. 특정 금리나 봉을 전 전략에 강제하지 않는다.

### 3.2 인디케이터 생명주기

1. **Catalog/Registry 조회**: LLM에는 등록된 `canonical_id`, alias, family, 입력, 지원 timeframe, lookback 범위, provenance, license, data contract만 제공한다.
2. **선택**: LLM은 registry ID와 파라미터·시간봉·lag를 조합해 `ResearchIntent.operations` 또는 Strategy IR feature reference를 제안한다. 임의 Python 식이나 외부 URL을 실행하지 않는다.
3. **미등록 특성 제안**: 필요한 특성이 없으면 `FeatureProposal`로 별도 제출한다. 이 제안은 해당 세대의 전략 실험에 즉시 사용할 수 없다.
4. **검증**: schema, 단위, historical fixture, no-future-leak, alignment, missing-data, reproducibility, resource-bounded, safety 테스트를 모두 통과해야 한다.
5. **중복 판정**: semantic identity와 `duplicate_group`으로 기존 특성과 비교한다. 같은 의미·입력·시간봉·파라미터를 다른 이름으로 재등록하지 않는다.
6. **등록**: 검증된 implementation hash와 provenance를 붙여 `REGISTERED` 상태로 registry에 추가한다. 실패하면 `QUARANTINED`로 남긴다.
7. **실험 허용**: 등록된 특성만 candidate IR에 들어간다. 등록은 전략 통과가 아니며, 후보는 전체 Funnel을 다시 통과해야 한다.
8. **퇴역**: 계산 불일치·데이터 계약 변경·재현성 실패가 발견되면 registry에서 새 후보 사용을 막고 기존 원장과 lineage는 보존한다.

### 3.3 출처·중복·라이선스

가져온 구현은 원 저장소 이름으로 실행하지 않는다. 계산기별로 독립 구현, 테스트 fixture, implementation hash, source repository, source license, duplicate group을 기록한다. AGPL 등 프로젝트 배포 조건을 바꾸는 라이선스는 코드 복사 없이 수식·행동을 검토한 독립 구현만 허용하며, 법적 판단이 필요한 경우 등록을 보류한다.

## 4. 제안→실험→평가→기억의 전체 연결

```text
Terminal command
  ↓
CodexExecProvider (read-only, structured JSON)
  ↓
ResearchIntent
  ├─ registered feature selection
  ├─ FeatureProposal → verify/register gate (미등록이면 실험 보류)
  └─ typed structural/parameter operations
  ↓
IntentValidator + Local Research Planner
  ↓
Strategy IR candidate(s)
  ├─ feature resolver: catalog/registry/provenance
  ├─ as-of timeframe alignment + leakage check
  └─ deterministic candidate hash
  ↓
Fast → Full → Cost/Risk → Robustness → Walk-forward/Validation
  ├─ absolute profitability (1순위)
  ├─ same-period QQQ/NASDAQ comparison
  ├─ complete-year trade count/return
  └─ existing statistics and gates
  ↓
EvaluationReport → TestRecord → Frontier/Rescue/Knowledge
  ↓
compact feedback context → next generation ResearchIntent
```

### 4.1 제안 단계

Director에 전달하는 context는 현재 baseline·Frontier·실패 원인·사용 가능한 feature catalog의 요약이다. 원시 시세, 전체 거래 로그, Sealed OOS, 키·계좌 정보는 전달하지 않는다.

Director의 한 번의 응답은 다음을 포함한다.

- `mode`: structure, parameter, mixed
- `parent_ids`: 탐색할 Frontier/Rescue 부모
- `operations`: typed mutation 목록
- `feature_selection`: registry canonical ID, series, timeframe, parameters, lag
- `feature_proposal`: 미등록 특성의 설명만 포함할 수 있음
- `rationale`: 가설과 예상 국면

`python_patch`, `evaluator_change`, 주문 명령, 임의 파일 경로, 임의 계산 코드는 거부한다.

### 4.2 실험 단계

Local Planner가 intent를 해석해 다음을 수행한다.

1. 부모 IR를 로드하고 parent hash를 확인한다.
2. operation schema, parameter 범위, feature registry 상태를 검사한다.
3. 구조 변이와 파라미터 탐색을 분리한다.
4. 가능한 parameter grid/random/Bayesian point를 로컬에서 생성한다.
5. 각 candidate에 feature set, 부모, 변이, 데이터 버전, 비용 정책을 고정한다.
6. Feature Resolver가 입력 series를 as-of 방식으로 결합하고 결측·시간대·봉 완성 여부를 검사한다.
7. deterministic candidate hash를 계산하고 중복 실험을 cache에서 건너뛴다.

인디케이터 값 자체를 LLM이 계산하거나 후보별 코드를 만들지 않는다. LLM은 “US10Y 주봉 RSI 14와 QQQ 일봉 RSI 14의 관계를 탐색”처럼 선택과 가설을 만들고, 실제 값 계산은 로컬 calculator가 수행한다.

### 4.3 평가 단계

각 후보에 대해 동일한 baseline과 다음 결과를 함께 기록한다.

- 절대 수익률, CAGR, 수익성 점수, 연도별 수익률
- QQQ 동일 기간 CAGR·총수익률·전략과의 delta
- NASDAQ 동일 기간 CAGR·총수익률·전략과의 delta
- 승률, 손익비, Sharpe/Sortino, 최대낙폭, 회복기간, 변동성
- 비용·슬리피지 stress 결과
- Walk-forward·validation·regime breakdown·parameter perturbation
- 거래수·완료 연도별 거래수·연도별 최대낙폭
- 사용 feature canonical ID, 입력 series, timeframe, lag, parameters, implementation hash, dataset hash
- feature 제거/교체 비교가 가능할 때의 기여도와 실패 원인

평가기는 다음 순서로 판정한다.

1. 구조적 유효성·데이터 누수·실행 가능성
2. 기존 Fast/Full/Robustness/Validation/Risk gate
3. 완료 연도별 거래수: 하나라도 `trade_count <= 30`이면 탈락
4. 절대 수익성: 순위 계산에서 1순위
5. 동일 기간 QQQ 대비 연환산 delta: 목표는 `strategy_cagr - qqq_cagr >= 0.10`
6. NASDAQ 비교와 기타 기존 지표
7. 복잡도·재현성·안정성·비용 민감도

수익성 1순위는 순위 기준이다. QQQ 목표, 연도 거래수, 위험·강건성 gate를 생략한다는 뜻이 아니다. QQQ/NASDAQ 비교는 기존 평가 항목을 대체하지 않고 추가한다.

### 4.4 기억과 다음 제안

한 세대의 전체 결과를 LLM에 다시 넣지 않는다. `EvaluationReport`에서 다음만 압축한다.

- candidate/parent/feature IDs와 hash
- 통과·실패한 gate와 구체적 이유
- 절대 수익성과 QQQ/NASDAQ delta
- 연도별 거래수·수익률 요약
- 어떤 feature 조합이 어느 국면에서 개선·악화했는지에 대한 집계
- 다음 탐색에서 시도할 수 있는 parameter 범위와 금지할 조합

이 요약은 `TestRecord`, Knowledge, Frontier/Rescue에 각각 목적에 맞게 저장하고 다음 generation context의 입력으로 사용한다. 통과 후보를 자동 Champion으로 올리지 않으며 별도 승격 절차를 둔다.

## 5. 세대 실행 정책

한 세대는 “LLM 1~2회 제안 + 로컬 다수 후보 실험”으로 구성한다.

1. baseline·Frontier·Rescue를 읽는다.
2. 탐색 예산과 feature catalog snapshot을 고정한다.
3. Director가 구조·파라미터·혼합 방향을 제안한다.
4. 미등록 FeatureProposal이 있으면 검증 queue로 보내고 해당 feature를 사용하는 후보는 보류한다.
5. Local Planner가 등록된 feature만으로 후보를 만든다.
6. Fast screen으로 명백한 실패 후보를 제거한다.
7. 남은 후보에 Full, 비용·위험, 강건성, Walk-forward를 적용한다.
8. 연도별 거래수·수익률과 QQQ/NASDAQ 비교를 포함해 selector가 판정한다.
9. 결과를 원장에 추가하고 개선 후보만 Frontier에 반영한다.
10. 다음 세대에 전달할 압축 context를 만든다.

탐색 정책은 Explore, Exploit, Crossover, Rescue를 유지한다. 한 부모의 작은 개선만 계속 따라가는 greedy hill climbing을 막기 위해 Frontier를 전략 family별로 유지한다.

## 6. Codex 전용 터미널 설계

### 6.1 모드

- `chat`: 일반 질의응답. 저장소 변경 권한이 없는 `codex exec`로 실행한다.
- `autoresearch`: 위 세대 정책을 수행하며 IR과 registry를 통해서만 후보를 만든다.
- `direct-edit`: 사용자가 명시적으로 선택한 경우에만 disposable worktree에서 제한적으로 연다. 기본값은 차단이다.

IR 연구 호출은 다음 성격을 유지한다.

```text
codex exec - --ephemeral --sandbox read-only --output-schema <schema> -o <intent.json>
```

자식 환경에는 OpenAI/Codex/Quant LLM 키와 모든 KIS 환경변수를 전달하지 않는다. Codex CLI의 자체 인증을 사용하며, 터미널이 API 키를 직접 보관하거나 프롬프트에 넣지 않는다.

### 6.2 명령과 재개

```text
python cli.py terminal
/mode chat
/mode autoresearch
/research 20
/backtest
/status
/stop
/help
/exit
```

`/research 20`처럼 양의 유한 세대 수를 받는다. 실제 무한 loop 플래그는 제공하지 않는다. 중지 후에는 마지막 완료 generation, queue, seed, snapshot, 미완료 후보를 상태 파일에서 읽어 재개한다.

직접 수정은 다음 이중 gate가 모두 있어야 한다.

```text
--mode direct-edit --confirm-direct-edit --worktree <disposable-worktree>
```

현재 checkout·`main`·보호 경로·평가기·비용·데이터·KIS 주문 모듈은 수정할 수 없다. diff, 심볼릭 링크, 민감 파일, IR 정규화·백테스트 결과를 검사한 뒤 개선되지 않은 worktree는 폐기한다.

## 7. 상태·기록·대시보드 계약

- `state/system/terminal.json`: 터미널 모드, 실행 ID, 중지·실패 상태
- `state/system/autoresearch.json`: generation, intent, feature snapshot, candidate queue, 완료 수
- `state/test-records.jsonl`: 후보별 전체 평가, gate, feature lineage, 연도별 지표
- `state/llm/status.json`: 마지막 `codex exec` 상태·모델·소요시간·민감정보 제거 오류
- `state/llm/terminal-sessions.jsonl`: 질의·응답의 비밀정보 제거 기록
- 기존 `state/champion.json`, `state/frontier.json`, `state/rescue_pool.json`, `state/knowledge.json`: 상태 승격과 연구 기억

대시보드에는 한국어로 다음을 노출한다.

- 현재 모드와 Paper-only/주문 차단 상태
- 실행 중 generation·후보 수·마지막 성공·실패 이유
- 현재 Champion/Frontier와 baseline QQQ 비교
- 전략별 사용 인디케이터·입력 종목·시간봉·lag·파라미터
- 연도별 거래수·수익률, QQQ/NASDAQ delta, 기존 위험 지표
- feature 등록·검증·격리 상태와 provenance
- 병렬 worker의 online/busy/offline 및 마지막 heartbeat

키·APP Secret·계좌번호·토큰·원시 시세·Sealed OOS 값·전체 거래 로그는 화면·LLM context·Git 기록에 노출하지 않는다.

## 8. 현재 구현과 남은 연결 작업

현재 이미 존재하는 기반:

- Strategy IR, typed mutation, candidate generator, Funnel evaluator, yearly summary, QQQ/NASDAQ benchmark
- imported indicator catalog, semantic deduplication, provenance, timeframe/as-of calculator, FeatureProposal lifecycle
- Codex exec structured provider와 Paper-only 운영 경계
- 반복 evaluation 상태와 대시보드용 연도·catalog 데이터

아직 구현 완료로 간주하지 않는 핵심 gap:

1. `ResearchIntent.feature_proposal`의 검증·등록 결과를 generation controller가 받아 해당 세대의 candidate 사용 가능 여부로 연결해야 한다.
2. Director가 반환한 typed operations를 실제 Local Planner→Mutation Engine→candidate queue로 연결해야 한다. 현재 반복 runner가 자동으로 intent를 적용한다고 주장할 수 없다.
3. candidate/evaluation 기록에 feature lineage, timeframe, lag, data snapshot, implementation hash를 끝까지 전달해야 한다.
4. LLM context에 평가 결과를 안전하게 압축해 다음 generation intent로 되돌리는 bridge가 필요하다.
5. 직접 수정 모드의 disposable worktree·diff·보호 경로 검사를 end-to-end로 구현하고 테스트해야 한다.
6. ~~“일봉 종가 확정 후 다음 거래일 시가” 체결 규칙은 실제 backtest executor 경로를 다시 검증하고, 불일치하면 수정해야 한다.~~ **완료(2026-09-03):** ordinary/risk exit next-bar-open 및 future-bar mutation 회귀 테스트가 통과했다.
7. 기존 자동 연구 반복이 “전략 개선 성공”으로 오인되지 않도록 baseline 대비 동일 데이터 비교와 Champion/Frontier 승격 증거를 함께 저장해야 한다.

## 9. 구현 순서와 검증 기준

모든 단계는 테스트를 먼저 추가하고 구현한다.

### 단계 0 — 기준선 고정

- 승인 아키텍처 hash와 현재 branch/worktree 상태를 기록한다.
- 기존 테스트·ruff·mypy를 실행해 기준선과 기존 실패를 분리한다.
- 보호 경로와 민감정보 탐지 테스트를 먼저 확인한다.

### 단계 1 — 공통 연구 계약

- `ResearchIntent`에 feature selection·catalog snapshot·가설 목적을 명시적으로 연결한다.
- intent→validated plan→candidate queue 상태 계약과 schema 테스트를 추가한다.
- 잘못된 alias, 미등록 feature, 중복 semantic identity, 금지 code field를 거부한다.

### 단계 2 — Feature lifecycle 연결

- proposal→verification→registration→candidate eligibility를 controller에 연결한다.
- 네 외부 저장소 provenance·license·duplicate group을 catalog와 원장에 연결한다.
- 1d/1w/1mo 및 2/10/20년 금리의 as-of·lag·결측·미래누수 테스트를 추가한다.

### 단계 3 — 제안과 실험 연결

- Director intent를 Local Planner와 Mutation Engine에 전달한다.
- 구조 탐색·파라미터 탐색·Crossover/Rescue 예산을 generation 정책에 연결한다.
- 후보 hash·부모·feature lineage·data snapshot을 기록하고 중복 실행을 건너뛴다.

### 단계 4 — 평가와 피드백 연결

- 모든 후보에 절대 수익성 1순위, QQQ/NASDAQ 동일 기간 비교, 완료 연도 `>30` 거래수 gate, 연도 수익률을 연결한다.
- 기존 위험·강건성·Walk-forward·Funnel gate가 그대로 유지되는 회귀 테스트를 만든다.
- feature 제거/교체 비교와 실패 원인을 압축해 Knowledge→다음 intent context로 연결한다.

### 단계 5 — 터미널과 상태 복구

- chat/autoresearch/backtest/status/stop REPL과 배치 명령을 구현한다.
- 유한 세대·timeout·queue·worker resource limit·stop/resume를 검증한다.
- Codex exec 자식 환경의 키 제거와 output schema 검증을 회귀 테스트한다.

### 단계 6 — 대시보드와 병렬 worker

- 한국어 사용자 화면에 mode, paper gate, generation, feature lineage, 연도 지표, QQQ delta, worker heartbeat를 연결한다.
- 상태 파일은 원자 저장·추가 기록·재시작 복구를 검증한다.

### 단계 7 — 직접 수정 gate와 통합 테스트

- disposable worktree에서만 동작하는 직접 수정 경로를 구현한다.
- 보호 경로·민감 파일·심볼릭 링크 탈출·평가기 변경을 모두 차단한다.
- mock Codex provider, 실제 local backtest, Docker worker, 대시보드 상태, Paper-only 주문 차단을 포함한 통합 테스트를 실행한다.

최종 완료 조건은 “구현 테스트 통과”가 아니다. 같은 데이터의 baseline/candidate 비교, QQQ/NASDAQ 비교, 모든 완료 연도의 거래수·수익률, 비용·강건성·Walk-forward 증거, feature lineage와 재현 가능한 기록이 있어야 Frontier 또는 Champion 후보로 인정한다.

## 10. 승인 후 작업 방식

이 문서를 승인하면 다음 작업에서 단계 0부터 시작한다. 구현 중 기존 문서와 코드의 불일치가 발견되면 임의로 가정하지 않고 `현재 사실 / 설계 목표 / 필요한 변경 / 검증 결과`로 기록한다. 실전·모의 주문 실행은 이 연구 설계의 승인만으로 열지 않으며, 별도 운용 승인과 안전 검증이 필요하다.
