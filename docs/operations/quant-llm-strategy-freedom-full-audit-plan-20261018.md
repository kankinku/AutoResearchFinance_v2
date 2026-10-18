# Quant AutoResearch — LLM 자유형 알고리즘 연구 전수조사 및 단계별 개선계획

기준일: 2026-10-18 KST · 작업 성격: **운영·코드 변경 없는 읽기/진단/계획 수립** · Stage: T4 기능 완결 종속(F0~F7), Q01 Q02 Q03 Q04 Q05 Q06 Q07 Q08 Q09 Q10 Q11 Q12 Q13 Q14 Q15 Q17 Q18 Q19 Q20.

## 0. 범위와 요구 해석

**제품 목표:** LLM이 등록된 인디케이터를 자유롭게 선택·추가·조합하거나 필요시 연구·제안하고, 서로 다른 방식의 복합 매매 알고리즘을 설계해 실험 결과로 구조/가중치/국면별 정책/투자 비중/위험 규칙을 수정하는 *자율 연구 엔진*. 사용자의 `if(A>10 and B>20): up_strategy else: down_strategy`는 한 **예시**이며 상승/하락 이분법, 고정된 2~3개 전략 또는 조건문 형식으로 범위를 제한하지 않는다. 시장 국면 판정 외에도 다중 신호 앙상블, 여러 보조 전략의 선택/가중 합성, 위험예산 변화, 보유 중 정책 변경, 종목별 독립 정책, 포트폴리오 의사결정, 연구로 얻은 새 지표를 포괄해야 한다. 상위 목표는 **Q05/Q10 원래 20문답의 범위**이며 새로운 scope가 아니다. 판정은 백테스트가 아니라 진짜 GPT 설계→평가→진단→진화 전체 세대를 기준으로 한다.

**변경하지 않는 경계:** 기본 ChatGPT↔기존 Quant MCP URL/OAuth, 실주문 disabled, 보호된 canonical data/backtest/evaluator/costs/integrity, 봉인 OOS, Q01~Q20·기존 증거 SHA/원장, V05→T4→V01~V04→V06→V07 3단계 판정. LLM은 실거래 주문/외부 임의 프로그램/서버 명령/API 키/보호코드를 쓸 수 없다. 새 연구용 전략 구조는 typed·버전·크기 제한·기존 evaluator 호출로만 실행한다. 시범 구현이 영구적인 별도 백테스트를 만드는 것도 금지.

## 1. 핵심 경로 전수점검 범위와 결과 (source branch `1054211`, pinned T4)

