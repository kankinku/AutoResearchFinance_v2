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
| 02 | Shaakuni Liquidity Levels & Order Blocks v1.4 / indicator v6 | MPL-2.0 | **PARTIAL**: completed prior day/week H/L/EQ만 기존 `core/features/pine_liquidity_levels.py`. OB/세션/스윕 및 Registry 연결 미구현 |
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

**다음 후보 02 Shaakuni**를 원본 MPL-2.0/지표로 지정: 이미 완료된 일·주 고저/EQ 계산을 재사용해 ATR 기반 확정 OB·활성/만료·현재 봉의 실시간 패널 상태·최종 경보를 이벤트로 구현하고 (차트 도형은 의미를 가진 draw-spec으로 분리), 바 단위 prefix/delay 및 Pine 시각/거래 parity부터 완료할 것.

병행 과제로 현재 06 BOSWaves는 본문 numeric 포트→Pine 출력 비교 시점·ALMA seed/ATR warmup/parity 검증→합격한 feature만 Registry(운영과 분리된 opt-in) 연결→F1~F4 지표 장단점 연구/S7 비교→명시적 운영 승인. **FULL_PORT_PARITY_VERIFIED는 지금까지 0/11**.

다음 단계 선택에서도 사용자의 본래 목표인 GPT의 *부모 약점 → 필요한 지표 특성 분석 → 기존/새 알고리즘 진화*를 위해 지표 모듈로 이식하며, 원본 전략을 그대로 최고 전략으로 등재하지 않는다.
