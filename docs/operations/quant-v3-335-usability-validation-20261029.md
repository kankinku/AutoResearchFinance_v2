# Quant V3 Track1 — 335개 연구 지표 전수 실행·연결·중복 평가와 이식 수정

**기준 시점:** 2026-10-29 KST (2026-10-28 원본 코드 작업 세션). **범위:** T1-02/S6/S9 · Q05/Q10/Q11/Q12/Q18, 브랜치 `research/v3-strategy-evolution`만 수정. 기존 173개 + 신규 162개(1~4차) = 335개 등록 상태 유지. User approved source-indicator evaluation/port. 본 평가에서 새 지표 개수를 추가로 부풀리지 않고 기존 코드의 실행 오류와 수식 불일치를 수정함.

## 전수 실행 — 원장으로 재현 가능한 335/335

실행 명령: `python -m scripts.v3_audit_335_features`. 테스트는 실제 주문/계좌/OOS/외부 시장데이터가 전혀 없는 **420개 결정론적 OHLCV 개발용 합성 바**에서 수행했다. 각 FeatureSpec은 실제 `calculate_feature`로 전 길이 결과가 생성되는지 검사한 다음, **마지막 바를 잘라 다시 계산했을 때 원래 값의 동일 prefix**인지를 비교하고, `_new_feature_vector(FeatureRef(...))`를 통해 **StrategyIR 상속 전략 재생 입력과 수치가 정확하게 일치**하는지 비교했다. `None`을 제외한 값은 모두 유한한 숫자여야 하고, 기본값 계산에 적어도 한 개의 관측값이 있어야 통과했다.

| 상태 | 건수 | 판정 |
|---|---:|---|
| 등록된 전체 FeatureSpec | **335** | 연구 카탈로그의 명목 등록 수 |
| **OHLCV 기본값 계산 + 원본 prefix 동일 + inherited StrategyIR 연결** | **309** | 합성 개발 입력/기본 lookback 한정 실제 재생 가능 |
| **외부 PIT 데이터가 먼저 필요한 항목** | **14** | VIX, DXY, GOLD, QQQ/NASDAQ 벤치마크, 한·미·일 국채 금리. **현재 same-symbol OHLCV-only 입력으로 실행 불가** |
| **특화 입력 어댑터가 필요한 항목** | **12** | session 7개 + profile 2개 + order flow 3개. 일봉 scalar IR에 직접 이식하지 않음 |
| 정상 OHLCV에서 계산 실패/전부 None | **0** | 최초 12건에서 수정 후 0건 |

정확한 상태/입력/룩백/출처·라이선스/결과 길이/비결측 결과 수/StrategyIR 연결/실패 원인을 포함한 **335행 JSON**: `docs/operations/quant-v3-335-feature-usability-audit-20261029.json`.

## 실제 원인과 코드 수정

1. **12개 기존 실행불능 지표 복구:** 기존 `_ema`와 `_wilder`는 맨 앞 관측값이 `None`이면 리턴 전체가 `None`이 되는 초기화 버그가 있었음. chained EMA/RSI의 정상적인 warmup 구간을 처리하지 못하던 문제였다. 첫 완전한 유효 관측 윈도우에서 SMA seed를 만들고, 후속 결측 뒤에는 새로운 완전한 윈도우가 생기기 전까지 재시드하지 않도록 수정. DEMA, TEMA, MACD signal/histogram, RSI(EMA/Wilder), TRIX, TSI, RSX, Mass Index, Klinger, ZLEMA가 다시 계산됨. **의미 없는 첫 값 대입으로 시그널을 조기 생성하지 않음**.
2. **지표 정의 불일치 3종 수정:** `zero_lag_ema`는 종전 `2*EMA2−EMA1` 잘못된 식을 원래 ZLEMA의 `EMA(2·close[t]−close[t−lag])`로 변경. `vidya`가 RSI를 내던 구현을 CMO 절대값으로 smoothing weight가 달라지는 VIDYA로 교체. `connors_rsi`가 단순 3기간 RSI를 내던 구현을 **가격 RSI(3), 상승/하락 streak RSI(2), 지정 룩백 수익률 percentile rank**의 평균으로 교체. 검증은 synthetic exact/flat/prefix과 수식 정체성 테스트 수준이며 외부 TA-Lib binary parity 전체를 주장하지 않음.
3. **11개 캔들 패턴 결측 예외 복구:** `_price_action`가 전일·전전일 바를 읽을 때 결측을 검사하지 않아 `FeatureCalculationError`를 던지던 문제를 수정. 각 패턴이 실제로 참조하는 과거 바의 데이터가 모두 있을 때만 값을 내고, 결측 시 `None`으로 처리. 사후에 결측을 보간하거나 과거 값을 덮어쓰지 않음.
4. **GPT/MCP 서비스의 사용 가능성 분리:** `FeatureCatalogService.research_features()` 기존 **6키 계약을 보존**한 채 `capability_summary()`에서 총 335개와 *현재 same-symbol OHLCV 입력 적합 후보 309*, 외부 PIT 대기 14, 전용 어댑터 대기 12를 명시. 309는 *조건부 후보*로서 실제 독립적 연구 provider에 노출된 검증된 수익전략 309개를 뜻하지 않음. 오래된 `173개` 고정 테스트와 최초 RSI.Wilder 실패 기대치를 현실에 맞게 업데이트.

