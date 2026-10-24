# Quant AutoResearch — 일반화 성능 중심 100세대 연구 개선 계획 v1.0

**상태: PROPOSAL / NOT_IMPLEMENTED / NOT_APPROVED_SCOPE_CHANGE**
**작성일: 2026-10-24 KST**
**대응 사용자 질문:** 2020~2025 개발에 맞춰진 최고 전략이 미학습 2026년에서 음수 성과를 보인 문제를 근거로, 학습 성과와 실전 일반화 성과를 분리하고 다음 100세대를 의미 있게 개선하는 개발 계획.

## 0. 기존 승인 범위 / 작업 ID / 금지 사항
- 관련 원본 결정: Q02/Q04/Q05/Q06/Q07/Q08/Q09/Q10/Q11/Q13/Q14/Q15/Q16/Q17/Q18/Q20.
- 작업 제안 ID: GEN-P0~GEN-P6; **현재 승인된 단계 순서 V05 → T4 → V01~V04/T5 → V06 → V07을 변경하지 않는다.**
- T4 내부의 연구 품질·개발 데이터 검증을 강화하는 설계 제안이다. V01~V04 실물 PIT/OOS 인증을 우회하여 임의의 OOS PASS를 부여하지 않는다. 기존 로드맵 또는 권한을 실제로 수정하려면 별도 ADR과 사용자 승인 필요.
- 사용자 가치: 미학습 구간에서 무너지는 과적합 후보를 더 일찍 걸러내고, LLM이 독립적으로 알고리즘을 설계/진단하여 세대 진화 실효성을 계측.
- 하드 경계: 기존 ChatGPT↔Quant MCP OAuth·고정 URL·대시보드 서비스/인증 변경 금지; 원본 G452·G552, 현재 68/100 세션 `14626d55fb2b461faa485df911920071`와 S7/해시/서명/계보 불변; `orders_enabled=false`, `independent_oos_approved=false` 유지; 보호된 `core/data`, `core/backtest`, `core/evaluator`, `core/validation`, `core/costs`, `core/integrity`는 LLM의 자유 변형 대상으로 노출하지 않는다.
- 다음 100세대는 **새 격리 세션**, 이전 68/100은 삭제·재시작/재계수 없이 보존. 기존 세션의 남은 G69~G100 수행 여부와 새 연구의 100/100은 분리하여 보고.

## 1. 코드·원장 실사 결과 (read-only 확인)
- 실제 인증된 연구 세션 68/100, AWAITING_PLAN; G64 개발 최고 +188.5275%, MDD24.1318%, 청산 40, 평균 노출 67.3077%. 같은 개발 구간 QQQ 비용 기준 단순보유 +187.7724%. +0.7551%p 개발 초과 성과는 미래 우수성을 입증하지 않음.
- 개발 기간은 2020-01-02~2025-12-31; 로컬 파일 `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`. 수정본·원시가격·비-PIT·배당 재투자 미반영. 전략/Pine 간 지표·체결·종료 처리 비교 필요.
- `mcp__Quant_AutoResearch__list_market_data` 에서는 관리형 등록 데이터 0개, Tiingo/KIS 읽기 전용 공급자 모두 미설정: **2026년 검증을 실제 실행할 데이터가 현재 인증된 연구 공급 경로에는 없음**. 데이터 제공/권한 없으면 잠재적 검증은 BLOCKED로 남길 것.
- 기존 구현 재사용:
  - `research/indicator_engine/walkforward.py` = 과거 학습구간에서 두 가지 사전 정의 신호를 선택해 다음 개발 구간을 평가. 현재 범용 GPT 생성 StrategyIR/다중 지표·국면별 루프와 직접 연결된 검증기는 아님.
  - `core/validation/cpcv.py`, `tests/core/validation/test_cpcv_purge_embargo.py` = purge/embargo 분할 유틸과 테스트 존재. 그 자체로 거래 전략의 완전한 미래 정보 격리를 증명하지 않음.
  - `research/indicator_engine/sealed_oos_precommit.py` = 개발 단계 전략/소스 해시·사전 고정 영수증 (자체 서명·독립 보관 인증 없음). **봉인 OOS 결과 접근을 허용하지 않음.**
  - `application/academic_checkpoint_service.py` = 실 GPT MCP 기획→실제 개발 백테스트→근거 ID를 사용한 진단/S7→원장 커밋; 데이터는 동일 개발 구간 반복 사용.
  - `evaluation/academic_campaign_audit.py` = 반복 시험·중복·경제성 및 S7 계보 감사 기초.