| 계층·대상 | 소스·상태 근거 | 판정·빠진 기능 |
|---|---|---|
| 원본 결정과 개발 범위 | `docs/decisions/2026-10-14-autoresearch-interview-20q.md`, `...2026-10-16-autoresearch-20q-scope-lock-v1.md` | Q05/Q10 자유 조합·조건 분기·가중치·전환은 확정 요구. 최근 T4의 같은 QQQ 전략 임계값 변경은 목표 달성 아님 |
| 지표 등록 | `core/features/registry.py`, `catalog.py`; MCP `list_features` | **173개 등록**, 13개 family. REGISTERED 상태와 실제 입력 연결/수치 유효성/연구 선택 가능은 별개 |
| 실가격 전수 계산 smoke | `core/features/calculators.py`; QQQ 2020-01-02~2025-12-31 원본 1,508봉, 각 후보 1회 안전한 순수 계산 | **135개 하나 이상 유효값, 12개 1,508봉 모두 None, 5개 일반 계산기 호출 예외, 21개 외부/특수 입력 부족**. 이 결과는 계산 가능성 점검이고 수학적 정합성·PIT 인증/성과 아님 |
| 12개 전부 None | dema, klinger, macd_histogram, macd_signal, mass_index, rsi.ema, rsi.wilder, rsx, tema, trix, tsi, zero_lag_ema | 중첩 EMA/초기 결측 warm-up 처리 의심: `_ema`가 앞부분 None 뒤로 초기화하지 못하는 경로. 개별 독립 수학 참조와 prefix-invariance로 교정 필요 |
| 일반 계산 예외 5개 | order_flow_delta, order_flow_imbalance, tpo_profile, volume_profile, weis_wyckoff | `core/features/specialized.py`에 특수 계산은 있으나 `calculate_feature` 일반 경로와 typed input adapter가 분리. 전용 데이터 없을 때 실패 사유를 명시해야 함 |
| 입력 불충분 21개 | day_of_week 및 6개 session 계열, VIX/금/달러/미국·한국·일본 국채금리/QQQ·NASDAQ 등 14개 외부 시계열 | as-of 정렬·존재성·시간 스탬프·라이선스 충족 전에는 `INPUT_REQUIRED`, `PIT_UNVERIFIED`로 분류. 더미 숫자 대체 금지 |
| GPT 초기 학술 지표 | `application/academic_checkpoint_service.py::_catalog`, `research/indicator_engine/algorithm_plan.py`; `catalog-s6-v2.sqlite` | 11개 academic signal 중 VERIFIED 8, PROPOSED 3; **AlgorithmPlan GPT 후보는 현재 8개만**, 나머지 165개 feature와 별도 경로 |
| 규칙 분기·가중치 | `RegimeCase`, `WeightedVote`, `compile_algorithm_plan` | 순서가 있는 **단일 when gate**로 첫 분기 선택, 분기별 binary entry votes 1~8개/score. 최종 단일 entry/exit/regime vector; 모든 분기에서 공통 exit와 100% 포지션. 서로 다른 전략별 independent exit/risk/size 없음 |
| 범용 전략 IR | `strategy_ir/schema.py`, `strategy_ir/compiler.py` | entry/exit AND/OR RuleSet, flat `regime_filters`, fixed RiskConfig, legacy 일부 IndicatorType, feature reference. Boolean/산술 AST·중첩 판정·전략별 독립 정책·상태기계·서브 전략 합성·목표 포지션 벡터 없음. `compile_strategy` 소스는 실행 계획이 아니라 구성 출력 placeholder |
| 실제 evaluator | `core/backtest/engine.py` | 단일/다중 종목, next-open fill, 비용 및 제한적 risk/size는 존재. 그러나 현재 학술 계획 컴파일은 US equity 일봉 **단일 자산**, canonical audit에서 risk.stop/take=0, position_size=100 등 강제, 연구용 다중 정책 실험에는 미연결 |
| LLM 변경 인터페이스 | `research/llm/director.py::ResearchIntent`, `intent_bridge.py` | ADD_FEATURE / ADD_RULE / SWAP_INDICATOR / CHANGE_AND_OR 등 typed patch 표면 존재. 실제 부모 계승에선 `_stage_inherited_plan`이 변형을 허용하되 실행 벡터 보존 제약 때문에 새 지표/신호를 계산·재생하는 경로가 불완전 |
| 계승/재생의 핵심 blocker | `application/academic_checkpoint_service.py::_materialize_inherited`, `research/llm/autonomous_cycle.py::advance_inherited` | feature_values·replay가 부모와 같아야 함. **신규 계산 feature 추가 시 새 feature values·replay를 생성/감사해야 하는데 현행에는 없음**. duplicate effective signal은 늦게 감지되어 진단 checkpoint를 INTERRUPTED로 만들 수 있음 |
| 연구 기억·진화 | `cross_generation_memory.py`, `adaptive_direction.py`, `economic_feedback.py`, `lineage_selection.py` | 실험·해시·부모·경제성과 힌트 존재. 다만 단일 좋은 부모 주변 변형/필터 임계값 수정 반복, 알고리즘 family 다양성·새 출발·novelty 보장 및 session간 원장 계승 부재 |
| 증거·경제 검증 | `decision_audit.py`, `inherited_decision_audit.py`, `development_economics_v05.py`, S7 | 실제 체결/비용/QQQ/MDD 추적·S7 검증 장점 보존. 재사용 개발 기간은 **non-PIT**, 후보 다중탐색 및 인과·독립 OOS·실체결 실현수익성 승인 불가. 기존 연구 결과를 수정/미화하지 않는다 |
| 데이터·PIT | `core/data`, `research/indicator_engine/*asof*,*vintage*,*oos*` | 연결된 MCP 가격 입력은 QQQ raw/조정, QQQ 2026 raw, SPY raw. 외부 지표 실데이터와 타이밍 증빙 별도 필요 |
| 실행/배포/운영 | 기존 32 MCP tools, `scripts/run_academic_autopilot.py`, dashboard | GPT는 외부 **연결 ChatGPT**가 호출해야 하며 서버 기본 MCP가 무인 자기 호출하는 구조 아님. 세션 100 한도, 신규 session에 prior S7 child/학습 해시 자동 계승 안 됨. Dashboard supervisor 자동시작 수정은 별도 이전 작업; Windows 재부팅 미검증 |
| 품질 게이트 | 기존 262개 `test_*.py` 파일(소스 트리 집계); 통합 이전 1,729 PASS 기록 | 본 **조사 회차는 전수 pytest, 운영 HTTP, OOS, 재배포를 실행하지 않음**. 이전 전수 PASS는 현재 신규 AST 기능에 대한 증거가 아니다 |

