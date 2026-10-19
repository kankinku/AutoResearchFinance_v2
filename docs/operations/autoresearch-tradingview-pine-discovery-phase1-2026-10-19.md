# Quant AutoResearch — TradingView 공개 Pine 전략 카탈로그 1단계
**선정일: 2026-10-19 · 상태: `DISCOVERED_METADATA_ONLY` · 조사/선정 15개, 원본 Pine 전문 0개, 코드 SHA-256 검증 0개, 실제 백테스트 0개.**

## 범위·승인·실제 완료
사용자가 요청한 1단계는 *공개 Pine Script 전략 10~20개를 선별하고 구조를 정규화하는 작업*이다. 원본 20문답의 **Q05·Q10·Q11·Q12·Q18**, 기존 **S9 지표/전략 소스 다양화**의 보조 조사이며, 새로운 별도 성과 검증 단계나 기존 승인 로드맵 교체가 아니다. T4 실제 GPT 원인 진단, V01~V04 PIT/OOS, V06 paper, V07 GO/NO-GO 순서를 유지한다.

**완료:** 공식 게시 페이지 기반 전략 15개 메타데이터(저자, URL, script id, 페이지상 공개 상태, 계열, 대략적 진입·청산 개념, 난도, 엔진 차이, 우선순위)를 `research/pine_import/phase1_catalog_2026-10-19.json`에 정규화했다. 원본 코드의 지문/소스 해시, Pine 런타임 버전 및 라이선스 헤더는 전부 **미검증**으로 남겼다.

**하지 않음:** 원본 Pine 소스 내려받기/실행, Git 재배포, 전략수익 검증, 자동 포팅, 논문 검증, 운영 DB·MCP·OOS·실주문·평가기·비용 함수 변경.

## 공개 소스 게시 페이지를 확인한 15개
이 순서는 **인기도 순위가 아니다**. 공개 페이지에서 확인한 메타데이터와 현행 QQQ 일봉 엔진에 대한 구조적 다양성/구현 난이도로 선정했다. 페이지의 영문 설명은 코드의 실제 의미와 다를 수 있어 모든 규칙은 **`DESCRIPTION_ONLY`**다.