- G64의 2026 음수 성과는 사용자 TradingView 관측으로 **신고된 상태**, 원본 재현용 2026 공식 원장이 없음. 기존 Pine에 2025-12-31까지만 신호를 허용하는 제한이 있어 기간과 지표 정의부터 통제해야 한다. 실제 2026 성과 측정 수치를 임의 확정하지 않음.

## 2. 핵심 연구·검증 규칙 — 반드시 사전 고정
1. **데이터 계층 구별**:
   - DEV_TRAIN = 당시 시점까지 이용 가능한 개발 데이터만으로 LLM 가설·파라미터·부모 선택.
   - WALKFORWARD_REVIEW = 학습을 정지한 뒤 이어지는 시간 구간으로 성능 측정. 2023/2024/2025 각 연도 평가 후 결과 공개 시, 해당 기간은 *그 후에 시작하는* 개발 단계에서는 역사적 학습에 재사용 가능. **앞선 단계의 학습으로 역류 금지**.
   - EXPOSED_2026_DIAGNOSTIC = 2026 결과를 이미 사람이 살펴본 바 있으므로 독립 최종 테스트라고 표시하지 않음. 별도 설명·실패 분석 용도로만, 새 100세대 입력은 기본 차단.
   - SEALED_FUTURE / FORWARD = 최종 선택·해시·평가 규칙 확정 **이후에만 새로 도착한 자료**. 독립 공급자 및 권한/승인 전에는 결과 NULL/BLOCKED. 세션 내 자동 접근 불허.
2. **PIT/시점 주의**: 2020~2025를 오늘 관측하는 최신 수정본 원시 Parquet로 워크포워드 시뮬레이션할 수 있어도, 정확히 과거 그날 공개된 바 가격/vintage/기업행동이라고 주장하면 안 됨. `NON_PIT_HISTORICAL_REPLAY` 표시, 필요한 vendor timestamp·raw/adjusted 분리·거래가능시점·타임존·상장폐지 편향 확인; 데이터 미보유시 기존 비용 정책으로 개발 진단만.
3. **LLM 입력 경계**: 미공개 구간 수익/MDD·선택 결과가 LLM prompt/검색·에러 문구/로그를 통해 새 전략 생성으로 누출되지 않도록 응답 JSON 스키마 검사 및 테스트. 후속 시점에 공개된 이전 검증 데이터는 timestamp 로그로 분명히 구분.
4. **100세대 ≠ 100회 백테스트**: 1세대는 새 ResearchIntent/AlgorithmPlan → 실행체결 → 전략별 위험·수익/결정 로그 → 진단 가설 → 동등 대조(S7) 및 다음 계획 → 불변 Evidence/S7 해시 확정. `model_invocation_evidence`가 없는 단순 고정 규칙·mock 루프는 `RULE_POLICY_GENERATION`으로 따로 계수. 모델 사용을 증명할 수 없으면 모델 직접 작성의 확실성/독립 추론을 주장하지 않음.
5. **프리레지스터**: 연구 시작 전에 기간·타임프레임·실제 주문 없음을 명시한 모델/비용/데이터 버전·고정 점수 구조·상위 후보 선정 방식·검증 1회 정책·중단/재개 정책을 별도 manifest에 남김. 최종 검증 뒤 가중치를 바꾸지 않음.

