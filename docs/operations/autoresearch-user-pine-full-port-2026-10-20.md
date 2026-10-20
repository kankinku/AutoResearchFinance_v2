# Quant AutoResearch — 사용자 제공 Pine 11개 완전 이식 착수 / 이식 추적표

작성: 2026-10-20 KST. 범위 Q05/Q10/Q11/Q12/Q18, 기존 T4/S9의 하위 작업. **전체 11개 이식 완료 아님. 정식 세대/주문/운영 배포 없음.**

## 정의 — 언제 '완전 이식'으로 인정하는가

각 원본마다 ① 원문·작성자·라이선스·버전·SHA 확인 ② 시점 보존 계산식·상태기계/신호 구현 ③ 원본의 실제 거래 명령이 있으면 동일 주문 규칙·수량·세션·정산·수수료·갭·인트라바 모델까지 격리 실행 ④ 원본과 Pine bar-by-bar 신호/포지션/체결 교차 비교 ⑤ 우리 엔진의 typed Feature/StrategyIR로 안전하게 표현 ⑥ 개발 연구에서 GPT가 후보로 선택·변경·S7 평가 가능 ⑦ 원본 의도 및 라이선스 준수, 독립 검증을 모두 만족해야 'FULL_PORT_PARITY_VERIFIED'로 인정한다.

- **indicator()는 전략 아님**: 화면상의 entry/SL/TP 선을 거래 체결로 승격하지 않는다.
- **strategy()는 거래 의미 보존 필수**: stop/limit/OCA, 타임존, 피라미딩 등 미지원 요소를 무시하거나 QQQ 1d 근사로 바꾸지 않는다.
- 출처가 CC BY-NC-SA·All rights reserved·라이선스 미확인인 경우 권리 검토 전에 원문 복사/상업적 파생 이식을 진행하지 않는다. 아이디어 분석 및 원본과 무관한 독립 설계는 별도 검토.
- 173개 등록 지표와 Pine 변환 완료 건수를 합산하지 않는다. 기존 core/backtest/cost/integrity, 봉인 OOS, OAuth/MCP URL, 실주문 OFF는 불변.

## 사용자 제공 원본 11개 — 현재 상태

| 순서 | 원본 / 유형 | 출처 | 이식 현황 |
|---|---|---|---|
| 01 | Zeiierman Buyers & Sellers Profile + Dynamic S/R / indicator v6 | CC BY-NC-SA 4.0 | ANALYSIS_ONLY; 코드 재사용 제약, 선형 체결량/피벗·프로파일 구현·검증 없음 |
| 02 | Shaakuni Liquidity Levels & Order Blocks v1.4 / indicator v6 | MPL-2.0 | **CAUSAL_OB_PORT_STAGED**: 기존 `core/features/pine_liquidity_levels.py`의 확정 일·주 고저/EQ와 신규 `research/pine_import/shaakuni_order_blocks.py`의 ATR 스윙 돌파→충격봉→원본 캔들→fresh OB 생성·다음 봉부터 mitigation·confirmed-bar 기반 만료, 전일 고저 Break/Sweep 관측 및 NY 세션 독립 계산. `shaakuni_bridge.py`로 시점·해시 기반 1d 개발 연구 벡터 생성. **TradingView 도형·live timenow·weekend islast 동등성/운영 FeatureRegistry 미검증** |
| 03 | Wyckoff [theUltimator5] / indicator v6 | 라이선스 미확인 | 분석만, Wyckoff 상태/이벤트/MTF 실행 계약 미구현 |
| 04 | BigBeluga Volume Delta Pivot Matrix / indicator | CC BY-NC-SA 4.0 | 분석만. 추정 delta를 실제 호가 체결 delta라 주장하지 않음 |
| 05 | Michael_Fx_Trader RSI Signals Entries / indicator v6 | All rights reserved | 분석만, armed/fired 상태기계 미구현. 직접 복제 제한 |
| **06** | **BOSWaves Trend Target Ribbon / indicator v6** | **MPL-2.0** | **CAUSAL_NUMERIC_PORT_STAGED**: 신규 `boswaves_ribbon.py`에서 ALMA+Wilder ATR+stdev, hysteretic trend flips, conviction/ribbon, 바 단위 *시각적* 포지션·구조 SL·1~4R 목표 도달 상태를 독립 구현. 신규 `boswaves_bridge.py`가 QQQ 1d 개발 데이터의 차트 종료→다음 바 시점 보존 벡터를 typed 연구 자료로 생성. TradingView 그림/알림 전체 파리티와 운영 Feature Registry 등록은 **아직 미검증·미완료** |
| 07 | WillyAlgoTrader Gold Breakout 15M / strategy v6 | 라이선스 미확인 | 분석만, 15분 구간·OCA 두 방향 진입·스탑/강제청산·수량·가드·차트/알림 미이식 |
| 08 | adolgov Stop loss and Take Profit in $$ / strategy v4 | MPL-2.0 | **PARTIAL**: 현금 손절·익절의 틱 거리 계산 `core/features/pine_cash_risk.py`만. SMA교차 주문 및 TV 에뮬레이터 동등성 미구현 |
| 09 | 3Commas Bot / Bj Bot / strategy v5 | 미확인 | 분석만. ATR 추적손절·MTF/세션·실주문 웹훅 구조 미이식 |
| 10 | Daveatt BEST Strategy Template / strategy v4 | MPL-2.0 | 분석만. 외부 1/-1/2/-2 신호, 피라미딩 및 주문 위험 정책 미이식 |
| 11 | mks17 Oscillator Evaluator / strategy v4 | MPL-2.0 | 분석만. 6가지 전략 선택, 혼합 오실레이터, pyramiding=500 등 미지원 위험 동등성 보류 |

