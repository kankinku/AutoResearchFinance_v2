# Quant AutoResearch — 일반화 성능 강화 개발계획 v2.0 및 1차 구현

**작성일:** 2026-10-24 KST
**승계:** [v1.0](quant-generalization-research-v1-plan-20261024.md)
**상태:** v2.0 설계 적용 / 독립 실험 실행 전 / 실운영 미배포

## 1. v1.0 현실성 검토 및 결정
**기존 GEN-P5의 25/25/25/25 세대 분할은 폐기한다.** 연구 세대의 진화량과 검증 기간은 다른 축이다. 임의 25세대 시간 구간 변경은 부모 계승에 교란을 만들고 각 시점의 탐색예산을 비대칭으로 만든다.

다음 두 축을 분리한다.
- **연속 100 실제 GPT 세대:** 같은 2020-01-02~2025-12-31 development dataset 정책 아래 계획→체결→GPT 가설/진단→S7→부모 진화. 실행 예산은 100세대, 각 세대에서 발생한 백테스트/S7 실행 수는 별도 카운터. 세대 연구 중 실행하는 역사 연도별 점검은 '기본적으로 이미 개발에 노출된 데이터'라는 사실을 유지한다.
- **동결한 전략의 개발 기간별 강건성 분석:** 동일 AlgorithmPlan 또는 지원된 계승 StrategyIR에 대해 2021~2025 각 기간에서 cash-only warmup, 다음 봉 시가 체결, 동일 비용 QQQ 비교; 구간별 수익/MDD/거래수/비용 및 해시 기록. 개발 데이터 전체를 보고 최적화된 전략의 해당 구간 성과는 **EX_POST**이지 미학습 OOS 아님. 해당 결과를 다음 부모 선정에 써도 이것만으로는 미래 예측력 인증 불가.
- **엄밀한 역사적 워크포워드 (독립 실험):** 다른 시간 컷오프마다 GPT 연구 캠페인을 **처음부터 독립 재실행**, 컷오프 이후 가격이 LLM 및 후보 선정에 입력되지 않음; 컷오프 뒤 평가. 동일한 모델/연구예산을 쓰면 3개 컷오프별 100세대 = 추가 300세대 수준. 비용이 큰 독립 연구 실험이며, 현행 신규 100세대 수에 섞지 않는다. 초기 단위시험은 소수 세대로 단계 검증 가능하나 전체 100세대 일반화 증거라 하지 않는다.
- **2026:** 사용자에게 일부 결과가 노출되어 있으므로 순수 미학습 OOS를 다시 주장하지 않고 EXPOSED_DIAGNOSTIC으로만; 전략 고정 이후 신규 누적 자료가 진정한 전진 검증. 현재 관리형 신규 데이터 목록 0개, Tiingo/KIS 공급자 미설정. `DATA_PROVIDER_BLOCKED`는 성공/0수익이 아님.

## 2. 실제 코드에서 재사용할 것
- `research/indicator_engine/forward_window.py`: 독립 실행구간 전까지 캐시 보유액 유지, 지표 warmup, 다음 거래일 시가, 평가 결과 hash; 실험은 여전히 DEVELOPMENT non-PIT.
- `research/indicator_engine/development_benchmark.py`: 같은 원시 QQQ Parquet, 수수료/스프레드/슬리피지 합산 동일 모델, 다음 봉 시가 진입 비용 차감.
- `research/indicator_engine/algorithm_plan.py`: 검증된 typed 지표·장세 분기·가중투표, 임의 Python 미허용.
- `research/indicator_engine/walkforward.py`: 기존 두 계열 한정 train-only 선택. 향후 실제 GPT 전략 시점별 parent selection 재실행과는 다른 기능.
- `core/validation/cpcv.py`: 레이블 중첩 purge/embargo 유틸은 보조 검사이며 미래 데이터의 독립 연구를 자동 보장하지 않는다.
- `research/indicator_engine/sealed_oos_precommit.py`: 개발 사전선정 해시 동결; 독립 봉인 서명·실거래 인증 아님.