**실측 기초:** `GET /quant list_features` 173, 학술 catalog SQLite SELECT=11(VERIFIED 8), `research_feature_specs()`=173, 실제 QQQ 1508봉에 각 일반 feature 순수 계산 테스트=135+12+5+21, 최근 연결 100세대 세션/정식 전역 G200 완료 확인. 67개 계승 세대 feature set 동일. 계산 smoketest에 `None`이 없는 지표도 단위/시간 정렬/수치 편차/독립 라이브러리 비교에 실패할 수 있으므로 `VALIDATED`가 아니다.

## 2. GitHub 프로젝트·논문 기술검토 및 채택 판정

2026-10-18 외부 공식 README, 원 소스, 학술 논문 초록/원문 공개 정보를 대조. 출처·라이선스는 도입 시 재검증한다. 투자 성과 보고치는 제3자 주장으로만 취급한다.

| 외부 연구/프로젝트 | 근거 및 활용 가능한 설계 | 권장 결정 / 금지 |
|---|---|---|
| Microsoft Qlib, https://github.com/microsoft/qlib; 논문 https://arxiv.org/abs/2009.11189 | 지표 수식 연산자 AST, cache 재사용, 데이터-모델-평가 workflow 분리, 실험 재현성 | **아키텍처 참고 P0**. 외부 포괄 엔진 교체 NO |
| Microsoft RD-Agent, https://github.com/microsoft/RD-Agent; https://arxiv.org/abs/2505.15155 | 연구 가설→구현→평가→feedback→다음 방향, factor/model 동시 진화 및 적응적 research arm | **계획·실패 가설·연구 예산 정책 P1**. 별도 multiagent/code sandbox 기본 도입 NO, 기존 GPT MCP 유지 |
| QuantConnect LEAN, https://github.com/QuantConnect/Lean; https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview | alpha/portfolio construction/execution/risk model 분리, 다수 alpha의 합성 | **정책 계층 분리 P0**. LEAN 런타임으로 전면 전환 NO |
| AlphaGen, https://github.com/ICT-FinD-Lab/alphagen | 연산자·피처 기반 수식 트리 진화 및 alpha portfolio synergies | **유한 typed AST/신규 후보 family 설계 P0~P1**. 설명 없는 RL 신규 훈련 부담/성능 약속 NO |
| DEAP, https://github.com/DEAP/deap | strongly typed genetic programming, tree mutation·crossover, NSGA-II Pareto | **typed 변이기 설계 참고 P1**. 의존 패키지 직접 채택은 license/security 검토 후 |
| pyribs, https://github.com/icaros-usc/pyribs; https://doi.org/10.1145/3583131.3590374 | MAP-Elites/quality-diversity archive, 우수 전략 다양성 유지·탐색 출발점 분산 | **family/behavior archive 원리 적용 P1**. 별도 최적화 엔진 선행 대규모 교체 NO |
| Optuna, https://github.com/optuna/optuna | RDB persistence/heartbeat, mixed/conditional parameter selection, multi-objective support | **수치/가중치/파라미터 tuning 보조 P2**. 구조 설계 자체를 Optuna 수치 튜닝으로 대체 NO |
| Freqtrade, https://github.com/freqtrade/freqtrade, https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md, https://github.com/freqtrade/freqtrade/blob/develop/docs/recursive-analysis.md | 표본 전 시점 계산에 따른 미래정보 누출 탐지, warm-up 길이/재귀 지표 일관성 검사, callbacks 참고 | **미래누출/재귀 계산 metamorphic tests P0**. GPLv3 코드 직접 복사 금지, 설계·테스트 개념 참고 |
| vectorbt, https://github.com/polakowo/vectorbt, https://github.com/polakowo/vectorbt/blob/master/LICENSE.md | signal factory/indicator factory, 대량 후보 저렴한 사전 탐색 | **optional shadow/검산 벤치 P2**. Apache2+Commons Clause 상업화 제약, 채택 전 법적 검토. canonical evaluator 절대 대체 NO |
| Hamilton (1989), https://ideas.repec.org/a/ecm/emetrp/v57y1989i2p357-84.html | 관측 불가한 market state를 추정하는 Markov regime switching | **선택 가능한 시장 분류 연구 후보 P2**. 상승/하락 사전 하드코딩 금지; 레짐 추정의 PIT 재계산 필수 |
| Bailey·López de Prado DSR (2014), https://doi.org/10.3905/jpm.2014.40.5.094; Bailey et al. PBO (2017), https://escholarship.org/uc/item/4w1110bb; White Reality Check (2000), https://doi.org/10.1111/1468-0262.00152 | 탐색 반복/최고 전략 선택 편향 및 OOS 과적합 확률·다중검정 | **최고 전략 채택 증거를 조정 P1~V07**. DSR·PBO 수치가 미계측·기준 미충족이면 PROVISIONAL 표시, 임의 '유의' 판정 금지 |
| Purged/time-series CV 참고 구현 https://github.com/eslazarev/purged-cross-validation | 시계열 label horizon에 맞는 purge/embargo/WFO/CPCV | **실제 예측 label horizon 있을 때만 P2/V01~04**. 단순 매매 시뮬레이션의 별도 OOS처럼 포장하거나 무조건 KFold 적용 금지 |