## 3. 구현 작업표: 증상 → 변경 → 실제 통과 기준
| ID | 구현 범위·기존 파일 재사용 | acceptance / 증거 | 선행 |
|---|---|---|---|
| **GEN-P0** 보호·기준선 | 기존 68/100 및 G452/G552 원장 읽기/온라인 백업, head SHA·이력·S7 원장 수·SQLite integrity, Git 작업공간 및 OAuth/대시보드 스냅샷 보존. 기존 연구를 새 연구로 가짜 계승하지 않기 | 해시·세대 동일, git diff 소스에 민감정보 없음, order/OOS OFF. 실패 시 작업 중지 | 즉시 |
| **GEN-P1** 데이터·신호 동등성 | `core/data` 원본은 변경하지 않고 개발 연구 어댑터에서 기간/데이터 해시/영업일/RAW vs 배당조정/거래 비용/지표 구현 확인. G64 `Cutler RSI(SMA)`·`ADX(SMA)`·SMA20, 다음 봉 시가 매매를 TradingView와 바 단위 대조. 재현 불가능 지표는 불일치 명시. 2026 자료 미제공시 OOS 제외 | 첫/마지막 신호·체결시간·입출·누적 현금/수량/비용·포지션·MDD를 고정 fixture에서 일치; 2026에 대한 독립 평가 미실시 상태 유지 | P0 |
| **GEN-P2** 범용 typed WFO | `research/indicator_engine/walkforward.py` 확장 또는 어댑터: 학습 당시 선택한 **복합 StrategyIR/AlgorithmPlan**만 고정하여 타임스탬프 이후의 별도 창에서 실행. 단기 의사결정 feature warmup에만 이전 바를 사용하고 prior window 체결·자본·선택 신호는 test에 혼입 금지. fold별 부모/모델 해시·진입/청산체결 ID·비교군 1:1 로그 | 이후 창의 가격/label을 교란해도 그 창 **이전** 후보·부모/세대 해시 불변, 결제/시점/미래 통제, 접점 누수 방지, 첫 거래 신호 시점 이후 다음 봉 시가. 각 fold의 2023/24/25 성과 보존 | P1 |
| **GEN-P3** 공정 선택/통계 | `evaluation/academic_campaign_audit.py` 및 기존 `core/validation/cpcv.py` 연결. 수익률+MDD+노출·변동성 조정 초과성과+거래 수+비용/최악구간/계승 다양성 비교. 동일 1배 비용/2배 비용, 충분한 표본, 파라미터 근방 성과. 모든 실험 시도·탈락·S7 trial·효과 동일 전략 해시 기록; PBO/DSR은 필요한 샘플·trial 분포·상관 독립성 조건이 충족될 때 **신뢰도 진단**으로만 표시 | `INELIGIBLE_SAMPLE`, `UNAVAILABLE`, `NEEDS_REVIEW`와 0/성공 구별; QQQ 단순보유 대비 및 위험·노출 조정 proxy의 비용/기간 동일; 유효 trial 집계 로그 | P2 |
| **GEN-P4** GPT 진화 연결 | `application/academic_checkpoint_service.py`의 GPT plan/diagnosis/S7 checkpoint에 fold 컷오프·사전 평가 규칙·모델 귀속·후속 연구 의도를 연결. 통제 실험 결과에 따라 학습/탐색/새 복합지표 조합 자유 유지하되 중복·미측정/미입증 부모를 진화 성공으로 인정하지 않음. 모델 provider 미검증·실제 호출 부재 세대는 분리 | 10세대 실 MCP preflight: 유효 원본/진단/근거 거래 ID/S7/다음 부모 10세대 모두 유효, rerun/interrupt 재개 시 단일 계수, 학습 창 밖 읽기 0건, GPT 기획 귀속 10/10 또는 `PROVENANCE_UNVERIFIED` | P3 |
| **GEN-P5** 새로운 100세대 실행 | **기존 68/100과 별개의 session**으로 새 100세대 계획. 추천 연구 예산(조정 가능, 실행 전에 고정): 2020~22 train 기반 2023 검증 **25세대**; 2020~23 train 기반 2024 검증 **25세대**; 2020~24 train 기반 2025 검증 **25세대**; 2020~25 개발 최종 후보 연구·동결 **25세대**. 각 fold 후보 선택 후 단 1회 후속 평가, 다음 fold 시작 전 기존 검증 데이터가 과거 학습 데이터로 이동한 사실 기록. **100 실제 모델 판정** 대조, 백테스트/대조 횟수는 따로 표기 | 새 session 100/100 hash chain, 매 세대 계획/체결/분석/S7 로그, 각 창에 사전 선택 후보 해시와 성과, 등록 예산 이외 자동 실패/중단 보고; 단순 numeric tweak뿐이면 지표 다양성/원인 대조 가치 평가 | P4 |
| **GEN-P6** 최종 후보 봉인·미래 검증 | `research/indicator_engine/sealed_oos_precommit.py` 기존 개발 precommit을 이용해 데이터·AlgorithmPlan/StrategyIR·평가기준·비용·코드 버전 고정. 2026 이미 노출 자료는 `EXPOSED_DIAGNOSTIC`; 사후 개선 없이 별도 자료 공급·봉인/독립 검증(V01~V04 승인)에 따라 미래 별도 데이터 검증. `dashboard/static/fresh-performance.js`에는 DEV / HISTORICAL WFO / 2026 EXPOSED / FORWARD(미검증) 분리, 누적 return·MDD·trades·QQQ·비용·실험 수 표시 | 봉인 전 해시가 변하면 검증 거부, 자료/독립 서명 없으면 `BLOCKED`, 미래 OOS 수익률은 절대 0으로 채우지 않음. 실주문/승인 false 불변 | P5, 후속 V01~V04 |

