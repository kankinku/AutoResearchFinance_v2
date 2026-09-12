# Quant Autoresearch Harness 시스템 전수 설명서

> 조사 기준: 2026-09-12, 저장소 `master` 워크트리의 추적 코드·설정·테스트를 읽어 작성했다.
> 이 문서는 운영 설명용 현재 스냅샷이며, 승인 설계 원본인
> [`quant-autoresearch-architecture-v1.0.md`](quant-autoresearch-architecture-v1.0.md)를
> 대체하지 않는다. 설계 원본은 수정하지 않았다.

## 1. 한 문장 정의

이 시스템은 **Strategy IR을 유일한 전략 원본으로 삼아**, LLM은 제한된 연구 의도만
제출하고, 로컬 코드가 검증·변이·백테스트·평가·상태 저장을 담당하는 **Paper-only
정량 전략 연구 하네스**다. 연구와 KIS 주문은 분리되어 있으며, 연구 루프·대시보드·MCP는
주문 권한을 갖지 않는다.

```text
LLM/Codex ──(typed ResearchIntent)──> 로컬 사전검증
                                         │
Strategy IR ─> 후보 생성/변이 ─> 백테스트 ─> 평가 게이트 ─> Frontier/Champion/Knowledge
                                         │                         │
                              읽기 전용 데이터·Docker 격리          └─> 대시보드/상태 조회
```

핵심 원칙은 다음과 같다.

- **전략 원본**: YAML 또는 외부 전략은 먼저 `strategy_ir`의 정규화·검증을 거친다. 생성된
  Python/Lean은 실행 산출물이지 원본이 아니다.
- **권한 분리**: LLM은 DB나 상태를 직접 변경하지 않는다. `ResearchIntent`를 로컬에서
  type/path/reference 단위로 검증한 뒤에만 IR 복제본에 적용한다.
- **평가 독립성**: 후보를 만드는 연구 계층과 점수·선정 계층을 분리한다. 따라서 “제안됨”이나
  “테스트가 통과함”은 전략 성과·Champion 승격을 뜻하지 않는다.
- **Paper-only 기본값**: 정책의 `live_order_permission`은 `deny`이고, `PaperKISConfig`는
  paper/demo 이외 모드를 거부한다.

주요 근거: [`README.md`](../../README.md),
[`research/policy.yaml`](../../research/policy.yaml),
[`strategy_ir/schema.py`](../../strategy_ir/schema.py),
[`research/llm/intent_bridge.py`](../../research/llm/intent_bridge.py).

## 2. 현재 확인된 상태와 해석 범위

| 항목 | 현재 확인 결과 | 해석 |
|---|---:|---|
| 단위/통합 회귀 | `546 passed` | 구현 계약의 현재 회귀 검증 결과 |
| 린트 | `ruff check .` 통과 | 현재 검사 대상의 정적 스타일 검사 결과 |
| 타입 검사 | `131 source files`, 오류 0 | mypy 설정 대상의 정적 타입 검사 결과 |
| 저장 상태 | `Champion=EMPTY`, `frontier_families=0` | 이 워크트리 상태에는 현재 승격된 전략/Frontier가 없음 |
| 주문 기본값 | policy `deny`, 연구 상태 `orders_enabled=false` | 연구가 주문 권한을 보유하지 않음 |

따라서 이 조사로 확인된 것은 **시스템 연결·경계·회귀 테스트**다. 실제 시장 데이터의
수익성, QQQ 초과수익, Walk-forward/OOS 통과, KIS 접속성, 모의 주문 체결 또는 운영 중인
100세대 연구 완료는 이 문서가 증명하지 않는다. 그런 주장은 같은 데이터·비용·OOS 조건에서
생성된 실행 원장과 Champion/Frontier 상태로 별도 입증해야 한다.

또한 조사 시점에 `dashboard/state.py` 및 일부 `state/` 파일은 이미 변경된 워크트리
상태였다. 본 문서는 이 사용자 소유 변경을 수정하거나 초기화하지 않았다.