**자료 확보:** 2026-10-19 사용자 원본 11개 내용을 담은 과거 대화 첨부파일을 찾아 재확인. 원문 전체는 저작권과 불필요한 코드 중복을 방지하기 위해 리포지터리에 복사하지 않았다.

원본 BOSWaves 업로드(마크다운 변환 포함) SHA-256: `9b8a9fe90a17c488cc6c2f3464e686c1ac0882aee3ab6a338acd3692506760d4` (원시 .pine 파일 체크섬은 별도로 미확정). 원 저작권 표기/MPL 2.0 준수. 사용자 대화에서 이미 작성됐지만 정식 레포에 없던 ALMA 단독 변환본은 이 구현에 원리를 재사용했고 정식 지표 등록으로 **오인하지 않는다**.

## 이번 턴 실제 소스 변경

1. [연구 의미론 포트](../../research/pine_import/boswaves_ribbon.py) — 실거래 주문을 만들지 않으며, 모든 신호는 이미 마감된 바 데이터만 사용. 추세/플립, 표시용 리본, stop/target hit, 이전 봉 구조적 손절을 보존.
2. [학술 연구 자료 연결부](../../research/pine_import/boswaves_bridge.py) — `MarketDataSet(DEVELOPMENT,1d,us_equities)`만 허용, dataset/source/replay hash와 `execution_not_before[t]=timestamp[t+1]` 제공. 신호 이름 `pine.boswaves.bull_flip/bear_flip/trend/conviction`. **실제 GPT 런타임 FeatureRegistry와 운영 MCP에는 아직 미등록**.
3. 테스트 2개 파일: `tests/research/test_boswaves_ribbon_port.py`, `tests/research/test_boswaves_bridge_port.py`. 격리 로컬 등가 초안에 대해 4개 테스트 PASS, GitHub로 반영된 정확한 최종 코드 및 CI는 Moon 실행 환경 오류로 **미실행**, TradingView 원본 데이터 비교도 **미실행**. 테스트 코드가 커밋된 것과 모든 수락 시험 통과는 다르다.

## 다음의 구체적인 작업

**02 Shaakuni 현재 연구용 의미론 구현 단계 완료**: 원본 OB/mitigation 로직을 BAR_CLOSE 관측으로 구현하고 이전 고저/시점 계산을 연구 벡터로 연결. 原 Pine `timenow`/`barstate.islast`를 1d 일자별 백테스트 신호로 사용하지 않는다. 원본 차트와 1:1 확인/Registry 연결 전까지 FULL은 아님. **다음은** 원문-참조 출력을 바 단위로 비교하고 Pine 세션/인디케이터 도형의 비거래 시맨틱스를 검증·보강하는 것.