## 3. v2.0 단계별 구현
| 순서 | 개발 사항 | 수락 조건 | 상태 |
|---|---|---|---|
| P0 | 별도 Git worktree/브랜치, 운영 DB 원장·OAuth·대시보드 불변 확인 | 활성 68/100 checkpoint 원장 quick_check PASS, G452/G552 보존, OAuth/OOS/orders 그대로 | 기준선 확인 |
| P1 | 데이터 지표/비용/TradingView 동등성 audit | G64의 native RSI SMA·ADX SMA·다음 봉 시가와 TV 값/거래 ID 바 단위 재현. 분할/배당 원시 vs 조정 가격 일치 | 일부 자료·코드 확인, TV 독립 검증 미완료 |
| **P2-A** | **연속 100세대와 무관한 ex-post period diagnostic**: `historical_robustness.py`, 기존 forward_window·costed benchmark 재사용 | 여러 연도 반복·상태 명칭 non-OOS, 미래 데이터 컷오프 거부, 이후 연도 가격변경→이전 연도 불변, 기간별 비용·fill 추적 | **구현/테스트 단계** |
| **P2-B** | G64 등 **변이/부모로 계승된 실제 StrategyIR 및 feature vector** 리플레이 지원, 알고리즘 원본/해시·수식 보존 | 컴파일된 vector·StrategyIR 감사 일치, 실제 G64 전체 감사 SHA·40건 완료 거래 재생, 2021~2025 연도별 비용 수익 비교 | **구현·테스트 65 PASS / 개발 브랜치 한정. [실측 보고서](quant-generalization-p2b-g64-20261024.md)** |
| **P3-A** | 실제 audited counted 후보의 연도별 강건성 기반 Pareto/부모 순환 **별도 진단 선택기** | 원본 계보 해시/연도 QQQ 비용/최악 MDD, G64/G61/G45 실측, 운영 state 접근 거부, ex-post로만 표시 | **구현 / 실제 원장 복제본 검증 완료. [P3 보고서](quant-generalization-p3-parent-review-20261024.md)** |
| **P3-B** | **실제 counted S7 자식** 감사 및 새 세션 opt-in parent selector 코드 통합 | 원본 S7 실측·signed source/child 계보, 개발부모·S7 동등 평가, 기존 pinned 우선보존 | **개발 구현 및 오프라인 실원장 평가 검증 완료; 운영 미배포. [P3-B 보고서](quant-generalization-p3b-s7-scoped-integration-20261024.md)** |
| **P4** | GPT 작성 계획·진단 기반 격리 연구 10세대 + S7 실측 + 부모 계승 | 10세대 Evidence·10 S7·2 부모 pin, 오류 시 재제출 후 동일 token·해시 보존. 모델 호출 ID·투자 성능 미달 | **실제 10/10 기술 통합 PASS, 경제성 FAIL, 모델 invocation receipt 미구현. [P4 보고서](quant-generalization-p4-10gen-actual-study-20261024.md)** |
| **P4-1** | **노출률 및 위험 보정 연구 부모 게이트** | 실현 노출률/거래수 사전 적격성, QQQ 비용후 노출·변동성 보정 프록시, 감사 원장 보호 | **신규 세션 opt-in 구현·실제 P4 원장 복제 검증 67 PASS / 운영 미배포. [P4-1 기록](quant-generalization-p4-1-research-quality-20261024.md)** |
| **P4-2** | **외부 서명 캡처와 모델 판단·세대 증거 체인** | 서명된 session/gen/phase/response/context/decision 해시, 원장 연결, 다운그레이드·위조 차단 | **구현·격리 fixture 및 77개 회귀 PASS / provider 자체 호출증거 미확보. [P4-2 기록](quant-generalization-p4-2-model-provenance-20261024.md)** |
| **P4-3** | **S7 지원 metric 일치·무효 실험 사전거절** | exposure 실측, 미지원 지표 선거절, 신규 세션 전용 무효 진단·재제출 로그 | **개발 구현 / 회귀 검증, 운영 미배포. [P4-3 기록](quant-generalization-p4-3-s7-contract-quality-20261024.md)** |
| **P4-4** | **실제 10개 counted 전략 비용·연도·전일 국면별 사후 진단** | 기존 증거 재검증 후 commission/spread/slippage 전부 2배, 연도별/전일 국면별 QQQ, 독립 OOS 차단 | **10/10 개발 스트레스 재실행/52 관련 테스트 PASS·운영 미배포·독립 OOS 및 PIT BLOCKED. [P4-4 보고서](quant-generalization-p4-4-cost-regime-research-20261024.md)** |
| **T4-R1** | **10개 무작위 후보·S7 시도 예산 설명 대조** | 단일 사전고정 시드·검증된 지표/동일 QQQ 비용·후보 10 + S7 10, LLM 계승 차이 명시 | **실제 10후보 재현 비교 PASS, 인과·동등 연구세대 효과 NOT PROVEN, 신규 100세대 HOLD. [T4-R1 보고서](quant-t4-r1-preregistered-random-comparator-20261024.md)** |
| **P5** | **신규 별도 GPT 실제 연구 목표 100세대** | G1~G100 GPT 직접 알고리즘 설계→정식 비용 backtest→근거 있는 진단→S7→원장; 기존 68/100 DB 리셋/재계수 금지 | **2026-10-24 사용자 요청으로 신규 격리세션 `3b44e05e52b3497db6fa035681ed0a5d` 시작 및 GPT 작성 실제 G1~G10 (10/100) S7 10건 완료. 남은 90 미실행; 검증 적격 부모 0/10, 자동 계승 미검증; OOS·실주문 비활성. [P5 초기 10세대 보고서](quant-p5-new-100-session-first-10-20261024.md)** |
| P6 | 최종 후보 사전잠금 + 데이터 공급 재현성 + 미래 전진 검증 | 사용자가 확인한 2026 EXPOSED 구분, 2026 실제 시점 자료/독립 PIT 봉인 승인 전 OOS BLOCKED, 새 미래 자료로 진짜 검증 | 미구현 |

