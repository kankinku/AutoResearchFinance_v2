# S4 1차 — 세대별 알고리즘 연구·진단 체크포인트 실행기

기준일: 2026-10-14. [20문답 사용자 요구](../decisions/2026-10-14-autoresearch-interview-20q.md) 5·6·8·9·11·15·17·18·20번, [재정렬 로드맵](autoresearch-implementation-roadmap-2026-10-14.md). **코드 연결 및 Mock 기반 실제 백테스트 3세대 실행까지 구현·검증. 인증된 외부 LLM 사용 증거는 아직 없음.**

## 실행 계약

`research/llm/autonomous_cycle.py`의 `AcademicCycleService`는 `ResearchCatalog`의 VERIFIED 지표, 단일 개발용 `MarketDataSet`, `CycleResearcher`라는 외부 주입 `propose(context)` 제공자를 입력으로 받는다.

```
start(catalog,market,generations=N)
  → advance(...) / run_bounded(...,max_steps=N)
     → S3: verified indicator metadata → LLM AlgorithmPlan 응답 → typed Plan 검증
     → S3: indicator 계산 및 시장 분기·가중 투표 → canonical StrategyIR
     → S1: canonical backtest·비용·체결·의사결정 원장 Audit
     → S2: 실제 원장+메트릭 포함 LLM 진단 컨텍스트 → DiagnosticResponse 검증
     → S2: 관측 ID, 반대 설명, typed ResearchIntent, 부모 전략/자료/원장 해시 검증
     → 저장: generation, plan, measured metrics, audit hash, 원인 **가설**,
             실험 제안, previous_evidence_hash, hash chain
     → 다음 세대: 원인 가설과 이전 성과, 검증된 실험 제안을 제공자에게 전달
```

- 한 세대가 **생성+실행+실제 체결 원장+LLM 가설 검증+증거 저장**까지 완료되기 전에는 완료 건수 증가 불가.
- SQLite 데이터베이스는 사용자의 상태 경로(예: `state/indicator-engine/autonomous-sessions.sqlite`)에 저장하는 **논리적 append-only 세대 원장**. 각 레코드는 이전 레코드 해시를 포함해 체인을 구성한다. 파일 전체가 서명된 외부 감사 증거는 아니며, 완전 재해시 공격까지 검출한다고 주장하지 않는다.
- 세션은 고정 데이터 해시·지표 카탈로그 해시와 함께 시작한다. 중간에 수정된 가격·지표 등록 상태/Sealed OOS는 다음 세대에서 차단한다. 동일 `plan_id`가 아니라 **plan_id를 제외한 알고리즘 의미 해시**와 **실제 개발 구간의 entry/regime 신호 해시**로 중복을 검사한다. 다른 값이더라도 같은 결정을 냈다면 새 유효 세대로 집계하지 않는다.
- 동시에 두 실행자가 같은 세대를 편집할 수 없게 `EXECUTING` 단일 소유 token을 요구한다. 응답 오류·부정확한 분석·중복 실험은 `INTERRUPTED`로 실패 표시, 완료 세대는 보존하고 명시적 `resume()` 후 재시도. **프로세스 강제종료 후 남아 있는 EXECUTING 상태는 자동으로 반환/재실행하지 않으며, 운영자 수동 점검이 필요하다.** 이것은 완전한 크래시 복구가 아님.
- `run_bounded`는 한 명령에서 최대 100개의 세대를 동기 실행한다. **외부 공급자의 실제 호출 구현이 연결되지 않으면 자동 LLM 연구는 수행되지 않는다.** 백그라운드·무제한 지속 모드는 S5 과제이다.

## 중요한 미구현·검증 경계

현재 저장소 `research/llm/provider.py`는 내장 네트워크 LLM 클라이언트를 명시적으로 금지한다. GPT 연구 지시를 제공하려면 **인증된 ChatGPT/MCP 경로가 외부에서 호출되는 실제 제공자**를 붙여야 한다. 이번 테스트는 `ScriptedResearcher`라는 **모의 제공자**로 Plan과 분석 JSON을 응답했다. 이는 `real_model_connection_verified=false`이며, 실제 LLM 연구 능력·비용·응답 신뢰성·완전 무인 운용을 검증한 것이 아니다.

