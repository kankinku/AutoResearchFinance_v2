# Quant AutoResearch — 운용 원리·개선 설계 명세

> 상태: **검토용 제안** · 작성 2026-11-10 · **미승인 / 미구현 / 미배포**  
> 구현 계획: [`2026-11-10-quant-research-improvement.md`](../plans/2026-11-10-quant-research-improvement.md)  
> 저장소 문서 경로: `docs/superpowers/specs/2026-11-10-quant-research-improvement-design.md`

## 1. 목표·현재 계약

**목표:** 단일 QQQ 전략의 수익률 수동 최적화가 아니라, AI가 **등록된 지표를 조합해 알고리즘을 설계 → 독립적인 계산 엔진이 거래와 성과를 재현 → AI가 실패 원인 가설을 만들고 실제 대조 실험을 통해 다음 연구를 선택 → 원장으로 축적 → 독립 검증**하는 자율 금융 연구 시스템을 정확하고 반복 가능하게 운영한다.

승인된 원칙은 [20문답 원본](https://github.com/kankinku/AutoResearchFinance_v2/blob/main/docs/decisions/2026-10-14-autoresearch-interview-20q.md), [범위 고정 문서](https://github.com/kankinku/AutoResearchFinance_v2/blob/main/docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md), [AGENTS.md](https://github.com/kankinku/AutoResearchFinance_v2/blob/main/AGENTS.md)다. **V05 → T4 → V01~V04 → V06 → V07** 순서를 유지한다. 이번 설계의 결함 수정은 V05/T4의 사전 정확성 조건으로 간주하며 별도 최상위 프로젝트를 추가하지 않는다.

- 연구 대상은 *Indicator* 자체가 아닌 **Algorithm**(지표 조합·국면 전환·진입·청산·비중·위험 규칙).
- 1세대 완료 = 실제 후보 생성, typed StrategyIR 검증, 비용 포함 체결/성과, AI의 원인 **가설**, 실제 대조/다음 계획, 불변 Evidence 저장. 단순 백테스트·모의응답·계획 제출을 세대로 세지 않는다.
- 이 세 가지는 독립적으로 판정: **① 엔진 구현 ② 실제 모델의 자율 진화 효과 ③ 독립 검증 수익성**. `150/150 COMPLETED`도 ②/③을 뜻하지 않는다.
- 기존 ChatGPT↔MCP/OAuth/URL 기본 연결 유지. 별도 API 사용은 사전 명시적 승인 없이 도입하거나 기본값으로 교체하지 않는다.
- sealed OOS는 연구 루프에서 읽을 수 없고 OOS 결과는 학습으로 재유입하지 않는다. 실주문은 비활성으로 유지한다.
- `docs/architecture/quant-autoresearch-architecture-v1.0.md`, 원본 인터뷰, G1~G150 Evidence, 별도 백업 및 민감 파일은 변경하지 않는다. 연구 Director/생성 결과는 protected core 코드·권한·평가기준을 수정하지 못한다.

## 2. 실제 소스코드 조사 범위

2026-11-10 기준 저장소 `/shared/Quant`의 `main`=`c6fe2d7d70e34903110d889a718a9e80276e780a`를 기준으로 **추적 1,083파일 / Python 653파일(제품·스크립트 등 338, 테스트 315) / 총 Python 약 111,956줄**을 파일별 읽기 및 AST 파싱·import 관계·예외·함수/클래스·위험 집중 경로로 정적 전수 분석했다. Python 653개의 구문 오류는 0건이다. 비-Python 구성·정책·쉘·프런트 코드 파일 및 주요 문서의 목록/관계도 조사했다. **이는 11만 줄 모두의 의미론적 수동 검토나 모든 실행 경로의 실증 테스트를 뜻하지 않는다.**

개발 브랜치의 메인 대비 변경 Python도 별도로 파일별 읽고 파싱했다(중복 포함): `research/v3-strategy-evolution` 353개/46,543줄, `research/v3-causal-chart-wave-patterns-20261029` 355개/46,909줄, `fix/quant-v3-parent-feedback-ponytail-20261030` 34개/13,046줄. 모두 구문 오류 0. 앞의 두 브랜치 변경분에는 외부 `pandas_ta_classic` 벤더 소스 313개씩 포함되어 **제품 코드 313개 증가로 해석해서는 안 된다.** 개발 브랜치는 원격 배포 승인이나 운영 릴리스가 아니다.

- `research/v3-event-detection`: 메인 대비 계획·진행 문서 2개만 추가. 새 탐지 알고리즘 코드 구현/실행 기록 없음.
- `validation/v3-independent-oos`: 메인 대비 계획·진행 문서 2개만 추가. 독립 OOS 실행 전.
- GitHub 저장소의 기본 브랜치는 현재 `master`, 운영 연구 버전 베이스라인은 `main`이다. **반드시 작업 기준 SHA를 명시**하고 `master`에 실수로 PR을 열지 않는다.
- 기존 Moon 작업 공간의 과거 운영 원본 `cycles.sqlite`, `gateway.sqlite`, QQQ Parquet은 현재 검사한 경로에는 없음. 과거 성과를 현 환경에서 재실행했다고 주장할 수 없으며 **안전한 소스/DB 회수 자체가 T0 선행 조건**이다.

**기존 핵심 호출 경로:**

`integrations/chatgpt_mcp_sdk.py` → `application/academic_checkpoint_service.py` → `research/llm/autonomous_cycle.py` → `research/indicator_engine/{algorithm_plan,decision_audit}.py` → `research/indicator_engine/strategy_adapter.py` → `core/backtest/engine.py` → `research/llm/diagnostic_research.py` / `application/academic_checkpoint_service.py:evaluate_experiments` → `research/llm/{experiment_learning,adaptive_direction,lineage_selection,parent_portfolio_v2}.py` → SQLite Evidence 및 다음 체크포인트.

별도 `application/research_batch_worker.py` / `application/research_batch_service.py`의 장기 배치는 **매 세대 LLM 호출을 보장하는 경로가 아니다**. `research/llm/checkpoint_autopilot.py`는 호출자가 제공한 모델과 함께 진행하는 전경 실행기로, 실제 ChatGPT 앱 100세대 무인 연결을 입증하지 않았다. 둘을 혼동하지 않는다.

## 3. 핵심 관찰 및 문제 정의

| 사실·위치 | 평가 | 원칙적 처리 |
|---|---|---|
| `core/backtest/engine.py:534–537` / `research/llm/inherited_feature_compiler.py:84–87` | 이미 지연된 지표가 재지연되는 사례 재현(첫 유효 인덱스 3→5). 수익 및 거래 시점 왜곡 가능 | 사전계산·실시간계산의 지연 소유권을 한 번으로 통일. 호출자·고정 원장 호환성 먼저 확인 |
| `core/features/series.py:47–84` | 주봉·월봉에서 미래 기간 값 유입에 따라 과거 시점 결과가 달라짐. 접두(prefix) 안정성 실패 | **완료된 기간**과 관측 당일 잠정값을 구별. 완료 시각/공개 시각이 확정된 데이터만 신호 사용 |
| `research/indicator_engine/nasdaq_capture.py:123–156` | 동시 수집 시 실패 프로세스가 성공 프로세스가 만든 raw 파일 삭제 가능, 재현됨 | 경로별 단독 소유·배타적 생성 및 소유 파일만 정리. append-only 보호 유지 |
| `integrations/kis/paper_orders.py:99–145` | 부분 매수 후 미체결 잔여 주문을 취소/확인하지 않아도 `FLAT` 결과 가능, 모의 재현됨 | 미체결 주문이 존재하면 `FLAT` 금지, paper-only 취소→확인→반대 주문 검증 |
| `research/indicator_engine/development_economics_v05.py` | 비용 스트레스 일부가 **체결 고정 사후 비용 차감 프록시**. 실제 체결 재계산과 구분해야 함 | 기존 프록시 유지·정확히 명명; 추가 검증은 canonical engine 재실행으로 비교 |
| `research/llm/adaptive_direction.py` / `experiment_learning.py` | 감사된 실험을 바탕으로 EXPLORE/EVOLVE/TEST_HYPOTHESIS를 **권고**. 연구 효율 향상은 미입증 | 기존 함수를 재사용하되 동일 예산 랜덤·단순 규칙 대조에서 효용 확인, 거짓 '학습' 주장 금지 |
| `research/llm/parent_portfolio_v2.py` / `application/academic_checkpoint_service.py` | 부모 다양화 경로 존재하지만 `parent_portfolio_v2=False` 기본값. G94/G96/G106 집중 기록 | 기존 opt-in 전략을 대조 실험으로 평가; 결과가 좋을 때만 장래 세션에 채택 |
| `integrations/chatgpt_mcp_sdk.py` 개발 분기 | 정식 32개 도구 계약과 신규 33개 노출 충돌; 과거 실제 테스트 2개 실패 | 사용자 승인 없는 공개 도구 추가 금지. 인터페이스 계약을 고치거나 기존 도구 내 안전한 확장 사용 |
| 150세대 S7 감사 | 74개 child 수익 상승/71개 하락/5개 불변. 최고 G94 이후 56세대 최고 갱신 없음 | 세대 수보다 **유효한 실험, 다른 신호, 일반화, 동일 예산 효율** 중심으로 판단 |
| `memory/evidence_store.py:97–103`, 장대 파일 `application/academic_checkpoint_service.py` | 원장 전수 로드·복잡한 서비스 책임 집중 | 병목 실측 전 선제 재작성 금지; 해당 기능 수정 시 책임별 최소 분리 |

추가 주의: 이미 확정된 G150 StrategyIR 및 Evidence는 구버전 실행기/환경과 연결된다. 새로운 계산 수정으로 값이 달라질 수 있다. **과거 기록을 덮어쓰거나 재검증 없이 연결해서 이어 달리지 말고**, 기존 세션은 고정 조회하고 변경 버전의 새 연구 세션으로 안전하게 전환한다. 새 evaluator 버전·입력/정책 해시를 명시한다.

## 4. 개선 대안 및 결정

| 대안 | 장점 | 단점 | 권고 |
|---|---|---|---|
| A. 기존 코드 그대로 지표·연구 세대 확대 | 단기 개발량 적음 | 데이터 누출·시점 왜곡·탐색 편향을 확대 | 기각 |
| B. 신규 다중 에이전트/강화학습 엔진 전면 재작성 | 기능 확장 여지 | 기존 원장·권한·재현성 훼손, 비용 큼 | 기각 |
| **C. 기존 모듈 재사용 + 정확성 수정 + 실험으로 입증된 선택 정책만 도입** | 최소 변경, 이전 결과 보존, 측정 가능 | 안정된 단계별 진행 필요 | **추천안(미승인)** |

### 권장 미래 운용 구조

1. **Data/Strategy Gate:** 검증된 자료·정규화 StrategyIR·시장 시점·예산·권한 확인.
2. **Proposal:** ChatGPT가 가설, 변경 대상, 비교할 원본, 실패 가설, 다음 단계 계획 제출. 신규 코드를 임의 생성해 실행 엔진을 덮어쓰지 않음.
3. **Canonical Evaluation:** 엔진이 실제 거래·비용·현금·낙폭·레짐별 기여를 측정. 바뀌지 않은 실행 경로는 사전 중복 처리.
4. **Controlled S7:** 동일 데이터/예산/비용으로 반대 가설·ablation·파라미터 변화를 측정. 관측, 추정 원인, 확정 사실 구별.
5. **Research Memory + Parent Portfolio:** 합격·악화·미결·중복을 분리, 서로 다른 전략 계열을 유지, 다음 선택을 증거와 실험 기회로 결정. 정체 시 새로운 조합으로 확장하되 고정 비율을 무작정 변경하지 않음.
6. **Selection Benchmark:** 동일 전산 자원·모델 호출·후보 수로 GPT/기존 규칙/무작위 탐색 비교. 효과가 입증되기 전 새 선택 정책을 기본으로 승격하지 않음.
7. **Independent Validation:** 후보·검증 기간·지표·선택 기준을 **보기 전에** 고정, 별도 권한에서 한번만 독립 평가. 결과는 연구 루프로 역류 금지.

이 구조는 새 프레임워크를 제안하는 것이 아니라 기존 `academic_checkpoint_service`, S2/S7/S8, `parent_portfolio_v2`, Evidence, T4 스크립트를 **정확한 역할로 연결·검증**하는 개선이다.

## 5. 변경 금지 및 허용 경계

- **기본 계약 불변:** 원본 Q01–Q20, V05→T4→V01~V04→V06→V07 순서, MVP 모델 연결(ChatGPT↔MCP), OAuth 및 URL, broker permission, sealed OOS 정책, canonical StrategyIR/Evidence 포맷.
- **기존 점수 왜곡 금지:** 옛 G150 원장 자동 재계산·수정 금지. 기존 결과는 `LEGACY`라는 설명과 구버전 코드/해시로 조회; 수정된 엔진은 새 세션/버전/해시로 평가.
- **연구 AI 쓰기 제한:** protected core 파일/시세/평가 기준/수익 기준/자격 토큰/실주문 기능 변경 불가. 보호 경계 코드의 개발자 승인 수정은 검수·회귀 테스트를 거친 별도 PR로만.
- **도구 호환:** 기존 32개 ChatGPT 공개 도구를 기본 유지. 33번째 도구 배포나 기본 실행 방식 변경은 별도 ADR 승인.
- **데이터 누락:** 원본 SQLite/Parquet 회수 실패 시 `BLOCKED`로 기록. 모의 데이터로 실제 150세대 계보를 대체하지 않는다.
- **추가 범위 제한:** 등록 지표 수 대량 증설, 새 ML/AutoML 플랫폼, 새 실행기 재작성, 성과지표 임계치 완화, 자동 실거래, 미승인 OOS 개방은 본 계획에 포함하지 않는다.

## 6. 객관적인 합격 기준

| 단계 | 합격 조건 | 실패 시 |
|---|---|---|
| 기본 계약·정확성 | 지연/주봉 prefix, 수집 경쟁, paper 미체결에 대한 **실패 재현 → 단일 수정 → 회귀 통과**, 원본 증거 불변 | T4 진입 금지, 원인 복구 |
| V05 | 실제 재실행을 포함한 비용/체결 검증, 샘플 부족·다중 탐색·유동성 모호함 표시, 개발 데이터와 독립 검증 혼동 없음 | `BLOCKED/NOT_VALIDATED` |
| T4-10 | 실제 인증 ChatGPT의 10세대 각 Plan/Diagnosis/S7/Next Plan/Evidence, 중단·재개/비용·모델 호출 로그, 동등 예산 대조 | 실제 모델 자율 실행 미완료 처리 |
| T4-100 | 10세대 합격 후 최대 100 완결 세대; 유효 신호 변경·중복·비용·세대 수·실패 기록/원장 해시 검증. GPT 우월성은 별도 증거가 있어야 주장 | 엔진 통과와 AI 효율 통과를 구분 |
| 독립 검증 | 후보 G94/G106/G96/G60 고정 해시, PIT/기업행동/비용/기간/비교군 사전등록, 연구 입력 차단, 결과 단회 공개 | 외부 자료 미확보 시 `BLOCKED` |
| V06·V07 | 주문 OFF인 관측/종이 평가와 명시적 승인 게이트, 시험·원장 복구·안전성 확인 | GO 금지 |

**차단조건:** 원본 데이터/증거 미회수, 모델 연결 불명, 무작위 대조 비교 예산 불균형, 독립 OOS 소진, 실패한 테스트의 무시, 공개 API 무승인 확대. 단계마다 `docs/operations/autoresearch-master-progress.md`에 `PASS/FAIL/BLOCKED/NOT RUN`과 근거를 기록한다.

## 7. 이후 작업자의 승인 필요 지점

1. 이 **최소 수정 + 실험적 옵션 분기 방식**을 채택할지.
2. 결함 수정 후 구세션은 불변 읽기 전용으로 두고 **새 결과 버전·세션을 생성**하는 정책을 승인할지.
3. 메인 변경과 V3 Track1/2/3의 기능 승격은 각각 별도 리뷰·검증/ADR을 적용할지.

이 명세는 검토·승인 전까지 제안에 불과하다. 배포나 원본 데이터 변경을 승인하는 문서가 아니다.