라이선스 메모: Qlib/RD-Agent MIT, LEAN Apache 2.0, Optuna MIT 확인; Freqtrade GPLv3, vectorbt Apache2+Commons Clause 사용 주의. 처음에는 구현 원리를 참고하는 수준이며 외부 코드 무단 복제·vendor lock-in/출처 은폐 불허.

## 3. 목표 알고리즘 표현력 — 예시가 아닌 범용 설계

기존 StrategyIR v1을 삭제하지 않고 **StrategyProgramIR v2 (versioned)** 를 작성·검증한다. 임의 LLM Python 실행이 아니라 *bounded typed graph/AST*:

1. **FeatureExpr:** 등록된 feature ID / 버전 / source·as-of / 타임프레임 / lookback / 유형·단위·시차. 수치 벡터에 상수, 연산, 안전한 정규화, lag, 통계·롤링·상관·차분 등을 typed node로 합성한다. 분기 중첩 없는 지표 계산도 새로운 feature로 승격할 수 있도록 합성 identity hash.
2. **PredicateExpr:** <=, >=, cross, between, boolean AND/OR/NOT 및 깊이 제한 있는 중첩, 결측/미확정시 명시적 fallback. 여러 지표를 자유롭게 AND/OR 구성할 수 있으나 특정 지표 구성을 강제하지 않는다.
3. **PolicyNode:** entry / exit / hold / risk / stop / trailing / target_exposure / rebalancing / asset selection / flat. 각 정책이 자체 식·기간·비용·위험 모수를 갖고 진입과 청산이 공통 규칙으로 묶이지 않도록 한다.
4. **ControlNode:** conditions에 따른 switch/priority routing, weighted mixture/voting/ensemble, policy composition, nested finite-state regime transitions with explicit transition actions. 우선순위/동률/포지션 보유 중 정책 변경/주문 목표 변화 규칙을 정의한다. 단일 long-only 시작은 안전한 구현 단계이지 상위 제품의 한계로 영구 고정하지 않는다.
5. **PortfolioNode:** target-weight 벡터, 현금, 위험 예산, 종목별 exposure, 비용/회전 제한, 유동성. 시장/자산 추가는 data rights와 독립 시점 검증 후 확대한다. leverage/short/order 권한 기본 비활성.
6. **ResearchGraph mutation:** GPT가 새 프로그램 처음 생성 / 기존 프로그램 구조 재작성 / 고급 feature 추가 / 브랜치 편집 / policy 교체 / weight 학습 / subtree crossover / regime change를 제안하는 typed variant. 단순 숫자 조정만 강요하지 않는다.
7. **Proof/provenance:** AST normalized canonical hash, input availability/as-of, feature math version, IR-to-signal replay, entry/exit/target transition reasoning trace, realized fees/slippage, before-after paired diff. 동일 경제지표지만 다른 신호는 다른 후보, 진짜 동일 effective signal은 사전 rejected, 세대 미소모.
8. **Resource/safety bounds:** 임의 `eval/exec/import`, 외부 프롬프트 지시/URL 읽기, native dynamic Python plugin execution, order execution 금지. AST 최대 노드/깊이/feature 수/최적화 시도/메모리·CPU·wall budget 버전으로 관리. 검증되지 않은 source는 명시적 상태로 격리.