## 스트레스 테스트 및 중복 발견

`scripts/v3_audit_335_edge_cases.py`로 **309개**에 대해 flat-price(고저=종가), zero-volume, 두 바 연속 결측 각각을 적용. 수정 후 **각 시나리오 계산 예외/비유한 결과 0건** (결측에서 값 없는 구간은 허용). 결과: `docs/operations/quant-v3-335-edge-duplicate-evaluation-20261029.json`.

- 합성 가격 경로·기본 매개변수에서 **정확히 같은 비상수 벡터를 내는 그룹 22개**가 존재. 대표: EMA/FAMA/Guppy MMA/Hilbert trendline/ITrend 등, RSI/DC-based RSI/DTI/Laguerre RSI, SMA/Bollinger, CMF/VFI, ROC/returns. 이 기록은 수학적 동치가 입증되었다는 뜻은 아니며, 해당 원본 수식과 다른 입력 경로·파라미터로 재검증 전까지 독립적인 335종의 알파 기회로 계산하면 안 됨.
- 합성 가격에서 **상수 시그널 49개**: 대부분 희귀 캔들 패턴이 평탄한 합성 캔들에 나타나지 않아 전부 0이 된 경우. 다른 가격 국면/실제 시장에선 반응할 수 있으므로 무조건 실패·중복으로 제거하지 않음.
- `keltner`·`bollinger` 등 일부는 기본 출력이 중심선이라 EMA/SMA와 일치하며, 원본 밴드의 모든 출력이 별도 Feature로 이식됐는지는 미검증. 원본 공식과 output-index parity 추가 평가 필요.

## 검증 결과

- Core 및 관련 Research·governance 회귀 **450 passed**, GPT/MCP service·research-context·scope governance 회귀 **17 passed**(별도 실행).
- 신규 EMA·Wilder/ZLEMA 회귀 **16 passed**, VIDYA/Connors 수식 정체성 **3 passed**, Native candle 결측 **11 passed** 및 335개 전체 실행·재생 regression **1 passed**. 상기 test count는 일부 코어·전체 suite에 중복 포함됨; 합산 금지.
- Ruff 전체 `ruff check .` **PASS**, 변경된 주요 네 Python 파일 scoped `mypy --follow-imports=silent` **PASS**.
- 전체 `python -m pytest -q`는 기존 런타임 상태파일 누락으로 수집이 중단된 이력이 있고 이 차수에는 **미실행**. Moon `task_validate` release profile의 `uv` 바이너리 부재로 formal validation **FAIL/BLOCKED** (별도 수동 테스트 PASS를 formal release 통과로 과장하지 않음).
- 원본 4개 라이선스/소스 SHA, C/C# 전체 formula numeric parity, 소스 MIT 패키지의 운영 Python 3.10/NumPy1.24 지원, 정확한 PIT 데이터 원천 및 2026 이후 sealed OOS, 유효 순수익·거래비용 비교 등은 **이 차수에서 검증하지 않음**.
- 기존 68개 backlog 중 지난 회차에 남은 **58개 미확정** 작업은 이번 전수 평가와 별개이며 **새로 이식 완료되었다고 주장하지 않음**.

## 다음 순서(기존 승인된 연구 순서 고수)

서로 다른 335개 name을 모두 바로 GPT 생성 가능한 기회 335개로 광고하지 말 것. 현재 실제 단일 종목 OHLCV 연구 재생 가능 **309개**, 나머지 26개는 데이터/어댑터를 갖추기 전까지 사용보류. 유효 후보 309개 중 22개 동일 벡터 그룹은 **원본 수식·신호 출력 parity**로 정밀 중복 배제하거나 각 source의 독립 수식으로 수정해야 한다. 이후 T4 자동 세대 연구 및 독립 평가에서 비용·실현손익 개선을 검증. G1–150 원장·계보·hash, Frozen main, 브로커 주문 OFF, OAuth/고정 URL, OOS·PIT 보호 영역은 **전혀 수정하지 않음**.