| 단계 | ID · 원본 링크 | 게시자 | 유형 | 구현에서 확인할 핵심 |
|---|---|---|---|---|
| P1 | **P01** [SUPERTREND ATR WITH TRAILING STOP LOSS](https://www.tradingview.com/script/L9GkARD2-SUPERTREND-ATR-WITH-TRAILING-STOP-LOSS/) | `exit490` | ATR 추세 | STOP_TRAILING_INTRABAR |
| P1 | **P02** [Donchian Breakout Strategy](https://www.tradingview.com/script/hyYvFjux-Donchian-Breakout-Strategy/) | `millerrh` | 채널 돌파 | CHANNEL_STOP_MTF_OPTIONAL |
| P1 | **P03** [Bollinger Bands Mean Reversion by Kevin Davey](https://www.tradingview.com/script/umOCSa0t/) | `EdgeTools` | 평균회귀 | ENTRY_EXIT_EXACT_SOURCE_REQUIRED |
| P1 | **P04** [Keltner Channel - Trend Based Strategy](https://www.tradingview.com/script/ezSBm5MS-Keltner-Channel-Trend-Based-Strategy/) | `WunderTrading` | 채널 추세 | PARTIAL_EXITS_AND_STOP |
| P1 | **P05** [Bollinger Bands Mean Reversion using RSI [Krishna Peri]](https://www.tradingview.com/script/XRPeqEdA-Bollinger-Bands-Mean-Reversion-using-RSI-Krishna-Peri/) | `thechadyogi` | 밴드+RSI | EXACT_EXIT_REQUIRED |
| P2 | **P06** [RSI Divergence Strategy v6](https://www.tradingview.com/script/XNiLx725/) | `TagsTrading` | RSI 다이버전스 | PIVOT_LOOKAHEAD_AND_TRAILING |
| P2 | **P07** [SSL Hybrid Strategy](https://www.tradingview.com/script/2it69GUx-SSL-Hybrid-Strategy/) | `kevinmck100` | 추세+분할청산 | PARTIAL_EXITS_BREAKEVEN_MULTIORDER |
| P2 | **P08** [Dual Keltner Channels Strategy [Eastgate3194]](https://www.tradingview.com/script/M6YPrmR2-Dual-Keltner-Channels-Strategy-Eastgate3194/) | `eastgate3194` | 2단계 반전 | SEQUENTIAL_STATE_EXITS_REQUIRED |
| P2 | **P09** [Ichimoku Keltner Strategy](https://www.tradingview.com/script/WSufrZ4b-Ichimoku-Keltner-Strategy/) | `Flexa` | 복합 추세 | CLOUD_SHIFT_REPAINT_RISK |
| P2 | **P10** [Vinicius Setup ATR](https://www.tradingview.com/script/U98FoYXv/) | `sidimarvinicius` | 추세+거래량 | MULTI_SIGNAL_CONFIRMATION |
| P3 | **P11** [Opening-Range Breakout](https://www.tradingview.com/script/8vjWAdLN-Opening-Range-Breakout/) | `fabledforman` | 장중 ORB | INTRADAY_SESSION_AND_ORDER_ENGINE |
| P3 | **P12** [VWAP Strategy](https://www.tradingview.com/script/4HZ8MOod-VWAP-Strategy/) | `Neptuko` | 장중 VWAP | INTRADAY_ANCHOR_AND_CROSS_SYMBOL |
| P3 | **P13** [Machine Learning: SuperTrend Strategy TP/SL [YinYangAlgorithms]](https://www.tradingview.com/script/9Mm3qKME-Machine-Learning-SuperTrend-Strategy-TP-SL-YinYangAlgorithms/) | `YinYangAlgorithms` | KNN 추세 | ML_CALCULATION_NONCAUSAL_GUARD |
| P3 | **P14** [Keltner Channel Based Grid Strategy](https://www.tradingview.com/script/GLBJdTNC-Keltner-Channel-Based-Grid-Strategy/) | `signal2trade` | 그리드 | GRID_INVENTORY_MULTIORDER |
| P3 | **P15** [SSL Hybrid + QQE Strategy](https://www.tradingview.com/script/fl8CV2N0-SSL-Hybrid-QQE-Strategy/) | `kevinmck100` | SSL+QQE | MULTI_ENTRY_PARTIAL_EXITS |

## 우선 이식 후보 5개 — 서로 다른 규칙을 먼저 재현

### P01. SUPERTREND ATR WITH TRAILING STOP LOSS
원본: [TradingView L9GkARD2-SUPERTREND-ATR-WITH-TRAILING-STOP-LOSS](https://www.tradingview.com/script/L9GkARD2-SUPERTREND-ATR-WITH-TRAILING-STOP-LOSS/) · 저자 **exit490** · 확인된 페이지 날짜 **2019-08-05** · Pine 버전 **4**.

- **규칙의 핵심(게시 설명 기준):** 진입 — SuperTrend directional flip, ATR period/multiplier. 청산 — ATR trailing stop and initial SL, direction exit.
- **왜 먼저:** SuperTrend moves stop with ATR; foundational non-voting trend execution.
- **필요한 엔진 기능:** ATR/SuperTrend state, next-open or stop execution. 확인 태그 `STOP_TRAILING_INTRABAR`.

### P02. Donchian Breakout Strategy
원본: [TradingView hyYvFjux-Donchian-Breakout-Strategy](https://www.tradingview.com/script/hyYvFjux-Donchian-Breakout-Strategy/) · 저자 **millerrh** · 확인된 페이지 날짜 **2023-08-23** · Pine 버전 **5**.

- **규칙의 핵심(게시 설명 기준):** 진입 — Price breakout of preceding upper channel with optional MA filter. 청산 — Lower Donchian channel trailing stop.
- **왜 먼저:** Breakout structure beyond existing binary vote.
- **필요한 엔진 기능:** Prior-bar channel boundary, protective stop, optional HTF MA. 확인 태그 `CHANNEL_STOP_MTF_OPTIONAL`.

### P03. Bollinger Bands Mean Reversion by Kevin Davey
원본: [TradingView umOCSa0t](https://www.tradingview.com/script/umOCSa0t/) · 저자 **EdgeTools** · 확인된 페이지 날짜 **2024-10-24** · Pine 버전 **소스 확인 필요**.

- **규칙의 핵심(게시 설명 기준):** 진입 — Bollinger band price deviation and reversal conditions (exact code pending). 청산 — Return toward center band or script-defined exit (unverified).
- **왜 먼저:** Simple mean-reversion contrast for QQQ daily.
- **필요한 엔진 기능:** Rolling stddev, bar signal, exit parity check. 확인 태그 `ENTRY_EXIT_EXACT_SOURCE_REQUIRED`.

### P04. Keltner Channel - Trend Based Strategy
원본: [TradingView ezSBm5MS-Keltner-Channel-Trend-Based-Strategy](https://www.tradingview.com/script/ezSBm5MS-Keltner-Channel-Trend-Based-Strategy/) · 저자 **WunderTrading** · 확인된 페이지 날짜 **2023-09-11** · Pine 버전 **5**.

- **규칙의 핵심(게시 설명 기준):** 진입 — EMA/SMA trend crossover, candle opens inside/above upper Keltner, close breaks upper Keltner, DM threshold. 청산 — Two profit targets and one stop loss.
- **왜 먼저:** Adds multi-indicator channel logic and explicit multi-target exits.
- **필요한 엔진 기능:** KC bands, directional movement, partial TP, intrabar stop. 확인 태그 `PARTIAL_EXITS_AND_STOP`.

### P05. Bollinger Bands Mean Reversion using RSI [Krishna Peri]
원본: [TradingView XRPeqEdA-Bollinger-Bands-Mean-Reversion-using-RSI-Krishna-Peri](https://www.tradingview.com/script/XRPeqEdA-Bollinger-Bands-Mean-Reversion-using-RSI-Krishna-Peri/) · 저자 **thechadyogi** · 확인된 페이지 날짜 **2025-12-06** · Pine 버전 **소스 확인 필요**.

- **규칙의 핵심(게시 설명 기준):** 진입 — RSI oversold and bullish candle within lower Bollinger band for long; inverse for short. 청산 — Description does not fully establish exit implementation.
- **왜 먼저:** Complementary oscillator-filtered reversion structure.
- **필요한 엔진 기능:** RSI, bands, candle pattern, bar confirmation. 확인 태그 `EXACT_EXIT_REQUIRED`.

## 2·3순위 분류 이유

**P2:** RSI 다이버전스는 우측 피벗 확정 지연(미래 정보 오용 가능성), SSL Hybrid는 다중 익절·브레이크이븐, Dual Keltner는 상태를 기억하는 2단계 조건, Ichimoku는 선행스팬의 시각적 이동과 실제 데이터 참조 구분, SuperTrend+거래량은 ATR/캔들 강도/볼륨 결합을 추가 검증해야 한다.

**P3:** ORB와 VWAP은 장중 시세·세션·서머타임/앙커·주문체결 모델이 필요하여 현재 QQQ 1일봉 연구로는 정확히 재현할 수 없다. KNN SuperTrend에는 미래정보·유사도 계산 인과성 검증, Grid와 SSL+QQE에는 포지션 재고·추가진입·분할익절 구현이 필요하다.

## 수집·라이선스 통제

- 15개 게시 페이지 모두 TradingView의 **Open-source script** 문구 확인. 이것은 **실제 소스 코드 수집 완료나 개별 라이선스 확정이 아니다**.
- TradingView 공개 스크립트는 일반적으로 **MPL 2.0 기본값**이지만 저자가 별도 라이선스를 명시할 수 있다. `P01`은 게시 설명에 **MIT**라고 적혀 있어 별도 대상으로 표시했다. **P01의 MIT 라이선스 원본 파일/코드 헤더도 아직 확인되지 않았다**.
- TradingView의 공개 스크립트 재게시 규칙은 저자 표기·실질적 개선·소스 공개 등 별도의 제약을 둔다. **코드를 직접 옮기거나 공개 배포하기 전에** 원본 헤더·파일·작성자·버전·라이선스·수정 제한과 출처 표기를 확인한다.
- 출처 정책: [TradingView Script Publishing Rules](https://www.tradingview.com/support/solutions/43000590599-script-publishing-rules/), [공식 Pine Script 공개·라이선스 안내](https://www.tradingview.com/pine-script-docs/writing/publishing/).
- 원본 페이지/설명의 변경 가능성을 고려하여 `landing_page_verified_date`만 기록하고 `source_snapshot_hash=null`, `source_code_sha256=null`, `revision_hash=null`. 고정되지 않은 소스에 대해 해시를 추정하지 않는다.

## 2단계 인수 조건 (실제 이식 전 게이트)

1. **코드 취득·법적 확인:** 원본 Pine 전문을 합법적으로 수집하고, 저자·라이선스 헤더·Pine `//@version`·수정 기록·내용 SHA-256을 외부 읽기 전용 소스 증거로 고정한다. 실물 코드가 없는 후보는 **INGEST_BLOCKED**.
2. **파서·시간 의미 검사:** `strategy()` vs `indicator()`, `strategy.entry/exit/close/order`, 수량·pyramiding, `request.security`, `lookahead`, `barstate`, `ta.pivothigh/low`, `strategy.position_avg_price`, `calc_on_every_tick`, 스탑/지정가 주문, `timestamp/session`을 실제 코드에서 추출한다.
3. **타입드 적합성:** StrategyIR가 표현하지 못하는 기능은 `UNSUPPORTED`/별도 승인 상태로 기록하며, 조용히 규칙을 생략하거나 일봉으로 치환하지 않는다.
4. **동등성 기준:** TradingView와 Moon의 동일 OHLC/Corporate action 처리/시간대/수수료·슬리피지·진입/청산 이벤트를 교차 재생한다. 신호 시점·체결 수·거래가격·잔고·비용·이익/손실을 단계별로 비교하기 전에는 `PARITY_VERIFIED`로 표기하지 않는다.
5. **연구·성과 판정:** 모든 15개는 현재 `BACKTEST_NOT_RUN`·`NO_OOS`·`NO_CAUSAL_CLAIM`이다. 이식 직후 QQQ 과거 최고 수익만 근거로 채택하지 않는다. 독립 기간/다자산 PIT 및 350세대 검색 편향을 분리한다.

## 수락 판정 / 다음 작업

**1단계 조사 완료 조건:** `15/15 UNIQUE URL`, `15/15 게시 페이지상 공개`, `15/15 전략`, `P1/P2/P3 = 5/5/5`, `source captured = 0`, `code hashes verified = 0`, `executions/backtests = 0`. 머신 판독 카탈로그의 스키마·상호배타 우선순위·URL/저자/구조/보안 플래그를 검사한다.

**2단계 준비:** P1부터 원본 코드 확보 → 라이선스와 코드 해시 확인 → 기능 간극 실제 분석 → **단일 원본씩** 변환/체결 동등성 검증. 현재 과제가 완료된 후에도 원래 T4/V01~V04/V06/V07 과제 순서를 뒤집지 않는다.
