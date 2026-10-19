# Quant AutoResearch — 사용자 제공 Pine 코드 1차 분석 마감 및 전략 언어 발전안

**2026-10-19 KST · 결론 상태: `PHASE1_ANALYSIS_CLOSED` / `FULL_PORT_NOT_DONE`**

범위: 사용자 제공 Pine 11개(첫 3개 + 다음 4개 + 다음 4개)에서 필요한 *알고리즘 설계 언어·연산자·실행 계약*을 도출하는 1차 분석. 별개로 TradingView 게시 페이지에서 선정한 25개 메타데이터 후보는 코드 전문·라이선스 검증·백테스트 대상이 아닌 발견 목록이며, 두 집합의 단순 합산을 완료 이식 수로 표현하지 않는다.

## 1. 제공 자료에서 드러난 요구

| 사용자 제공 스크립트 | 원본 유형 | 확인된 주요 구조 | 결과 / 우선 시사점 |
|---|---|---|---|
| Zeiierman Buyers & Sellers Profile + Dynamic S/R | 지표 | 가격대별 거래량 추정, 피벗 확정, 흡수·증거 점수, 활성 레벨 교체·폐기 | 가격 수준 오브젝트·상태 누적 / CC BY-NC-SA 4.0 직접 재사용 제한 검토 |
| Shaakuni Liquidity Levels & Order Blocks | 지표 | 완료된 일/주 고저점, EQ, 돌파·ATR 임펄스 오더블록, 세션 | 완료 기간 값 계산 일부만 구현; 오더블록/세션 미구현, MPL-2.0 |
| Wyckoff [theUltimator5] | 지표 | 매집/분산 A–E 단계, 후속 이벤트, 다중 타임프레임, 구조 이력 | 이벤트 상태기계·확정 시점·MTF 정렬 / 원본 라이선스 미확인 |
| BigBeluga Volume Delta Pivot Matrix | 지표 | 피벗 양쪽 확인 지연, 추정 델타, 활성 지지/저항 수준 폐기 | 실시간 델타 아님(OHLCV 근사); 확정 지연 검증 / CC BY-NC-SA 4.0 |
| Michael_Fx_Trader RSI Signals Entries | 지표 | RSI 영역 진입마다 armed/fired 상태, 캔들 필터, SL/TP 가격 표시 | 상태기계·일회성 이벤트 / 'All rights reserved' 선언, 원본 코드 이식 보류 |
| BOSWaves Trend Target Ribbon | 지표 | ALMA+표준편차+ATR 추세, 추세 전환, 고정 R 다중 목표 시각화 | ALMA 단독 로컬 변환 실험은 있었으나 **Moon 정식 기능 등록 없음** / MPL-2.0 |
| WillyAlgoTrader Gold Breakout 15M | 전략 | 서버 시간대 00–07시 범위, 양방향 stop, OCA, 거래일 1회, 시간 청산, 계좌 위험별 수량 | 일봉 전략 아님; 주문 상태·세션/DST·체결 모델 필요 / 소스 라이선스 미확인 |
| adolgov Stop loss and Take Profit in $$ | 전략 | SMA 14/28 교차, 손익 현금 예산 → 틱 거리 변환 | 현금/틱 변환 일부 독립 구현, 원본 체결 동등성 미검증 / MPL-2.0 |
| 3Commas Bot / Bj Bot | 전략 | MA 종류 전환, ATR 변동 추적손절, 시간 필터, 역방향 전환, 웹훅 | 전략 이벤트·위험 상태 및 안전한 order adapter / 소스 라이선스 미확인 |
| Daveatt BEST Strategy Template | 전략 | 외부 신호의 long/short/close, 피라미딩, 손절 유형 전환, 거래 횟수·연속 손실 제한 | 신호와 실행의 분리 / MPL-2.0 |
| mks17 Oscillator Evaluator | 전략(분석 도구) | 기간 혼합 오실레이터 및 6가지 진입 메커니즘, pyramiding=500 | 합성 입력·전략 모듈 비교·고위험 파라미터 상한 / MPL-2.0 |

**분류:** 지표 6개 + Pine 전략 5개. 분석 완료는 Pine 실행 검증을 의미하지 않는다. CC BY-NC-SA, 저작권 유보, 미확인 라이선스에는 별도 허가 검토 전 코드 직접 편입 금지.

## 2. 현재 Moon 능력과 실제 부족한 부분 (코드 기준)