## 3. 소스 트리와 책임 지도

| 영역 | 주 책임 | 대표 진입점/파일 |
|---|---|---|
| `strategy_ir/` | 전략 스키마, 파싱, 정규화, 검증, 컴파일 | `schema.py`, `validator.py`, `normalizer.py` |
| `mutation/` | 구조 변이와 파라미터 탐색 | `engine.py`, `parameter.py` |
| `experiments/` | 후보 계획, 중복 제거, 캐시, 결과/매니페스트 | `planner.py`, `candidate_generator.py`, `result_store.py` |
| `core/data/` | 버전·구역 메타데이터가 있는 Parquet 계약 | `contracts.py`, `parquet.py`, `access.py` |
| `core/features/` | FeatureSpec 카탈로그, 계산, 시간 정렬, provenance | `catalog.py`, `calculators.py`, `alignment.py` |
| `core/backtest/`, `core/costs/` | 신호 실행, 거래 결과, 비용·슬리피지 | `engine.py`, `model.py` |
| `evaluation/`, `core/validation/` | 지표, 벤치마크, 위험, 강건성, 선택, split 검증 | `selector.py`, `benchmark.py`, `robustness.py` |
| `orchestration/` | 한 세대의 순서와 로컬 평가 조립 | `pipeline.py`, `evaluation_runner.py` |
| `memory/` | Champion, Frontier, Knowledge, rescue pool 상태 | `promotion.py`, `frontier.py`, `knowledge.py` |
| `research/llm/` | Codex 호출, 의도 계약, 정책상 LLM 경계 | `director.py`, `intent_bridge.py`, `codex_exec.py` |
| `runtime/` | 유한 자동연구, Mimir/REPL, Docker worker, supervisor | `research_loop.py`, `mimir.py`, `terminal.py` |
| `integrations/` | 제한형 Codex MCP와 paper KIS 어댑터 | `codex_mcp_server.py`, `kis/` |
| `dashboard/` | FastAPI 상태 조회·운영 화면 API | `app.py`, `service.py`, `state.py` |

`core/data`, `core/backtest`, `core/evaluator`, `core/validation`, `core/costs`,
`core/integrity`은 AGENTS 계약상 Research Director나 생성 산출물이 변경하면 안 되는
보호 경로다. 이 경계는 시스템의 “LLM이 평가 규칙을 자기에게 유리하게 고치지 못하게
한다”는 안전 장치다.

## 4. 데이터와 전략의 신뢰 경계

### 4.1 Strategy IR의 역할

모든 정상 연구 경로는 Strategy IR에서 시작한다. 외부 전략 가져오기는 AST/정적 분석만
사용하며, 외부 Python을 실행하지 않는다. 표현 불가능하거나 동적인 코드는
`REVIEW_REQUIRED`로 남기고, 등록·중복 분류 후에만 카탈로그에 표시한다.

IR 검증은 다음을 막는 관문이다.

- 지원하지 않는 지표/primitive, 잘못된 parameter type·범위
- 존재하지 않는 condition/feature alias 참조
- LLM의 임의 JSON Patch 또는 비정규 path
- 순서가 잘못되어 새 참조를 만들기 전에 그 참조를 사용하는 변경

LLM 의도는 `ADD_RULE`, `ADD_REGIME_FILTER` 같은 제한된 typed operation으로 변환된다.
`apply_intent()`는 부모 IR 복제본에 dry-run 적용하고 최종 IR을 재검증한다. 즉 LLM은
제안을 하지만, 전략을 저장하거나 평가 결과를 직접 바꾸지 못한다.

### 4.2 데이터 구역

`DataZone`은 `development`, `validation`, `sealed_oos` 세 구역이다.

| 구역 | 정책 권한 | 목적 |
|---|---|---|
| development | 연구 읽기/쓰기 | 후보 탐색과 개발 |
| validation | promotion only | 승격 전 검증 |
| sealed_oos | promotion gate only | 누수 방지가 필요한 최종 OOS 판단 |