사용자 예시 시장별 2전략 분기는 `Switch(Predicate(A,B), PolicyA, PolicyB)` 의 한 형태일 뿐. GPT는 `WeightedEnsemble(Policy1,Policy2,Policy3)`, `Switch(RiskRegime, MeanReversion, TrendFollowing, Flat)`, `VolTarget(Policy)`, `OnFailure(SwitchFamily)`, `AssetSelector(Portfolio)` 및 더 복잡한 타이핑된 트리를 설계·변이할 수 있어야 한다. NONE/unknown/insufficient warmup branch 처리 별도 테스트.

## 4. 실행 계획: 테스트·증거 중심의 최소 단계

| 순서 | 작업 ID / 구현 범위 | 수락 기준과 실제 사용자 가치 |
|---|---|---|
| 0 | **F0 기준 동결·소유권**: 현재 canonical cost/backtest·MCP/OAuth URL·G101~G200 증거 golden SHA/실제 원장 읽기 전용 백업, 변형 연구 과거 경로 불변. 각 stage 테스트/롤백 가드 작성 | 기존 G100 local evidence/replay 동일, 주문 off, URL/OAuth 불변. 이 단계는 연구 기능 구현을 대체하지 않음 |
| 1 | **F1 지표 완전 연결**: 단일 feature registry/list for all 173, `REGISTERED`와 실행 적격/원 데이터 상태 분리. 12개 전부 None 원인 수정(EMA/warmup), 5개 specialized adapter, 21개 외부 입력 missing/as-of preflight, 지표 산출 hash/version, cache/determinism | 173/173 각각 `READY_AND_AUDITED` / `DATA_REQUIRED` / `MATH_REVIEW` / `QUARANTINED` 상태와 이유·소스·버전 기록. 실제 QQQ 원본 OHLCV 147/147 계산 + 무결성/단위/prefix/reference 테스트 통과가 목표(현재 135 유효, 12 결함), 특수·외부 26은 실제 입력 없을 때 거절하고 dummy 보충 금지 |
| 2 | **F2 ProgramIR v2 + typed expressions**: 기존 v1 무변경·버전된 변환기, predicates, expression nodes, policy graph, mixtures, branches, independent position/risk targets, AST canonicalizer/type checker | LLM 제시한 서로 구조적으로 다른 ≥10개 프로그램을 스키마로 표현: 단일 추세, 역추세, multi-timeframe, ensemble, multi-branch switch, nested conditions, risk overlay, holding exit switch, variable sizing, flat fallback. 유효한 부분그래프만 mutation. 구조가 다른 두 프로그램이 잘못 같은 hash로 합쳐지지 않음 |
| 3 | **F3 canonical executor/trace adapter**: F2 AST를 causal values·desired target/decision graph로 변환 후 **기존 canonical 비용·체결·포지션/타이밍 의미를 재사용**, v1과 golden parity를 증명. protected core 변경은 별도 검토/승인된 코드 경계·리뷰·테스트에 한정, LLM 직접 수정 금지 | 같은 v1 전략이 v2 wrapper에서도 fill/fees/equity 동일; 다양한 정책을 보유 중 바꿔도 목표 잔고·매매비용·체결 시간 재현, lookahead/timezone/point-in-time/portfolio reconciliation 테스트 통과 |
| 4 | **F4 자유형 GPT 생성·수정 + S7**: `start_algorithm_research` 입력 및 inherited S2/S7 버전드 지원, 새 feature recompute/replay, AST/subtree/param/risk/weight changes; typed preflight와 사전 중복 거절. 오류는 세대 미소모·비중단; 상용 모델 API 기본 호출 없음 | 새로운 지표 추가와 **feature-vectors 변형**을 직접 제출한 실 GPT Plan→S2→지표 당시 값·fill IDs·원인 분석→S7→다음 후보 순환 ≥10세대 완결. 각 세대 해시·결정 근거·데이터·수익/MDD·benchmark, 취소/재개/idempotency 확인 |
| 5 | **F5 연구 다양성·기억·계승**: distinct family/program AST archives(quality-diversity), novelty/distance, separate random from-scratch + targeted mutation + hypothesis ablation arms, data-driven budget with nonzero exploration, plateau diagnosis; 100세대 세션 rollover provenance | 최소 3개 전략 family에서 신규 프로그램 도출, 기존 최고 전략이 독점하지 않는 seed/계열 다양성; 동일 신호 사전 탈락; 부정적/미확인 실험 보존; source-session → new-session StrategyIR+source data+S7+memory hashes 감사로 연속 100세대 이상 가능함을 증명 |
| 6 | **F6 타당성·효율 최적화**: DAG caching keyed by feature/version/input/as-of, incremental warm-up, cost-aware reject, deterministic parallel candidate eval, failure/root-cause logging, walk-forward & random/control fair budget, DSR/PBO/White-style selector diagnostics only with appropriate input | cold/warm cache 결과 바이트 동일; partial-prefix no future leaks; 동일 비용·시간·데이터로 GPT/random/local mutation arm 비교; 선택 과적합 미승인시 “development only”; 10개 유형의 전략에 대한 국면별 손익·위험·체결 ID 보고, 분산·최악 구간과 QQQ 위험 맞춤 비교 |
| 7 | **F7 릴리스·확대**: 독립 test/rollback, paper-only deploy, 기존 MCP URL 유지, dashboard에 feature coverage/family archive/novelty/generation/runtime/memory/S7 state 추가. F4~F6 성과가 확인되면 20→100 실제 GPT 세대 | 샘플 10세대에서 구조 다양성·비중 변경·분기별 다른 처분·계승 등 증명된 후 20/100 단계로 확대. 독립 PIT/OOS/실제 거래 순수익은 별도 V01~V07 게이트 통과 시만 GO |