병행 과제로 현재 06 BOSWaves는 본문 numeric 포트→Pine 출력 비교 시점·ALMA seed/ATR warmup/parity 검증→합격한 feature만 Registry(운영과 분리된 opt-in) 연결→F1~F4 지표 장단점 연구/S7 비교→명시적 운영 승인. **FULL_PORT_PARITY_VERIFIED는 지금까지 0/11**.

다음 단계 선택에서도 사용자의 본래 목표인 GPT의 *부모 약점 → 필요한 지표 특성 분석 → 기존/새 알고리즘 진화*를 위해 지표 모듈로 이식하며, 원본 전략을 그대로 최고 전략으로 등재하지 않는다.

## 2026-10-20 이어 진행: Shaakuni v1.4 연구 의미론 이식

**추가한 코드**
- [OB/POI 계산](../../research/pine_import/shaakuni_order_blocks.py): 원본의 ATR_PERIOD=14, OB_MIN_HOFF=3, swing length=10/지정범위, current-ATR impulse threshold, 이전 스윙 극값 돌파, 반대색 캔들 탐색, 구역 fresh 체크, 생성 다음 봉부터 mitigation, 생성 확정봉 기준 zone lookback 만료. 원본 `showOB`=false 때 새 구역 생성 금지.
- [연구 신호 연결](../../research/pine_import/shaakuni_bridge.py): completed prior day/week high/low, bull/bear OB 확인 시그널, fresh zone 수, mitigation 수를 종료된 봉 기준 연구 벡터로 출력하며 다음 봉 이전 거래 금지. 소스 업로드 SHA-256 `54dabcd62a87df46e0b248ef290ccf3f1346d4b2f5f49ec72b6c68148e703f78`, 원본 MPL-2.0.
- [OB 테스트](../../tests/research/test_shaakuni_order_blocks_port.py), [브리지 테스트](../../tests/research/test_shaakuni_bridge_port.py): 황소/곰 반전 대칭 예제, 새로 생성된 구역 동일봉 완화 금지, 후속 완화·만료, 미래 봉 변경에 대한 과거 신호 불변, 개발 데이터/타임프레임 범위 차단.

**검증 한계:** 테스트들은 **GitHub에 작성 완료했으나 해당 커밋을 실행한 pytest/CI 증거는 아직 없음**(Moon shell `spawn /bin/bash ENOENT`). 소스 Pine과 TradingView 출력을 비교해 확인한 *완전한 parity* 없음. 일봉의 NY session은 원본 `timenow` 현재 실시간 표기와 다르기 때문에 역사적 시점 snapshot으로 분리했고, weekend last-bar shifts는 미래 정보 위험으로 연구 시그널에서는 제외. ATR/OB core 구현 또한 TradingView 내장 `ta.atr` 대비 참조 샘플 검증 전까지 COMPLETE로 표기하지 않음. G350/원본 S7, 보호 원장, 주문 비활성, 독립 OOS 불변. **완전 검증 0/11**.

**후속:** Moon 명령 실행 환경 복구 → 정확한 저장소 커밋의 신규 테스트·전체 Ruff/Mypy·회귀 → Pine 기준 벡터/그림 parity 수락 시험 → 라이선스 준수 모듈만 opt-in feature 등록 → 다음 11개 원본 순차 이식.

## 2026-10-20 인터뷰 확정 이후 P3→P4 조합 경로 (개발 연구 격리)

- [5문답 확정 ADR](../decisions/2026-10-20-pinecode-internalization-5q-user-confirmed.md) — 본 문서의 원본 재현+독립 알고리즘 분해+GPT 자율 창안+격리 검증+실제 연구 사용 완료 기준을 상위 계약으로 고정.
- [타입드 Pine 교차-원리 실험](../../research/pine_import/expression_study.py) — 기존 `research/indicator_engine/expression_ir.py`의 `compile_expression`/`evaluate_expression`를 재사용하고, 연구 브리지 2개의 causally aligned 8개 신호를 이름 붙여 `AND/OR/IF/비교/수치 연산`이 들어간 GPT-작성 수식 정의를 **격리 연구**로 평가. 새 Pine interpreter, eval, Python 실행, 백테스터/주문모듈 수정 없음.
- 결과에 `dataset_hash`, typed algorithm hash, 원본 브리지 해시, 관측값 hash, `next_bar_timestamps`와 `broker_executable=False` / `operationally_registered=False` / `tradingview_parity_verified=False`를 보존. 사용 가능 소스 이름을 8개로 고정하고 미등록 키·boolean 이외의 최종 타입·봉인 OOS를 차단함.
- [조합 회귀 테스트](../../tests/research/test_pine_expression_study.py) 4개를 **작성·GitHub 반영했으나 실행은 미완료**. 검증 환경 Moon shell 오류 때문에 정확한 저장소 커밋의 pytest/Ruff/Mypy는 `NOT_RUN`. 테스트 코드 존재를 PASS라고 주장하지 않음.
- **이것은 GPT가 실험 수식을 투입할 수 있는 opt-in 라이브러리 경계까지만 구현**한 것. 아직 정식 GPT MCP context 자동 노출, FeatureRegistry 검증·등록, S7 부모 전략 변형/계승 및 실제 G351+ 세대의 사용 증거가 없으므로 **P6/P7 미완료 / 최종 내재화 0/11**.