Parquet 입력은 `dataset_version`과 `data_zone` 메타데이터를 반드시 가져야 한다.
`GenerationPipeline.run()`은 sealed OOS 데이터를 일반 generation research에 쓰는 것을
거부한다. 외부 시계열도 동일 Parquet 계약을 따르며, `available_at` 기반 as-of 정렬로
미래 공개값을 차단한다.

## 5. 한 세대의 평가 흐름

`orchestration.pipeline.GenerationPipeline`은 IR과 데이터셋을 받아 다음 단계를 조립한다.

1. 후보를 만들고 중복을 제거한다. 탐색 방법은 grid, random, bayesian이며, policy 기본
   candidate target은 256이다.
2. feature 입력과 lineage를 구성하고, Fast screen을 먼저 수행한다.
3. 통과 후보만 Full backtest로 보내 거래·비용·지표를 계산한다.
4. robustness, validation, walk-forward/CSCV/CPCV 등 검증 레이어의 결과를 모은다.
5. QQQ/나스닥 벤치마크가 제공되면 같은 기간 비교와 초과수익 지표를 추가한다.
6. selector가 통과·탈락 사유와 Pareto/가족 정보를 바탕으로 Frontier·Champion 후보를
   결정하고, memory 계층이 상태 파일에 저장한다.

기본 정책은 최소 거래수 30, 연도별 최소 거래수 30, QQQ CAGR 차이 최소 `0.10`이며,
Fast screen·Full backtest·robustness·validation을 모두 켜 둔다. 이는 **기본 게이트**일
뿐이고, 실제 성과의 증거는 아니다.

## 6. 자동연구와 실패 복구

`runtime.research_loop`은 유한 세대만 실행한다. 매 세대는 다음 상태를 남긴다.

```text
proposal_started
  -> preflight_completed
  -> (필요 시 repair_started)
  -> evaluation_started
  -> 평가/선택 결과
```

잘못된 Codex payload는 canonical typed operation 계약에서 막힌다. 오류가 재시도 가능하면
구조화된 진단으로 읽기 전용 Codex 복구를 제한 횟수만큼 요청한다. 같은 잘못된 payload가
반복되면 repair knowledge에 서명을 기록하고, 부모 전략으로 `FALLBACK` 평가를 수행한다.
복구 및 fallback이 있어도 `orders_enabled`는 false다.

완료 상태는 처리 완료 의미와 전략 품질 의미를 구별한다.

| 상태 예 | 의미 |
|---|---|
| `REPAIRED` | 수정된 제안으로 해당 세대를 평가함 |
| `FALLBACK` | 제안/후보 문제로 부모 전략 평가로 전환함 |
| `DEGRADED` | 후보와 fallback 모두 실패했지만 루프가 다음 세대로 진행함 |
| `COMPLETED_WITH_FALLBACKS` | 모든 세대를 처리했지만 전략 개선 성공을 뜻하지 않음 |

현재 루프는 repair knowledge와 연구 이벤트를 상태 파일에 남긴다. 결정 시점의 입력·hash·위험
상태·근거·재현 결과를 별도 append-only failure ledger로 확대 보관하는 방식은 기존 설계/계획에
기록돼 있으나, 이 조사에서는 해당 확장 기능의 현재 end-to-end 동작을 별도 실행 검증하지 않았다.
그 기능을 운영화할 때도 credential, 원시 시장 행, sealed-OOS payload는 기록 대상에서 제외해야 한다.

## 7. 사용자 진입점

### CLI

`cli.py`는 상태 초기화/조회, 모드, 전략 import/검증, feature 목록, 세대 계획·실행,
반복 연구, Codex 자동연구, dashboard, terminal, paper promotion과 audit을 제공한다.
실무에서 자주 쓰는 경로는 다음과 같다.