## 4. 실험 정책 (차기 신규 100세대 시작 전 확정할 항목)
1. 실행 세대 수 100, 메타지표는 총 소요시간/실험 회수/실제 GPT 의사결정 횟수/유효한 계승/중복 실행 금지.
2. 동일 데이터(2020~2025)의 연간 성적은 **강건성 진단 지표**, 독립 미래 예측 인증이나 '연속 100 학습 세대와 별개 100 WF 세대'로 오인 금지. 전 구간 재최적화 후 과거 기간 성적을 'out-of-sample'로 명명 금지.
3. 부모 계승 기준은 사전 선언한 비용 차감 순수익, drawdown, bench-relative & exposure-aware 진단, 장세별 강점 및 S7 복제/무효 실험; Pareto 후보 다양성 보전. PBO/DSR의 표본수 부족/의존성은 명시.
4. 매 봉 현재 이후의 데이터/후속 fold 가격을 입력했을 때 이전 기간 연구 계획/체결/선택 내용이 변하는 회귀테스트.
5. 2026 외부 데이터 품질/가격시점/adjusted vs RAW/Corporate Action/수수료 비교, Pine 전략에 학습 기간 한정 진입 허용 코드가 있으면 2026 테스트를 정확히 측정할 수 없는 문제 병기.
6. 원장 불변: 기존 OAuth/MCP 서비스, 대시보드/고정 public URL, G452/G552/G68 및 S7 Evidence, orders disabled; 실패 시 분리된 Git worktree에서 롤백.

## 5. 1차 테스트 및 결과 추적
- 테스트 스위트: `tests/research/test_academic_historical_robustness.py`. TDD: 새 모듈 부재→test collection FAIL 먼저 관찰, 이후 구현해 PASS.
- API: `evaluate_historical_robustness(catalog, plan, market, years=..., last_development_date=...)`; 해당 cutoff를 **전체 market 상한으로 검증**. 완료된 연도만 요구하며 자료가 부족하면 예외, 없는 연도의 수익을 0%로 표시 금지.
- 반환: `EX_POST_DEVELOPMENT_ROBUSTNESS_ONLY`, `independent_oos_approved=False`, `candidate_promotable=False`, `broker_executable=False`. 연도별 비용 QQQ, MDD, fill, 독립 report hash.
- 운영 상태/배포: Git 개발 브랜치에서 검증, 운영 MCP는 원본 그대로. 새 100세대는 아직 실행되지 않았다.