**다음 의존 작업:** (1) Moon 테스트 실행 환경 복구 또는 같은 브랜치에 대한 동등한 CI 설치/실행, (2) Pine 원본 series/이벤트 바 단위 비교 + ATR·시계열 시점 상이점 수정(P5), (3) 검증된 지표만 타입드 사용 허용 및 실제 GPT T4 세대 선택/분석/재계승 실험(P6/P7). 권리 불명확 원본은 그대로 편입하지 않음.

## 2026-10-21 실제 회귀 검증 및 Pine 원본 의미론 수정

- 원본 BOSWaves Pine v6 Active Position 로직 기준 **플립 봉 targetHit 즉시 평가**, stop은 다음 봉부터 평가하도록 수정. Wide-wick 반례 재현 RED→GREEN 테스트 신규 추가. 원본 전체 parity는 여전히 NOT RUN.
- 9개 변경 파일 source commit **974d5f7** push 확인. BOSWaves / Shaakuni / 교차-지표 typed 연구 및 기존 20문답 governance 테스트 **26 PASS**. Repo 전체 Ruff PASS, scoped Pine Mypy PASS.
- 전체 pytest collection 63 ERRORS / 전체 Mypy 31 ERRORS는 새 격리 작업환경의 FastAPI/MCP 등의 전체 dependency 부족으로 인한 실패. 전체 PASS 불가. [증빙 및 후속](autoresearch-pine-port-validation-2026-10-21.md).
- 정식 Pine 원본 내재화 0/11, P5 full parity·P6 runtime registry·P7 GPT 실제 연구 미완료. PineCode는 Python 원리 재구현과 독립 baseline을 병행; 기존 G350 및 실주문 OFF 그대로.

## 2026-10-21 P5 early-window calculation fix and executable test evidence

- BOSWaves Pine source ta.lowest/highest(lookback)[1] needs a full historical window: native partial-window SL risk 6.0 versus Pine-defined 1.5 on regression fixture. RED → GREEN fix made.
- Added independent ALMA/stdev/Wilder ATR source formula checks (2 PASS). Existing Pine/typed-expression/scope-lock tests 29 PASS; full Ruff PASS; full Mypy 294 source PASS; 1,904 tests collected successfully. **Full pytest suite was INTERRUPTED at 185-second timeout, not PASS.**
- Full P5 requires real TradingView exported bar/event comparison; P6/P7 not deployed; **0/11** originals fully internalized. Code commit 271175dbb8d6c56de0dcf4a5dd311946d6e975f2 pushed. [Detailed report](autoresearch-pine-p5-window-2026-10-21.md).

## 2026-10-21 P5 외부 Pine 기준 CSV 검증 도입

원본 archive·dataset·CSV SHA, UTC-offset timestamp, OHLC, 지표/이벤트 봉별 검증. 실제 TradingView 원본 CSV는 확보하지 않았으므로 synthetic 7테스트 PASS와 외부 독립 동등성은 별개. source commit ffb317e Push 확인. Scoped 36 PASS/Ruff PASS/Mypy 295 PASS. Full-suite shard 결과 research 670 PASS, 9 FAIL(외부 G33 snapshot 누락), 17 SKIP; other/integration 3그룹 TIMEOUT. 이식 완료 0/11, P5 외부 파리티/P6/P7 미완료. [관측값 상세](autoresearch-pine-p5-shards-2026-10-21.md).