```powershell
python cli.py init --state-dir state                 # 새 상태 디렉터리에서만 1회
python cli.py set-mode --state-dir state --mode paper
python cli.py run-generation --source <IR> --data <Parquet> --method grid --count 8
python cli.py autoresearch --source <IR> --data <Parquet> --generations 20
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

`init`은 기존 실험 이력을 가진 `state/`에 다시 실행하면 안 된다. `set-mode live`라는
상태 표기는 존재하지만, policy 및 research process 권한은 live order를 허용하지 않는다.

### Mimir / REPL

editable install 뒤 `Mimir /research 20` 또는 `python -m runtime.mimir /research 20`을
쓸 수 있다. `MIMIR_SOURCE`, `MIMIR_DATA`, `MIMIR_SERIES_DATA` 또는 마지막 research-loop
설정으로 입력을 찾고, 없으면 fail closed 한다. 기존 `quant>` REPL도 `/research 20`과
`Mimir /research 20`을 같은 파서로 처리한다. 즉시 중지는 현재 PowerShell의 `Ctrl+C`가
맞으며, `/stop`은 동기 작업을 강제 종료하지 않는 중지 요청 표기다.

### Codex MCP

MCP 공개 도구는 `get_research_context`, `list_features`, `get_dashboard_status`,
`submit_research_intent`, `run_evaluation` 및 시스템 lifecycle
(`check_system`, `start_system`, `get_system_status`, `stop_system`)이다. order, live account,
credential, arbitrary write, raw-market, sealed-OOS 도구는 공개하지 않는다.

## 8. 대시보드·운영 상태

현재 실행 UI는 `cli.py dashboard`가 시작하는 FastAPI 대시보드이며, 루트
`dashboard.py`의 Streamlit 화면은 보존/테스트 목적이다. FastAPI 서비스는 mode,
Champion, Frontier, Knowledge, rescue pool, 평가 ledger, feature catalog, LLM 상태 및
worker heartbeat를 읽어 API와 정적 화면에 제공한다. 상태 우선순위는 안전/전역 문맥 →
주의 필요 항목 → 다음 행동 → Champion/Frontier → 원시 상세다.

대시보드 refresh는 paper KIS의 읽기 전용 계좌·시세 정보를 갱신할 수 있으나 주문을
실행하지 않는다. dashboard supervisor는 프로세스 종료 시 재시작하고 로그를
`state/system/dashboard-supervisor.log`에 남기는 보조 운영 도구다.

## 9. KIS와 주문의 정확한 경계

이 저장소에는 다음 두 가지가 분리되어 있다.

1. `KISAPIClient`: paper 환경의 읽기 전용 계좌·시세 확인.
2. `KISPaperOrderClient`: 명시적 `paper-order-smoke --confirm-paper-order`에서만 쓰는
   별도 모의 주문 경로.

후자는 KIS virtual endpoint와 paper/demo mode를 확인하고 1주 매수 → 체결 확인 → 체결된
수량만 매도한다. 미체결·잔고 조회 실패·장외 오류 시 추가 매도를 내지 않는다. 이 명령은
연구·대시보드·MCP와 독립돼 있다. live KIS endpoint는 `PaperKISConfig` 및 order client가
거부한다.

따라서 `promote-paper`는 hash와 검증·만료 조건을 확인하는 상태 경로이지, live 주문 권한을
부여하는 기능이 아니다. 실거래는 별도의 human approval, 계정, data provider, calendar,
이미지 digest 등 추가 승인/인프라를 요구하며 이 연구 패키지 범위 밖이다.

## 10. 격리·보안·복구

- Docker runner는 입력을 읽기 전용으로 mount하고 네트워크를 끄며 capability를 drop하고
  run output directory만 기록 대상으로 둔다.
- Codex child process에는 KIS 비밀값을 주지 않고, intent/context는 sanitize한다.
- secret scan은 추적 워크트리 바이트와 Git index blob을 점검한다. `.env`, raw data,
  runtime state와 credential은 Git에 저장하지 않는 것이 계약이다.
- `resume`, `rebuild-cache`, `audit`와 운영 문서의 recovery 절차가 중단/캐시 문제의
  복구 진입점이다. 복구도 평가 원장이나 OOS 경계를 우회해서는 안 된다.

상세 운영 절차는 [`../operations/recovery.md`](../operations/recovery.md),
[`../operations/verification.md`](../operations/verification.md),
[`../security/quant-autoresearch-threat-model.md`](../security/quant-autoresearch-threat-model.md)를
따른다.

## 11. 테스트가 보장하는 것과 보장하지 않는 것

현재 102개 테스트 모듈은 다음 영역을 나누어 검사한다.

| 범주 | 대표 검증 |
|---|---|
| IR/변이/import | 스키마, parser, normalizer, primitive, AST analyzer, fingerprint |
| core | 데이터 구역, Parquet, feature, 비용, backtest signal, validation split |
| evaluation/orchestration | 지표·위험·benchmark·selector·pipeline·evaluation runner |
| runtime/research | autoresearch, Mimir, terminal, Docker, scheduler, supervisor |
| integration/security | Codex MCP, KIS isolation/paper order, protected boundary, secret scan |
| dashboard/CLI | API, 정적 자산, 상태·ledger, strategy catalog, CLI command contract |

이 범위는 인터페이스·안전 경계·결정론적 계산의 회귀 방어에 강하다. 반대로 아래 항목은
별도 실증이 필요하다.

- 특정 전략이 향후에도 수익을 낸다는 주장
- 실제 데이터 품질, 슬리피지/비용 가정, 시장 국면 일반화
- API credential의 현재 유효성, KIS paper endpoint의 실시간 체결
- Docker image, dashboard process, Codex CLI가 현 장비에서 항상 기동된다는 주장
- sealed OOS와 walk-forward를 통과한 Champion 승격

## 12. 운영자가 지켜야 할 최소 규칙

1. 전략은 반드시 Strategy IR과 `validate-strategy`/import 경로로 들인다.
2. 연구 입력에는 version·zone metadata가 있는 Parquet만 쓰고 sealed OOS를 탐색에 쓰지 않는다.
3. LLM 출력은 `ResearchIntent`로만 수용하고, DB/상태 직접 수정 권한을 주지 않는다.
4. Champion을 선언하기 전 같은 데이터 기간의 benchmark, 거래수, 비용, robustness,
   walk-forward/OOS와 저장된 Frontier/Champion 근거를 함께 확인한다.
5. KIS credential은 `.env`에만 두고 prompt·로그·Git에 넣지 않는다.
6. 자동연구의 `COMPLETED` 계열 상태는 처리 완료일 수 있으므로, 성과 승격으로 해석하지 않는다.
7. 모의 주문 확인이 필요할 때도 `paper-order-smoke --confirm-paper-order`를 별도 작업으로
   실행하고, 연구 루프를 주문 경로로 확장하지 않는다.

## 13. 조사 근거와 후속 점검

이번 조사는 `README.md`, architecture v1.0, policy, CLI/Mimir/MCP, pipeline, data/KIS 경계,
운영 문서와 재귀 테스트 목록을 교차 확인했다. 실행 검증은 아래 결과를 얻었다.

```text
python -m pytest -q  -> 546 passed in 21.94s
ruff check .         -> All checks passed!
python -m mypy .     -> Success: no issues found in 131 source files
python cli.py status --state-dir state -> Champion EMPTY, frontier_families 0
```

다음 운영 점검은 실데이터·외부 서비스에 영향을 줄 수 있으므로 필요 시 별도 실행한다:
dashboard `/api/health` 확인, Docker preflight, sanitized KIS read-only refresh, 명시적
paper-order smoke, 그리고 동일 기간 benchmark/OOS 증거를 갖춘 candidate evaluation.