## 6. 실제 DEVELOPMENT Parquet 스모크 (선행 기능 검증, G64 **아님**)
- 입력 파일: `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`, 1,508봉, dataset SHA `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`.
- **전략:** 기존 `tests/research/test_academic_algorithm_plan.py`의 `_plan()` 고정 synthetic 연구 **테스트 후보**. 실제 G64 계승 StrategyIR 아님, 따라서 현재 최고 전략의 OOS 평가 결과로 보고하면 안 됨.
- 조건: 연도별 초기자본 1만 달러 리셋, 첫 완료 종가 이후 다음 봉 시가 진입, 원본 수수료 모델, 최초 trading-bar 시작 전 매수 금지.
- 2022: 후보 -2.739%, 비용 반영 QQQ -33.854%, MDD4.392%, 체결 22건.
- 2023: 후보 +19.955%, 비용 반영 QQQ +53.462%, MDD8.174%, 체결 17건.
- 2024: 후보 +15.832%, 비용 반영 QQQ +27.728%, MDD11.428%, 체결 7건.
- 2025: 후보 +6.042%, 비용 반영 QQQ +19.571%, MDD9.546%, 체결 13건.
- 함수 반환 상태 `EX_POST_DEVELOPMENT_ROBUSTNESS_ONLY`, report hash `da90095a2a213cca885619c75dba44d0956a4cfcbb62c9b25053868e59f96bf8`. 해당 전략의 2022~2025 성적에 2020/2021 개발 이력 및 사전 선정 독립성 인증 없음. 이는 **기술적인 평가 계산 시험**이며 검증된 투자 성과가 아니다.
- 검증 한계: 현재 API는 원래 AlgorithmPlan을 직접 지원한다. 연구에서 변이·계승한 G64 등 StrategyIR 실재생까지 연결해야 P2-B 완료. 2026 데이터를 읽거나 검증하지 않음.

## 7. 첫 구현 검수 증거
- TDD 첫 실행: 모듈 부재 `ModuleNotFoundError`로 RED; 구현 후 신규 11개 테스트 PASS.
- 회귀 통합: 기존 AlgorithmPlan / 기존 Walkforward / V04 개발 사전동결 / CPCV purge+embargo / 범위잠금 + 신규 = **55 passed in 26.15s**.
- `ruff check` 변경 2개 Python 파일 **PASS**; `mypy` 신규 구현 소스 **PASS**.
- 미실행/미검증: 전체 repository tests, 운영 대시보드 GUI 인증, TradingView G64 1:1, 새 GPT 루프/100세대, 2026 OOS, 실제 미래 순수익. 새 코드 **운영 미배포**.

## 8. 다음 작업
1. 실제 QQQ 2020~2025 데이터에서 동결된 typed AlgorithmPlan 및 실제 최고 G64 **변이된 StrategyIR** 2021~2025 연도별 비용·체결 진단 **완료**([P2-B 실측 기록](quant-generalization-p2b-g64-20261024.md)). G64 원본 full-audit SHA 일치, 기존 운영 원장 불변.
2. 2026 데이터 공급이 현재 없다면 UNAVAILABLE 상태를 유지하며 누적 Pine 성적만으로 강제 손익 판정하지 않는다.
3. P3-B에서 S7 자식 원본 보고서/계보/전체 감사 해시 재현 → 동일 개발 기간별 평가 → 신규 세션 등록 시 선택기 opt-in 코드를 구현했다. 이제 P4 **격리 신규 연구 세션 실제 GPT 10세대** 계획→S7→부모 선정→계승/중단재개→증거해시 검증. 현재 개발 코드 운영 미배포이며 독립 미래 데이터 OOS 성능 실증은 별개다.
4. 10세대 이후 실제 100세대 연속 진화. 비용·진단 및 안전 게이트 실패하면 우선 해결.

**이 문서는 기존 20Q 결정 및 V05→T4→V01~V04→V06→V07 승인 순서를 변경하지 않으며, 범위 확대 항목은 추가 승인 필요.**