## 4. 100세대 운영 방식 상세
- 해당 예산 분배 **25/25/25/25는 초기 제안값이지 사용자가 확정한 정책이 아님**; fold당 거래 수·시장 국면이 부족하면 `INSUFFICIENT_SAMPLE` 보고. 추가 데이터를 임의 편입하거나 2026년을 대신 개발 데이터로 사용하지 않음.
- 각 fold에서 GPT는 `training_prefix_hash`까지만 데이터를 토대로 모델 계획 제출. 실험은 전체 백테스트가 아닌 개발 창에서 수행하고 비용·포지션·채택 후 지속 가능성 검사.
- fold 외부 검증을 **같은 fold에서 곧바로 역으로 반복 학습에 사용 금지**. 다음 **시간** fold부터 공개된 과거 데이터로만 이어가며, 이전 테스트가 어떤 시점부터 학습으로 이동했는지 manifest에 기록. 실험 정책 그 자체가 2026 결과를 보고 설계됐다는 정보 오염은 별도로 기록.
- 여러 시장 국면(상승/하락/고변동/저변동)은 **실제 관측일 이전 완료 정보**로만 식별. 국면별 성과는 사전 선택 가능, 최종 구간에서 최고 국면/전략을 다시 맞추지 않음.
- GPT 전략 표현의 자유를 유지하면서 가설 대비 실측 괴리, S7 동일 체결/무효 실험, 부모 재생 성공 여부로 진화 효과 구분. 무작위 동일 연구예산 베이스라인 반드시 병행; 100 GPT 세대에 random 수십/수백 테스트를 섞어 가짜 100 성과로 표기하지 않음.
- 선정: **안전/데이터/최소 검증 가능성 게이트 → 비용 차감·위험/노출 보정의 Pareto frontier → 사전 고정된 선정 규칙**; 수익률 1위만 채택 금지. 최소 거래 수의 임계치는 연구 기간에 맞춰 사전 지정하며 샘플 부족 시 성공/실패 대신 불확실 판정. 단일 2026 음수만으로 기계적 탈락하지 않고 벤치마크·위험·표본 규모를 같이 제시.
- 절대로 `WFO_PASS = LIVE_PROFITABLE`라고 정의하지 않는다. 성공 분리: (1) 엔진/증거 정상, (2) GPT 진화 효과 개선, (3) 독립 미래 예측 실현 가능성 각각 별도.