- `strategy_ir/schema.py`: 조건은 비교·교차 + 한 단계 `AND/OR` RuleSet. 지표·FeatureRef·단순 RegimeFilters·백분율 위험 설정은 있음. 중첩 불리언/산술 표현식, 이벤트 상태·주문 타입·동적 비중/여러 익절을 동일 IR에서 선언할 수 없음.
- **중요: 분기와 가중 투표 자체는 이미 존재함.** `research/indicator_engine/algorithm_plan.py`의 `RegimeCase`는 순서대로 첫 일치 케이스를 선택하고 `WeightedVote`를 집계. 단, 현재 컴파일 경계는 검증된 바이너리 지표, 1d US equities, single asset, long/FLAT, 100% 고정 포지션, next-bar, 연구 전용으로 제한된다. 기존 S3 구현을 '미구현'으로 재개발하지 말 것.
- `research/indicator_engine/strategy_adapter.py`는 개발 데이터에 대한 보수적 체결·거래 감사 경로가 있으나 원본 Pine의 OCA/stop-limit/분할/시장가·틱·인트라바 우선순위를 재현한 것은 아님.
- `core/features/pine_liquidity_levels.py`, `core/features/pine_cash_risk.py`는 실제 repo에 존재하는 **독립 계산 부품 2개**. Registry와 StrategyIR에는 아직 연결되지 않아 LLM의 가용 기능으로 셀 수 없음.
- ALMA Pine 변환은 이전 턴 로컬 산출물로만 생성되었으며 이 브랜치 런타임/FeatureRegistry 등록은 확인되지 않음. 라이선스, 출처·버전 고정, 수학적 동등성, TradingView 신호/체결 비교는 별도 게이트.

## 3. 추천 개선 순서 (고정 로드맵의 S9/T4 종속 개선안, 별도 단계 승격 아님)

| 우선 | 작업 | 구체적 스코프 | 첫 수락 테스트 |
|---|---|---|---|
| **A** | 검증된 지표를 **LLM에 실제 노출** | FeatureSpec/Registry 연동, 계산기의 PIT·시간 정렬·소스·라이선스·해시; 사용 가능한 feature 목록과 구현 실제 일치 | 검증 미완료/미허가 source fail-closed; source → timestamped series → plan 참조 통합 테스트 |
| **B** | AlgorithmPlan/StrategyIR의 **표현력 확장** | 중첩 AND/OR/NOT, 비교/산술, 변형 가능한 국면별 entry/exit/position policy, 이벤트 상태(arm/fire/reset), 다단계 피벗·오더블록·Wyckoff | 참조 타입/이벤트 타이밍 유효성; 미래 피벗을 확정 전 거래하는 시도를 거부 |
| **C** | 주문·청산 **시뮬레이션 계약** | 다음 봉 체결, market/stop/limit, OCA, 분할 청산, 추적손절, 부분·반전, 거래 시간대·DST, 수량·틱·통화·수수료 | Gold ORB를 15m 합성바로 재생해 동시에 체결 불가·하루 1회·장종료 청산 확인 |
| **D** | 자산·노출 위험정책 | cash/%/ATR/R 손절, 포지션 수량/최대 레버리지/잔여 노출, 브레이크이븐·거래 수·연속 손실 가드 | 리스크 예산·틱 반올림·갭 손실을 별도 측정, 100% 고정 비중을 요청 시 명시적으로만 해제 |
| **E** | 실증적 동등성·연구 진화 | TradingView 원본 거래/시점 비교 → 독립 PIT/OOS → LLM의 실패 가설/대조 실험/부모 승계에 새 기능 활용 | 동일 기간 거래 이벤트·비용·PNL diff와 원인 분류; 모델 개선은 독립 대조로 입증 |

A→B→C→D→E는 **기술 의존성 권고**이며, 사용자 승인 범위 `V05 → T4 → V01~V04 → V06 → V07`를 변경하지 않는다. 기존 20문답 Q05/Q10/Q11/Q12/Q18 목표를 구체화하는 분석이다. 기존 protected `core/backtest`, costs, evaluator, integrity, sealed OOS, OAuth/URL 및 주문 권한은 수정·완화하지 않는다. 실행 모델 기능 변경은 위험 검토·명시 승인을 먼저 거친다.

## 4. 즉시 회피할 오류

1. `indicator()`를 진입·청산 전략으로 가정하거나, 시각적 목표가를 실제 익절 체결로 간주하지 말 것.
2. 확정된 피벗을 '과거 피벗봉 시각'에 매매 가능했다고 소급하지 말 것. Wyckoff MTF·`timenow`·실시간 캔들 상태와 차트의 사후 표시는 엄격히 분리.
3. OHLCV 봉 종가 위치에서 추정한 delta를 진짜 bid/ask 체결 Delta로 이름 붙이지 말 것.
4. 장중 전략을 1d QQQ 테스트에 억지로 넣거나 TV 백테스트와 일치한다고 주장하지 말 것.
5. '소스 후보 25개', '사용자 원본 11개', '독립 계산기 2개', '완전 이식 전략 0개'를 혼동하지 말 것.

## 5. 1차 종료 판정

**종료 대상:** 사용자 제공 11개 Pine의 역량 갭 식별과 순차적인 기술 개선안. **미완료:** 11개 원본 모두의 Pine 실행 동등성, StrategyIR 원형 이식, LLM 접근 가능한 정식 FeatureRegistry 등록, 독립 백테스트 성과. 실거래 여전히 OFF, G350 기존 연구 원장 변경 없음. 이 작업으로 새로운 '정식 세대'는 만들지 않는다.