**실행 순서 변경 여부:** 기존 사용자 승인 V05→T4→V01~04→V06→V07은 **변경하지 않음**. F0~F7은 최초 Q05/Q10을 빠뜨린 채 ‘같은 부모 임계값 100회’로 진행하지 않기 위한 T4 내부 단계이며, 추가 검증 프로젝트를 무기한 추가하기 위한 것이 아님. 실제 구현 착수 시 브랜치 분리, 테스트 먼저, commit/push, master ledger 갱신 후 staging·rollback 검증; 한 단계 합격 후 다음 단계를 진행.

## 5. 실전 수락 실험 (결과 만들어내지 않을 것)

- **지표:** 173개 전체 manifest/타입/데이터 상태 판정. 현재 12 ALL_NULL에는 과거 관측값 기반 참조 계산과 잘린 prefix의 동일시점 결과가 같다는 metamorphic 검사. 무분별한 원본 뒤쪽 채우기 금지.
- **자유도:** GPT가 feature를 새로 선택해 처음부터 StrategyProgramIR 생성하고, 다중 branch/mixture/동적 sizing/hold-state exit·portfolio weight·risk nodes를 조합. 단순 threshold 변경의 비율, 신규 AST shape·사용 지표 종류·실효적 fill 변화·전략-family diversity를 수치화.
- **시장별 전환 테스트:** 서로 다른 3개 이상 정책이 서로 다른 상황에 선택되고, 각각 자체 entry/exit/position size를 사용하며, 보유 중 전환 시 설정된 liquidation/keep/rebalance 동작대로 next-open fill. A/B 예시 한 가지 하드코딩만 검사하면 수락 불가.
- **무결성:** 코어 비용·샘플 선택·실행시간/제어 권한·PIT 및 sealed OOS를 연구자가 손댈 수 없어야 함. 경제 결과가 부모 대비 같다는 이유로 유효한 다른 전략을 거짓 중복으로 배제하지 않고, 동일 신호 중복은 Plan preflight로 비중단 거절.
- **탐색:** 실제 GPT 신규 family 3개 이상, random from-scratch 별도 실험, 동일 예산 비교, 보상 아닌 **독립 데이터에서 유의한 증거 없으면 알파 미입증** 표시; 10~20세대 후 효과가 없으면 연구 목표/증거의 병목 분석.
- **안정성:** 정전·중단·checkpoint restore·재실행 2회 모두 이미 커밋된 SHA 유지, 세대 증가 중복 0, 100단위 session rollover parent/S7 memory 서명 연속성, dashboard 자동 재시작/401 보호/주문 0.
- **성능:** 일봉 1508봉 173 후보에 대한 CPU·메모리·캐시 최적화 실측; 전/후 중앙값과 tail latency를 기록. 정확도 손실 없는 성능 향상일 때만 채택. exact latency 목표는 baseline 측정 후 제안.
- **경제:** 반복 QQQ 2020~2025 개발기간 수익률만으로 연구 성공 선언 금지. PIT/OOS 불확실성·선택편향·비용·실현가능한 규모와 benchmark 노출률 차이를 표기하고, 독립 평가 입력 없는 통계치(N/A)는 감추지 않는다.