## 5. 테스트·회귀 품질 게이트
1. **Test-first**: 미래 바 가격 교란과 시점 컷오프 유출 테스트, 이어서 기간 분리/신호 동등성/Evidence 원장/거래비용/다중검정/재시작 테스트 작성 후 구현.
2. 지정된 보호 모듈 및 연구·대시보드 regression, `tests/research/test_academic_walkforward.py`, `tests/core/validation/test_cpcv_purge_embargo.py`, `tests/research/test_sealed_oos_precommit_v04.py`, `tests/evaluation/test_academic_campaign_audit.py`, `tests/governance/test_autoresearch_scope_lock.py` 재사용. 새 모듈 만드는 것보다 현재 계약으로 통합하는 게 기본.
3. Ruff, 변경 범위 Mypy, 필수 통합 pytest/HTTP 200/401, 공격적 에러 테스트, 독립 원장 해시 확인. 전체 테스트/정적검사 미실행 시 각각 `NOT_RUN` 명시.
4. 매 단계 완료마다 영향점, GPT 학습 출처, 데이터·시험 범위, 통과/실패 여부, Git commit/Pushed SHA와 실제 배포 상태, 복구 명령, 다음 선행 의존성을 원장에 남길 것.

## 6. 실패/중단 정책
- 외부 시장 공급자/독립 PIT/OOS 증거가 없다 → **`DATA_PROVIDER_BLOCKED`**. 2026 가짜 수익률 생성 금지; 과거 개발 재생은 별도 범위에서만 가능.
- 100세대 모델이 매번 새로 판단하지 않는다 → **`MODEL_PROVENANCE_UNVERIFIED`**, 실제 100 GPT 자동 진화 성공 NO.
- 학습 구간에서 우수하나 워크포워드가 불리하다 → 우수 부모 계승 차단/재검토, 원인 검증 가설 기록. 탐색 정책의 일괄 중단 대신 다양성 유지.
- PBO·DSR 표본/분포 부족 → 신뢰도 `INSUFFICIENT_SAMPLE`, 0점/임의 성공값 금지. CSCV 결과는 독립 미래 시험을 대체하지 않는다.
- 2026 재사용 자료에서 마이너스 → 진단으로 기록하되 지표/비용/기간 재현 여부 표시; 결과를 학습에 투입한 순간 독립 검증성 소멸.
- 연구 도중 비인가 OAuth/주문권한/봉인 접근/해시·계보 변조 → 즉시 중단 후 롤백/격리, 기존 서비스 및 증거 보존.

## 7. 가장 빠른 가치 전달 순서
- 먼저 GEN-P0~P2를 *기존 코드에 대한 좁은 통합 개선*으로 구현해 fold-selection이 이후 가격 변화에 불변임을 확인.
- 이어 P3/P4를 작은 10세대 진짜 GPT 연구로 실측, 비용·시간/세대/실제 실험 수를 계측.
- 증거 충족 시 P5 새 100세대 실행. 부족하면 숫자만 100으로 늘리지 않고 근거 기반 재개.
- P6은 전체 최종 전략 봉인과 데이터 공급·권한 준비 단계. 미래 실증은 원래 승인 V01~V04에 맞춰 순차 추진.

## 8. 참고
- Bailey et al., *The Probability of Backtest Overfitting* (2017), https://doi.org/10.21314/JCF.2016.322
- Bailey & López de Prado, *The Deflated Sharpe Ratio* (2014), https://doi.org/10.3905/jpm.2014.40.5.094
- 수학적 통계 검증은 모든 수익률이 `NON_PIT_DEVELOPMENT`인 사실을 제거하지 못함.

**최종 승인 필요 사항:** 이 계획은 사용자의 요청으로 정리한 구현 제안이다. 현재 잠금된 로드맵의 단계 재배치, OOS 열람·자산/거래 권한 변경, 외부 모델 API 전환을 승인한 것으로 해석할 수 없다. 제안의 코드 개발을 시작할 때에도 운영 범위/변경통제를 준수한다.