S2의 `next_intent`는 우선 유효한 *후속 실험 제안*으로 저장하며, 다음 세대의 S3 Plan은 분석 정보를 본 **별도 알고리즘 제안**으로 생성된다. 따라서 다음 Plan이 직전의 특정 원인 가설을 실험했다고 검증할 수 없다. **반증 가능한 통제 실험의 자동 실행 및 귀속(S7)이 남아 있다.**

S3 알고리즘 컴파일러는 현재 검증된 이진 진입 지표와 단일 레짐/리스크 게이트 및 고정 자본 노출만 처리한다. 지속형 실행, 실제 외부 GPT 인증, 모든 인디케이터의 자율 확장, 동적 포지션 규모 변경, 다자산 진화, 독립 검증은 남은 개발 대상이다.

## 실제 기존 QQQ 개발 구간 스모크 (기능 검증)

- 소스: Tiingo QQQ 2020-01-02 ~ 2025-12-31, 1,508개 완료봉, `DEVELOPMENT`, historical vendor revision **NON-PIT**.
- 지표: `time_series_momentum`, `previous_range_breakout`, `parkinson_variance`를 검증 등록.
- 한 번의 `run_bounded(max_steps=3)`에서 모의 제공자의 `AlgorithmPlan` 응답 3회 + `DiagnosticResponse` 응답 3회, 원장 자동 연결 3회, SQLite 체크포인트 3회 및 해시 체인 재읽기 성공.

| 세대 | 누적 수익률 | MDD | 거래 체결 | 관측된 상태 |
|---:|---:|---:|---:|---|
| 1 | +56.55% | 12.98% | 69 | 초기 테스트 Plan |
| 2 | -1.87% | 9.72% | 186 | 기존 성과에 대한 구조화 피드백이 포함된 새 Plan |
| 3 | +41.27% | 30.95% | 43 | 앞 세대 결과를 전달한 별개 연구 Plan |

위 차이는 **성공적인 자율 수익 개선을 의미하지 않는다**. 테스트 제공자가 의도적으로 매매 규칙을 다르게 만들었고 실질적인 성과도 서로 달랐다는 것을 확인한 것이다. 같은 기간·같은 자산의 개발 자료를 반복 관측했으므로 각 세대 결과는 독립 OOS 점수가 아니다.

## 테스트와 후속 작업

- 세대 두 번/세 번 자동 완료, 모의 원인 분석의 거래 ID 확인, 수정된 수익·지표 기록 거부, 동일 알고리즘 의미/신호 중복 차단, 다른 개발 자료·카탈로그 거부, Sealed OOS를 제공자에게 노출하기 전에 차단, 오류 후 완료 카운터 보존, SQLite 체인 조작 탐지, 명시적 재개를 테스트한다.
- **S4 잔여 최우선:** 실제 인증 ChatGPT/MCP 연구 요청/응답을 세대 실행기와 연결하고, 구조화 Plan+진단의 응답 식별·모델/버전·LLM 호출 비용/실패 원인을 기록해 적어도 2~3세대가 진짜 모델 호출로 순차 연결됨을 검증. 모델이 호출될 수 없는 환경에서 모의 구현을 'LLM 자율 실행 완료'로 표시하지 않는다.
- **S5:** 중단·재시도·복구 정책 강화, N=10/100세대 및 지속형 운영 시간·자원 예산 제한. **S7:** 실험 설계→실제 반증 실험→검증된 원인/기각된 원인 기록.
- 모든 경로에서 운영·실거래·KIS 주문·protected core·Sealed OOS 권한 변경 없음.

## 최종 검증 및 저장소 상태

- `tests/research/test_autonomous_academic_cycle.py`: 세대 실행기 관련 테스트 8개 통과.
- S1~S4 통합 집중 테스트 48개 통과(세대 실행 8 + 기존 S1/S2/S3 관련 40).
- 저장소 전체 `pytest -q -p no:cacheprovider`: **1,333 passed, 0 failed / 400.98s**.
- `ruff check .`: 통과. `mypy .`: 통과, **222 source files**.
- 실제 QQQ 데이터 검증: 모델 모의 응답 3회의 계획/진단 각각 성공, 체인 검증 및 재조회 일치. 중복 매매 신호인 매개변수 변경만 한 제안은 별도 테스트에서 중단됨.
- 모든 증거와 상태는 테스트용 디렉터리/메모리 내에서 실행됐으며 운영 서비스 호출, GitHub 운영 브랜치, broker, 실거래 권한, Sealed OOS를 변경하지 않음.