## 6. 위험 / 제한 / 보류

1. `173 REGISTERED`는 `173 VERIFIED CORRECT`가 아님. 특히 단일 QQQ로 금리·세션·orderflow/volume profile 자료를 만들 수는 없다. 26개 입력 의존은 확보 전 `DATA_REQUIRED` 처리.
2. 동적 정책을 완전히 지원하려면 canonical 목표 포지션/비용 계약의 명시적 버전 확장이 필요. backtester를 무심코 수정해서 과거 증거 SHA를 깨뜨리면 안 된다.
3. 지표/문법 자유도가 올라가면 탐색 후보가 급증하여 overfitting 위험 증가. 데이터 결함·lookahead·복수시도 통계·OOS 잠금을 동시에 강화.
4. 모든 173개를 매 후보에 강제로 쓰지 않음. LLM에게 조건을 충족하는 **전체 카탈로그 접근권**을 제공하고 필요한 subset을 선택하게 할 것.
5. F0~F7 코딩/배포 **NOT STARTED**. 현재 작업은 목표·전수 경로·실데이터 계산 상태·외부 자료 조사만 완료. 실 GPT 100개 신규 세대, 성능개선, OOS/실주문은 전혀 달성한 것으로 보고하지 않는다.
6. 신규 데이터 소스/라이선스·대용량 의존성·원격 코드/모델 서비스는 별도 검토, 사용자 미승인 비용·권한 변경 금지. GPT-MCP 기존 주소와 session audit 증거를 보존.

### 다음 즉시 개발 단계

**F0** 완료 조건을 freeze & preflight로 최소화한 뒤 **F1의 12개 실제 계산 결함과 catalog-to-GPT 연결**을 바로 해결할 것. 병행하여 F2 typed AST/Policy 설계 및 F3 golden parity 테스트를 먼저 작성한다. 단순 임계값 추가 100세대는 새 전략의 발명·진화 능력을 증명하지 못하므로 F4 기능/실GPT 10세대 수락 이전 추가 완료 주장 금지.
